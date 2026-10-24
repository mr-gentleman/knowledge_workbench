# Hybrid tables for the Workbench save — benchmark

#claude 2026-10-23 · branch `claude/spcs-spike` · script [bench/hybrid_bench.py](bench/hybrid_bench.py), summary [bench/summarize.py](bench/summarize.py), raw data [bench/results-2026-10-23.json](bench/results-2026-10-23.json)

**Evidence kind:** local run against Snowflake from Chris's laptop, session `5296369439966987`, role WORKBENCH_APP, warehouse BIZ_AI_WH. All 434 statements matched in `QUERY_HISTORY_BY_SESSION`. No run from inside SPCS; SPCS numbers below are estimates.

## Verdict

**Hybrid tables cut the save from ~2.7 s to ~1.0 s from a laptop. Server time is ~0.5 s, so a save from SPCS should land well under 1 s (estimate, unverified).** The win is all in DML and COMMIT: each statement drops from 330–610 ms to 70–150 ms server time.

**Recommendation: migrate, but only with a backup plan in the same migration.** Hybrid tables have no Fail-safe, no UNDROP, Time Travel `AT TIMESTAMP` only, no schema-level clone and no replication. Backup and retention for WORKBENCH is on the V1 checklist, so those gaps count against hybrid tables. The smallest fix is a scheduled copy of the hybrid tables into standard tables (see Gotchas). If Chris won't take that on, stay on standard tables and rely on the optimistic save display; the save then stays at ~2.7 s.

## Method

Scratch tables `AI_PLATFORM.WORKBENCH.zz_bench_{std,hyb}_{candidate,revision,op_log}`, same columns as `metric_candidate` (001 + 003 `create_token`), `revision` and `op_log`. Seeded with 1,000 candidates (~1.5 KB descriptions) and 5,000 revisions. All six were dropped at the end. A one-off grant made this possible: CoCo granted `CREATE TABLE, CREATE HYBRID TABLE` on the schema to WORKBENCH_APP. **Revoke it.**

One save: `BEGIN` → `UPDATE … SET …, revision_no = revision_no + 1 WHERE candidate_id = ? AND revision_no = ?` (rowcount must be 1) → `INSERT revision … SELECT …, OBJECT_CONSTRUCT_KEEP_NULL(*) FROM candidate WHERE candidate_id = ?` (~2 KB snapshot) → `INSERT op_log` → `COMMIT`. Python `snowflake-connector-python` 3.11, `qmark`, one connection. 30 rounds interleaved A, B, C, after one warm-up each.

- **A:** standard tables.
- **B:** hybrid tables, with PKs `candidate_id`; `(record_type, record_id, revision_no)`; `op_id`.
- **C:** B with revision and op_log written in one `INSERT ALL`. Works on hybrid tables.

## Results

Click-to-commit, client wall time (laptop → Snowflake; `SELECT 1` round trip p50 131 ms):

| Variant | p50 | p95 | max | after 75 s idle |
|---|---|---|---|---|
| A standard | 2659 ms | 3317 | 3365 | 2838 |
| B hybrid | **1005 ms** | 1237 | 1365 | 1628 |
| C hybrid + INSERT ALL | **900 ms** | 1395 | 1404 | 1006 |

Per statement, warm p50: client ms | server `total_elapsed_time` (compile / exec):

| Statement | A standard | B hybrid | C hybrid |
|---|---|---|---|
| BEGIN | 180 \| 86 (50/34) | 182 \| 86 | 179 \| 87 |
| UPDATE | 592 \| 448 (150/292) | 202 \| 114 (58/52) | 217 \| 114 |
| INSERT revision | 603 \| 460 (206/256) | 188 \| 95 (63/31) | — |
| INSERT op_log | 432 \| 326 (120/204) | 164 \| 68 (53/13) | — |
| INSERT ALL | — | — | 203 \| 102 (71/29) |
| COMMIT | 757 \| 610 (42/568) | 248 \| 152 (42/110) | 253 \| 154 |
| **Server sum** | **1930** | **515** | **457** |

