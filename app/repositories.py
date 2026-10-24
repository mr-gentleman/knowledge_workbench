"""Persistence. Owns SQL; every content write is one CALL to the save procedure (sql/004); a SQL
check's result is stamped in place (record_check). No business rules."""
import json
import logging
import time

from snowflake.connector.errors import ProgrammingError

from app import db
from app.db import SCHEMA, locked_session, mark_dirty, query

log = logging.getLogger(__name__)

# 1 = OBJECT_CONSTRUCT(*): NULL fields were omitted, so read a missing key as NULL.
# 2 = OBJECT_CONSTRUCT_KEEP_NULL(*): every column present (HIST-06).
SNAPSHOT_VERSION = 2
LIST_LIMIT = 200  # sidebar cap (PLAT-05); search narrows beyond it


def _ms(since: float) -> int:
    return int((time.monotonic() - since) * 1000)


# ── metrics ─────────────────────────────────────────────────────────────────

def list_metrics(search: str = ""):
    """Most recently updated first. The page filters this list as you type; search here
    only once the list is capped."""
    return query(
        f"""SELECT metric_id, full_name, description, disambig, category, status,
                   original_author, updated_by, updated_at
            FROM {SCHEMA}.metric
            WHERE ? = '' OR (full_name || ' ' || COALESCE(description, '') || ' ' || COALESCE(disambig, '')) ILIKE '%' || ? || '%'
            ORDER BY updated_at DESC
            LIMIT {LIST_LIMIT}""",
        [search, search],
    )


def get_metric(metric_id: int):
    rows = query(f"SELECT * FROM {SCHEMA}.metric WHERE metric_id = ?", [metric_id])
    return rows[0].as_dict() if rows else None


def metric_for_token(token: str):
    rows = query(f"SELECT metric_id FROM {SCHEMA}.metric WHERE create_token = ?", [token])
    return rows[0][0] if rows else None


# ── physical implementations (metric_calc) ──────────────────────────────────

def list_calcs(metric_id: int) -> list[dict]:
    rows = query(
        f"""SELECT * FROM {SCHEMA}.metric_calc
            WHERE metric_id = ? AND status = 'active'
            ORDER BY calc_id""",
        [metric_id],
    )
    return [r.as_dict() for r in rows]


def get_calc(calc_id: int):
    rows = query(f"SELECT * FROM {SCHEMA}.metric_calc WHERE calc_id = ?", [calc_id])
    return rows[0].as_dict() if rows else None


def reserve_calc_id() -> int:
    """Taken before the first save, so the id doubles as that create's retry key
    (metric_calc has no create_token). Abandoned ids leave gaps, which are fine."""
    return query(f"SELECT {SCHEMA}.seq_calc_id.NEXTVAL")[0][0]


# ── SQL checks (sql/007, DEC-022) ───────────────────────────────────────────

CHECK_MAX_ROWS = 100
CHECK_TIMEOUT_S = 30
_TIMEOUT_ERRNOS = {604, 630}  # statement canceled / reached its timeout


def run_check(sql_text: str) -> dict:
    """Runs SME SQL through the read-only run_check procedure on its own connection.
    → {ok, ms, columns, rows, error, query_id}; ok False = the SQL failed or timed out.
    Raises when the check itself couldn't run (no connection, procedure missing)."""
    started = time.monotonic()
    with db.check_connection(CHECK_TIMEOUT_S) as conn:
        cur = conn.cursor()
        try:
            cur.execute(f"CALL {SCHEMA}.run_check(?, ?)", [sql_text, CHECK_MAX_ROWS])
        except ProgrammingError as exc:
            if exc.errno not in _TIMEOUT_ERRNOS:
                raise
            return {"ok": False, "ms": _ms(started), "columns": [], "rows": [], "query_id": exc.sfqid,
                    "error": f"Stopped after {CHECK_TIMEOUT_S} s."}
        columns, rows = [d[0] for d in cur.description], cur.fetchall()
    failed = columns[:1] == ["KW_CHECK"] and rows and rows[0][0] == "KW_CHECK_FAILED"
    return {"ok": not failed, "ms": _ms(started), "columns": [] if failed else columns,
            "rows": [] if failed else rows, "query_id": cur.sfqid, "error": rows[0][2] if failed else None}


