"""Save-path benchmark: inline procedure vs Python statements, on hybrid and standard tables (2026-10-23).

Runs the real save logic, not a toy: the procedure variant runs sql/004's body unchanged (table
names swapped for scratch copies) as an anonymous procedure (`WITH … AS PROCEDURE … CALL`). The
Python variant does the same steps as client statements: replay + change-check read, BEGIN,
conditional UPDATEs, revision snapshots and op_log in one INSERT ALL, COMMIT. Both then do the
app's refresh reads (candidate, its PIs, sidebar list). Two shapes: definition-only edit, and
definition + one PI SQL edit.

  P_std  procedure, standard tables      Py_std  Python, standard tables
  P_hyb  procedure, hybrid tables        Py_hyb  Python, hybrid tables

Scratch tables AI_PLATFORM.WORKBENCH.zz_sp_{std,hyb}_{candidate,calc,revision,op_log}, created and
dropped here; reads the real metric_core only if a rename check runs (it doesn't: check_name NULL).
Hybrid op_log uses the surrogate key + op_id index planned for the migration, so its DDL is tested too.

    python3 docs/spikes/spcs/bench/save_path_bench.py [rounds] [out.json]
"""
import json
import pathlib
import random
import string
import sys
import time
import uuid

import snowflake.connector

S = "AI_PLATFORM.WORKBENCH"
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 15
OUT = sys.argv[2] if len(sys.argv) > 2 else "save_path_results.json"
PROC_SQL = (pathlib.Path(__file__).parents[4] / "sql/004_save_metric_proc.sql").read_text()
N_CAND, N_CALC, N_REV, N_LOG = 1000, 1500, 5000, 5000

CANDIDATE = """candidate_id NUMBER NOT NULL, full_name VARCHAR NOT NULL, description VARCHAR,
    disambig VARCHAR, department VARCHAR, category VARCHAR, source VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'open', promoted_metric_id NUMBER, duplicate_of_metric_id NUMBER,
    original_author VARCHAR, revision_no NUMBER NOT NULL DEFAULT 1, created_by VARCHAR NOT NULL,
    created_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(), updated_by VARCHAR NOT NULL,
    updated_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(), create_token VARCHAR"""
CALC = """calc_id NUMBER NOT NULL, metric_id NUMBER, origin_candidate_id NUMBER, disambig VARCHAR,
    source VARCHAR NOT NULL, sql_text VARCHAR, source_table VARCHAR,
    is_default BOOLEAN NOT NULL DEFAULT FALSE, status VARCHAR NOT NULL DEFAULT 'active',
    validated_revision_no NUMBER, validation_status VARCHAR, validation_message VARCHAR,
    validation_query_id VARCHAR, validated_at TIMESTAMP_TZ, served_revision_no NUMBER,
    original_author VARCHAR, revision_no NUMBER NOT NULL DEFAULT 1, created_by VARCHAR NOT NULL,
    created_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(), updated_by VARCHAR NOT NULL,
    updated_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()"""
REVISION = """record_type VARCHAR NOT NULL, record_id VARCHAR NOT NULL, revision_no NUMBER NOT NULL,
    action VARCHAR NOT NULL, snapshot VARIANT NOT NULL, schema_version NUMBER NOT NULL DEFAULT 1,
    actor VARCHAR NOT NULL, acted_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(), change_note VARCHAR"""
OP_LOG = """op_id VARCHAR NOT NULL, op VARCHAR NOT NULL, actor VARCHAR NOT NULL, record_id VARCHAR,
    outcome VARCHAR NOT NULL, lock_wait_ms NUMBER NOT NULL, duration_ms NUMBER NOT NULL,
    last_query_id VARCHAR, error VARCHAR, logged_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()"""


def t(p, name):
    return f"{S}.zz_sp_{p}_{name}"


