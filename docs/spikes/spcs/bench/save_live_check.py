"""Live check of app/repositories.save_metric (DEC-025) on scratch hybrid tables (2026-10-23).

Runs the real repository code, pointed at AI_PLATFORM.WORKBENCH.zz_lc_{metric,metric_calc,revision,op_log}
(hybrid, sql/010's keys and indexes; created and dropped here). Walks create → replay → edit + new PI →
label-only PI edit keeps its check → stale → no-op → retire resets the default, then times N
definition + PI edits with the page's refresh reads. One create draws one real seq_metric_id value (a gap).

    PYTHONPATH=. python docs/spikes/spcs/bench/save_live_check.py [n] [out.json]
"""
import json
import statistics
import sys
import time
import uuid

from api import spcs
from app import db
from app import repositories as repo

S = "AI_PLATFORM.WORKBENCH"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
OUT = sys.argv[2] if len(sys.argv) > 2 else "save_live_check.json"
T = {n: f"{S}.zz_lc_{n}" for n in ("metric", "metric_calc", "revision", "op_log")}
DDL = [
    f"""CREATE HYBRID TABLE {T['metric']} (
        metric_id NUMBER NOT NULL, full_name VARCHAR NOT NULL, description VARCHAR, disambig VARCHAR,
        department VARCHAR, category VARCHAR, source VARCHAR NOT NULL, status VARCHAR NOT NULL DEFAULT 'candidate',
        duplicate_of_metric_id NUMBER, superseded_by NUMBER, create_token VARCHAR, original_author VARCHAR,
        revision_no NUMBER NOT NULL DEFAULT 1, created_by VARCHAR NOT NULL,
        created_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(), updated_by VARCHAR NOT NULL,
        updated_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
        PRIMARY KEY (metric_id), INDEX ix_metric_create_token (create_token))""",
    f"""CREATE HYBRID TABLE {T['metric_calc']} (
        calc_id NUMBER NOT NULL, metric_id NUMBER NOT NULL, disambig VARCHAR, source VARCHAR NOT NULL,
        sql_text VARCHAR, source_table VARCHAR, is_default BOOLEAN NOT NULL DEFAULT FALSE,
        status VARCHAR NOT NULL DEFAULT 'active', validated_revision_no NUMBER, validation_status VARCHAR,
        validation_message VARCHAR, validation_query_id VARCHAR, validated_at TIMESTAMP_TZ,
        served_revision_no NUMBER, original_author VARCHAR, revision_no NUMBER NOT NULL DEFAULT 1,
        created_by VARCHAR NOT NULL, created_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
        updated_by VARCHAR NOT NULL, updated_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
        PRIMARY KEY (calc_id), INDEX ix_metric_calc_metric_id (metric_id))""",
    f"""CREATE HYBRID TABLE {T['revision']} (
        record_type VARCHAR NOT NULL, record_id VARCHAR NOT NULL, revision_no NUMBER NOT NULL,
        action VARCHAR NOT NULL, snapshot VARIANT NOT NULL, schema_version NUMBER NOT NULL DEFAULT 1,
        actor VARCHAR NOT NULL, acted_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(), change_note VARCHAR,
        PRIMARY KEY (record_type, record_id, revision_no))""",
    f"""CREATE HYBRID TABLE {T['op_log']} (
        log_id VARCHAR NOT NULL DEFAULT UUID_STRING(), op_id VARCHAR NOT NULL, op VARCHAR NOT NULL,
        actor VARCHAR NOT NULL, record_id VARCHAR, outcome VARCHAR NOT NULL, lock_wait_ms NUMBER NOT NULL,
        duration_ms NUMBER NOT NULL, last_query_id VARCHAR, error VARCHAR,
        logged_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
        PRIMARY KEY (log_id), INDEX ix_op_log_op_id (op_id))""",
]


def q(sql, params=()):
    return db.query(sql, list(params))


def fields(name="LC metric", desc="first"):
    return {"full_name": name, "description": desc, "disambig": None, "department": None, "category": None}


def calc(cid, rev, sql, label, retire=False):
    return {"calc_id": cid, "expected_revision": rev, "retire": retire, "is_default": False,
            "fields": {"sql_text": sql, "source_table": "AC.MART.FACT_X", "disambig": label}}


