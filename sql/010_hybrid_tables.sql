-- 010 — Write tables become hybrid tables (DEC-025): saves ~2.5–4 s → ~0.5 s (bench, HYBRID_BENCH.md).
-- Run by CoCo as ACCOUNTADMIN, AFTER 009, with the app suspended (docs/hybrid-migration-handoff.md).
-- Names are fully qualified on purpose: never rely on USE (AGENTS.md).
--
-- A table can't be ALTERed into a hybrid one, so each table is rebuilt: create the hybrid table
-- (explicit DDL: keys, indexes, defaults), copy the rows, rename the old one to <name>_std010, rename
-- the new one into place. The _std010 copies stay until the acceptance check passes (cleanup in the
-- handoff). Sequences are separate objects and are not touched: IDs continue, never reused.
--
-- What changes besides speed:
--   * Primary keys are enforced: a duplicate revision or a second row for a key now fails.
--   * op_log gets a surrogate key log_id: a replayed or conflicting save writes another row for the
--     same op_id, so op_id can't be the key. op_id gets an index for the replay check.
--   * Secondary indexes for the app's non-key lookups: metric.create_token, metric_calc.metric_id.
--   * No Fail-safe, no UNDROP, no table or schema clone, no replication, Time Travel AT(TIMESTAMP) only.
--     sql/011's nightly copy into standard tables gives those back for the copy.
--   * Queries never use the result cache (lists recompute; KB-sized tables).
-- legacy_id_map stays standard: written only by the one-time import.
-- Rollback: sql/rollback/010_hybrid_tables_down.sql.

-- ── metric (009) ───────────────────────────────────────────────────────────
CREATE HYBRID TABLE AI_PLATFORM.WORKBENCH.metric_hyb010 (
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
    PRIMARY KEY (metric_id),
    INDEX ix_metric_create_token (create_token)
);
INSERT INTO AI_PLATFORM.WORKBENCH.metric_hyb010
      (metric_id, full_name, description, disambig, department, category, source, status,
       duplicate_of_metric_id, superseded_by, create_token, original_author, revision_no,
       created_by, created_at, updated_by, updated_at)
SELECT metric_id, full_name, description, disambig, department, category, source, status,
       duplicate_of_metric_id, superseded_by, create_token, original_author, revision_no,
       created_by, created_at, updated_by, updated_at
FROM AI_PLATFORM.WORKBENCH.metric;

-- ── metric_calc (009) ──────────────────────────────────────────────────────
CREATE HYBRID TABLE AI_PLATFORM.WORKBENCH.metric_calc_hyb010 (
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
    PRIMARY KEY (calc_id),
    INDEX ix_metric_calc_metric_id (metric_id)
);
INSERT INTO AI_PLATFORM.WORKBENCH.metric_calc_hyb010
      (calc_id, metric_id, disambig, source, sql_text, source_table, is_default, status,
       validated_revision_no, validation_status, validation_message, validation_query_id, validated_at,
       served_revision_no, original_author, revision_no, created_by, created_at, updated_by, updated_at)
SELECT calc_id, metric_id, disambig, source, sql_text, source_table, is_default, status,
       validated_revision_no, validation_status, validation_message, validation_query_id, validated_at,
       served_revision_no, original_author, revision_no, created_by, created_at, updated_by, updated_at
FROM AI_PLATFORM.WORKBENCH.metric_calc;