def ddl(p):
    if p == "hyb":
        tables = [
            f"CREATE HYBRID TABLE {t(p, 'candidate')} ({CANDIDATE}, PRIMARY KEY (candidate_id),"
            f" INDEX ix_cand_token (create_token))",
            f"CREATE HYBRID TABLE {t(p, 'calc')} ({CALC}, PRIMARY KEY (calc_id),"
            f" INDEX ix_calc_origin (origin_candidate_id))",
            f"CREATE HYBRID TABLE {t(p, 'revision')} ({REVISION}, PRIMARY KEY (record_type, record_id, revision_no))",
            f"CREATE HYBRID TABLE {t(p, 'op_log')} (log_id VARCHAR NOT NULL DEFAULT UUID_STRING(), {OP_LOG},"
            f" PRIMARY KEY (log_id), INDEX ix_op_log_op_id (op_id))",
        ]
    else:
        tables = [f"CREATE TABLE {t(p, n)} ({cols})" for n, cols in
                  (("candidate", CANDIDATE), ("calc", CALC), ("revision", REVISION), ("op_log", OP_LOG))]
    return tables + [
        f"""INSERT INTO {t(p, 'candidate')} (candidate_id, full_name, description, source, created_by, updated_by)
            SELECT SEQ4() + 1, 'metric ' || (SEQ4() + 1), RANDSTR(1500, RANDOM()), 'import', 'BENCH', 'BENCH'
            FROM TABLE(GENERATOR(ROWCOUNT => {N_CAND}))""",
        f"""INSERT INTO {t(p, 'calc')} (calc_id, origin_candidate_id, disambig, source, sql_text, source_table,
                                       created_by, updated_by)
            SELECT SEQ4() + 1, MOD(SEQ4(), {N_CAND}) + 1, 'v' || SEQ4(), 'import', RANDSTR(1200, RANDOM()),
                   'AC.MART.FACT_X', 'BENCH', 'BENCH'
            FROM TABLE(GENERATOR(ROWCOUNT => {N_CALC}))""",
        f"""INSERT INTO {t(p, 'revision')} (record_type, record_id, revision_no, action, snapshot, actor)
            SELECT 'metric_candidate', TO_VARCHAR(MOD(SEQ4(), {N_CAND}) + 1), -1 - FLOOR(SEQ4() / {N_CAND}),
                   'import', OBJECT_CONSTRUCT('description', RANDSTR(1800, RANDOM())), 'BENCH'
            FROM TABLE(GENERATOR(ROWCOUNT => {N_REV}))""",
        f"""INSERT INTO {t(p, 'op_log')} (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms)
            SELECT UUID_STRING(), 'metric.save', 'BENCH', TO_VARCHAR(MOD(SEQ4(), {N_CAND}) + 1), 'committed', 0, 0
            FROM TABLE(GENERATOR(ROWCOUNT => {N_LOG}))""",
    ]


def proc_sql(p):
    body = PROC_SQL.split("$$", 2)[1]
    for real, scratch in (("metric_candidate", "candidate"), ("metric_calc", "calc"),
                          ("revision", "revision"), ("op_log", "op_log")):
        body = body.replace(f"AI_PLATFORM.WORKBENCH.{real}", t(p, scratch))
    return (f"WITH save_metric AS PROCEDURE (p_request VARCHAR) RETURNS VARIANT LANGUAGE SQL AS $${body}$$\n"
            "CALL save_metric(?)")


def text(n):
    return "".join(random.choices(string.ascii_letters + "     ", k=n))


