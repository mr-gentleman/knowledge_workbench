# Handoff for CoCo — read-only SQL check and save-proc update (sql/007, sql/008; DEC-022, DEC-023)

For: #chris → CoCo on Opus. Role: ACCOUNTADMIN. Branch: claude/implementations.

1. Run `sql/007_sql_check.sql` as is. It creates role `WORKBENCH_SQLCHECK` (USAGE + SELECT on database
   `AC` only), the procedure `AI_PLATFORM.WORKBENCH.run_check(VARCHAR, NUMBER)` owned by that role, and
   grants `WORKBENCH_APP` USAGE on the procedure. Nothing else changes.
2. Run the verify block at the bottom of the file and paste the results back:
   - `SHOW GRANTS TO ROLE WORKBENCH_SQLCHECK;` shows only USAGE/SELECT
     (plus ownership of run_check).
   - `SHOW GRANTS TO ROLE WORKBENCH_APP;` shows no privileges on `AC`, and USAGE on run_check.
   - As WORKBENCH_APP: `SELECT 1` returns a row; `DELETE …` and the `; DROP …` injection return one
     `KW_CHECK_FAILED` row; reading `AI_PLATFORM.WORKBENCH.metric_calc` returns `KW_CHECK_FAILED`.
3. Then run `sql/008_save_metric_keep_check.sql` (replaces `save_metric`; CREATE OR REPLACE resets
   ownership, and the file re-grants it to WORKBENCH_APP). Run its verify block: the owner is
   WORKBENCH_APP, and the default-count query returns no rows.
4. Also confirm one thing the app assumes: with `ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 5`,
   `CALL AI_PLATFORM.WORKBENCH.run_check('SELECT SYSTEM$WAIT(10)', 100);` is cancelled after ~5 s, and
   note the error code (the app treats 604 and 630 as a timeout).
