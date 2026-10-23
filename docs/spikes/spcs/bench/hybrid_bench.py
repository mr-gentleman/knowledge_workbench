"""Save-latency benchmark: standard vs hybrid tables (spike, 2026-10-23).

One save = BEGIN; conditional UPDATE of the candidate (rowcount must be 1); INSERT the
revision snapshot built from the updated row; INSERT op_log; COMMIT.
  A  standard tables
  B  hybrid tables (PKs enforced)
  C  hybrid, revision + op_log in one INSERT ALL

Runs on scratch tables AI_PLATFORM.WORKBENCH.zz_bench_* (created and dropped here; no existing
object is read or written), one connection
(`workbench_deploy`, qmark), warehouse BIZ_AI_WH. Rounds are interleaved A,B,C so drift hits
all variants alike. Then one cold save per variant after > 60 s idle (warehouse auto-suspends).

    python3 docs/spikes/spcs/bench/hybrid_bench.py [rounds] [out.json]
"""
import json
import random
import string
import sys
import time
import uuid

import snowflake.connector

S = "AI_PLATFORM.WORKBENCH"
TABLES = [f"{S}.zz_bench_{p}_{t}" for p in ("std", "hyb") for t in ("candidate", "revision", "op_log")]
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
OUT = sys.argv[2] if len(sys.argv) > 2 else "hybrid_bench_results.json"
IDLE_S = 75

CANDIDATE_COLS = """
    candidate_id NUMBER NOT NULL, full_name VARCHAR NOT NULL, description VARCHAR,
    disambig VARCHAR, department VARCHAR, category VARCHAR, source VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'open', promoted_metric_id NUMBER,
    duplicate_of_metric_id NUMBER, original_author VARCHAR,
    revision_no NUMBER NOT NULL DEFAULT 1, created_by VARCHAR NOT NULL,
    created_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(), updated_by VARCHAR NOT NULL,
    updated_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(), create_token VARCHAR"""
REVISION_COLS = """
    record_type VARCHAR NOT NULL, record_id VARCHAR NOT NULL, revision_no NUMBER NOT NULL,
    action VARCHAR NOT NULL, snapshot VARIANT NOT NULL, schema_version NUMBER NOT NULL DEFAULT 1,
    actor VARCHAR NOT NULL, acted_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    change_note VARCHAR"""
OP_LOG_COLS = """
    op_id VARCHAR NOT NULL, op VARCHAR NOT NULL, actor VARCHAR NOT NULL, record_id VARCHAR,
    outcome VARCHAR NOT NULL, lock_wait_ms NUMBER NOT NULL, duration_ms NUMBER NOT NULL,
    last_query_id VARCHAR, error VARCHAR,
    logged_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()"""
SEED_CANDIDATES, SEED_REVISIONS = 1000, 5000


def ddl(prefix, hybrid):
    kind = "HYBRID TABLE" if hybrid else "TABLE"
    pk = ",\n    PRIMARY KEY ({})" if hybrid else ""
    t = f"{S}.zz_bench_{prefix}"
    return [
        f"CREATE {kind} {t}_candidate ({CANDIDATE_COLS}{pk.format('candidate_id')})",
        f"CREATE {kind} {t}_revision ({REVISION_COLS}{pk.format('record_type, record_id, revision_no')})",
        f"CREATE {kind} {t}_op_log ({OP_LOG_COLS}{pk.format('op_id')})",
        f"""INSERT INTO {t}_candidate (candidate_id, full_name, description, source, created_by, updated_by)
            SELECT SEQ4() + 1, 'metric ' || (SEQ4() + 1), RANDSTR(1500, RANDOM()), 'import', 'BENCH', 'BENCH'
            FROM TABLE(GENERATOR(ROWCOUNT => {SEED_CANDIDATES}))""",
        f"""INSERT INTO {t}_revision (record_type, record_id, revision_no, action, snapshot, actor)
            SELECT 'metric_candidate', TO_VARCHAR(MOD(SEQ4(), {SEED_CANDIDATES}) + 1),
                   -1 - FLOOR(SEQ4() / {SEED_CANDIDATES}), 'import',
                   OBJECT_CONSTRUCT('description', RANDSTR(1800, RANDOM())), 'BENCH'
            FROM TABLE(GENERATOR(ROWCOUNT => {SEED_REVISIONS}))""",
    ]