- **Where the remaining time goes:** ~90–100 ms per statement is the laptop round trip (client minus server). Inside SPCS that round trip should be tens of ms, so B is roughly 0.55–0.65 s and C roughly 0.5 s (estimate). Dropping the explicit `BEGIN` (connector `autocommit=False`) would save one more round trip; untested.
- **Stale revision:** `UPDATE … AND revision_no = 0` affected **0 rows** on both standard and hybrid tables, followed by a ROLLBACK. Optimistic concurrency works unchanged.
- **The "cold" column isn't a cold warehouse:** BIZ_AI_WH was still `STARTED` before every idle save (it is shared, or suspends later than 60 s). Only the session was idle. A warehouse resume would add its own ~1–2 s to either table type; not measured.
- **The 1.6 s idle save on B is one sample:** its COMMIT took 543 ms on the server, against ~150 ms warm. One sample, so treat it as noise until repeated.

## Gotchas that matter for us

From Snowflake docs ([limitations](https://docs.snowflake.com/en/user-guide/tables-hybrid-limitations), [cloning](https://docs.snowflake.com/en/user-guide/tables-hybrid-clone), [cost](https://docs.snowflake.com/en/user-guide/tables-hybrid-cost)), read 2026-10-23. Only what the benchmark exercised is verified live.

**Backup and retention, compared with standard tables (V1 checklist):**

| Feature | Standard table | Hybrid table |
|---|---|---|
| Time Travel | AT/BEFORE with TIMESTAMP, OFFSET or STATEMENT | `AT(TIMESTAMP => …)` only, with the same timestamp across the database. No BEFORE, OFFSET or STATEMENT |
| UNDROP TABLE | yes | **no**. UNDROP SCHEMA/DATABASE "succeeds" but the hybrid tables are not restored |
| Fail-safe | 7 days | **none** |
| Clone | table, schema, database | **database level only**. A schema clone of WORKBENCH needs `IGNORE HYBRID TABLES`, which skips exactly these tables. Table clone fails (391411) |
| Replication | yes | **no** |

Mitigation (untested): a scheduled task that copies the three hybrid tables nightly into standard tables in a backup schema. That restores UNDROP, Fail-safe and clone for the copy, at up to a day of lost edits. `revision` already holds full snapshots, so the copy of `revision` is the important one.

**Schema and migration:**
- **Primary keys are enforced, and the key column types are restricted.** VARIANT and TIMESTAMP_TZ can't be key columns; neither appears in our keys. A good side effect: a duplicate revision now fails instead of silently landing twice. Our PKs matched the declared ones; all created without error (verified).
- **op_log needs a different key.** The `save_metric` replay path (`sql/004`) writes a second `replayed` row with the same `op_id`, so `PRIMARY KEY (op_id)` would make every replay fail. Add a surrogate key (e.g. `log_id` UUID), or key on `(op_id, outcome)`.
- **The real save also writes `metric_calc`.** `save_metric` updates PIs and their revisions too. Make `metric_calc` hybrid as well, or every save touching a PI keeps a ~450 ms standard-table UPDATE plus a slower COMMIT. Mixing table types in one transaction is allowed.
- **Changing type means building new tables.** You can't ALTER a table into a hybrid one: `CREATE HYBRID TABLE … AS SELECT`, then rename or swap. Grants and future grants must be re-checked. The new `sql/` migration has to be run by ACCOUNTADMIN or the table owner.
- **Results cache:** queries against hybrid tables never hit it. That doesn't matter for the save; list and search queries would recompute each time. Not measured.

**Cost:** warehouse compute is the same as for standard tables. Row-store storage is priced higher than standard storage (Service Consumption Table 3(b)). At our size (KB–MB) it's negligible. Time Travel data is billed at the standard rate. 2 TB row-store quota per database.

**Cross-session read lag:** reads in the same session always see that session's writes. Another session may read data up to <100 ms stale, unless it sets `READ_LATEST_WRITES = TRUE` (a few ms more per query). The app shares one connection (DEC-007), so after its own save it reads its own writes. A second app instance or the Oracle could briefly see the previous revision. Not tested: it would have needed a second login.

## If Chris says migrate

1. One new `sql/00N_hybrid_tables.sql`: hybrid `metric_candidate`, `metric_calc`, `revision`, and `op_log` with a surrogate key. Copy, rename, re-grant, then a backup task into standard tables.
2. Measure a save from the SPCS app (`op_log.duration_ms`) to confirm < 1 s.
3. Revoke the bench grant: `REVOKE CREATE TABLE, CREATE HYBRID TABLE ON SCHEMA AI_PLATFORM.WORKBENCH FROM ROLE WORKBENCH_APP;`
