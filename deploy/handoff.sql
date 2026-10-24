-- SPCS spike — objects and grants for #chris / CoCo to review and run. Nothing here has been run.
-- Run as ACCOUNTADMIN. Fully qualified throughout (never rely on USE).
-- The service is owned by WORKBENCH_APP, so its owner's rights = today's SiS app rights:
-- write AI_PLATFORM.WORKBENCH only, nothing on AI_PLATFORM.DICTIONARY (DEC-007 isolation holds).

-- 1. Image repository (one per schema is enough; holds the spike image).
GRANT CREATE IMAGE REPOSITORY ON SCHEMA AI_PLATFORM.WORKBENCH TO ROLE WORKBENCH_APP;
-- then, as WORKBENCH_APP:
--   CREATE IMAGE REPOSITORY IF NOT EXISTS AI_PLATFORM.WORKBENCH.KW_IMAGES;

-- 2. Service creation + a public (Snowflake-login) endpoint.
GRANT CREATE SERVICE ON SCHEMA AI_PLATFORM.WORKBENCH TO ROLE WORKBENCH_APP;
GRANT BIND SERVICE ENDPOINT ON ACCOUNT TO ROLE WORKBENCH_APP;  -- account-level: lets this role expose public endpoints

-- 3. Compute — pick ONE.
-- 3a (try first, no new spend line): the pool the SiS app already runs on. WORKBENCH_APP has USAGE on it
--     already (granted for SiS). Unverified whether user-created services are allowed on a system pool;
--     if CREATE SERVICE refuses, use 3b (deploy.sh defaults to 3a; KW_POOL=KW_SPIKE_POOL selects 3b).
-- 3b: a dedicated 1-node XS pool. Measured in this account: an XS node ≈ 0.11 credits/hr
--     (TUTORIAL_COMPUTE_POOL, last 30 days) ≈ 80 credits/month if never suspended.
CREATE COMPUTE POOL IF NOT EXISTS KW_SPIKE_POOL
  MIN_NODES = 1 MAX_NODES = 1
  INSTANCE_FAMILY = CPU_X64_XS
  AUTO_RESUME = TRUE
  AUTO_SUSPEND_SECS = 600          -- pool suspends once no service is running on it
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Knowledge Workbench SPCS spike — drop after the spike';
GRANT USAGE, MONITOR ON COMPUTE POOL KW_SPIKE_POOL TO ROLE WORKBENCH_APP;

-- 4. Caller's rights (only for the spike's identity check; the write path doesn't need it).
--    Caller grants cap what a caller's-rights connection may do: privileges = caller's ∩ these.
--    Needs MANAGE CALLER GRANTS (ACCOUNTADMIN has it).
GRANT CALLER USAGE ON WAREHOUSE BIZ_AI_WH TO ROLE WORKBENCH_APP;

-- 5. After `deploy/deploy.sh --create` (as WORKBENCH_APP): who may open the app.
--    Ingress checks the signed-in user's roles; one plain account role gates the app (see COCO_HANDOFF Part 3).
-- CREATE ROLE IF NOT EXISTS WORKBENCH_USER; GRANT SERVICE ROLE AI_PLATFORM.WORKBENCH.KW_SPIKE!KW_USER TO ROLE WORKBENCH_USER; GRANT ROLE WORKBENCH_USER TO USER CLENZINI;

-- 6. Idle cost control, after create (verify syntax/availability in this account first):
-- ALTER SERVICE AI_PLATFORM.WORKBENCH.KW_SPIKE SET AUTO_SUSPEND_SECS = 1800;  -- resumes on next request

-- Teardown after the spike:
-- DROP SERVICE IF EXISTS AI_PLATFORM.WORKBENCH.KW_SPIKE;
-- DROP COMPUTE POOL IF EXISTS KW_SPIKE_POOL;
-- DROP IMAGE REPOSITORY IF EXISTS AI_PLATFORM.WORKBENCH.KW_IMAGES;
