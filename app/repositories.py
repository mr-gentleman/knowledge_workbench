"""Persistence. Owns SQL and transaction boundaries; no business rules."""
import logging
import time
import uuid

from app.db import SCHEMA, is_dirty, locked_session, mark_dirty, query, set_tag

log = logging.getLogger(__name__)

# 1 = OBJECT_CONSTRUCT(*): NULL fields were omitted, so read a missing key as NULL.
# 2 = OBJECT_CONSTRUCT_KEEP_NULL(*): every column present (HIST-06).
SNAPSHOT_VERSION = 2
LIST_LIMIT = 200  # sidebar cap (PLAT-05); search narrows beyond it


class StaleEdit(Exception):
    """Someone saved a newer revision since this form was loaded."""


def _snapshot(record_type: str, table: str, key: str, record_id: int,
              action: str, actor: str, note: str | None, execute):
    # Snapshot = the committed row itself, so history can't drift from current state.
    execute(
        f"""INSERT INTO {SCHEMA}.revision
              (record_type, record_id, revision_no, action, snapshot, schema_version, actor, change_note)
            SELECT ?, {key}::VARCHAR, revision_no, ?, OBJECT_CONSTRUCT_KEEP_NULL(*), ?, ?, ?
            FROM {SCHEMA}.{table} WHERE {key} = ?""",
        [record_type, action, SNAPSHOT_VERSION, actor, note, record_id],
    )


def _ms(since: float) -> int:
    return int((time.monotonic() - since) * 1000)


def _in_txn(fn, op: str, actor: str, record_id=None):
    """The only place a transaction starts (DEC-004, DEC-007). fn(execute, meta) runs inside it;
    it may set meta["record_id"] / meta["replayed"]. Each attempt is logged after the transaction
    ends, so a rollback can't erase the record: certain outcomes to op_log, uncertain ones
    (UNCERTAIN) to the app log only, since the connection is then quarantined."""
    op_id, started = uuid.uuid4().hex, time.monotonic()
    meta = {"record_id": record_id, "replayed": False}
    outcome, error = "interrupted", None
    with locked_session() as s:
        lock_wait_ms = _ms(started)
        set_tag(s, {"op_id": op_id, "op": op, "actor": actor, "record_id": record_id})

        def execute(sql, params=None):
            return s.sql(sql, params=params or []).collect()

        committing = False
        try:
            s.sql("BEGIN").collect()
            out = fn(execute, meta)
            committing = True
            s.sql("COMMIT").collect()
            outcome = "replayed" if meta["replayed"] else "committed"
            return out
        except BaseException as exc:
            error = repr(exc)[:2000]
            if committing:
                outcome = "commit_uncertain"  # the COMMIT may have landed without its acknowledgement
            elif isinstance(exc, StaleEdit):
                outcome = "conflict"
            elif isinstance(exc, Exception):
                outcome = "rolled_back"
            try:
                s.sql("ROLLBACK").collect()
            except BaseException as rb:  # noqa: BLE001 — any failure here leaves the outcome unknown
                outcome = "rollback_failed"
                exc.add_note(f"ROLLBACK also failed: {rb!r}")
            raise
        finally:
            _finish(s, op_id, op, actor, meta["record_id"], outcome, lock_wait_ms, _ms(started), error)


UNCERTAIN = ("interrupted", "commit_uncertain", "rollback_failed")


def _finish(s, op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, error):
    """Quarantine first, then optional bookkeeping that can neither bypass the quarantine
    nor replace the operation's own exception."""
    if outcome in UNCERTAIN:
        mark_dirty()  # ROLLBACK may have run, but prove the connection clean before reuse
    try:
        _log_op(s, op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, error)
        if not is_dirty():  # ALTER SESSION could implicitly commit an abandoned transaction
            set_tag(s, None)
    except BaseException as exc:  # bookkeeping must not mask the real outcome
        if error is None:
            raise  # the operation succeeded; let e.g. a stop request through
        log.warning("Bookkeeping for %s failed: %r", op_id, exc)


