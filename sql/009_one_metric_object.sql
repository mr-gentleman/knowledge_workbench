-- 009 — One metric object (DEC-024): candidate and canon are statuses of one row with one ID.
-- Run by CoCo / #chris as ACCOUNTADMIN, in one go, BEFORE deploying the app code from
-- claude/unified-metric (older app code reads metric_candidate and breaks after this; newer code
-- breaks before it). Schema still disposable (no real import yet): the 5 test candidates are dropped.
-- Names are fully qualified on purpose: never rely on USE (AGENTS.md).

-- ── Tables ─────────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS AI_PLATFORM.WORKBENCH.metric_candidate;
DROP TABLE IF EXISTS AI_PLATFORM.WORKBENCH.metric_core;
DROP SEQUENCE IF EXISTS AI_PLATFORM.WORKBENCH.seq_candidate_id;
-- seq_metric_id (sql/001) stays: it starts at 100000 and has never been used.

-- Every metric, from first save to retirement. The ID never changes.
CREATE TABLE IF NOT EXISTS AI_PLATFORM.WORKBENCH.metric (
    metric_id           NUMBER        NOT NULL,   -- seq_metric_id; legacy ids (2–90412) live in legacy_id_map
    full_name           VARCHAR       NOT NULL,   -- the one name; unique among canon (DEC-006)
    description         VARCHAR,                  -- required to become canon
    disambig            VARCHAR,                  -- when to use it / how it differs from similar metrics
    department          VARCHAR,
    category            VARCHAR,
    source              VARCHAR       NOT NULL,   -- sme | import | extraction | conversation | feedback
    -- candidate → canon (promotion) | rejected (never canon); canon → retired (no longer served).
    -- Only deliberate actions change it; "not ready yet" is a computed checklist, never a status.
    -- The why of a reject/retire goes in revision.change_note.
    status              VARCHAR       NOT NULL DEFAULT 'candidate',  -- candidate | canon | rejected | retired
    duplicate_of_metric_id NUMBER,                -- rejected as a duplicate of this canon
    superseded_by       NUMBER,                   -- retired: optional "see instead" pointer
    create_token        VARCHAR,                  -- a create's retry key (REL-02)
    original_author     VARCHAR,                  -- who wrote the content (NULL = unknown, don't guess)
    revision_no         NUMBER        NOT NULL DEFAULT 1,
    created_by          VARCHAR       NOT NULL,   -- who typed/imported it (trusted viewer identity)
    created_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_by          VARCHAR       NOT NULL,
    updated_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_metric PRIMARY KEY (metric_id)
);

-- PIs belong to one metric from creation; promotion doesn't move them. No reassignment in V1:
-- wrong attachment = new PI + retire the old one. Empty today, so recreated without
-- origin_candidate_id.
CREATE OR REPLACE TABLE AI_PLATFORM.WORKBENCH.metric_calc (
    calc_id             NUMBER        NOT NULL,
    metric_id           NUMBER        NOT NULL,
    disambig            VARCHAR,                  -- how this PI differs from its siblings: "monthly", "by cohort", …
    source              VARCHAR       NOT NULL,   -- sme | import | extraction | conversation | feedback
    sql_text            VARCHAR,                  -- content, never executed on save; may be unfinished
    source_table        VARCHAR,                  -- AC.SCHEMA.TABLE; must match an active fact_table_core row to promote
    is_default          BOOLEAN       NOT NULL DEFAULT FALSE,  -- the oldest active PI (DEC-023)
    status              VARCHAR       NOT NULL DEFAULT 'active',  -- active | retired
    -- Validation is bound to the revision it checked; it carries over while the SQL is unchanged
    -- (CHECK-06). Running a check updates these in place; it is NOT a content revision.
    validated_revision_no NUMBER,
    validation_status   VARCHAR,                  -- passed | failed | NULL (never checked)
    validation_message  VARCHAR,
    validation_query_id VARCHAR,
    validated_at        TIMESTAMP_TZ,
    -- What the Oracle uses: the latest revision that PASSED.
    served_revision_no  NUMBER,
    original_author     VARCHAR,
    revision_no         NUMBER        NOT NULL DEFAULT 1,
    created_by          VARCHAR       NOT NULL,
    created_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_by          VARCHAR       NOT NULL,
    updated_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_metric_calc PRIMARY KEY (calc_id)
);

-- Old IDs for historic Oracle logs and evals (DEC-024); filled by the legacy import.
CREATE TABLE IF NOT EXISTS AI_PLATFORM.WORKBENCH.legacy_id_map (
    record_type         VARCHAR       NOT NULL,   -- metric | metric_calc
    legacy_id           NUMBER        NOT NULL,   -- id in AI_PLATFORM.DICTIONARY
    new_id              NUMBER        NOT NULL,
    mapped_at           TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_legacy_id_map PRIMARY KEY (record_type, legacy_id)
);

-- Grants: 002's schema-level FUTURE TABLES grants apply to these new tables (WORKBENCH_APP
-- SELECT/INSERT/UPDATE; readers SELECT). Checked by the verify queries at the bottom.