def text(n):
    return "".join(random.choices(string.ascii_letters + "     ", k=n))


class Bench:
    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor()
        self.rev = {}  # (prefix, candidate_id) -> current revision_no

    def run(self, sql, params=None):
        t0 = time.perf_counter()
        self.cur.execute(sql, params)
        return self.cur.rowcount, self.cur.sfqid, (time.perf_counter() - t0) * 1000

    def save(self, prefix, insert_all, candidate_id, expected=None):
        """One save. Returns timings; raises nothing on conflict (rolls back, outcome=conflict)."""
        t = f"{S}.zz_bench_{prefix}"
        expected = self.rev.get((prefix, candidate_id), 1) if expected is None else expected
        op_id, steps = str(uuid.uuid4()), []
        t0 = time.perf_counter()
        steps.append(("BEGIN",) + self.run("BEGIN")[1:])
        n, qid, ms = self.run(
            f"""UPDATE {t}_candidate SET full_name = ?, description = ?, disambig = ?,
                       revision_no = revision_no + 1, updated_by = ?, updated_at = CURRENT_TIMESTAMP()
                WHERE candidate_id = ? AND revision_no = ?""",
            [f"metric {candidate_id}", text(1800), text(120), "BENCH", candidate_id, expected])
        steps.append(("UPDATE", qid, ms))
        if n != 1:
            steps.append(("ROLLBACK",) + self.run("ROLLBACK")[1:])
            return {"outcome": "conflict", "rows": n, "total_ms": (time.perf_counter() - t0) * 1000,
                    "steps": steps}
        snap = f"""SELECT 'metric_candidate', TO_VARCHAR(candidate_id), revision_no, 'edit',
                          OBJECT_CONSTRUCT_KEEP_NULL(*), 2, 'BENCH', NULL
                   FROM {t}_candidate WHERE candidate_id = ?"""
        rev_cols = "(record_type, record_id, revision_no, action, snapshot, schema_version, actor, change_note)"
        log_cols = "(op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms)"
        if insert_all:
            steps.append(("INSERT ALL",) + self.run(
                f"""INSERT ALL
                      INTO {t}_revision {rev_cols} VALUES (rt, rid, rno, act, snap, sv, actor, note)
                      INTO {t}_op_log {log_cols} VALUES (?, 'candidate.edit', actor, rid, 'committed', 0, 0)
                    SELECT 'metric_candidate' rt, TO_VARCHAR(candidate_id) rid, revision_no rno,
                           'edit' act, OBJECT_CONSTRUCT_KEEP_NULL(*) snap, 2 sv, 'BENCH' actor, NULL note
                    FROM {t}_candidate WHERE candidate_id = ?""",
                [op_id, candidate_id])[1:])
        else:
            steps.append(("INSERT revision",) + self.run(
                f"INSERT INTO {t}_revision {rev_cols} {snap}", [candidate_id])[1:])
            steps.append(("INSERT op_log",) + self.run(
                f"INSERT INTO {t}_op_log {log_cols} VALUES (?, 'candidate.edit', 'BENCH', ?, 'committed', 0, 0)",
                [op_id, str(candidate_id)])[1:])
        steps.append(("COMMIT",) + self.run("COMMIT")[1:])
        self.rev[(prefix, candidate_id)] = expected + 1
        return {"outcome": "committed", "total_ms": (time.perf_counter() - t0) * 1000, "steps": steps}

    def warehouse_state(self):
        self.cur.execute("SHOW WAREHOUSES LIKE 'BIZ_AI_WH'")
        cols = [c[0] for c in self.cur.description]
        row = self.cur.fetchone()
        return dict(zip(cols, row)).get("state") if row else None


VARIANTS = {"A_standard": ("std", False), "B_hybrid": ("hyb", False), "C_hybrid_insert_all": ("hyb", True)}


