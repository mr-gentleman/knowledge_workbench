"""Rehearse sql/010 and its rollback on scratch copies (AI_PLATFORM.WORKBENCH.zz_rh_*), 2026-10-23.

Every table name in both scripts is rewritten to zz_rh_<name>. Seeds standard zz_rh_* tables from the
rollback's DDL with the live rows (fact_table_core, revision, op_log; one metric + PI), runs 010, checks
counts / table kinds / indexes, runs the rollback, checks again, drops everything it created.
    python3 docs/spikes/spcs/bench/rehearse_010.py
"""
import re
import sys

import snowflake.connector

S = "AI_PLATFORM.WORKBENCH"
TABLES = ["metric", "metric_calc", "revision", "op_log", "fact_table_core"]
NAME = re.compile(r"AI_PLATFORM\.WORKBENCH\.(metric_calc|metric|revision|op_log|fact_table_core)(\w*)")


def scratch(sql):
    return NAME.sub(lambda m: f"{S}.zz_rh_{m.group(1)}{m.group(2)}", sql)


def statements(path):
    text = "\n".join(l for l in open(path).read().splitlines() if not l.lstrip().startswith("--"))
    return [s.strip() for s in text.split(";") if s.strip()]


def main():
    conn = snowflake.connector.connect(connection_name="workbench_deploy", paramstyle="qmark")
    cur = conn.cursor()
    run = lambda sql, p=None: cur.execute(sql, p).fetchall()
    if run(f"SHOW TABLES LIKE 'ZZ_RH_%' IN SCHEMA {S}"):
        sys.exit("zz_rh_* already exist; drop them first")
    down = statements("sql/rollback/010_hybrid_tables_down.sql")
    try:
        # Seed: standard tables with the rollback's DDL, named like the live ones.
        for st in down:
            if st.startswith("CREATE TABLE"):
                run(scratch(st).replace("_std_rb", ""))
        for t, cols in (("fact_table_core", "*"), ("revision", "*")):
            run(f"INSERT INTO {S}.zz_rh_{t} SELECT {cols} FROM {S}.{t}")
        run(f"""INSERT INTO {S}.zz_rh_op_log (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms,
                       last_query_id, error, logged_at)
                SELECT op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id, error, logged_at
                FROM {S}.op_log""")
        run(f"INSERT INTO {S}.zz_rh_metric (metric_id, full_name, source, created_by, updated_by) VALUES (1, 'm', 'sme', 'R', 'R')")
        run(f"INSERT INTO {S}.zz_rh_metric_calc (calc_id, metric_id, source, created_by, updated_by) VALUES (1, 1, 'sme', 'R', 'R')")
        counts = lambda: {t: run(f"SELECT COUNT(*) FROM {S}.zz_rh_{t}")[0][0] for t in TABLES}
        before = counts()
        print("seeded:", before)

        for st in statements("sql/010_hybrid_tables.sql"):
            run(scratch(st))
        after = counts()
        kinds = {r[1]: r for r in run(f"SHOW HYBRID TABLES LIKE 'ZZ_RH_%' IN SCHEMA {S}")}
        idx = [r[1] for r in run(f"SHOW INDEXES IN SCHEMA {S}") if str(r[1]).startswith("IX_")]
        print("after 010:", after, "hybrid:", sorted(kinds), "indexes:", idx)
        assert after == before, (before, after)
        assert sorted(kinds) == sorted(f"ZZ_RH_{t.upper()}" for t in TABLES), kinds
        assert run(f"SELECT COUNT(DISTINCT log_id) FROM {S}.zz_rh_op_log")[0][0] == before["op_log"]

        for st in down:
            run(scratch(st))
        back = counts()
        hybrid_left = sorted(r[1] for r in run(f"SHOW HYBRID TABLES LIKE 'ZZ_RH_%' IN SCHEMA {S}"))
        print("after rollback:", back, "hybrid left:", hybrid_left)
        assert back == before and all(n.endswith("_HYB_ROLLEDBACK") for n in hybrid_left)
        print("REHEARSAL OK")
    finally:
        for name in [r[1] for r in run(f"SHOW TABLES LIKE 'ZZ_RH_%' IN SCHEMA {S}")]:
            run(f"DROP TABLE IF EXISTS {S}.{name}")
        conn.close()


if __name__ == "__main__":
    main()