-- ── save_metric ────────────────────────────────────────────────────────────
-- 008's procedure on the one metric table. Changes: request key `metric` (was `candidate`),
-- result keys metric_id / metric_revision, PIs matched on metric_id, revision record_type
-- 'metric', one duplicate-name lookup over candidates and canon. Everything else as 008.
-- Request (JSON text): {op_id, actor, lock_wait_ms, schema_version, change_note, check_name,
--   metric: {id (NULL = create), expected_revision, create_token, source, original_author,
--            fields: {full_name, description, disambig, department, category}},
--   calcs: [{calc_id, expected_revision (NULL = new), retire, is_default,
--            fields: {sql_text, source_table, disambig}}]}
-- Result: {outcome: committed | no_change | conflict | replayed, metric_id, metric_revision,
--   changed_calcs, new_calcs, checks_due, collisions: [{KIND (candidate | canon), ID, FULL_NAME}]}
-- Status changes (promote, reject, retire) are not part of this save; promotion is LIFE-01.

CREATE OR REPLACE PROCEDURE AI_PLATFORM.WORKBENCH.save_metric(p_request VARCHAR)
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
    started      TIMESTAMP_NTZ DEFAULT SYSDATE();
    req          VARIANT;
    v_op_id      VARCHAR;
    v_actor      VARCHAR;
    v_wait       NUMBER;
    v_ver        NUMBER;
    v_note       VARCHAR;
    v_check      VARCHAR;
    v_calcs      ARRAY;
    v_mid        NUMBER;
    v_exp        NUMBER;
    v_token      VARCHAR;
    v_name       VARCHAR;
    v_desc       VARCHAR;
    v_dis        VARCHAR;
    v_dept       VARCHAR;
    v_cat        VARCHAR;
    v_creating   BOOLEAN;
    v_found      NUMBER DEFAULT 1;
    v_metric_n   NUMBER DEFAULT 0;   -- 1 when the metric's content changed
    v_old_name   VARCHAR;
    v_replay     NUMBER;
    v_n_conflict NUMBER DEFAULT 0;
    v_n_changed  NUMBER DEFAULT 0;
    v_n_new      NUMBER DEFAULT 0;
    v_changed    ARRAY DEFAULT ARRAY_CONSTRUCT();
    v_new        ARRAY DEFAULT ARRAY_CONSTRUCT();
    v_checks     ARRAY DEFAULT ARRAY_CONSTRUCT();
    v_hits       ARRAY DEFAULT NULL;
    v_source     VARCHAR;
    v_author     VARCHAR;
    v_err        VARCHAR;
    lost_race    EXCEPTION (-20001, 'A concurrent save changed a record after the revision check.');
