-- 006 — One-time seed of AI_PLATFORM.WORKBENCH.fact_table_core from the legacy registry
-- AI_PLATFORM.DICTIONARY.FACT_TABLE_CORE (61 rows on 2026-10-23; UX-04, "seed before promotion
-- testing" in docs/features.md). Role: WORKBENCH_APP (it reads DICTIONARY, writes WORKBENCH).
-- Idempotent: skips names already registered, so re-running adds only new legacy tables.
--
-- Mapping (legacy → workbench): TABLE_NAME_FULL → table_name_full (upper case), TABLE_ALIAS →
-- display_name, GRAIN → grain, TIME_DIMENSION → time_dimension, UNIVERSAL_FILTER → required_filter,
-- GOTCHAS → gotchas, DEPARTMENT → the app's names (Finance*, CX / Support → Customer; others NULL).
-- Values starting 'TBD' or 'N/A' become NULL: they are notes, not knowledge. Joins, key measures,
-- query patterns and field lists stay in DICTIONARY (deferred, sql/001 comment). source = 'import'.

BEGIN TRANSACTION;

INSERT INTO AI_PLATFORM.WORKBENCH.fact_table_core
      (table_name_full, display_name, grain, time_dimension, required_filter, gotchas, department,
       source, status, created_by, updated_by)
SELECT UPPER(TRIM(l.table_name_full)),
       IFF(l.table_alias ILIKE 'TBD%' OR l.table_alias ILIKE 'N/A%', NULL, l.table_alias),
       IFF(l.grain ILIKE 'TBD%' OR l.grain ILIKE 'N/A%', NULL, l.grain),
       IFF(l.time_dimension ILIKE 'TBD%' OR l.time_dimension ILIKE 'N/A%', NULL, l.time_dimension),
       IFF(l.universal_filter ILIKE 'TBD%' OR l.universal_filter ILIKE 'N/A%', NULL, l.universal_filter),
       IFF(l.gotchas ILIKE 'TBD%' OR l.gotchas ILIKE 'N/A%', NULL, l.gotchas),
       CASE WHEN l.department ILIKE 'Finance%' THEN 'Finance'
            WHEN l.department ILIKE 'CX%' THEN 'Customer' END,
       'import', 'active', 'import', 'import'
FROM AI_PLATFORM.DICTIONARY.FACT_TABLE_CORE l
WHERE NOT EXISTS (SELECT 1 FROM AI_PLATFORM.WORKBENCH.fact_table_core w
                  WHERE w.table_name_full = UPPER(TRIM(l.table_name_full)));

-- Revision 1 snapshot for every imported row that has none yet.
INSERT INTO AI_PLATFORM.WORKBENCH.revision
      (record_type, record_id, revision_no, action, snapshot, schema_version, actor, change_note)
SELECT 'fact_table_core', f.table_name_full, f.revision_no, 'import', OBJECT_CONSTRUCT_KEEP_NULL(f.*), 2,
       'import', 'Seeded from AI_PLATFORM.DICTIONARY.FACT_TABLE_CORE (sql/006)'
FROM AI_PLATFORM.WORKBENCH.fact_table_core f
WHERE f.source = 'import'
  AND NOT EXISTS (SELECT 1 FROM AI_PLATFORM.WORKBENCH.revision r
                  WHERE r.record_type = 'fact_table_core' AND r.record_id = f.table_name_full);

COMMIT;

-- ── Verify ─────────────────────────────────────────────────────────────────
-- SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH.fact_table_core;                                 -- 61
-- SELECT COUNT(*) FROM AI_PLATFORM.WORKBENCH.revision WHERE record_type = 'fact_table_core';  -- 61
-- SELECT COUNT_IF(grain IS NOT NULL) FROM AI_PLATFORM.WORKBENCH.fact_table_core;              -- 6
