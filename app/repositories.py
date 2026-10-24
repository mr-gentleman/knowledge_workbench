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


# ── candidates ──────────────────────────────────────────────────────────────

def list_candidates(search: str = ""):
    """Most recently updated first. The page filters this list as you type; search here
    only once the list is capped."""
    return query(
        f"""SELECT candidate_id, full_name, description, disambig, category, status,
                   promoted_metric_id, original_author, updated_by, updated_at
            FROM {SCHEMA}.metric_candidate
            WHERE ? = '' OR (full_name || ' ' || COALESCE(description, '') || ' ' || COALESCE(disambig, '')) ILIKE '%' || ? || '%'
            ORDER BY updated_at DESC
            LIMIT {LIST_LIMIT}""",
        [search, search],
    )


def get_candidate(candidate_id: int):
    rows = query(f"SELECT * FROM {SCHEMA}.metric_candidate WHERE candidate_id = ?", [candidate_id])
    return rows[0].as_dict() if rows else None


def candidate_for_token(token: str):
    rows = query(f"SELECT candidate_id FROM {SCHEMA}.metric_candidate WHERE create_token = ?", [token])
    return rows[0][0] if rows else None


# ── physical implementations (metric_calc) ──────────────────────────────────

def list_calcs_for_candidate(candidate_id: int) -> list[dict]:
    rows = query(
        f"""SELECT * FROM {SCHEMA}.metric_calc
            WHERE origin_candidate_id = ? AND status = 'active'
            ORDER BY calc_id""",
        [candidate_id],
    )
    return [r.as_dict() for r in rows]


def get_calc(calc_id: int):
    rows = query(f"SELECT * FROM {SCHEMA}.metric_calc WHERE calc_id = ?", [calc_id])
    return rows[0].as_dict() if rows else None


def reserve_calc_id() -> int:
    """Taken before the first save, so the id doubles as that create's retry key
    (metric_calc has no create_token). Abandoned ids leave gaps, which are fine."""
    return query(f"SELECT {SCHEMA}.seq_calc_id.NEXTVAL")[0][0]


# ── fact tables (fact_table_core) ───────────────────────────────────────────

FACT_TABLE_LIMIT = 500  # the whole registry (61 legacy tables); revisit if it outgrows this


def list_fact_tables():
    """Every fact table, active first, by name. table_name is the 3-part AC.SCHEMA.TABLE key."""
    return query(
        f"""SELECT table_name_full AS table_name, display_name, description, disambig, gotchas,
                   required_filter, grain, primary_key, time_dimension, department, source, status,
                   original_author, revision_no, updated_by, updated_at
            FROM {SCHEMA}.fact_table_core
            ORDER BY status = 'active' DESC, table_name_full
            LIMIT {FACT_TABLE_LIMIT}"""
    )


def get_fact_table(table_name: str):
    rows = query(f"SELECT * FROM {SCHEMA}.fact_table_core WHERE table_name_full = ?", [table_name])
    return rows[0].as_dict() if rows else None


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

def save_metric(op_id: str, actor: str, candidate: dict, calcs: list[dict],
                change_note: str | None = None, check_name: str | None = None) -> dict:
    """Saves a candidate and the PIs a draft touched in one CALL, all or nothing (DEC-020, DEC-021).
    candidate: {id, expected_revision, create_token, fields}; calcs: [{calc_id, expected_revision,
    retire, is_default, fields}]. Returns the procedure's result (outcome committed | no_change |
    conflict | replayed; see sql/004). Reuse op_id when retrying the same draft: a save that
    landed is then reported as replayed instead of conflicting with itself."""
    return _call_save("save_metric", "metric.save", op_id, actor, candidate.get("id"),
                      {"change_note": change_note, "check_name": check_name,
                       "candidate": {**candidate, "fields": _nulls(candidate["fields"])},
                       "calcs": [{**c, "fields": _nulls(c["fields"])} for c in calcs]})


def save_fact_table(op_id: str, actor: str, table: dict, change_note: str | None = None) -> dict:
    """Creates or edits one fact table in one CALL (sql/005). table: {table_name, expected_revision
    (None = create), fields}. Outcome committed | no_change | conflict | exists | replayed."""
    return _call_save("save_fact_table", "fact_table.save", op_id, actor, table["table_name"],
                      {"change_note": change_note, "table": {**table, "fields": _nulls(table["fields"])}})


def _call_save(proc: str, op: str, op_id: str, actor: str, record_id, request: dict) -> dict:
    """A transaction can't outlive the CALL, but a failed or interrupted CALL may or may not have
    committed, so the connection is proven clean before reuse (DEC-008)."""
    started, outcome = time.monotonic(), "uncertain"
    tag = json.dumps({"op_id": op_id, "op": op, "actor": actor, "record_id": record_id}, sort_keys=True)
    with locked_session() as s:
        lock_wait_ms = _ms(started)
        request = {"op_id": op_id, "actor": actor, "lock_wait_ms": lock_wait_ms,
                   "schema_version": SNAPSHOT_VERSION, **request}
        try:
            rows = s.sql(f"CALL {SCHEMA}.{proc}(?)", params=[json.dumps(request)]).collect(
                statement_params={"QUERY_TAG": tag})
            result = json.loads(rows[0][0])
            outcome = result["outcome"]
            return result
        except BaseException:
            mark_dirty()
            raise
        finally:
            log.info("op %s %s %s record=%s %s wait=%sms total=%sms",
                     op_id, op, actor, record_id, outcome, lock_wait_ms, _ms(started))


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

