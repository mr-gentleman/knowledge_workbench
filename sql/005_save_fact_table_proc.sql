-- 005 — One-call fact-table save (UX-04; same contract as save_metric, DEC-020/DEC-021). Re-runnable.
-- Role: ACCOUNTADMIN, then ownership moves to WORKBENCH_APP (below). Apply before deploying the app
-- code that calls it. Names are fully qualified on purpose: never rely on USE (AGENTS.md).
--
-- One CALL creates or edits one AI_PLATFORM.WORKBENCH.fact_table_core row. Validation (3-part name,
-- status) happens in app/services.py first; this procedure owns the transaction. Rules:
--   * The key is table_name_full and is never changed here (a rename is a separate, later workflow).
--   * Edit = conditional UPDATE on revision_no. Row not at the expected revision → 'conflict',
--     nothing written; the caller re-reads to say who changed what. Unchanged content → 'no_change'.
--   * Create of a name that already exists → 'exists', nothing written. Standard tables don't enforce
--     the primary key, so the INSERT itself checks; the app's process-wide lock serializes saves.
--   * One revision snapshot per write (OBJECT_CONSTRUCT_KEEP_NULL(*) + the caller's schema_version),
--     action create | edit | retire. One op_log row per outcome (op 'fact_table.save'); 'committed'
--     is written inside the transaction. Actor is the viewer the app passes in, never CURRENT_USER().
--   * Replay: an op_id already committed means this save landed before → 'replayed', no writes.
--   * A transaction begun here ends here, so a CALL never leaves one open on the shared connection.
--
-- Request (JSON text): {op_id, actor, lock_wait_ms, schema_version, change_note,
--   table: {table_name, expected_revision (NULL = create),
--           fields: {display_name, description, disambig, gotchas, required_filter, grain,
--                    primary_key, time_dimension, department, status}}}
-- Empty strings must arrive as null: changes are detected with EQUAL_NULL against NULLIF(col, '').
-- Result: {outcome: committed | no_change | conflict | exists | replayed, table_name, revision_no}

CREATE OR REPLACE PROCEDURE AI_PLATFORM.WORKBENCH.save_fact_table(p_request VARCHAR)
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
    started    TIMESTAMP_NTZ DEFAULT SYSDATE();
    req        VARIANT;
    f          VARIANT;
    v_op_id    VARCHAR;
    v_actor    VARCHAR;
    v_wait     NUMBER;
    v_ver      NUMBER;
    v_note     VARCHAR;
    v_name     VARCHAR;
    v_exp      NUMBER;
    v_creating BOOLEAN;
    v_found    NUMBER DEFAULT 0;
    v_changed  NUMBER DEFAULT 0;
    v_retiring BOOLEAN DEFAULT FALSE;
    v_outcome  VARCHAR;
    v_err      VARCHAR;
    lost_race  EXCEPTION (-20001, 'A concurrent save changed the fact table after the revision check.');
BEGIN
    req        := PARSE_JSON(p_request);
    f          := req:table:fields;
    v_op_id    := req:op_id::VARCHAR;
    v_actor    := req:actor::VARCHAR;
    v_wait     := req:lock_wait_ms::NUMBER;
    v_ver      := req:schema_version::NUMBER;
    v_note     := req:change_note::VARCHAR;
    v_name     := req:table:table_name::VARCHAR;
    v_exp      := req:table:expected_revision::NUMBER;
    v_creating := (v_exp IS NULL);

    SELECT COUNT(*) INTO :v_found FROM AI_PLATFORM.WORKBENCH.op_log
    WHERE op_id = :v_op_id AND outcome = 'committed';
    IF (v_found > 0) THEN
        v_outcome := 'replayed';
    ELSEIF (v_creating) THEN
        SELECT COUNT(*) INTO :v_found FROM AI_PLATFORM.WORKBENCH.fact_table_core
        WHERE table_name_full = :v_name;
        v_outcome := IFF(v_found > 0, 'exists', NULL);
    ELSE
        SELECT COUNT(*),
               COUNT_IF(NOT (EQUAL_NULL(NULLIF(display_name, ''), r.j:display_name::VARCHAR)
                             AND EQUAL_NULL(NULLIF(description, ''), r.j:description::VARCHAR)
                             AND EQUAL_NULL(NULLIF(disambig, ''), r.j:disambig::VARCHAR)
                             AND EQUAL_NULL(NULLIF(gotchas, ''), r.j:gotchas::VARCHAR)
                             AND EQUAL_NULL(NULLIF(required_filter, ''), r.j:required_filter::VARCHAR)
                             AND EQUAL_NULL(NULLIF(grain, ''), r.j:grain::VARCHAR)
                             AND EQUAL_NULL(NULLIF(primary_key, ''), r.j:primary_key::VARCHAR)
                             AND EQUAL_NULL(NULLIF(time_dimension, ''), r.j:time_dimension::VARCHAR)
                             AND EQUAL_NULL(NULLIF(department, ''), r.j:department::VARCHAR)
                             AND EQUAL_NULL(status, r.j:status::VARCHAR))),
               COALESCE(BOOLOR_AGG(status = 'active' AND r.j:status::VARCHAR = 'retired'), FALSE)
        INTO :v_found, :v_changed, :v_retiring
        FROM AI_PLATFORM.WORKBENCH.fact_table_core, (SELECT :f AS j) r
        WHERE table_name_full = :v_name AND revision_no = :v_exp;
        v_outcome := IFF(v_found = 0, 'conflict', IFF(v_changed = 0, 'no_change', NULL));
    END IF;
    IF (v_outcome IS NOT NULL) THEN
        INSERT INTO AI_PLATFORM.WORKBENCH.op_log
              (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id)
        SELECT :v_op_id, 'fact_table.save', :v_actor, :v_name, IFF(:v_outcome = 'exists', 'conflict', :v_outcome),
               :v_wait, DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID();
        RETURN OBJECT_CONSTRUCT('outcome', v_outcome, 'table_name', v_name,
                                'revision_no', IFF(v_outcome = 'no_change', v_exp, NULL));
    END IF;

    BEGIN TRANSACTION;
    IF (v_creating) THEN
        INSERT INTO AI_PLATFORM.WORKBENCH.fact_table_core
              (table_name_full, display_name, description, disambig, gotchas, required_filter, grain,
               primary_key, time_dimension, department, source, status, original_author, created_by, updated_by)
        SELECT :v_name, r.j:display_name::VARCHAR, r.j:description::VARCHAR, r.j:disambig::VARCHAR,
               r.j:gotchas::VARCHAR, r.j:required_filter::VARCHAR, r.j:grain::VARCHAR, r.j:primary_key::VARCHAR,
               r.j:time_dimension::VARCHAR, r.j:department::VARCHAR, 'sme', COALESCE(r.j:status::VARCHAR, 'active'),
               :v_actor, :v_actor, :v_actor
        FROM (SELECT :f AS j) r
        WHERE NOT EXISTS (SELECT 1 FROM AI_PLATFORM.WORKBENCH.fact_table_core WHERE table_name_full = :v_name);
    ELSE
        UPDATE AI_PLATFORM.WORKBENCH.fact_table_core
        SET display_name = r.j:display_name::VARCHAR, description = r.j:description::VARCHAR,
            disambig = r.j:disambig::VARCHAR, gotchas = r.j:gotchas::VARCHAR,
            required_filter = r.j:required_filter::VARCHAR, grain = r.j:grain::VARCHAR,
            primary_key = r.j:primary_key::VARCHAR, time_dimension = r.j:time_dimension::VARCHAR,
            department = r.j:department::VARCHAR, status = r.j:status::VARCHAR,
            revision_no = revision_no + 1,
            updated_by = :v_actor, updated_at = CURRENT_TIMESTAMP()
        FROM (SELECT :f AS j) r
        WHERE table_name_full = :v_name AND revision_no = :v_exp;
    END IF;
    IF (SQLROWCOUNT = 0) THEN
        RAISE lost_race;
    END IF;

    INSERT INTO AI_PLATFORM.WORKBENCH.revision
          (record_type, record_id, revision_no, action, snapshot, schema_version, actor, change_note)
    SELECT 'fact_table_core', table_name_full, revision_no,
           IFF(:v_creating, 'create', IFF(:v_retiring, 'retire', 'edit')),
           OBJECT_CONSTRUCT_KEEP_NULL(*), :v_ver, :v_actor, :v_note
    FROM AI_PLATFORM.WORKBENCH.fact_table_core
    WHERE table_name_full = :v_name;

    INSERT INTO AI_PLATFORM.WORKBENCH.op_log
          (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id)
    SELECT :v_op_id, 'fact_table.save', :v_actor, :v_name, 'committed', :v_wait,
           DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID();
    COMMIT;

    RETURN OBJECT_CONSTRUCT('outcome', 'committed', 'table_name', v_name,
                            'revision_no', IFF(v_creating, 1, v_exp + 1));
EXCEPTION
    WHEN lost_race THEN  -- another save landed between the check and the write
        ROLLBACK;
        INSERT INTO AI_PLATFORM.WORKBENCH.op_log
              (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id)
        SELECT :v_op_id, 'fact_table.save', :v_actor, :v_name, 'conflict', :v_wait,
               DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID();
        RETURN OBJECT_CONSTRUCT('outcome', IFF(v_creating, 'exists', 'conflict'), 'table_name', v_name);
    WHEN OTHER THEN
        ROLLBACK;
        v_err := LEFT(SQLERRM, 2000);
        INSERT INTO AI_PLATFORM.WORKBENCH.op_log
              (op_id, op, actor, record_id, outcome, lock_wait_ms, duration_ms, last_query_id, error)
        SELECT :v_op_id, 'fact_table.save', :v_actor, :v_name, 'rolled_back', :v_wait,
               DATEDIFF('millisecond', :started, SYSDATE()), LAST_QUERY_ID(), :v_err;
        RAISE;
END;
$$;

-- EXECUTE AS OWNER runs with the owner's privileges, so the owner must be the app role (see 004).
-- CREATE OR REPLACE resets ownership: re-run this after ANY change to the procedure.
GRANT OWNERSHIP ON PROCEDURE AI_PLATFORM.WORKBENCH.save_fact_table(VARCHAR)
  TO ROLE WORKBENCH_APP REVOKE CURRENT GRANTS;

-- ── Verify ─────────────────────────────────────────────────────────────────
-- SHOW PROCEDURES LIKE 'SAVE_FACT_TABLE' IN SCHEMA AI_PLATFORM.WORKBENCH;   -- owner WORKBENCH_APP
