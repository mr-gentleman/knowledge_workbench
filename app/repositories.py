"""Persistence. Owns SQL and the save transaction (DEC-025); a SQL check's result is stamped in place
(record_check). No business rules."""
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
        f"""SELECT metric_id, full_name, description, disambig, department, category, status,
                   revision_no, source, original_author, updated_by, updated_at
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

_T = {n: f"{SCHEMA}.{n}" for n in ("metric", "metric_calc", "revision", "op_log")}
_OP_LOG = (f"INSERT INTO {_T['op_log']} (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, "
           "last_query_id) SELECT ?, 'metric.save', ?, ?, ?, ?, ?, LAST_QUERY_ID()")
# Request PIs as rows (one JSON parameter, so any number of PIs costs the same statements).
_REQ_CALCS = """(SELECT value:calc_id::NUMBER AS id, value:expected_revision::NUMBER AS exp_rev,
                        COALESCE(value:retire::BOOLEAN, FALSE) AS retire, COALESCE(value:is_default::BOOLEAN, FALSE) AS is_default,
                        value:fields:sql_text::VARCHAR AS sql_text, value:fields:source_table::VARCHAR AS source_table,
                        value:fields:disambig::VARCHAR AS disambig
                 FROM TABLE(FLATTEN(input => PARSE_JSON(?))))"""


class _LostRace(Exception):
    """A concurrent save changed a record between the revision check and the write."""


def save_metric(op_id: str, actor: str, metric: dict, calcs: list[dict],
                change_note: str | None = None, check_name: str | None = None) -> dict:
    """Saves a metric and the PIs a draft touched in one transaction, all or nothing (DEC-020, DEC-025).
    metric: {id (None = create), expected_revision, create_token, source, original_author, fields};
    calcs: [{calc_id, expected_revision (None = new), retire, is_default, fields}].
    Returns {outcome: committed | no_change | conflict | replayed, metric_id, metric_revision,
    changed_calcs, new_calcs, checks_due, collisions: [{KIND (candidate | canon), ID, FULL_NAME}]
    (None = the lookup failed)}. Same contract and rules as sql/009's procedure, which it replaces.
    Reuse op_id when retrying the same draft: a save that landed is then 'replayed'.
    The transaction lives only inside this call. Any failure marks the connection dirty, so DEC-008's
    heal rolls back and proves it clean before the next operation (a commit may or may not have landed)."""
    started, outcome = time.monotonic(), "uncertain"
    tag = json.dumps({"op_id": op_id, "op": "metric.save", "actor": actor,
                      "record_id": metric.get("id")}, sort_keys=True)
    with locked_session() as s:
        lock_wait_ms = _ms(started)

        def run(sql, params=()):
            return s.sql(sql, params=list(params)).collect(statement_params={"QUERY_TAG": tag})

        def log_op(result, record_id):  # outside a transaction: autocommits on its own
            run(_OP_LOG, [op_id, actor, None if record_id is None else str(record_id), result,
                          lock_wait_ms, _ms(started)])

        try:
            res = _save(run, log_op, op_id, actor, metric, calcs, change_note, check_name,
                        lambda: (lock_wait_ms, _ms(started)))
            outcome = res["outcome"]
            return res
        except BaseException:
            mark_dirty()
            raise
        finally:
            log.info("op %s metric.save %s record=%s %s wait=%sms total=%sms",
                     op_id, actor, metric.get("id"), outcome, lock_wait_ms, _ms(started))


def _save(run, log_op, op_id, actor, metric, calcs, change_note, check_name, timing) -> dict:
    mid, exp = metric.get("id"), metric.get("expected_revision")
    creating, fields = mid is None, _nulls(metric["fields"])
    calcs = [{**c, "fields": _nulls(c["fields"])} for c in calcs]
    new_ids = [c["calc_id"] for c in calcs if c["expected_revision"] is None]

    # 1. Replay markers (this op committed, the create token is used, a reserved calc_id exists)
    #    and the metric as stored at the expected revision, in one read.
    replay, *stored = run(
        f"""SELECT (SELECT MAX(x) FROM (
                       SELECT TRY_TO_NUMBER(record_id) AS x FROM {_T['op_log']}
                       WHERE op_id = ? AND outcome = 'committed'
                       UNION ALL SELECT metric_id FROM {_T['metric']} WHERE ? AND create_token = ?
                       UNION ALL SELECT metric_id FROM {_T['metric_calc']} WHERE calc_id IN ({_marks(new_ids)}))),
                   m.metric_id, m.full_name, m.description, m.disambig, m.department, m.category
            FROM (SELECT 1) d
            LEFT JOIN {_T['metric']} m ON m.metric_id = ? AND m.revision_no = ?""",
        [op_id, creating, metric.get("create_token"), *new_ids, mid, exp])[0]
    if replay is not None:
        log_op("replayed", replay)
        return {"outcome": "replayed", "metric_id": int(replay)}

    # 2. What changed, and is every record still at the revision the draft started from?
    #    Only active PIs of this metric at their expected revision count as a match.
    found = creating or stored[0] is not None
    metric_changed = creating or (found and _blank(stored[1:]) != tuple(fields.get(k) for k in _METRIC_FIELDS))
    rows = {r[0]: r for r in run(
        f"""SELECT calc_id, revision_no, sql_text, source_table, disambig FROM {_T['metric_calc']}
            WHERE calc_id IN ({_marks(calcs)}) AND metric_id = ? AND status = 'active'""",
        [*(c["calc_id"] for c in calcs), mid])} if calcs and not creating else {}
    changed, new, checks = [], [], []
    for c in calcs:
        f, row = c["fields"], rows.get(c["calc_id"])
        if c["expected_revision"] is None:
            if not c["retire"]:  # a new PI that is also removed is skipped
                new.append(c["calc_id"])
                checks.append(c["calc_id"])
        elif row is None or row[1] != c["expected_revision"]:
            found = False
        elif c["retire"] or _blank(row[2:]) != (f.get("sql_text"), f.get("source_table"), f.get("disambig")):
            changed.append(c["calc_id"])
            if not c["retire"] and _blank(row[2:3]) != (f.get("sql_text"),):
                checks.append(c["calc_id"])
    if not found:
        log_op("conflict", mid)
        return {"outcome": "conflict", "metric_id": mid}
    if not (metric_changed or changed or new):
        log_op("no_change", mid)
        return {"outcome": "no_change", "metric_id": mid, "metric_revision": exp}
    hits = _collisions(run, check_name) if check_name and (
        creating or (stored[1] or "").strip().lower() != check_name) else []

    # 3. Write only what changed, every edit conditional on its revision, in one transaction.
    run("BEGIN")
    try:
        if creating:
            mid = run(f"SELECT {SCHEMA}.seq_metric_id.NEXTVAL")[0][0]
            run(f"""INSERT INTO {_T['metric']} (metric_id, full_name, description, disambig, department,
                        category, source, original_author, created_by, updated_by, create_token)
                    SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?""",
                [mid, *(fields.get(k) for k in _METRIC_FIELDS), metric.get("source") or "sme",
                 metric.get("original_author") or actor, actor, actor, metric.get("create_token")])
        elif metric_changed and run(
                f"""UPDATE {_T['metric']}
                    SET full_name = ?, description = ?, disambig = ?, department = ?, category = ?,
                        revision_no = revision_no + 1, updated_by = ?, updated_at = CURRENT_TIMESTAMP()
                    WHERE metric_id = ? AND revision_no = ?""",
                [*(fields.get(k) for k in _METRIC_FIELDS), actor, mid, exp])[0][0] != 1:
            raise _LostRace
        req_calcs = json.dumps(calcs)
        if changed and run(
                f"""UPDATE {_T['metric_calc']} c
                    SET sql_text     = IFF(r.retire, c.sql_text, r.sql_text),
                        source_table = IFF(r.retire, c.source_table, r.source_table),
                        disambig     = IFF(r.retire, c.disambig, r.disambig),
                        status       = IFF(r.retire, 'retired', c.status),
                        -- A check counts until the SQL changes (CHECK-06). Right-hand sides read the old row.
                        validated_revision_no = IFF(NOT r.retire AND c.validated_revision_no = c.revision_no
                                                    AND EQUAL_NULL(NULLIF(c.sql_text, ''), r.sql_text),
                                                    c.revision_no + 1, c.validated_revision_no),
                        revision_no  = c.revision_no + 1, updated_by = ?, updated_at = CURRENT_TIMESTAMP()
                    FROM {_REQ_CALCS} r
                    WHERE c.calc_id = r.id AND c.revision_no = r.exp_rev AND c.metric_id = ?
                      AND c.status = 'active' AND ARRAY_CONTAINS(r.id::VARIANT, PARSE_JSON(?))""",
                [actor, req_calcs, mid, json.dumps(changed)])[0][0] != len(changed):
            raise _LostRace
        if new:
            run(f"""INSERT INTO {_T['metric_calc']} (calc_id, metric_id, disambig, source, sql_text,
                        source_table, is_default, original_author, created_by, updated_by)
                    SELECT r.id, ?, r.disambig, 'sme', r.sql_text, r.source_table, r.is_default, ?, ?, ?
                    FROM {_REQ_CALCS} r WHERE ARRAY_CONTAINS(r.id::VARIANT, PARSE_JSON(?))""",
                [mid, actor, actor, actor, req_calcs, json.dumps(new)])
        if new or any(c["retire"] for c in calcs if c["calc_id"] in changed):
            # The oldest active PI is the default; retired PIs never are (DEC-019, DEC-023). Only adding
            # or retiring a PI can change which one that is. Not a content revision.
            run(f"""UPDATE {_T['metric_calc']} c
                    SET is_default = (c.status = 'active' AND c.calc_id = d.first_id)
                    FROM (SELECT MIN(calc_id) AS first_id FROM {_T['metric_calc']}
                          WHERE metric_id = ? AND status = 'active') d
                    WHERE c.metric_id = ?
                      AND c.is_default IS DISTINCT FROM (c.status = 'active' AND c.calc_id = d.first_id)""",
                [mid, mid])
        # One snapshot per written record (the row as written) plus the committed op_log row, in one
        # statement, so history and log can't drift from the save.
        lock_wait_ms, elapsed_ms = timing()
        run(f"""INSERT ALL
                  WHEN TRUE THEN INTO {_T['revision']}
                    (record_type, record_id, revision_no, action, snapshot, schema_version, actor, change_note)
                    VALUES (rt, rid, rno, act, snap, ?, ?, ?)
                  WHEN first THEN INTO {_T['op_log']}
                    (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id)
                    VALUES (?, 'metric.save', ?, ?, 'committed', ?, ?, LAST_QUERY_ID())
                SELECT rt, rid, rno, act, snap, ROW_NUMBER() OVER (ORDER BY rt) = 1 AS first FROM (
                  SELECT 'metric' AS rt, metric_id::VARCHAR AS rid, revision_no AS rno,
                         IFF(?, 'create', 'edit') AS act, OBJECT_CONSTRUCT_KEEP_NULL(*) AS snap
                  FROM {_T['metric']} WHERE metric_id = ? AND ?
                  UNION ALL
                  SELECT 'metric_calc', calc_id::VARCHAR, revision_no,
                         IFF(ARRAY_CONTAINS(calc_id::VARIANT, PARSE_JSON(?)), 'create',
                             IFF(status = 'retired', 'retire', 'edit')), OBJECT_CONSTRUCT_KEEP_NULL(*)
                  FROM {_T['metric_calc']} WHERE calc_id IN ({_marks(changed + new)}))""",
            [SNAPSHOT_VERSION, actor, change_note, op_id, actor, str(mid), lock_wait_ms, elapsed_ms,
             creating, mid, metric_changed, json.dumps(new), *changed, *new])
        run("COMMIT")
    except _LostRace:  # another save landed between the check and the write
        run("ROLLBACK")
        log_op("conflict", mid)
        return {"outcome": "conflict", "metric_id": mid}
    return {"outcome": "committed", "metric_id": mid, "metric_revision": 1 if creating else exp + metric_changed,
            "changed_calcs": changed, "new_calcs": new, "checks_due": checks, "collisions": hits}


_METRIC_FIELDS = ("full_name", "description", "disambig", "department", "category")


def _collisions(run, name: str) -> list | None:
    """Advisory duplicate-name check for a new or renamed metric; never fails a save (REL-11)."""
    try:
        return [{"KIND": r[0], "ID": r[1], "FULL_NAME": r[2]} for r in run(
            f"""SELECT status, metric_id, full_name FROM {_T['metric']}
                WHERE LOWER(TRIM(full_name)) = ? AND status IN ('candidate', 'canon')""", [name])]
    except Exception:
        log.warning("duplicate-name check failed", exc_info=True)
        return None


def _marks(ids: list) -> str:
    # Bound IN-lists keep hybrid-table lookups on the primary key; NULL matches nothing.
    return ", ".join("?" * len(ids)) or "NULL"


def _blank(values) -> tuple:
    return tuple(None if v == "" else v for v in values)


def _nulls(fields: dict) -> dict:
    # Change detection compares with stored values, where "" never appears as content: "" means NULL.
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

