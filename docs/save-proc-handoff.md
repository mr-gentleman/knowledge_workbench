# Handoff — create the metric save procedure (DEC-020, DEC-021, PLAT-09)

For #chris / CoCo. Branch `claude/save-proc`. Nothing here has been run, and **#chris approves
before any of it is applied.** Order matters: **create the procedure before deploying this
branch** — every save in the new app code (including the frozen Streamlit form) calls it, so a
deploy without it makes all saves fail.

## 1. Create it (role: ACCOUNTADMIN)

Paste `sql/004_save_metric_proc.sql` whole. It creates
`AI_PLATFORM.WORKBENCH.save_metric(VARCHAR)` and transfers ownership to `WORKBENCH_APP`.
`CREATE OR REPLACE` resets ownership, so after **any** later change re-run the whole file.

If it fails to compile, the likeliest spots (not verifiable locally): binding the `v_calcs` ARRAY
variable into `TABLE(FLATTEN(input => :v_calcs))`, the `lost_race` custom exception, and the
same-SELECT alias reuse (`same_sql` inside `same_content`). Send the error back; don't patch blind.

## 2. Check the owner and that the app role is still read-only outside WORKBENCH

```sql
DESCRIBE PROCEDURE AI_PLATFORM.WORKBENCH.save_metric(VARCHAR);   -- EXECUTE AS OWNER
SHOW GRANTS ON PROCEDURE AI_PLATFORM.WORKBENCH.save_metric(VARCHAR);
-- expect: OWNERSHIP → WORKBENCH_APP, nothing else

SHOW GRANTS TO ROLE WORKBENCH_APP;
-- expect: INSERT/UPDATE only on AI_PLATFORM.WORKBENCH tables; on DICTIONARY, SELECT/USAGE only
```

Checked 2026-10-23 before this change (ACCOUNT_USAGE.GRANTS_TO_ROLES): WORKBENCH_APP's only
non-read privileges are INSERT/UPDATE on WORKBENCH tables, INSERT on revision, and CREATE
STREAMLIT/STAGE on WORKBENCH.

## 3. Optional smoke test before deploying (writes permanent test rows)

Rows are never deleted (no DELETE grant). Skip this if you'd rather test through the app.

```sql
-- a) create a candidate with one PI (reserve the PI id first)
SELECT AI_PLATFORM.WORKBENCH.seq_calc_id.NEXTVAL;   -- → <P1>
CALL AI_PLATFORM.WORKBENCH.save_metric('{"op_id":"smoke-1","actor":"CLENZINI","lock_wait_ms":0,
  "schema_version":2,"check_name":"zz save-proc smoke",
  "candidate":{"id":null,"create_token":"smoke-tok-1","fields":{"full_name":"ZZ save-proc smoke"}},
  "calcs":[{"calc_id":<P1>,"expected_revision":null,"retire":false,"is_default":true,
            "fields":{"sql_text":"SELECT 1","disambig":null}}]}');
-- expect: outcome committed, candidate_id <N>, new_calcs [<P1>], checks_due [<P1>]

-- b) same request again → outcome replayed, nothing written
-- c) no-op: candidate id <N>, expected_revision 1, same fields, calcs [] → outcome no_change
-- d) edit the PI with a stale revision (expected_revision 0) → outcome conflict, nothing written
-- e) retire it: {"calc_id":<P1>,"expected_revision":1,"retire":true,"fields":{"sql_text":"SELECT 1"}}
--    → committed, changed_calcs [<P1>]

SELECT op_id, outcome, record_id, duration_ms, error FROM AI_PLATFORM.WORKBENCH.op_log
WHERE op_id LIKE 'smoke-%' ORDER BY logged_at;
SELECT record_type, record_id, revision_no, action, snapshot:STATUS
FROM AI_PLATFORM.WORKBENCH.revision
WHERE (record_type, record_id) IN (('metric_candidate', '<N>'), ('metric_calc', '<P1>'))
ORDER BY record_type, revision_no;
-- expect: candidate rev 1 create; calc rev 1 create, rev 2 retire 'retired'; no rows for b–d
```

## 4. Deploy and measure (#chris)

`scripts/deploy.sh` from this branch, then in the app: create a candidate, edit it, force a
conflict (two tabs). Then:

```sql
SELECT op, outcome, lock_wait_ms, duration_ms, logged_at
FROM AI_PLATFORM.WORKBENCH.op_log ORDER BY logged_at DESC LIMIT 5;

-- the CALL's own elapsed time (compare with 2026-10-23's ~2.4 s write path)
SELECT start_time, total_elapsed_time, compilation_time, execution_time, query_tag
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE role_name = 'WORKBENCH_APP' AND query_text ILIKE 'CALL AI_PLATFORM.WORKBENCH.save_metric%'
  AND start_time > DATEADD(hour, -3, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
-- query_tag non-empty = statement-level QUERY_TAG works on a CALL (unverified so far)
```

Record the numbers on PLAT-09 in docs/features.md and a Releases row in docs/changelog.md.

## Rollback

Redeploy the previous app commit. The procedure can stay; nothing else calls it.