BEGIN
    req        := PARSE_JSON(p_request);
    v_op_id    := req:op_id::VARCHAR;
    v_actor    := req:actor::VARCHAR;
    v_wait     := req:lock_wait_ms::NUMBER;
    v_ver      := req:schema_version::NUMBER;
    v_note     := req:change_note::VARCHAR;
    v_check    := req:check_name::VARCHAR;
    v_calcs    := COALESCE(req:calcs::ARRAY, ARRAY_CONSTRUCT());
    v_mid      := req:metric:id::NUMBER;
    v_exp      := req:metric:expected_revision::NUMBER;
    v_token    := req:metric:create_token::VARCHAR;
    v_name     := req:metric:fields:full_name::VARCHAR;
    v_desc     := req:metric:fields:description::VARCHAR;
    v_dis      := req:metric:fields:disambig::VARCHAR;
    v_dept     := req:metric:fields:department::VARCHAR;
    v_cat      := req:metric:fields:category::VARCHAR;
    v_source   := COALESCE(req:metric:source::VARCHAR, 'sme');
    v_author   := COALESCE(req:metric:original_author::VARCHAR, v_actor);
    v_creating := (v_mid IS NULL);

    -- Replay: this save already landed (it is all-or-nothing, so any marker means all of it).
    SELECT MAX(cid) INTO :v_replay FROM (
        SELECT TRY_TO_NUMBER(record_id) AS cid FROM AI_PLATFORM.WORKBENCH.op_log
        WHERE op_id = :v_op_id AND outcome = 'committed'
        UNION ALL
        SELECT metric_id FROM AI_PLATFORM.WORKBENCH.metric
        WHERE :v_creating AND create_token = :v_token
        UNION ALL
        SELECT c.metric_id FROM AI_PLATFORM.WORKBENCH.metric_calc c
        JOIN TABLE(FLATTEN(input => :v_calcs)) r ON c.calc_id = r.value:calc_id::NUMBER
        WHERE r.value:expected_revision::NUMBER IS NULL);
    IF (v_replay IS NOT NULL) THEN
        INSERT INTO AI_PLATFORM.WORKBENCH.op_log
              (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id)
        SELECT :v_op_id, 'metric.save', :v_actor, :v_replay::VARCHAR, 'replayed', :v_wait,
               DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID();
        RETURN OBJECT_CONSTRUCT('outcome', 'replayed', 'metric_id', v_replay);
    END IF;

    -- What changed, and is every record still at the revision the draft started from?
    IF (NOT v_creating) THEN
        SELECT COUNT(*),
               COUNT_IF(NOT (EQUAL_NULL(NULLIF(full_name, ''), :v_name)
                             AND EQUAL_NULL(NULLIF(description, ''), :v_desc)
                             AND EQUAL_NULL(NULLIF(disambig, ''), :v_dis)
                             AND EQUAL_NULL(NULLIF(department, ''), :v_dept)
                             AND EQUAL_NULL(NULLIF(category, ''), :v_cat))),
               MAX(LOWER(TRIM(full_name)))
        INTO :v_found, :v_metric_n, :v_old_name
        FROM AI_PLATFORM.WORKBENCH.metric
        WHERE metric_id = :v_mid AND revision_no = :v_exp;
    END IF;
    IF (ARRAY_SIZE(v_calcs) > 0) THEN
        SELECT COUNT_IF(exp_rev IS NOT NULL AND hit IS NULL),
               COUNT_IF(hit IS NOT NULL AND (retire OR NOT same_content)),
               COUNT_IF(exp_rev IS NULL AND NOT retire),
               ARRAY_AGG(IFF(hit IS NOT NULL AND (retire OR NOT same_content), id, NULL)),
               ARRAY_AGG(IFF(exp_rev IS NULL AND NOT retire, id, NULL)),
               ARRAY_AGG(IFF(NOT retire AND (exp_rev IS NULL OR (hit IS NOT NULL AND NOT same_sql)), id, NULL))
        INTO :v_n_conflict, :v_n_changed, :v_n_new, :v_changed, :v_new, :v_checks
        FROM (SELECT r.id, r.exp_rev, r.retire, c.calc_id AS hit,
                     EQUAL_NULL(NULLIF(c.sql_text, ''), r.sql_text) AS same_sql,
                     same_sql AND EQUAL_NULL(NULLIF(c.source_table, ''), r.source_table)
                              AND EQUAL_NULL(NULLIF(c.disambig, ''), r.disambig) AS same_content
              FROM (SELECT value:calc_id::NUMBER AS id, value:expected_revision::NUMBER AS exp_rev,
                           COALESCE(value:retire::BOOLEAN, FALSE) AS retire,
                           value:fields:sql_text::VARCHAR AS sql_text,
                           value:fields:source_table::VARCHAR AS source_table,
                           value:fields:disambig::VARCHAR AS disambig
                    FROM TABLE(FLATTEN(input => :v_calcs))) r
              -- only active PIs of this metric at the expected revision count as a match
              LEFT JOIN AI_PLATFORM.WORKBENCH.metric_calc c
                ON c.calc_id = r.id AND c.revision_no = r.exp_rev
               AND c.metric_id = :v_mid AND c.status = 'active');
    END IF;
    IF (v_found = 0 OR v_n_conflict > 0) THEN
        INSERT INTO AI_PLATFORM.WORKBENCH.op_log
              (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id)
        SELECT :v_op_id, 'metric.save', :v_actor, :v_mid::VARCHAR, 'conflict', :v_wait,
               DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID();
        RETURN OBJECT_CONSTRUCT('outcome', 'conflict', 'metric_id', v_mid);
    END IF;
    IF (NOT v_creating AND v_metric_n = 0 AND v_n_changed = 0 AND v_n_new = 0) THEN
        INSERT INTO AI_PLATFORM.WORKBENCH.op_log
              (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id)
        SELECT :v_op_id, 'metric.save', :v_actor, :v_mid::VARCHAR, 'no_change', :v_wait,
               DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID();
        RETURN OBJECT_CONSTRUCT('outcome', 'no_change', 'metric_id', v_mid,
                                'metric_revision', v_exp);
    END IF;

    -- Advisory duplicate-name check, only for a new or renamed metric; never fails a save (REL-11).
    IF (v_check IS NOT NULL AND (v_creating OR NOT EQUAL_NULL(v_old_name, v_check))) THEN
        BEGIN
            SELECT ARRAY_AGG(OBJECT_CONSTRUCT('KIND', status, 'ID', metric_id, 'FULL_NAME', full_name)) INTO :v_hits
            FROM AI_PLATFORM.WORKBENCH.metric
            WHERE LOWER(TRIM(full_name)) = :v_check AND status IN ('candidate', 'canon');
        EXCEPTION
            WHEN OTHER THEN v_hits := NULL;
        END;
    ELSE
        v_hits := ARRAY_CONSTRUCT();
    END IF;

    BEGIN TRANSACTION;
    IF (v_creating) THEN
        SELECT AI_PLATFORM.WORKBENCH.seq_metric_id.NEXTVAL INTO :v_mid;
        INSERT INTO AI_PLATFORM.WORKBENCH.metric
              (metric_id, full_name, description, disambig, department, category,
               source, original_author, created_by, updated_by, create_token)
        SELECT :v_mid, :v_name, :v_desc, :v_dis, :v_dept, :v_cat,
               :v_source, :v_author, :v_actor, :v_actor, :v_token;
    ELSEIF (v_metric_n > 0) THEN
        UPDATE AI_PLATFORM.WORKBENCH.metric
        SET full_name = :v_name, description = :v_desc, disambig = :v_dis,
            department = :v_dept, category = :v_cat,
            revision_no = revision_no + 1,
            updated_by = :v_actor, updated_at = CURRENT_TIMESTAMP()
        WHERE metric_id = :v_mid AND revision_no = :v_exp;
        IF (SQLROWCOUNT = 0) THEN
            RAISE lost_race;
        END IF;
    END IF;

    IF (v_n_changed > 0) THEN
        UPDATE AI_PLATFORM.WORKBENCH.metric_calc c
        SET sql_text     = IFF(r.retire, c.sql_text, r.sql_text),
            source_table = IFF(r.retire, c.source_table, r.source_table),
            disambig     = IFF(r.retire, c.disambig, r.disambig),
            status       = IFF(r.retire, 'retired', c.status),
            -- A check counts until the SQL changes (CHECK-06). Right-hand sides read the old row.
            validated_revision_no = IFF(NOT r.retire AND c.validated_revision_no = c.revision_no
                                        AND EQUAL_NULL(NULLIF(c.sql_text, ''), r.sql_text),
                                        c.revision_no + 1, c.validated_revision_no),
            revision_no  = c.revision_no + 1,
            updated_by   = :v_actor, updated_at = CURRENT_TIMESTAMP()
        FROM (SELECT value:calc_id::NUMBER AS id, value:expected_revision::NUMBER AS exp_rev,
                     COALESCE(value:retire::BOOLEAN, FALSE) AS retire,
                     value:fields:sql_text::VARCHAR AS sql_text,
                     value:fields:source_table::VARCHAR AS source_table,
                     value:fields:disambig::VARCHAR AS disambig
              FROM TABLE(FLATTEN(input => :v_calcs))) r
        WHERE c.calc_id = r.id AND c.revision_no = r.exp_rev
          AND c.metric_id = :v_mid AND c.status = 'active'
          AND ARRAY_CONTAINS(r.id::VARIANT, :v_changed);
        IF (SQLROWCOUNT <> v_n_changed) THEN
            RAISE lost_race;
        END IF;
    END IF;

    IF (v_n_new > 0) THEN
        INSERT INTO AI_PLATFORM.WORKBENCH.metric_calc
              (calc_id, metric_id, disambig, source, sql_text, source_table,
               is_default, original_author, created_by, updated_by)
        SELECT value:calc_id::NUMBER, :v_mid, value:fields:disambig::VARCHAR, 'sme',
               value:fields:sql_text::VARCHAR, value:fields:source_table::VARCHAR,
               COALESCE(value:is_default::BOOLEAN, FALSE), :v_actor, :v_actor, :v_actor
        FROM TABLE(FLATTEN(input => :v_calcs))
        WHERE ARRAY_CONTAINS(value:calc_id, :v_new);
    END IF;

    -- The oldest active PI is the default; retired PIs never are (DEC-019, UX-06).
    IF (v_n_changed > 0 OR v_n_new > 0) THEN
        UPDATE AI_PLATFORM.WORKBENCH.metric_calc c
        SET is_default = (c.status = 'active' AND c.calc_id = d.first_id)
        FROM (SELECT MIN(calc_id) AS first_id FROM AI_PLATFORM.WORKBENCH.metric_calc
              WHERE metric_id = :v_mid AND status = 'active') d
        WHERE c.metric_id = :v_mid
          AND c.is_default IS DISTINCT FROM (c.status = 'active' AND c.calc_id = d.first_id);
    END IF;

    -- One snapshot per written record = the row as written, so history can't drift from it.
    INSERT INTO AI_PLATFORM.WORKBENCH.revision
          (record_type, record_id, revision_no, action, snapshot, schema_version, actor, change_note)
    SELECT 'metric', metric_id::VARCHAR, revision_no, IFF(:v_creating, 'create', 'edit'),
           OBJECT_CONSTRUCT_KEEP_NULL(*), :v_ver, :v_actor, :v_note
    FROM AI_PLATFORM.WORKBENCH.metric
    WHERE metric_id = :v_mid AND (:v_creating OR :v_metric_n > 0)
    UNION ALL
    SELECT 'metric_calc', c.calc_id::VARCHAR, c.revision_no,
           IFF(ARRAY_CONTAINS(c.calc_id::VARIANT, :v_new), 'create', IFF(c.status = 'retired', 'retire', 'edit')),
           OBJECT_CONSTRUCT_KEEP_NULL(c.*), :v_ver, :v_actor, :v_note
    FROM AI_PLATFORM.WORKBENCH.metric_calc c
    WHERE ARRAY_CONTAINS(c.calc_id::VARIANT, ARRAY_CAT(:v_changed, :v_new));

    INSERT INTO AI_PLATFORM.WORKBENCH.op_log
          (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id)
    SELECT :v_op_id, 'metric.save', :v_actor, :v_mid::VARCHAR, 'committed', :v_wait,
           DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID();
    COMMIT;

    RETURN OBJECT_CONSTRUCT('outcome', 'committed', 'metric_id', v_mid,
                            'metric_revision', IFF(v_creating, 1, v_exp + v_metric_n),
                            'changed_calcs', v_changed, 'new_calcs', v_new,
                            'checks_due', v_checks, 'collisions', v_hits);