class Bench:
    def __init__(self, conn):
        self.conn, self.cur = conn, conn.cursor()
        self.rev = {}  # (prefix, kind, id) -> current revision_no
        self.procs = {p: proc_sql(p) for p in ("std", "hyb")}
        self.qids = []

    def run(self, sql, params=None):
        self.cur.execute(sql, params)
        self.qids.append(self.cur.sfqid)
        return self.cur

    def request(self, p, cid, calc_id, op_id, stale=False):
        r = lambda kind, i: 0 if stale else self.rev.get((p, kind, i), 1)  # noqa: E731
        calcs = [] if calc_id is None else [{
            "calc_id": calc_id, "expected_revision": r("calc", calc_id), "retire": False, "is_default": False,
            "fields": {"sql_text": "SELECT " + text(1200), "source_table": "AC.MART.FACT_X", "disambig": f"v{calc_id}"}}]
        return {"op_id": op_id, "actor": "BENCH", "lock_wait_ms": 0, "schema_version": 2, "change_note": None,
                "check_name": None,
                "candidate": {"id": cid, "expected_revision": r("cand", cid), "create_token": None,
                              "fields": {"full_name": f"metric {cid}", "description": text(1500),
                                         "disambig": text(120), "department": None, "category": None}},
                "calcs": calcs}

    # ── the two save paths ─────────────────────────────────────────────────
    def save_proc(self, p, req):
        row = self.run(self.procs[p], [json.dumps(req)]).fetchone()
        return json.loads(row[0])["outcome"]

    def save_python(self, p, req):
        """Same steps and rules as sql/004 for an edit (no create, no retire)."""
        cand, calcs, op_id = req["candidate"], req["calcs"], req["op_id"]
        f = cand["fields"]
        row = self.run(
            f"""SELECT (SELECT COUNT(*) FROM {t(p, 'op_log')} WHERE op_id = ? AND outcome = 'committed'),
                       c.candidate_id, c.full_name, c.description, c.disambig, c.department, c.category
                FROM (SELECT 1 AS one) d
                LEFT JOIN {t(p, 'candidate')} c ON c.candidate_id = ? AND c.revision_no = ?""",
            [op_id, cand["id"], cand["expected_revision"]]).fetchone()
        if row[0]:
            return "replayed"
        stored = {}
        if calcs:
            ids = [c["calc_id"] for c in calcs]
            for r in self.run(
                    f"""SELECT calc_id, revision_no, sql_text, source_table, disambig FROM {t(p, 'calc')}
                        WHERE calc_id IN ({','.join('?' * len(ids))}) AND origin_candidate_id = ?
                          AND status = 'active'""", ids + [cand["id"]]).fetchall():
                stored[r[0]] = r
        if row[1] is None or any(stored.get(c["calc_id"], (0, -1))[1] != c["expected_revision"] for c in calcs):
            return "conflict"
        cand_changed = tuple(row[2:]) != (f["full_name"], f["description"], f["disambig"],
                                          f["department"], f["category"])
        changed = [c for c in calcs if tuple(stored[c["calc_id"]][2:]) != (
            c["fields"]["sql_text"], c["fields"]["source_table"], c["fields"]["disambig"])]
        if not cand_changed and not changed:
            return "no_change"
        self.run("BEGIN")
        try:
            if cand_changed and self.run(
                    f"""UPDATE {t(p, 'candidate')} SET full_name = ?, description = ?, disambig = ?,
                               department = ?, category = ?, revision_no = revision_no + 1,
                               updated_by = ?, updated_at = CURRENT_TIMESTAMP()
                        WHERE candidate_id = ? AND revision_no = ?""",
                    [f["full_name"], f["description"], f["disambig"], f["department"], f["category"],
                     req["actor"], cand["id"], cand["expected_revision"]]).rowcount != 1:
                raise LostRace
            for c in changed:
                if self.run(
                        f"""UPDATE {t(p, 'calc')} SET sql_text = ?, source_table = ?, disambig = ?,
                                   revision_no = revision_no + 1, updated_by = ?, updated_at = CURRENT_TIMESTAMP()
                            WHERE calc_id = ? AND revision_no = ? AND origin_candidate_id = ? AND status = 'active'""",
                        [c["fields"]["sql_text"], c["fields"]["source_table"], c["fields"]["disambig"],
                         req["actor"], c["calc_id"], c["expected_revision"], cand["id"]]).rowcount != 1:
                    raise LostRace
            calc_ids = [c["calc_id"] for c in changed] or [None]
            self.run(
                f"""INSERT ALL
                      WHEN TRUE THEN INTO {t(p, 'revision')}
                        (record_type, record_id, revision_no, action, snapshot, schema_version, actor, change_note)
                        VALUES (rt, rid, rno, 'edit', snap, ?, ?, ?)
                      WHEN first THEN INTO {t(p, 'op_log')}
                        (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms)
                        VALUES (?, 'metric.save', ?, ?, 'committed', ?, 0)
                    SELECT rt, rid, rno, snap, ROW_NUMBER() OVER (ORDER BY rt DESC) = 1 AS first FROM (
                      SELECT 'metric_candidate' rt, TO_VARCHAR(candidate_id) rid, revision_no rno,
                             OBJECT_CONSTRUCT_KEEP_NULL(*) snap
                      FROM {t(p, 'candidate')} WHERE candidate_id = ? AND ?
                      UNION ALL
                      SELECT 'metric_calc', TO_VARCHAR(calc_id), revision_no, OBJECT_CONSTRUCT_KEEP_NULL(*)
                      FROM {t(p, 'calc')} WHERE calc_id IN ({','.join('?' * len(calc_ids))}))""",
                [req["schema_version"], req["actor"], req["change_note"],
                 op_id, req["actor"], str(cand["id"]), req["lock_wait_ms"], cand["id"], cand_changed] + calc_ids)
            self.run("COMMIT")
        except LostRace:
            self.run("ROLLBACK")
            return "conflict"
        return "committed"

    def refresh(self, p, cid):
        self.run(f"SELECT * FROM {t(p, 'candidate')} WHERE candidate_id = ?", [cid]).fetchall()
        self.run(f"SELECT * FROM {t(p, 'calc')} WHERE origin_candidate_id = ? AND status = 'active' ORDER BY calc_id",
                 [cid]).fetchall()
        self.run(f"""SELECT candidate_id, full_name, description, disambig, category, status, promoted_metric_id,
                            original_author, updated_by, updated_at
                     FROM {t(p, 'candidate')} ORDER BY updated_at DESC LIMIT 200""").fetchall()

    def save(self, variant, cid, calc_id):
        path, p = variant.split("_")
        req = self.request(p, cid, calc_id, str(uuid.uuid4()))
        self.qids = []
        t0 = time.perf_counter()
        outcome = (self.save_proc if path == "P" else self.save_python)(p, req)
        t1 = time.perf_counter()
        self.refresh(p, cid)
        t2 = time.perf_counter()
        if outcome == "committed":
            self.rev[(p, "cand", cid)] = self.rev.get((p, "cand", cid), 1) + 1
            if calc_id is not None:
                self.rev[(p, "calc", calc_id)] = self.rev.get((p, "calc", calc_id), 1) + 1
        return {"outcome": outcome, "save_ms": (t1 - t0) * 1000, "refresh_ms": (t2 - t1) * 1000,
                "save_qids": self.qids[:-3], "refresh_qids": self.qids[-3:], "req": req}

    def checks(self, variant, cid, calc_id):
        """Conflict and replay behave the same on both paths."""
        path, p = variant.split("_")
        fn = self.save_proc if path == "P" else self.save_python
        stale = fn(p, self.request(p, cid, calc_id, str(uuid.uuid4()), stale=True))
        first = self.save(variant, cid, calc_id)
        again = fn(p, first["req"])
        return {"stale": stale, "first": first["outcome"], "same_op_id_again": again}


