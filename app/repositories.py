"""Persistence. Owns SQL; every write is one CALL to the save procedure (sql/004). No business rules."""
import json
import logging
import time

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


# ── the one write path ──────────────────────────────────────────────────────

_SAVE_METRIC = f"CALL {SCHEMA}.save_metric(?)"


def save_metric(op_id: str, actor: str, candidate: dict, calcs: list[dict],
                change_note: str | None = None, check_name: str | None = None) -> dict:
    """Saves a candidate and the PIs a draft touched in one CALL, all or nothing (DEC-020, DEC-021).
    candidate: {id, expected_revision, create_token, fields}; calcs: [{calc_id, expected_revision,
    retire, is_default, fields}]. Returns the procedure's result (outcome committed | no_change |
    conflict | replayed; see sql/004). Reuse op_id when retrying the same draft: a save that
    landed is then reported as replayed instead of conflicting with itself.
    A transaction can't outlive the CALL, but a failed or interrupted CALL may or may not have
    committed, so the connection is proven clean before reuse (DEC-008)."""
    started, outcome = time.monotonic(), "uncertain"
    tag = json.dumps({"op_id": op_id, "op": "metric.save", "actor": actor,
                      "record_id": candidate.get("id")}, sort_keys=True)
    with locked_session() as s:
        lock_wait_ms = _ms(started)
        request = {"op_id": op_id, "actor": actor, "lock_wait_ms": lock_wait_ms,
                   "schema_version": SNAPSHOT_VERSION, "change_note": change_note,
                   "check_name": check_name,
                   "candidate": {**candidate, "fields": _nulls(candidate["fields"])},
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
                     op_id, actor, candidate.get("id"), outcome, lock_wait_ms, _ms(started))


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