-- ── revision (001) ─────────────────────────────────────────────────────────
CREATE HYBRID TABLE AI_PLATFORM.WORKBENCH.revision_hyb010 (
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
INSERT INTO AI_PLATFORM.WORKBENCH.revision_hyb010
      (record_type, record_id, revision_no, action, snapshot, schema_version, actor, acted_at, change_note)
SELECT record_type, record_id, revision_no, action, snapshot, schema_version, actor, acted_at, change_note
FROM AI_PLATFORM.WORKBENCH.revision;

-- ── op_log (003) + surrogate key ───────────────────────────────────────────
CREATE HYBRID TABLE AI_PLATFORM.WORKBENCH.op_log_hyb010 (
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
    PRIMARY KEY (log_id),
    INDEX ix_op_log_op_id (op_id)
);
INSERT INTO AI_PLATFORM.WORKBENCH.op_log_hyb010
      (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id, error, logged_at)
SELECT op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id, error, logged_at
FROM AI_PLATFORM.WORKBENCH.op_log;

-- ── fact_table_core (001) ──────────────────────────────────────────────────
CREATE HYBRID TABLE AI_PLATFORM.WORKBENCH.fact_table_core_hyb010 (
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
INSERT INTO AI_PLATFORM.WORKBENCH.fact_table_core_hyb010
      (table_name_full, display_name, description, disambig, gotchas, required_filter, grain, primary_key,
       time_dimension, department, source, status, original_author, revision_no, created_by, created_at,
       updated_by, updated_at)
SELECT table_name_full, display_name, description, disambig, gotchas, required_filter, grain, primary_key,
       time_dimension, department, source, status, original_author, revision_no, created_by, created_at,
       updated_by, updated_at
FROM AI_PLATFORM.WORKBENCH.fact_table_core;

-- ── Swap into place ────────────────────────────────────────────────────────
-- Run only after the pre-swap check in the handoff (row counts equal). Old tables keep their data
-- and grants under _std010.
ALTER TABLE AI_PLATFORM.WORKBENCH.metric          RENAME TO AI_PLATFORM.WORKBENCH.metric_std010;
ALTER TABLE AI_PLATFORM.WORKBENCH.metric_hyb010   RENAME TO AI_PLATFORM.WORKBENCH.metric;
ALTER TABLE AI_PLATFORM.WORKBENCH.metric_calc        RENAME TO AI_PLATFORM.WORKBENCH.metric_calc_std010;
ALTER TABLE AI_PLATFORM.WORKBENCH.metric_calc_hyb010 RENAME TO AI_PLATFORM.WORKBENCH.metric_calc;
ALTER TABLE AI_PLATFORM.WORKBENCH.revision        RENAME TO AI_PLATFORM.WORKBENCH.revision_std010;
ALTER TABLE AI_PLATFORM.WORKBENCH.revision_hyb010 RENAME TO AI_PLATFORM.WORKBENCH.revision;
ALTER TABLE AI_PLATFORM.WORKBENCH.op_log          RENAME TO AI_PLATFORM.WORKBENCH.op_log_std010;
ALTER TABLE AI_PLATFORM.WORKBENCH.op_log_hyb010   RENAME TO AI_PLATFORM.WORKBENCH.op_log;
ALTER TABLE AI_PLATFORM.WORKBENCH.fact_table_core        RENAME TO AI_PLATFORM.WORKBENCH.fact_table_core_std010;
ALTER TABLE AI_PLATFORM.WORKBENCH.fact_table_core_hyb010 RENAME TO AI_PLATFORM.WORKBENCH.fact_table_core;

-- ── Grants ─────────────────────────────────────────────────────────────────
-- 002's schema-level FUTURE TABLES grants already applied when the hybrid tables were created
-- (checked on a scratch hybrid table 2026-10-23: WORKBENCH_APP SELECT/INSERT/UPDATE; CORTEX_CODE_ROLE,
-- DATAENG, DATAENG_RO SELECT). Restated per table so the result doesn't depend on that. No DELETE.
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
-- The _std010 copies must not take writes by mistake meanwhile:
REVOKE INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.metric_std010          FROM ROLE WORKBENCH_APP;
REVOKE INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.metric_calc_std010     FROM ROLE WORKBENCH_APP;
REVOKE INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.revision_std010        FROM ROLE WORKBENCH_APP;
REVOKE INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.op_log_std010          FROM ROLE WORKBENCH_APP;
REVOKE INSERT, UPDATE ON TABLE AI_PLATFORM.WORKBENCH.fact_table_core_std010 FROM ROLE WORKBENCH_APP;

-- ── Verify (the handoff lists the expected results) ────────────────────────
-- SHOW HYBRID TABLES IN SCHEMA AI_PLATFORM.WORKBENCH;      -- the five tables above
-- SHOW INDEXES IN SCHEMA AI_PLATFORM.WORKBENCH;            -- the three secondary indexes
-- SHOW GRANTS ON TABLE AI_PLATFORM.WORKBENCH.metric;       -- WORKBENCH_APP S/I/U; readers SELECT
