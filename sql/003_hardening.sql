-- 003 — M1 hardening (DEC-007): idempotent creates + operations log.
-- Apply before deploying the app code that uses them. Re-runnable.
USE SCHEMA AI_PLATFORM.WORKBENCH;

-- REL-10: one token per create attempt; a retry with the same token returns the first row.
ALTER TABLE metric_candidate ADD COLUMN IF NOT EXISTS create_token VARCHAR;

-- PLAT-04: one row per write attempt, inserted after the transaction ends (outside it),
-- so a rollback can't erase the record. QUERY_TAG on the statements carries the same op_id.
CREATE TABLE IF NOT EXISTS op_log (
    op_id           VARCHAR       NOT NULL,   -- uuid; also in QUERY_TAG of every statement in the op
    op              VARCHAR       NOT NULL,   -- candidate.create | candidate.edit | …
    actor           VARCHAR       NOT NULL,   -- trusted viewer (st.user), not the service user
    record_id       VARCHAR,
    -- committed | replayed (create retry returned the first row) | conflict | rolled_back.
    -- Uncertain outcomes (commit_uncertain, interrupted, rollback_failed) go to the app log
    -- only: the connection is quarantined first, and this insert could join an abandoned txn.
    outcome         VARCHAR       NOT NULL,
    lock_wait_ms    NUMBER        NOT NULL,   -- time to acquire db_lock (DEC-004's cost, measured)
    duration_ms     NUMBER        NOT NULL,
    last_query_id   VARCHAR,                  -- the COMMIT / ROLLBACK
    error           VARCHAR,
    logged_at       TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP()
);
-- Grants: covered by 002's FUTURE TABLES grants (WORKBENCH_APP gets SELECT/INSERT/UPDATE).
