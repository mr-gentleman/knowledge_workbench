-- 004 — One-call, all-or-nothing metric save (DEC-020, DEC-021). Re-runnable. Role: ACCOUNTADMIN,
-- then ownership moves to WORKBENCH_APP (below). Apply before deploying the app code that calls it.
-- Names are fully qualified on purpose: never rely on USE (AGENTS.md).
--
-- One CALL saves a metric page: the candidate plus any of its PIs (metric_calc) the draft touched.
-- Validation (required fields, PI labels, which new PI is default) happens in app/services.py first;
-- this procedure owns the transaction. Rules:
--   * Only records whose content changed are written; each gets one revision snapshot
--     (OBJECT_CONSTRUCT_KEEP_NULL(*) + the caller's schema_version). Unchanged → no write.
--   * Every edit is a conditional UPDATE on revision_no. Any record not at its expected revision
--     (or not an active PI of this candidate) → nothing is written, outcome 'conflict'. The caller
--     re-reads to say which records and who changed them.
--   * Retire = status 'retired', revision + 1, snapshot. A new PI that is also retired is skipped.
--   * Replay: an op_id already committed, a create_token already used, or a reserved calc_id that
--     already exists means this save landed before (it is atomic) → outcome 'replayed', no writes.
--   * One op_log row per outcome; 'committed' is written inside the transaction. Actor is the viewer
--     the app passes in, never CURRENT_USER().
--   * A transaction begun in a procedure must end in it, so a CALL never leaves one open on the
--     app's shared connection (the DEC-008 hazard).
--
-- Request (JSON text): {op_id, actor, lock_wait_ms, schema_version, change_note, check_name,
--   candidate: {id, expected_revision, create_token, source, original_author,
--               fields: {full_name, description, disambig, department, category}},
--   calcs: [{calc_id, expected_revision (NULL = new), retire, is_default,
--            fields: {sql_text, source_table, disambig}}]}
-- Empty strings must arrive as null: changes are detected with EQUAL_NULL against NULLIF(col, '').
-- Result: {outcome: committed | no_change | conflict | replayed, candidate_id, candidate_revision,
--   changed_calcs: [ids updated or retired], new_calcs: [ids inserted], checks_due: [ids whose SQL
--   changed], collisions: [{KIND, ID, FULL_NAME}] (absent = not checked or the lookup failed)}

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
    v_cid        NUMBER;
    v_cand_exp   NUMBER;
    v_token      VARCHAR;
    v_name       VARCHAR;
    v_desc       VARCHAR;
    v_dis        VARCHAR;
    v_dept       VARCHAR;
    v_cat        VARCHAR;
    v_creating   BOOLEAN;
    v_found      NUMBER DEFAULT 1;
    v_cand_n     NUMBER DEFAULT 0;   -- 1 when the candidate's content changed
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
    v_cid      := req:candidate:id::NUMBER;
    v_cand_exp := req:candidate:expected_revision::NUMBER;
    v_token    := req:candidate:create_token::VARCHAR;
    v_name     := req:candidate:fields:full_name::VARCHAR;
    v_desc     := req:candidate:fields:description::VARCHAR;
    v_dis      := req:candidate:fields:disambig::VARCHAR;
    v_dept     := req:candidate:fields:department::VARCHAR;
    v_cat      := req:candidate:fields:category::VARCHAR;
    v_source   := COALESCE(req:candidate:source::VARCHAR, 'sme');
    v_author   := COALESCE(req:candidate:original_author::VARCHAR, v_actor);
    v_creating := (v_cid IS NULL);

    -- Replay: this save already landed (it is all-or-nothing, so any marker means all of it).
    SELECT MAX(cid) INTO :v_replay FROM (
        SELECT TRY_TO_NUMBER(record_id) AS cid FROM AI_PLATFORM.WORKBENCH.op_log
        WHERE op_id = :v_op_id AND outcome = 'committed'
        UNION ALL
        SELECT candidate_id FROM AI_PLATFORM.WORKBENCH.metric_candidate
        WHERE :v_creating AND create_token = :v_token
        UNION ALL
        SELECT c.origin_candidate_id FROM AI_PLATFORM.WORKBENCH.metric_calc c
        JOIN TABLE(FLATTEN(input => :v_calcs)) r ON c.calc_id = r.value:calc_id::NUMBER
        WHERE r.value:expected_revision::NUMBER IS NULL);
    IF (v_replay IS NOT NULL) THEN
        INSERT INTO AI_PLATFORM.WORKBENCH.op_log
              (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id)
        SELECT :v_op_id, 'metric.save', :v_actor, :v_replay::VARCHAR, 'replayed', :v_wait,
               DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID();
        RETURN OBJECT_CONSTRUCT('outcome', 'replayed', 'candidate_id', v_replay);
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
        INTO :v_found, :v_cand_n, :v_old_name
        FROM AI_PLATFORM.WORKBENCH.metric_candidate
        WHERE candidate_id = :v_cid AND revision_no = :v_cand_exp;
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
              -- only active PIs of this candidate at the expected revision count as a match
              LEFT JOIN AI_PLATFORM.WORKBENCH.metric_calc c
                ON c.calc_id = r.id AND c.revision_no = r.exp_rev
               AND c.origin_candidate_id = :v_cid AND c.status = 'active');
    END IF;
    IF (v_found = 0 OR v_n_conflict > 0) THEN
        INSERT INTO AI_PLATFORM.WORKBENCH.op_log
              (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id)
        SELECT :v_op_id, 'metric.save', :v_actor, :v_cid::VARCHAR, 'conflict', :v_wait,
               DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID();
        RETURN OBJECT_CONSTRUCT('outcome', 'conflict', 'candidate_id', v_cid);
    END IF;
    IF (NOT v_creating AND v_cand_n = 0 AND v_n_changed = 0 AND v_n_new = 0) THEN
        INSERT INTO AI_PLATFORM.WORKBENCH.op_log
              (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id)
        SELECT :v_op_id, 'metric.save', :v_actor, :v_cid::VARCHAR, 'no_change', :v_wait,
               DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID();
        RETURN OBJECT_CONSTRUCT('outcome', 'no_change', 'candidate_id', v_cid,
                                'candidate_revision', v_cand_exp);
    END IF;

    -- Advisory duplicate-name check, only for a new or renamed metric; never fails a save (REL-11).
    IF (v_check IS NOT NULL AND (v_creating OR NOT EQUAL_NULL(v_old_name, v_check))) THEN
        BEGIN
            SELECT ARRAY_AGG(OBJECT_CONSTRUCT('KIND', kind, 'ID', id, 'FULL_NAME', full_name)) INTO :v_hits
            FROM (SELECT 'candidate' AS kind, candidate_id AS id, full_name
                  FROM AI_PLATFORM.WORKBENCH.metric_candidate
                  WHERE LOWER(TRIM(full_name)) = :v_check AND status = 'open'
                  UNION ALL
                  SELECT 'metric', metric_id, full_name
                  FROM AI_PLATFORM.WORKBENCH.metric_core
                  WHERE LOWER(TRIM(full_name)) = :v_check AND status = 'active');
        EXCEPTION
            WHEN OTHER THEN v_hits := NULL;
        END;
    ELSE
        v_hits := ARRAY_CONSTRUCT();
    END IF;

    BEGIN TRANSACTION;
    IF (v_creating) THEN
        SELECT AI_PLATFORM.WORKBENCH.seq_candidate_id.NEXTVAL INTO :v_cid;
        INSERT INTO AI_PLATFORM.WORKBENCH.metric_candidate
              (candidate_id, full_name, description, disambig, department, category,
               source, original_author, created_by, updated_by, create_token)
        SELECT :v_cid, :v_name, :v_desc, :v_dis, :v_dept, :v_cat,
               :v_source, :v_author, :v_actor, :v_actor, :v_token;
    ELSEIF (v_cand_n > 0) THEN
        UPDATE AI_PLATFORM.WORKBENCH.metric_candidate
        SET full_name = :v_name, description = :v_desc, disambig = :v_dis,
            department = :v_dept, category = :v_cat,
            revision_no = revision_no + 1,
            updated_by = :v_actor, updated_at = CURRENT_TIMESTAMP()
        WHERE candidate_id = :v_cid AND revision_no = :v_cand_exp;
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
            revision_no  = c.revision_no + 1,
            updated_by   = :v_actor, updated_at = CURRENT_TIMESTAMP()
        FROM (SELECT value:calc_id::NUMBER AS id, value:expected_revision::NUMBER AS exp_rev,
                     COALESCE(value:retire::BOOLEAN, FALSE) AS retire,
                     value:fields:sql_text::VARCHAR AS sql_text,
                     value:fields:source_table::VARCHAR AS source_table,
                     value:fields:disambig::VARCHAR AS disambig
              FROM TABLE(FLATTEN(input => :v_calcs))) r
        WHERE c.calc_id = r.id AND c.revision_no = r.exp_rev
          AND c.origin_candidate_id = :v_cid AND c.status = 'active'
          AND ARRAY_CONTAINS(r.id::VARIANT, :v_changed);
        IF (SQLROWCOUNT <> v_n_changed) THEN
            RAISE lost_race;
        END IF;
    END IF;

    IF (v_n_new > 0) THEN
        INSERT INTO AI_PLATFORM.WORKBENCH.metric_calc
              (calc_id, origin_candidate_id, disambig, source, sql_text, source_table,
               is_default, original_author, created_by, updated_by)
        SELECT value:calc_id::NUMBER, :v_cid, value:fields:disambig::VARCHAR, 'sme',
               value:fields:sql_text::VARCHAR, value:fields:source_table::VARCHAR,
               COALESCE(value:is_default::BOOLEAN, FALSE), :v_actor, :v_actor, :v_actor
        FROM TABLE(FLATTEN(input => :v_calcs))
        WHERE ARRAY_CONTAINS(value:calc_id, :v_new);
    END IF;

    -- One snapshot per written record = the row as written, so history can't drift from it.
    INSERT INTO AI_PLATFORM.WORKBENCH.revision
          (record_type, record_id, revision_no, action, snapshot, schema_version, actor, change_note)
    SELECT 'metric_candidate', candidate_id::VARCHAR, revision_no, IFF(:v_creating, 'create', 'edit'),
           OBJECT_CONSTRUCT_KEEP_NULL(*), :v_ver, :v_actor, :v_note
    FROM AI_PLATFORM.WORKBENCH.metric_candidate
    WHERE candidate_id = :v_cid AND (:v_creating OR :v_cand_n > 0)
    UNION ALL
    SELECT 'metric_calc', c.calc_id::VARCHAR, c.revision_no,
           IFF(ARRAY_CONTAINS(c.calc_id::VARIANT, :v_new), 'create', IFF(c.status = 'retired', 'retire', 'edit')),
           OBJECT_CONSTRUCT_KEEP_NULL(c.*), :v_ver, :v_actor, :v_note
    FROM AI_PLATFORM.WORKBENCH.metric_calc c
    WHERE ARRAY_CONTAINS(c.calc_id::VARIANT, ARRAY_CAT(:v_changed, :v_new));

    INSERT INTO AI_PLATFORM.WORKBENCH.op_log
          (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id)
    SELECT :v_op_id, 'metric.save', :v_actor, :v_cid::VARCHAR, 'committed', :v_wait,
           DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID();
    COMMIT;

    RETURN OBJECT_CONSTRUCT('outcome', 'committed', 'candidate_id', v_cid,
                            'candidate_revision', IFF(v_creating, 1, v_cand_exp + v_cand_n),
                            'changed_calcs', v_changed, 'new_calcs', v_new,
                            'checks_due', v_checks, 'collisions', v_hits);
