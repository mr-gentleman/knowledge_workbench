-- 011 — Nightly copy of the Workbench tables into standard tables (DEC-025, PLAT-06).
-- Run by CoCo as ACCOUNTADMIN, after 010. Re-runnable. Names fully qualified (AGENTS.md).
--
-- Hybrid tables have no Fail-safe, UNDROP or clone. A standard-table copy has all three, and its
-- Time Travel keeps earlier nights: SELECT … AT(OFFSET => -86400 * n) reads the copy as of n days ago.
-- Worst case = the edits since the last copy (~1 day). revision holds full snapshots, so its copy alone
-- can rebuild every record's latest state.
-- Isolation: WORKBENCH_APP gets nothing here; the app can't write or drop its own backup.

CREATE SCHEMA IF NOT EXISTS AI_PLATFORM.WORKBENCH_BACKUP
  COMMENT = 'Nightly standard-table copy of AI_PLATFORM.WORKBENCH (sql/011). Not served.';
-- 30 days needs Enterprise edition; on Standard edition this fails, so use 1 (Fail-safe adds 7 days).
ALTER SCHEMA AI_PLATFORM.WORKBENCH_BACKUP SET DATA_RETENTION_TIME_IN_DAYS = 30;

-- Same columns as the source, standard table type (a CTAS from a hybrid table creates a standard one,
-- checked 2026-10-23). A column added to a source table later must be added here too, or the copy
-- fails loudly (TASK_HISTORY shows it; check in the handoff).
CREATE TABLE IF NOT EXISTS AI_PLATFORM.WORKBENCH_BACKUP.metric          AS SELECT * FROM AI_PLATFORM.WORKBENCH.metric          WHERE FALSE;
CREATE TABLE IF NOT EXISTS AI_PLATFORM.WORKBENCH_BACKUP.metric_calc     AS SELECT * FROM AI_PLATFORM.WORKBENCH.metric_calc     WHERE FALSE;
CREATE TABLE IF NOT EXISTS AI_PLATFORM.WORKBENCH_BACKUP.revision        AS SELECT * FROM AI_PLATFORM.WORKBENCH.revision        WHERE FALSE;
CREATE TABLE IF NOT EXISTS AI_PLATFORM.WORKBENCH_BACKUP.op_log          AS SELECT * FROM AI_PLATFORM.WORKBENCH.op_log          WHERE FALSE;
CREATE TABLE IF NOT EXISTS AI_PLATFORM.WORKBENCH_BACKUP.fact_table_core AS SELECT * FROM AI_PLATFORM.WORKBENCH.fact_table_core WHERE FALSE;
CREATE TABLE IF NOT EXISTS AI_PLATFORM.WORKBENCH_BACKUP.legacy_id_map   AS SELECT * FROM AI_PLATFORM.WORKBENCH.legacy_id_map   WHERE FALSE;

-- One transaction: the copy is all of one night or none of it. Full copies, not increments: the
-- tables are KB–MB, so this costs seconds of BIZ_AI_WH and stays trivially correct.
CREATE OR REPLACE TASK AI_PLATFORM.WORKBENCH_BACKUP.nightly_copy
  WAREHOUSE = BIZ_AI_WH
  SCHEDULE = 'USING CRON 0 3 * * * America/Chicago'
  COMMENT = 'sql/011: copy AI_PLATFORM.WORKBENCH into WORKBENCH_BACKUP (standard tables)'
AS
BEGIN
    BEGIN TRANSACTION;
    DELETE FROM AI_PLATFORM.WORKBENCH_BACKUP.metric;
    INSERT INTO AI_PLATFORM.WORKBENCH_BACKUP.metric          SELECT * FROM AI_PLATFORM.WORKBENCH.metric;
    DELETE FROM AI_PLATFORM.WORKBENCH_BACKUP.metric_calc;
    INSERT INTO AI_PLATFORM.WORKBENCH_BACKUP.metric_calc     SELECT * FROM AI_PLATFORM.WORKBENCH.metric_calc;
    DELETE FROM AI_PLATFORM.WORKBENCH_BACKUP.revision;
    INSERT INTO AI_PLATFORM.WORKBENCH_BACKUP.revision        SELECT * FROM AI_PLATFORM.WORKBENCH.revision;
    DELETE FROM AI_PLATFORM.WORKBENCH_BACKUP.op_log;
    INSERT INTO AI_PLATFORM.WORKBENCH_BACKUP.op_log          SELECT * FROM AI_PLATFORM.WORKBENCH.op_log;
    DELETE FROM AI_PLATFORM.WORKBENCH_BACKUP.fact_table_core;
    INSERT INTO AI_PLATFORM.WORKBENCH_BACKUP.fact_table_core SELECT * FROM AI_PLATFORM.WORKBENCH.fact_table_core;
    DELETE FROM AI_PLATFORM.WORKBENCH_BACKUP.legacy_id_map;
    INSERT INTO AI_PLATFORM.WORKBENCH_BACKUP.legacy_id_map   SELECT * FROM AI_PLATFORM.WORKBENCH.legacy_id_map;
    COMMIT;
END;

ALTER TASK AI_PLATFORM.WORKBENCH_BACKUP.nightly_copy RESUME;

-- ── Verify ─────────────────────────────────────────────────────────────────
-- EXECUTE TASK AI_PLATFORM.WORKBENCH_BACKUP.nightly_copy;   -- first copy now; then the drill in the handoff
-- SELECT name, state, error_message, completed_time
-- FROM TABLE(AI_PLATFORM.INFORMATION_SCHEMA.TASK_HISTORY(TASK_NAME => 'NIGHTLY_COPY')) ORDER BY scheduled_time DESC LIMIT 5;