def main():
    conn = snowflake.connector.connect(connection_name="workbench_deploy", paramstyle="qmark",
                                       client_session_keep_alive=True)
    b, out = Bench(conn), {"rounds": ROUNDS, "warm": {v: [] for v in VARIANTS}, "cold": {}}
    created = False
    try:
        b.cur.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_SESSION()")
        out["session"] = b.cur.fetchone()
        b.cur.execute("SHOW GRANTS TO ROLE WORKBENCH_APP")
        cols = [c[0] for c in b.cur.description]
        out["grants_on_workbench_schema"] = sorted(
            g["privilege"] for g in (dict(zip(cols, r)) for r in b.cur.fetchall())
            if g["granted_on"] == "SCHEMA" and g["name"] == "AI_PLATFORM.WORKBENCH")
        print("grants on WORKBENCH schema:", out["grants_on_workbench_schema"], flush=True)
        # Never drop a table this run didn't create.
        b.cur.execute(f"SHOW TABLES LIKE 'ZZ_BENCH_%' IN SCHEMA {S}")
        if b.cur.fetchall():
            raise SystemExit("zz_bench_* tables already exist; drop them by hand first")
        created = True
        for prefix, hybrid in (("std", False), ("hyb", True)):
            for stmt in ddl(prefix, hybrid):
                b.cur.execute(stmt)
        out["round_trip_ms"] = [b.run("SELECT 1")[2] for _ in range(10)]

        # Stale-revision check on hybrid: expected revision 0 never matches (rows start at 1).
        out["stale_check_hybrid"] = b.save("hyb", False, 999, expected=0)
        out["stale_check_standard"] = b.save("std", False, 999, expected=0)

        # Warm-up (not recorded), then interleaved rounds; each round edits a fresh candidate id
        # in A and the shared hybrid tables (B and C use different ids so revisions never clash).
        for v, (prefix, ia) in VARIANTS.items():
            b.save(prefix, ia, 990 + list(VARIANTS).index(v))
        for i in range(ROUNDS):
            for v, (prefix, ia) in VARIANTS.items():
                cid = 1 + i + (500 if v == "C_hybrid_insert_all" else 0)
                out["warm"][v].append(b.save(prefix, ia, cid))
            print(f"round {i + 1}/{ROUNDS}: " + ", ".join(
                f"{v[0]} {out['warm'][v][-1]['total_ms']:.0f}" for v in VARIANTS), flush=True)

        for v, (prefix, ia) in VARIANTS.items():
            print(f"idle {IDLE_S}s before cold {v}", flush=True)
            time.sleep(IDLE_S)
            state = b.warehouse_state()
            r = b.save(prefix, ia, 900 + list(VARIANTS).index(v))
            r["warehouse_state_before"] = state
            out["cold"][v] = r
            print(f"cold {v}: {r['total_ms']:.0f} ms (warehouse was {state})", flush=True)

        time.sleep(5)  # let QUERY_HISTORY catch up
        qids = [s[1] for runs in out["warm"].values() for r in runs for s in r["steps"]]
        qids += [s[1] for r in out["cold"].values() for s in r["steps"]]
        b.cur.execute(
            """SELECT query_id, total_elapsed_time, compilation_time, execution_time,
                      queued_provisioning_time, queued_overload_time, transaction_blocked_time
               FROM TABLE(AI_PLATFORM.INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION(RESULT_LIMIT => 10000))""")
        cols = [c[0].lower() for c in b.cur.description]
        wanted = set(qids)
        out["query_history"] = {r[0]: dict(zip(cols, r)) for r in b.cur.fetchall() if r[0] in wanted}
        out["query_history_found"] = f"{len(out['query_history'])}/{len(wanted)}"
    finally:
        try:
            if created:
                b.cur.execute("ROLLBACK")
                for t in TABLES:
                    b.cur.execute(f"DROP TABLE IF EXISTS {t}")
                out["dropped"] = True
        finally:
            with open(OUT, "w") as f:
                json.dump(out, f, indent=1, default=str)
            conn.close()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