def main():
    db.session = spcs.session
    repo._T.update(T)
    out, steps = {}, []
    created = False
    try:
        if q(f"SHOW TABLES LIKE 'ZZ_LC_%' IN SCHEMA {S}"):
            raise SystemExit("zz_lc_* tables already exist; drop them by hand first")
        created = True
        for stmt in DDL:
            q(stmt)
        out["lock_timeout"] = q("SHOW PARAMETERS LIKE 'LOCK_TIMEOUT' IN SESSION")[0][1]

        def save(label, metric, calcs=(), op_id=None, check="lc metric"):
            r = repo.save_metric(op_id or str(uuid.uuid4()), "LIVECHECK", metric, list(calcs), label, check)
            steps.append((label, r))
            print(label, "→", r["outcome"], {k: r.get(k) for k in ("metric_id", "metric_revision",
                                                                    "changed_calcs", "new_calcs", "checks_due")})
            return r

        token, op = str(uuid.uuid4()), str(uuid.uuid4())
        mid = save("create", {"id": None, "create_token": token, "fields": fields()}, op_id=op)["metric_id"]
        save("same op again", {"id": None, "create_token": token, "fields": fields()}, op_id=op)
        save("edit + new PI", {"id": mid, "expected_revision": 1, "fields": fields(desc="second")},
             [calc(9000001, None, "SELECT 1", "daily"), calc(9000002, None, "SELECT 2", "monthly")])
        q(f"UPDATE {T['metric_calc']} SET validated_revision_no = revision_no, validation_status = 'passed' "
          "WHERE calc_id = 9000001")
        save("PI label only", {"id": mid, "expected_revision": 2, "fields": fields(desc="second")},
             [calc(9000001, 1, "SELECT 1", "daily, UTC")])
        save("stale", {"id": mid, "expected_revision": 1, "fields": fields(desc="third")})
        save("no change", {"id": mid, "expected_revision": 2, "fields": fields(desc="second")})
        save("retire default PI", {"id": mid, "expected_revision": 2, "fields": fields(desc="second")},
             [calc(9000001, 2, "SELECT 1", "daily, UTC", retire=True)])
        out["calcs"] = [r.as_dict() for r in q(
            f"""SELECT calc_id, status, is_default, revision_no, validated_revision_no
                FROM {T['metric_calc']} ORDER BY calc_id""")]
        out["revisions"] = [tuple(r) for r in q(
            f"SELECT record_type, record_id, revision_no, action FROM {T['revision']} ORDER BY acted_at, record_type")]
        out["op_log"] = [tuple(r) for r in q(f"SELECT outcome, duration_ms FROM {T['op_log']} ORDER BY logged_at")]
        print("calcs:", out["calcs"])

        # Timing: definition + one PI SQL edit, then the page's refresh reads.
        rev, crev, times = 2, 1, []
        for i in range(N):
            t0 = time.perf_counter()
            r = repo.save_metric(str(uuid.uuid4()), "LIVECHECK", {"id": mid, "expected_revision": rev,
                                 "fields": fields(desc=f"timed {i}")}, [calc(9000002, crev, f"SELECT {i}", "monthly")])
            t1 = time.perf_counter()
            q(f"SELECT * FROM {T['metric']} WHERE metric_id = ?", [mid])
            q(f"SELECT * FROM {T['metric_calc']} WHERE metric_id = ? AND status = 'active' ORDER BY calc_id", [mid])
            q(f"SELECT metric_id, full_name, status, updated_at FROM {T['metric']} ORDER BY updated_at DESC LIMIT 200")
            t2 = time.perf_counter()
            assert r["outcome"] == "committed", r
            rev, crev = rev + 1, crev + 1
            times.append(((t1 - t0) * 1000, (t2 - t1) * 1000))
        save_ms, refresh_ms = [t[0] for t in times], [t[1] for t in times]
        logged = [r[0] for r in q(f"""SELECT duration_ms FROM {T['op_log']}
                                      WHERE outcome = 'committed' ORDER BY logged_at DESC LIMIT {N}""")]
        out["timing"] = {"n": N, "save_p50": statistics.median(save_ms), "save_max": max(save_ms),
                         "refresh_p50": statistics.median(refresh_ms), "op_log_duration_p50": statistics.median(logged)}
        print("timing:", out["timing"])
    finally:
        try:
            if created:
                for t in T.values():
                    q(f"DROP TABLE IF EXISTS {t}")
                out["dropped"] = True
        finally:
            out["steps"] = steps
            with open(OUT, "w") as fh:
                json.dump(out, fh, indent=1, default=str)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