class LostRace(Exception):
    pass


VARIANTS = ["P_std", "P_hyb", "Py_std", "Py_hyb"]
SHAPES = {"definition": False, "definition+PI": True}


def main():
    conn = snowflake.connector.connect(connection_name="workbench_deploy", paramstyle="qmark",
                                       client_session_keep_alive=True)
    b = Bench(conn)
    out = {"rounds": ROUNDS, "runs": {f"{v} {s}": [] for v in VARIANTS for s in SHAPES}}
    created = False
    try:
        b.cur.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_SESSION()")
        out["session"] = b.cur.fetchone()
        b.cur.execute(f"SHOW TABLES LIKE 'ZZ_SP_%' IN SCHEMA {S}")
        if b.cur.fetchall():
            raise SystemExit("zz_sp_* tables already exist; drop them by hand first")
        created = True
        for p in ("std", "hyb"):
            for stmt in ddl(p):
                b.cur.execute(stmt)
        print("scratch tables created", flush=True)
        out["round_trip_ms"] = []
        for _ in range(10):
            t0 = time.perf_counter()
            b.cur.execute("SELECT 1")
            out["round_trip_ms"].append((time.perf_counter() - t0) * 1000)

        # Each variant edits its own candidate range so revisions never clash. PI = one of its own calcs.
        base = {v: 1 + 200 * i for i, v in enumerate(VARIANTS)}
        out["checks"] = {v: b.checks(v, base[v] + 190, base[v] + 190) for v in VARIANTS}
        print("checks:", out["checks"], flush=True)
        for v in VARIANTS:  # warm-up, not recorded
            b.save(v, base[v] + 191, base[v] + 191)
        for i in range(ROUNDS):
            for s, with_pi in SHAPES.items():
                for v in VARIANTS:
                    cid = base[v] + i + (100 if with_pi else 0)
                    r = b.save(v, cid, cid if with_pi else None)
                    r.pop("req")
                    out["runs"][f"{v} {s}"].append(r)
            print(f"round {i + 1}/{ROUNDS}: " + ", ".join(
                f"{k} {rs[-1]['save_ms']:.0f}+{rs[-1]['refresh_ms']:.0f}" for k, rs in out["runs"].items()), flush=True)

        time.sleep(5)  # let QUERY_HISTORY catch up
        b.cur.execute(
            """SELECT query_id, total_elapsed_time, compilation_time, execution_time
               FROM TABLE(AI_PLATFORM.INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION(RESULT_LIMIT => 10000))""")
        out["query_history"] = {r[0]: {"total": r[1], "compile": r[2], "exec": r[3]} for r in b.cur.fetchall()}
    finally:
        try:
            if created:
                b.cur.execute("ROLLBACK")
                for p in ("std", "hyb"):
                    for n in ("candidate", "calc", "revision", "op_log"):
                        b.cur.execute(f"DROP TABLE IF EXISTS {t(p, n)}")
                out["dropped"] = True
        finally:
            with open(OUT, "w") as fh:
                json.dump(out, fh, indent=1, default=str)
            conn.close()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