EXCEPTION
    WHEN lost_race THEN  -- another save landed between the revision check and the write
        ROLLBACK;
        INSERT INTO AI_PLATFORM.WORKBENCH.op_log
              (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id)
        SELECT :v_op_id, 'metric.save', :v_actor, :v_mid::VARCHAR, 'conflict', :v_wait,
               DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID();
        RETURN OBJECT_CONSTRUCT('outcome', 'conflict', 'metric_id', v_mid);
    WHEN OTHER THEN
        ROLLBACK;
        v_err := LEFT(SQLERRM, 2000);
        INSERT INTO AI_PLATFORM.WORKBENCH.op_log
              (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id, error)
        SELECT :v_op_id, 'metric.save', :v_actor, :v_mid::VARCHAR, 'rolled_back', :v_wait,
               DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID(), :v_err;
        RAISE;
END;
$$;

-- EXECUTE AS OWNER runs with the owner's privileges, so the owner must be the app role (see 004).
-- CREATE OR REPLACE resets ownership: re-run this after ANY change to the procedure.
GRANT OWNERSHIP ON PROCEDURE AI_PLATFORM.WORKBENCH.save_metric(VARCHAR)
  TO ROLE WORKBENCH_APP REVOKE CURRENT GRANTS;

-- ── Verify ─────────────────────────────────────────────────────────────────
-- SHOW TABLES LIKE 'METRIC%' IN SCHEMA AI_PLATFORM.WORKBENCH;   -- METRIC, METRIC_CALC; no METRIC_CANDIDATE / METRIC_CORE
-- SHOW GRANTS ON PROCEDURE AI_PLATFORM.WORKBENCH.save_metric(VARCHAR);   -- OWNERSHIP → WORKBENCH_APP only
-- SHOW GRANTS ON TABLE AI_PLATFORM.WORKBENCH.metric;        -- WORKBENCH_APP: SELECT, INSERT, UPDATE; DATAENG, DATAENG_RO, CoCo, Glean: SELECT
-- SHOW GRANTS ON TABLE AI_PLATFORM.WORKBENCH.metric_calc;   -- same
