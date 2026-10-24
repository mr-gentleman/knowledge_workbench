# Handoff — move the Workbench write tables to hybrid tables (DEC-025, PLAT-10, PLAT-06)

For CoCo on Opus, from #claude 2026-10-23. Branch `claude/hybrid-tables` (built on `claude/unified-metric`).
Every name below is fully qualified; never rely on `USE`.

**What it does:** saves get ~3–5× faster. The save moves from the `save_metric` procedure back into one
Python transaction, on hybrid tables (`metric`, `metric_calc`, `revision`, `op_log`, `fact_table_core`).
A nightly copy into standard tables gives back the Fail-safe, UNDROP and clone that hybrid tables lack.

**Evidence so far** (local runs from Chris's laptop against Snowflake; nothing from SPCS yet):
- Benchmark, 15 rounds ([HYBRID_BENCH.md](spikes/spcs/HYBRID_BENCH.md), second run). Save with one implementation (PI) edit:
  - procedure on standard tables: 4.7 s (the live app measures 4.0–4.7 s);
  - procedure on hybrid tables: 2.8 s;
  - Python on hybrid tables: **1.5 s from the laptop, 0.8 s Snowflake server time, est. ~0.6 s from SPCS**.
- The real `repositories.save_metric` ran against scratch hybrid tables ([save_live_check.py](spikes/spcs/bench/save_live_check.py)):
  create, replay, edit + new PI, label-only edit keeps its check, stale → conflict, no-op, retire moves the
  default. All as specified. 20 timed saves: p50 1.45 s from the laptop, plus 0.42 s of refresh reads.
- `010` and its rollback rehearsed on scratch copies of the live rows ([rehearse_010.py](spikes/spcs/bench/rehearse_010.py)):
  78 revisions, 17 op_log rows and 61 fact tables made the round trip. Kinds, indexes and unique `log_id`s checked.
- **Not rehearsed:** `011` (needs CREATE SCHEMA / CREATE TASK), and grants as ACCOUNTADMIN.

## Order

| # | Step | Role | Notes |
|---|---|---|---|
| 0 | `sql/007`, `sql/008`, `sql/009` if not yet applied | ACCOUNTADMIN | As their own handoffs say. 009 must run before 010. |
| 1 | Suspend the app: `ALTER SERVICE AI_PLATFORM.WORKBENCH.KW_SPIKE SUSPEND;` | WORKBENCH_APP (owner) | No writes during the copy. |
| 2 | Pre-checks (below) | ACCOUNTADMIN | Write the numbers down. |
| 3 | `sql/010_hybrid_tables.sql` up to "Swap into place" | ACCOUNTADMIN | Creates `*_hyb010`, copies rows. |
| 4 | Compare counts `*_hyb010` vs originals (below) | ACCOUNTADMIN | Stop if any differ: drop the `*_hyb010` tables, nothing else has changed. |
| 5 | Rest of `sql/010` (swap, grants, revokes) | ACCOUNTADMIN | |
| 6 | `sql/011_nightly_backup.sql`, then `EXECUTE TASK AI_PLATFORM.WORKBENCH_BACKUP.nightly_copy;` | ACCOUNTADMIN | If `DATA_RETENTION_TIME_IN_DAYS = 30` fails (edition), set it to 1 and re-run the file. |
| 7 | Post-checks (below) | ACCOUNTADMIN | |
| 8 | #claude deploys this branch's image (`deploy/deploy.sh`), resumes the service | WORKBENCH_APP | The Python save, plus LOCK_TIMEOUT 5 s on the app connection. |
| 9 | Test save + timing (below) | Chris in the app; CoCo reads `op_log` | Acceptance: save < 1 s server side. |
| 10 | Restore drill (below) | ACCOUNTADMIN | Once, now. That's what makes PLAT-06 done. |
| 11 | Cleanup, after acceptance (below) | ACCOUNTADMIN | |

## Pre-checks (step 2)

```sql
SELECT 'metric' t, COUNT(*) n, MAX(metric_id) max_id FROM AI_PLATFORM.WORKBENCH.metric
UNION ALL SELECT 'metric_calc', COUNT(*), MAX(calc_id) FROM AI_PLATFORM.WORKBENCH.metric_calc
UNION ALL SELECT 'revision', COUNT(*), NULL FROM AI_PLATFORM.WORKBENCH.revision
UNION ALL SELECT 'op_log', COUNT(*), NULL FROM AI_PLATFORM.WORKBENCH.op_log
UNION ALL SELECT 'fact_table_core', COUNT(*), NULL FROM AI_PLATFORM.WORKBENCH.fact_table_core;
-- Duplicate keys would make the hybrid INSERT fail; all must return 0 rows:
SELECT record_type, record_id, revision_no FROM AI_PLATFORM.WORKBENCH.revision GROUP BY 1, 2, 3 HAVING COUNT(*) > 1;
SELECT metric_id FROM AI_PLATFORM.WORKBENCH.metric GROUP BY 1 HAVING COUNT(*) > 1;
SELECT calc_id FROM AI_PLATFORM.WORKBENCH.metric_calc GROUP BY 1 HAVING COUNT(*) > 1;
SELECT table_name_full FROM AI_PLATFORM.WORKBENCH.fact_table_core GROUP BY 1 HAVING COUNT(*) > 1;
SHOW GRANTS ON TABLE AI_PLATFORM.WORKBENCH.revision;   -- keep for comparison
```

## Copy check (step 4)

```sql
SELECT (SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH.metric)          = (SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH.metric_hyb010)
   AND (SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH.metric_calc)     = (SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH.metric_calc_hyb010)
   AND (SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH.revision)        = (SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH.revision_hyb010)
   AND (SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH.op_log)          = (SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH.op_log_hyb010)
   AND (SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH.fact_table_core) = (SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH.fact_table_core_hyb010) AS all_equal;   -- TRUE
```

## Post-checks (step 7)

```sql
SHOW HYBRID TABLES IN SCHEMA AI_PLATFORM.WORKBENCH;     -- METRIC, METRIC_CALC, REVISION, OP_LOG, FACT_TABLE_CORE
SHOW INDEXES IN SCHEMA AI_PLATFORM.WORKBENCH;           -- IX_METRIC_CREATE_TOKEN, IX_METRIC_CALC_METRIC_ID, IX_OP_LOG_OP_ID
-- Same counts and max IDs as the pre-check:
SELECT 'metric' t, COUNT(*) n, MAX(metric_id) max_id FROM AI_PLATFORM.WORKBENCH.metric
UNION ALL SELECT 'metric_calc', COUNT(*), MAX(calc_id) FROM AI_PLATFORM.WORKBENCH.metric_calc
UNION ALL SELECT 'revision', COUNT(*), NULL FROM AI_PLATFORM.WORKBENCH.revision
UNION ALL SELECT 'op_log', COUNT(*), NULL FROM AI_PLATFORM.WORKBENCH.op_log
UNION ALL SELECT 'fact_table_core', COUNT(*), NULL FROM AI_PLATFORM.WORKBENCH.fact_table_core;
-- Sequences are untouched and ahead of every ID (each NEXTVAL leaves a gap, which is fine):
SELECT AI_PLATFORM.WORKBENCH.seq_metric_id.NEXTVAL, AI_PLATFORM.WORKBENCH.seq_calc_id.NEXTVAL;   -- > the max IDs above
SHOW GRANTS ON TABLE AI_PLATFORM.WORKBENCH.revision;    -- WORKBENCH_APP SELECT/INSERT/UPDATE; CORTEX_CODE_ROLE, DATAENG, DATAENG_RO SELECT; no DELETE
SHOW FUTURE GRANTS IN SCHEMA AI_PLATFORM.WORKBENCH;     -- unchanged from 002
SHOW GRANTS TO ROLE WORKBENCH_APP;                      -- nothing on AI_PLATFORM.WORKBENCH_BACKUP; no INSERT/UPDATE on DICTIONARY
-- First backup landed:
SELECT name, state, error_message FROM TABLE(AI_PLATFORM.INFORMATION_SCHEMA.TASK_HISTORY(TASK_NAME => 'NIGHTLY_COPY'))
ORDER BY scheduled_time DESC LIMIT 3;                   -- SUCCEEDED
SELECT (SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH_BACKUP.revision) = (SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH.revision);  -- TRUE
```

## Test save and timing (step 9)

Chris edits one metric's description and one PI's SQL in the app, saves, then reloads the page. Then:

```sql
SELECT op_id, outcome, lock_wait_ms, duration_ms, logged_at
FROM AI_PLATFORM.WORKBENCH.op_log ORDER BY logged_at DESC LIMIT 5;     -- committed; duration_ms well under 1000
SELECT record_type, record_id, revision_no, action, actor
FROM AI_PLATFORM.WORKBENCH.revision ORDER BY acted_at DESC LIMIT 5;    -- one 'metric' and one 'metric_calc' row; actor = Chris
```

`op_log.duration_ms` covers lock wait to just before the history + COMMIT statements (~150–250 ms more on
hybrid tables). The app log line `op … metric.save … total=…ms` has the full save time. For the whole
statement chain, use `QUERY_HISTORY_BY_SESSION` on the `QUERY_TAG` op_id. **Acceptance:** 5 saves, p50
total < 1 s. If it's slower than 2 s, roll back (below) and tell #claude.

## Restore drill (step 10)

A drill restores a scratch copy, never the live table:

```sql
-- 1. Yesterday's copy (or any night within retention):
SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH_BACKUP.revision AT(OFFSET => -60*5);   -- the copy as of 5 minutes ago
-- 2. Rebuild one table from the backup as a hybrid table, under a scratch name:
CREATE HYBRID TABLE AI_PLATFORM.WORKBENCH.zz_restore_revision (
    record_type VARCHAR NOT NULL, record_id VARCHAR NOT NULL, revision_no NUMBER NOT NULL,
    action VARCHAR NOT NULL, snapshot VARIANT NOT NULL, schema_version NUMBER NOT NULL DEFAULT 1,
    actor VARCHAR NOT NULL, acted_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(), change_note VARCHAR,
    PRIMARY KEY (record_type, record_id, revision_no));
INSERT INTO AI_PLATFORM.WORKBENCH.zz_restore_revision SELECT * FROM AI_PLATFORM.WORKBENCH_BACKUP.revision;
-- 3. Same rows as live (minus edits since the copy):
SELECT COUNT(*), MAX(acted_at) FROM AI_PLATFORM.WORKBENCH.zz_restore_revision;
SELECT COUNT(*), MAX(acted_at) FROM AI_PLATFORM.WORKBENCH.revision;
-- 4. The copy itself is protected: drop and undrop it.
DROP TABLE AI_PLATFORM.WORKBENCH_BACKUP.op_log;  UNDROP TABLE AI_PLATFORM.WORKBENCH_BACKUP.op_log;
DROP TABLE AI_PLATFORM.WORKBENCH.zz_restore_revision;
```

Record date, counts and who ran it on PLAT-06 in docs/features.md.

**A real restore** (data lost or damaged in a live table T):
1. Suspend the app.
2. `ALTER TABLE AI_PLATFORM.WORKBENCH.T RENAME TO AI_PLATFORM.WORKBENCH.T_damaged_<date>;`
3. Create T with its block from `sql/010`, using the name T instead of `T_hyb010`.
4. `INSERT INTO … SELECT … FROM AI_PLATFORM.WORKBENCH_BACKUP.T` (add `AT(TIMESTAMP => …)` for an earlier night). Then run 010's grants for T.
5. Re-apply the edits since that copy from `T_damaged_<date>` if it is readable. Otherwise `revision`'s snapshots show what was lost.
6. Resume the app.

## Rollback

`sql/rollback/010_hybrid_tables_down.sql` (ACCOUNTADMIN, app suspended). It builds standard tables with the
original DDL, copies the *current* rows (no edit is lost), swaps them in and re-grants. The hybrid tables
stay as `*_hyb_rolledback`. The Python save works on standard tables too, just at ~2–3 s, so no code
rollback is needed for speed alone. The nightly copy keeps working either way.

## Cleanup (step 11, after acceptance)

```sql
REVOKE CREATE TABLE, CREATE HYBRID TABLE ON SCHEMA AI_PLATFORM.WORKBENCH FROM ROLE WORKBENCH_APP;   -- the bench grant
DROP PROCEDURE IF EXISTS AI_PLATFORM.WORKBENCH.save_metric(VARCHAR);       -- superseded by the Python save (DEC-025)
DROP PROCEDURE IF EXISTS AI_PLATFORM.WORKBENCH.save_fact_table(VARCHAR);   -- likewise (PLAT-11)
-- After a week of normal use (they are standard tables, so UNDROP still works for the retention period):
DROP TABLE AI_PLATFORM.WORKBENCH.metric_std010;
DROP TABLE AI_PLATFORM.WORKBENCH.metric_calc_std010;
DROP TABLE AI_PLATFORM.WORKBENCH.revision_std010;
DROP TABLE AI_PLATFORM.WORKBENCH.op_log_std010;
DROP TABLE AI_PLATFORM.WORKBENCH.fact_table_core_std010;
```

`save_fact_table` moved to a Python transaction too (PLAT-11, #chris: one pattern for every user-saved
table), so after the deploy that ships it nothing calls either procedure.

## Known gaps

- **A crash mid-save** leaves a transaction open, and its row locks, until Snowflake aborts it. Per Astra,
  that's after 5 minutes for transactions on hybrid tables; not verified here. Meanwhile a save to the same
  rows fails after 5 s (`LOCK_TIMEOUT`) with "try again" instead of freezing the app. Other metrics save normally.
- **Reads from another session** (the Oracle, a second app instance) may lag a write by < 100 ms, unless
  that session sets `READ_LATEST_WRITES = TRUE`.
- **One real `seq_metric_id` value (100000)** was drawn by the live check on 2026-10-23, so the first real
  metric is 100001 or later. IDs never repeat; gaps are fine.
