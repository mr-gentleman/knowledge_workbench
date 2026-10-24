# Handoff — fact-table save procedure + registry seed (UX-04)

For #chris / CoCo on Opus. Branch `claude/fact-tables`. Nothing here has been run; **#chris approves
before any of it is applied.** No new tables or columns: `AI_PLATFORM.WORKBENCH.fact_table_core`
(sql/001) already has every field the screen edits.

Until step 1 is done, the Fact tables screen reads fine but every Save fails. Until step 3 is done,
the registry is empty (`GET /api/fact-tables` returns `[]`).

## 1. Create the procedure (role: ACCOUNTADMIN)

Paste `sql/005_save_fact_table_proc.sql` whole. It creates
`AI_PLATFORM.WORKBENCH.save_fact_table(VARCHAR)` (EXECUTE AS OWNER) and transfers ownership to
`WORKBENCH_APP`. Same shape as `save_metric` (sql/004), which compiled fine.

Likeliest compile trouble (not verifiable locally): `FROM (SELECT :f AS j) r` binding a VARIANT
variable, `UPDATE … FROM` a one-row subquery, and `BOOLOR_AGG` into a BOOLEAN variable. Send the
error back; don't patch blind.

## 2. Check

```sql
SHOW GRANTS ON PROCEDURE AI_PLATFORM.WORKBENCH.save_fact_table(VARCHAR);  -- OWNERSHIP → WORKBENCH_APP only
SHOW GRANTS TO ROLE WORKBENCH_APP;  -- still no INSERT/UPDATE outside AI_PLATFORM.WORKBENCH
```

Optional smoke test (leaves a permanent row in `fact_table_core` and `revision`; schema is still
disposable before the first real import):

```sql
CALL AI_PLATFORM.WORKBENCH.save_fact_table('{"op_id":"ft-smoke-1","actor":"CLENZINI","lock_wait_ms":0,"schema_version":2,
  "table":{"table_name":"AC.SMOKE.FACT_TABLE_TEST","expected_revision":null,"fields":{"grain":"one row per test","status":"active"}}}');
-- → {"outcome":"committed","revision_no":1,...}
CALL AI_PLATFORM.WORKBENCH.save_fact_table('{"op_id":"ft-smoke-1","actor":"CLENZINI","lock_wait_ms":0,"schema_version":2,
  "table":{"table_name":"AC.SMOKE.FACT_TABLE_TEST","expected_revision":null,"fields":{"grain":"one row per test","status":"active"}}}');
-- → replayed
CALL AI_PLATFORM.WORKBENCH.save_fact_table('{"op_id":"ft-smoke-2","actor":"CLENZINI","lock_wait_ms":0,"schema_version":2,
  "table":{"table_name":"AC.SMOKE.FACT_TABLE_TEST","expected_revision":1,"fields":{"grain":"one row per test","status":"retired"}}}');
-- → committed, revision_no 2; revision row action = 'retire'
CALL AI_PLATFORM.WORKBENCH.save_fact_table('{"op_id":"ft-smoke-3","actor":"CLENZINI","lock_wait_ms":0,"schema_version":2,
  "table":{"table_name":"AC.SMOKE.FACT_TABLE_TEST","expected_revision":1,"fields":{"grain":"x","status":"active"}}}');
-- → conflict (stale revision), nothing written
SELECT op_id, outcome FROM AI_PLATFORM.WORKBENCH.op_log WHERE op = 'fact_table.save' ORDER BY logged_at;
```

## 3. Seed the registry from DICTIONARY (role: WORKBENCH_APP)

Paste `sql/006_seed_fact_tables.sql`. Copies the 61 legacy tables (names, plus grain / time field /
required filter for the 6 that have them; `TBD…` notes become NULL) with a revision-1 `import`
snapshot each. Re-runnable: skips names already registered. Verify queries are at the bottom.
**Decide first:** seed now, or wait for the legacy import (step 6 of the sprint)? The seed is the
"controlled seed" docs/features.md asks for before promotion testing.
