-- 007 — Read-only SQL check for physical implementations (CHECK-01, DEC-022). Run by CoCo as ACCOUNTADMIN.
--
-- The app (WORKBENCH_APP) never runs SME SQL itself. It calls run_check, an owner's-rights procedure
-- owned by WORKBENCH_SQLCHECK, a role that can only read (it inherits BI_RO). Writes and DDL in checked SQL fail
-- on privileges; wrapping the SQL as a subquery also makes anything but a query a syntax error.
-- Errors in the checked SQL come back as one row (KW_CHECK = 'KW_CHECK_FAILED', CODE, MESSAGE) so the
-- app can tell "the SQL failed" from "the check could not run". The caller's STATEMENT_TIMEOUT applies.

CREATE ROLE IF NOT EXISTS WORKBENCH_SQLCHECK;
GRANT ROLE WORKBENCH_SQLCHECK TO ROLE ACCOUNTADMIN;

-- Read AC by inheriting BI_RO (#chris 2026-10-23: per-table grants on ~11.6k AC objects were too slow,
-- and BI_RO is kept current as tables appear). Checked 2026-10-23 (SHOW GRANTS TO ROLE BI_RO): SELECT on
-- AC / DEV_AC / DEV_BI / POSTMARK tables and views, no INSERT/UPDATE/DELETE anywhere; it can CREATE
-- objects in AC_DATA_LAKE, which a wrapped SELECT can't reach. BI_RO shows no USAGE on database AC.
-- No warehouse grant: an owner's-rights procedure uses the caller's warehouse.
GRANT ROLE BI_RO               TO ROLE WORKBENCH_SQLCHECK;
GRANT USAGE ON DATABASE AC     TO ROLE WORKBENCH_SQLCHECK;
-- To own a procedure in WORKBENCH (no table access there):
GRANT USAGE  ON DATABASE AI_PLATFORM                 TO ROLE WORKBENCH_SQLCHECK;
GRANT USAGE  ON SCHEMA   AI_PLATFORM.WORKBENCH       TO ROLE WORKBENCH_SQLCHECK;

CREATE OR REPLACE PROCEDURE AI_PLATFORM.WORKBENCH.run_check(p_sql VARCHAR, p_max_rows NUMBER)
RETURNS TABLE()
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
    rs RESULTSET;
BEGIN
    -- The newline ends a trailing line comment in p_sql before the closing parenthesis.
    rs := (EXECUTE IMMEDIATE 'SELECT * FROM (' || :p_sql || '\n) LIMIT ' || :p_max_rows::INTEGER);
    RETURN TABLE(rs);
EXCEPTION
    WHEN OTHER THEN
        rs := (SELECT 'KW_CHECK_FAILED' AS kw_check, :sqlcode AS code, :sqlerrm AS message);
        RETURN TABLE(rs);
END;
$$;

GRANT OWNERSHIP ON PROCEDURE AI_PLATFORM.WORKBENCH.run_check(VARCHAR, NUMBER)
    TO ROLE WORKBENCH_SQLCHECK REVOKE CURRENT GRANTS;
GRANT USAGE ON PROCEDURE AI_PLATFORM.WORKBENCH.run_check(VARCHAR, NUMBER) TO ROLE WORKBENCH_APP;

-- ── Verify ─────────────────────────────────────────────────────────────────
-- SHOW GRANTS TO ROLE WORKBENCH_SQLCHECK;   -- role BI_RO, USAGE on AC + AI_PLATFORM.WORKBENCH, ownership of run_check
-- SHOW GRANTS TO ROLE BI_RO;                -- re-check: still no INSERT/UPDATE/DELETE/OWNERSHIP
-- SHOW GRANTS TO ROLE WORKBENCH_APP;        -- still no privileges on AC; USAGE on run_check
-- USE ROLE WORKBENCH_APP;
-- CALL AI_PLATFORM.WORKBENCH.run_check('SELECT 1 AS one', 100);                          -- one row: ONE = 1
-- CALL AI_PLATFORM.WORKBENCH.run_check('SELECT COUNT(*) FROM AC.acdb.csat', 100);        -- a count
-- CALL AI_PLATFORM.WORKBENCH.run_check('DELETE FROM AC.acdb.csat', 100);                 -- KW_CHECK_FAILED (syntax)
-- CALL AI_PLATFORM.WORKBENCH.run_check('SELECT 1) ; DROP TABLE AC.acdb.csat; SELECT (1', 100);  -- KW_CHECK_FAILED
-- CALL AI_PLATFORM.WORKBENCH.run_check('SELECT * FROM AI_PLATFORM.WORKBENCH.metric_calc', 100); -- KW_CHECK_FAILED (not authorized)