def record_check(calc_id: int, revision_no: int, passed: bool, message: str | None, query_id: str | None) -> bool:
    """Stamps a check result on the revision it ran against; not a content revision (sql/001).
    False when the PI has moved on meanwhile: a late result never marks a newer revision (CHECK-01)."""
    rows = query(
        f"""UPDATE {SCHEMA}.metric_calc
            SET validated_revision_no = revision_no, validation_status = ?, validation_message = ?,
                validation_query_id = ?, validated_at = CURRENT_TIMESTAMP()
            WHERE calc_id = ? AND revision_no = ? AND status = 'active'""",
        ["passed" if passed else "failed", message, query_id, calc_id, revision_no],
    )
    return rows[0][0] == 1


# ── the one write path ──────────────────────────────────────────────────────

_SAVE_METRIC = f"CALL {SCHEMA}.save_metric(?)"


def save_metric(op_id: str, actor: str, metric: dict, calcs: list[dict],
                change_note: str | None = None, check_name: str | None = None) -> dict:
    """Saves a metric and the PIs a draft touched in one CALL, all or nothing (DEC-020, DEC-021).
    metric: {id, expected_revision, create_token, fields}; calcs: [{calc_id, expected_revision,
    retire, is_default, fields}]. Returns the procedure's result (outcome committed | no_change |
    conflict | replayed; see sql/009). Reuse op_id when retrying the same draft: a save that
    landed is then reported as replayed instead of conflicting with itself.
    A transaction can't outlive the CALL, but a failed or interrupted CALL may or may not have
    committed, so the connection is proven clean before reuse (DEC-008)."""
    started, outcome = time.monotonic(), "uncertain"
    tag = json.dumps({"op_id": op_id, "op": "metric.save", "actor": actor,
                      "record_id": metric.get("id")}, sort_keys=True)
    with locked_session() as s:
        lock_wait_ms = _ms(started)
        request = {"op_id": op_id, "actor": actor, "lock_wait_ms": lock_wait_ms,
                   "schema_version": SNAPSHOT_VERSION, "change_note": change_note,
                   "check_name": check_name,
                   "metric": {**metric, "fields": _nulls(metric["fields"])},
                   "calcs": [{**c, "fields": _nulls(c["fields"])} for c in calcs]}
        try:
            rows = s.sql(_SAVE_METRIC, params=[json.dumps(request)]).collect(
                statement_params={"QUERY_TAG": tag})
            result = json.loads(rows[0][0])
            outcome = result["outcome"]
            return result
        except BaseException:
            mark_dirty()
            raise
        finally:
            log.info("op %s metric.save %s record=%s %s wait=%sms total=%sms",
                     op_id, actor, metric.get("id"), outcome, lock_wait_ms, _ms(started))


def _nulls(fields: dict) -> dict:
    # The procedure detects changes with EQUAL_NULL against NULLIF(column, ''): "" must be NULL.
    return {k: v if v != "" else None for k, v in fields.items()}


def snapshot_at(record_type: str, record_id, revision_no: int) -> dict | None:
    """The record as it was at a revision (UPPER-case keys) — what a draft started from."""
    rows = query(
        f"""SELECT snapshot FROM {SCHEMA}.revision
            WHERE record_type = ? AND record_id = ? AND revision_no = ?""",
        [record_type, str(record_id), revision_no],
    )
    return json.loads(rows[0][0]) if rows else None


def history(record_type: str, record_id: int):
    return query(
        f"""SELECT revision_no, action, actor, acted_at, change_note, snapshot, schema_version
            FROM {SCHEMA}.revision
            WHERE record_type = ? AND record_id = ?
            ORDER BY revision_no DESC""",
        [record_type, str(record_id)],
    )

