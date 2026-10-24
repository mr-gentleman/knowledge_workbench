-- Rollback of 010: back to standard tables, keeping every row written since (DEC-025).
-- Run by CoCo as ACCOUNTADMIN with the app suspended; then deploy app code from before DEC-025 only if
-- the Python save itself is the problem (it works on standard tables too, just slower).
-- Not a migration: it lives outside the numbered sequence on purpose. Names fully qualified (AGENTS.md).
--
-- Same DDL as 001/003/009 (explicit, so defaults and NOT NULL survive; a CTAS would drop defaults the
-- save relies on), op_log keeps 010's log_id. Primary keys are informational again on standard tables.
-- Within the acceptance window, the _std010 tables are an older copy; this script copies the current
-- rows instead, so no edit made after the migration is lost.

-- ── metric (009) ───────────────────────────────────────────────────────────
CREATE TABLE AI_PLATFORM.WORKBENCH.metric_std_rb (
    metric_id           NUMBER        NOT NULL,
    full_name           VARCHAR       NOT NULL,
    description         VARCHAR,
    disambig            VARCHAR,
    department          VARCHAR,
    category            VARCHAR,
    source              VARCHAR       NOT NULL,
    status              VARCHAR       NOT NULL DEFAULT 'candidate',  -- candidate | canon | rejected | retired
    duplicate_of_metric_id NUMBER,
    superseded_by       NUMBER,
    create_token        VARCHAR,
    original_author     VARCHAR,
    revision_no         NUMBER        NOT NULL DEFAULT 1,
    created_by          VARCHAR       NOT NULL,
    created_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_by          VARCHAR       NOT NULL,
    updated_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (metric_id)
);
INSERT INTO AI_PLATFORM.WORKBENCH.metric_std_rb
      (metric_id, full_name, description, disambig, department, category, source, status,
       duplicate_of_metric_id, superseded_by, create_token, original_author, revision_no,
       created_by, created_at, updated_by, updated_at)
SELECT metric_id, full_name, description, disambig, department, category, source, status,
       duplicate_of_metric_id, superseded_by, create_token, original_author, revision_no,
       created_by, created_at, updated_by, updated_at
FROM AI_PLATFORM.WORKBENCH.metric;

-- ── metric_calc (009) ──────────────────────────────────────────────────────
CREATE TABLE AI_PLATFORM.WORKBENCH.metric_calc_std_rb (
    calc_id             NUMBER        NOT NULL,
    metric_id           NUMBER        NOT NULL,
    disambig            VARCHAR,
    source              VARCHAR       NOT NULL,
    sql_text            VARCHAR,
    source_table        VARCHAR,
    is_default          BOOLEAN       NOT NULL DEFAULT FALSE,
    status              VARCHAR       NOT NULL DEFAULT 'active',
    validated_revision_no NUMBER,
    validation_status   VARCHAR,
    validation_message  VARCHAR,
    validation_query_id VARCHAR,
    validated_at        TIMESTAMP_TZ,
    served_revision_no  NUMBER,
    original_author     VARCHAR,
    revision_no         NUMBER        NOT NULL DEFAULT 1,
    created_by          VARCHAR       NOT NULL,
    created_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_by          VARCHAR       NOT NULL,
    updated_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (calc_id)
);
INSERT INTO AI_PLATFORM.WORKBENCH.metric_calc_std_rb
      (calc_id, metric_id, disambig, source, sql_text, source_table, is_default, status,
       validated_revision_no, validation_status, validation_message, validation_query_id, validated_at,
       served_revision_no, original_author, revision_no, created_by, created_at, updated_by, updated_at)
SELECT calc_id, metric_id, disambig, source, sql_text, source_table, is_default, status,
       validated_revision_no, validation_status, validation_message, validation_query_id, validated_at,
       served_revision_no, original_author, revision_no, created_by, created_at, updated_by, updated_at
FROM AI_PLATFORM.WORKBENCH.metric_calc;

-- ── revision (001) ─────────────────────────────────────────────────────────
CREATE TABLE AI_PLATFORM.WORKBENCH.revision_std_rb (
    record_type         VARCHAR       NOT NULL,
    record_id           VARCHAR       NOT NULL,
    revision_no         NUMBER        NOT NULL,
    action              VARCHAR       NOT NULL,
    snapshot            VARIANT       NOT NULL,
    schema_version      NUMBER        NOT NULL DEFAULT 1,
    actor               VARCHAR       NOT NULL,
    acted_at            TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    change_note         VARCHAR,
    PRIMARY KEY (record_type, record_id, revision_no)
);
INSERT INTO AI_PLATFORM.WORKBENCH.revision_std_rb
      (record_type, record_id, revision_no, action, snapshot, schema_version, actor, acted_at, change_note)
SELECT record_type, record_id, revision_no, action, snapshot, schema_version, actor, acted_at, change_note
FROM AI_PLATFORM.WORKBENCH.revision;

-- ── op_log (keeps log_id: harmless on a standard table, and the rows keep their key) ───────────────────────────────────────────
CREATE TABLE AI_PLATFORM.WORKBENCH.op_log_std_rb (
    log_id              VARCHAR       NOT NULL DEFAULT UUID_STRING(),
    op_id               VARCHAR       NOT NULL,
    op                  VARCHAR       NOT NULL,
    actor               VARCHAR       NOT NULL,
    record_id           VARCHAR,
    outcome             VARCHAR       NOT NULL,
    lock_wait_ms        NUMBER        NOT NULL,
    duration_ms         NUMBER        NOT NULL,
    last_query_id       VARCHAR,
    error               VARCHAR,
    logged_at           TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (log_id)
);
INSERT INTO AI_PLATFORM.WORKBENCH.op_log_std_rb
      (log_id, op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id, error, logged_at)