EXCEPTION
    WHEN lost_race THEN  -- another save landed between the revision check and the write
        ROLLBACK;
        INSERT INTO AI_PLATFORM.WORKBENCH.op_log
              (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id)
        SELECT :v_op_id, 'metric.save', :v_actor, :v_cid::VARCHAR, 'conflict', :v_wait,
               DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID();
        RETURN OBJECT_CONSTRUCT('outcome', 'conflict', 'candidate_id', v_cid);
    WHEN OTHER THEN
        ROLLBACK;
        v_err := LEFT(SQLERRM, 2000);
        INSERT INTO AI_PLATFORM.WORKBENCH.op_log
              (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id, error)
        SELECT :v_op_id, 'metric.save', :v_actor, :v_cid::VARCHAR, 'rolled_back', :v_wait,
               DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID(), :v_err;
        RAISE;
END;
$$;

-- EXECUTE AS OWNER runs with the owner's privileges, so the owner must be the app role: it writes
-- only AI_PLATFORM.WORKBENCH and is read-only everywhere else (checked 2026-10-23: INSERT/UPDATE
-- on WORKBENCH tables only; SELECT on DICTIONARY). Never leave ACCOUNTADMIN or CORTEX_CODE_ROLE
-- as owner. CREATE OR REPLACE resets ownership: re-run this after ANY change to the procedure.
GRANT OWNERSHIP ON PROCEDURE AI_PLATFORM.WORKBENCH.save_metric(VARCHAR)
  TO ROLE WORKBENCH_APP REVOKE CURRENT GRANTS;

-- ── Verify ─────────────────────────────────────────────────────────────────
-- SHOW PROCEDURES LIKE 'SAVE_METRIC' IN SCHEMA AI_PLATFORM.WORKBENCH;   -- owner WORKBENCH_APP
-- SHOW GRANTS TO ROLE WORKBENCH_APP;   -- still NO INSERT/UPDATE outside AI_PLATFORM.WORKBENCH