def _log_op(s, op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, error):
    # Never affects the operation's outcome. Uncertain outcomes reach the app log only: on a
    # dirty connection the INSERT could join an abandoned transaction.
    log.info("op %s %s %s record=%s %s wait=%sms total=%sms",
                 op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms)
    if is_dirty():
        return
    try:
        s.sql(
            f"""INSERT INTO {SCHEMA}.op_log
                  (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id, error)
                SELECT ?, ?, ?, ?, ?, ?, ?, LAST_QUERY_ID(), ?""",
            params=[op_id, op, actor, None if record_id is None else str(record_id),
                    outcome, lock_wait_ms, duration_ms, error],
        ).collect()
    except Exception:
        log.exception("op_log write failed for %s", op_id)


# ── candidates ──────────────────────────────────────────────────────────────

def list_candidates(search: str = ""):
    return query(
        f"""SELECT candidate_id, full_name, category, status,
                   promoted_metric_id, original_author, updated_by, updated_at
            FROM {SCHEMA}.metric_candidate
            WHERE ? = '' OR full_name ILIKE '%' || ? || '%'
            ORDER BY updated_at DESC
            LIMIT {LIST_LIMIT}""",
        [search, search],
    )


def get_candidate(candidate_id: int):
    rows = query(f"SELECT * FROM {SCHEMA}.metric_candidate WHERE candidate_id = ?", [candidate_id])
    return rows[0].as_dict() if rows else None


def find_by_exact_name(normalized_name: str):
    """Collisions across candidates and canon. Normalization rule lives in services."""
    return query(
        f"""SELECT 'candidate' AS kind, candidate_id AS id, full_name
            FROM {SCHEMA}.metric_candidate
            WHERE LOWER(TRIM(full_name)) = ? AND status = 'open'
            UNION ALL
            SELECT 'metric', metric_id, full_name
            FROM {SCHEMA}.metric_core
            WHERE LOWER(TRIM(full_name)) = ? AND status = 'active'""",
        [normalized_name, normalized_name],
    )


def candidate_for_token(token: str):
    rows = query(f"SELECT candidate_id FROM {SCHEMA}.metric_candidate WHERE create_token = ?", [token])
    return rows[0][0] if rows else None


def insert_candidate(fields: dict, actor: str, token: str, source: str = "sme") -> int:
    """Idempotent per token: a retry of the same create returns the first id (REL-10)."""
    def run(execute, meta):
        prior = execute(f"SELECT candidate_id FROM {SCHEMA}.metric_candidate WHERE create_token = ?", [token])
        if prior:
            meta["record_id"], meta["replayed"] = prior[0][0], True
            return prior[0][0]
        cid = execute(f"SELECT {SCHEMA}.seq_candidate_id.NEXTVAL")[0][0]
        meta["record_id"] = cid
        execute(
            f"""INSERT INTO {SCHEMA}.metric_candidate
                  (candidate_id, full_name, description, disambig, department, category,
                   source, original_author, created_by, updated_by, create_token)
                SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?""",
            [cid, fields["full_name"], fields.get("description"),
             fields.get("disambig"), fields.get("department"), fields.get("category"),
             source, fields.get("original_author") or actor, actor, actor, token],
        )
        _snapshot("metric_candidate", "metric_candidate", "candidate_id", cid, "create", actor, None, execute)
        return cid

    return _in_txn(run, "candidate.create", actor)


def update_candidate(candidate_id: int, expected_revision: int, fields: dict,
                     actor: str, note: str | None = None) -> int:
    def run(execute, meta):
        res = execute(
            f"""UPDATE {SCHEMA}.metric_candidate
                SET full_name = ?, description = ?, disambig = ?, department = ?, category = ?,
                    revision_no = revision_no + 1,
                    updated_by = ?, updated_at = CURRENT_TIMESTAMP()
                WHERE candidate_id = ? AND revision_no = ?""",
            [fields["full_name"], fields.get("description"),
             fields.get("disambig"), fields.get("department"), fields.get("category"),
             actor, candidate_id, expected_revision],
        )
        if res[0][0] == 0:
            raise StaleEdit(candidate_id)
        _snapshot("metric_candidate", "metric_candidate", "candidate_id", candidate_id, "edit", actor, note, execute)
        return expected_revision + 1

    return _in_txn(run, "candidate.edit", actor, candidate_id)


def history(record_type: str, record_id: int):
    return query(
        f"""SELECT revision_no, action, actor, acted_at, change_note, snapshot, schema_version
            FROM {SCHEMA}.revision
            WHERE record_type = ? AND record_id = ?
            ORDER BY revision_no DESC""",
        [record_type, str(record_id)],
    )