SELECT log_id, op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id, error, logged_at
FROM AI_PLATFORM.WORKBENCH.op_log;

-- ── fact_table_core (001) ──────────────────────────────────────────────────
CREATE TABLE AI_PLATFORM.WORKBENCH.fact_table_core_std_rb (
    table_name_full     VARCHAR       NOT NULL,
    display_name        VARCHAR,
    description         VARCHAR,
    disambig            VARCHAR,
    gotchas             VARCHAR,
    required_filter     VARCHAR,
    grain               VARCHAR,
    primary_key         VARCHAR,
    time_dimension      VARCHAR,
    department          VARCHAR,
    source              VARCHAR       NOT NULL,
    status              VARCHAR       NOT NULL DEFAULT 'active',
    original_author     VARCHAR,
    revision_no         NUMBER        NOT NULL DEFAULT 1,
    created_by          VARCHAR       NOT NULL,
    created_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_by          VARCHAR       NOT NULL,
    updated_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (table_name_full)
);
INSERT INTO AI_PLATFORM.WORKBENCH.fact_table_core_std_rb
      (table_name_full, display_name, description, disambig, gotchas, required_filter, grain, primary_key,
       time_dimension, department, source, status, original_author, revision_no, created_by, created_at,
       updated_by, updated_at)
SELECT table_name_full, display_name, description, disambig, gotchas, required_filter, grain, primary_key,
       time_dimension, department, source, status, original_author, revision_no, created_by, created_at,
       updated_by, updated_at
FROM AI_PLATFORM.WORKBENCH.fact_table_core;

-- ── Swap into place ────────────────────────────────────────────────────────
-- After the check in docs/hybrid-migration-handoff.md (row counts equal). The hybrid tables stay as
-- _hyb_rolledback until someone decides to drop them.
ALTER TABLE AI_PLATFORM.WORKBENCH.metric RENAME TO AI_PLATFORM.WORKBENCH.metric_hyb_rolledback;
ALTER TABLE AI_PLATFORM.WORKBENCH.metric_std_rb RENAME TO AI_PLATFORM.WORKBENCH.metric;
ALTER TABLE AI_PLATFORM.WORKBENCH.metric_calc RENAME TO AI_PLATFORM.WORKBENCH.metric_calc_hyb_rolledback;
ALTER TABLE AI_PLATFORM.WORKBENCH.metric_calc_std_rb RENAME TO AI_PLATFORM.WORKBENCH.metric_calc;
ALTER TABLE AI_PLATFORM.WORKBENCH.revision RENAME TO AI_PLATFORM.WORKBENCH.revision_hyb_rolledback;
ALTER TABLE AI_PLATFORM.WORKBENCH.revision_std_rb RENAME TO AI_PLATFORM.WORKBENCH.revision;
ALTER TABLE AI_PLATFORM.WORKBENCH.op_log RENAME TO AI_PLATFORM.WORKBENCH.op_log_hyb_rolledback;
ALTER TABLE AI_PLATFORM.WORKBENCH.op_log_std_rb RENAME TO AI_PLATFORM.WORKBENCH.op_log;
ALTER TABLE AI_PLATFORM.WORKBENCH.fact_table_core RENAME TO AI_PLATFORM.WORKBENCH.fact_table_core_hyb_rolledback;
ALTER TABLE AI_PLATFORM.WORKBENCH.fact_table_core_std_rb RENAME TO AI_PLATFORM.WORKBENCH.fact_table_core;

-- ── Grants (002's FUTURE grants apply to the new tables; restated) ──────────
GRANT SELECT, INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.metric          TO ROLE WORKBENCH_APP;
GRANT SELECT, INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.metric_calc     TO ROLE WORKBENCH_APP;
GRANT SELECT, INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.revision        TO ROLE WORKBENCH_APP;
GRANT SELECT, INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.op_log          TO ROLE WORKBENCH_APP;
GRANT SELECT, INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.fact_table_core TO ROLE WORKBENCH_APP;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.metric          TO ROLE CORTEX_CODE_ROLE;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.metric_calc     TO ROLE CORTEX_CODE_ROLE;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.revision        TO ROLE CORTEX_CODE_ROLE;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.op_log          TO ROLE CORTEX_CODE_ROLE;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.fact_table_core TO ROLE CORTEX_CODE_ROLE;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.metric          TO ROLE DATAENG;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.metric_calc     TO ROLE DATAENG;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.revision        TO ROLE DATAENG;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.op_log          TO ROLE DATAENG;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.fact_table_core TO ROLE DATAENG;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.metric          TO ROLE DATAENG_RO;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.metric_calc     TO ROLE DATAENG_RO;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.revision        TO ROLE DATAENG_RO;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.op_log          TO ROLE DATAENG_RO;
GRANT SELECT ON TABLE AI_PLATFORM.WORKBENCH.fact_table_core TO ROLE DATAENG_RO;
REVOKE INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.metric_hyb_rolledback FROM ROLE WORKBENCH_APP;
REVOKE INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.metric_calc_hyb_rolledback FROM ROLE WORKBENCH_APP;
REVOKE INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.revision_hyb_rolledback FROM ROLE WORKBENCH_APP;
REVOKE INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.op_log_hyb_rolledback FROM ROLE WORKBENCH_APP;
REVOKE INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.fact_table_core_hyb_rolledback FROM ROLE WORKBENCH_APP;

-- ── Then ───────────────────────────────────────────────────────────────────
-- The nightly copy (011) reads the tables by name and keeps working; leave it on.
-- SHOW HYBRID TABLES IN SCHEMA AI_PLATFORM.WORKBENCH;   -- only the _hyb_rolledback tables
