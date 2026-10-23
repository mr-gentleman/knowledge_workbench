# CoCo handoff: SPCS spike setup

Three parts. CoCo does 1 and 3 in Snowflake. Part 2 runs on Chris's Mac, because building an image needs podman and CoCo can't build one.

---

## Part 1: paste into CoCo (as ACCOUNTADMIN)

> Set up Snowpark Container Services for the Knowledge Workbench SPCS spike. Fully qualify every name (DB.SCHEMA.OBJECT); don't rely on USE. Run as ACCOUNTADMIN unless a step says otherwise. After each grant, confirm it with `SHOW GRANTS TO ROLE WORKBENCH_APP`. Stop and report if anything errors. Don't work around errors.
>
> ```sql
> -- Grants to the app role (it already owns the Streamlit app and writes only AI_PLATFORM.WORKBENCH)
> GRANT CREATE IMAGE REPOSITORY ON SCHEMA AI_PLATFORM.WORKBENCH TO ROLE WORKBENCH_APP;
> GRANT CREATE SERVICE          ON SCHEMA AI_PLATFORM.WORKBENCH TO ROLE WORKBENCH_APP;
> GRANT BIND SERVICE ENDPOINT   ON ACCOUNT                      TO ROLE WORKBENCH_APP;
> GRANT CALLER USAGE ON WAREHOUSE BIZ_AI_WH                     TO ROLE WORKBENCH_APP;
>
> -- Image repository, owned by the app role
> USE ROLE WORKBENCH_APP;
> CREATE IMAGE REPOSITORY IF NOT EXISTS AI_PLATFORM.WORKBENCH.KW_IMAGES;
> SHOW IMAGE REPOSITORIES IN SCHEMA AI_PLATFORM.WORKBENCH;   -- report repository_url
> USE ROLE ACCOUNTADMIN;
> ```
>
> Then answer one question without creating anything: can a user-created service run on `SYSTEM_COMPUTE_POOL_CPU`? WORKBENCH_APP already has USAGE on it, and the Streamlit app runs there as service `AI_PLATFORM.WORKBENCH.STPLATSTREAMLIT315687177`. Check the docs or any restriction you know of. If the answer is no or unclear, create a fallback pool:
>
> ```sql
> CREATE COMPUTE POOL IF NOT EXISTS KW_SPIKE_POOL
>   MIN_NODES = 1 MAX_NODES = 1 INSTANCE_FAMILY = CPU_X64_XS
>   AUTO_RESUME = TRUE AUTO_SUSPEND_SECS = 600 INITIALLY_SUSPENDED = TRUE
>   COMMENT = 'Knowledge Workbench SPCS spike - drop after the spike';
> GRANT USAGE, MONITOR ON COMPUTE POOL KW_SPIKE_POOL TO ROLE WORKBENCH_APP;
> ```
>
> Report: the repository_url, which pool to use, and the grant list.

---

## Part 2: Chris, on the Mac (repo worktree `kw-spcs-spike`)

The podman machine must be running (`podman machine start` if not). Then:

```bash
spike/spcs/deploy.sh --create
```

Add `KW_POOL=KW_SPIKE_POOL` in front of the command if CoCo created the fallback pool. The script logs in to the registry, builds and pushes the image, creates `AI_PLATFORM.WORKBENCH.KW_SPIKE`, waits for READY, and prints timings and the endpoint URL. Paste the timings into FINDINGS.md (criterion 1). Later deploys run without `--create`.

If `--create` fails on the system pool, have CoCo create the fallback pool, then rerun with `KW_POOL=KW_SPIKE_POOL`.

---

## Part 3: paste into CoCo (after the service is READY)

> The Knowledge Workbench spike service `AI_PLATFORM.WORKBENCH.KW_SPIKE` is deployed. Do the following:
>
> ```sql
> -- App access = membership in one plain account role. No in-app permissions: whoever gets in can do everything.
> CREATE ROLE IF NOT EXISTS WORKBENCH_USER COMMENT = 'People who may open the Knowledge Workbench';
> GRANT SERVICE ROLE AI_PLATFORM.WORKBENCH.KW_SPIKE!KW_USER TO ROLE WORKBENCH_USER;
> GRANT ROLE WORKBENCH_USER TO USER CLENZINI;   -- add SMEs the same way later
> SELECT SYSTEM$GET_SERVICE_STATUS('AI_PLATFORM.WORKBENCH.KW_SPIKE');
> SHOW ENDPOINTS IN SERVICE AI_PLATFORM.WORKBENCH.KW_SPIKE;            -- report ingress_url
> SELECT SYSTEM$GET_SERVICE_LOGS('AI_PLATFORM.WORKBENCH.KW_SPIKE', 0, 'web', 50);
> ```
>
> Also check whether the service can auto-suspend when idle. If supported, set `ALTER SERVICE AI_PLATFORM.WORKBENCH.KW_SPIKE SET AUTO_SUSPEND_SECS = 1800;`. Then report the `auto_suspend_secs` value from `SHOW SERVICES LIKE 'KW_SPIKE' IN SCHEMA AI_PLATFORM.WORKBENCH`.

**Chris, the live checks after Part 3** (FINDINGS.md has the details):
1. Open the ingress URL and sign in. The page should load and the green banner should show your user name.
2. Open `<url>/api/me`. Read `user` and `caller.current_user` / `current_role`.
3. Save an edit on a `ZZ_*` test candidate. Ask CoCo to show the latest `AI_PLATFORM.WORKBENCH.op_log` and `AI_PLATFORM.WORKBENCH.revision` rows for it. Both should be attributed to you.
4. Forged-header test: in the browser devtools console, on the app's own page, run
   `fetch('/api/me',{headers:{'Sf-Context-Current-User':'NOT_ME'}}).then(r=>r.json()).then(console.log)`.
   `user` must still be you. If it shows `NOT_ME`, the identity design fails. Stop and flag it.
5. Speed (FE-01 gate 3): run the search-timing snippet from FINDINGS.md in the console, and note the ms shown in the Save toast from step 3. Record both in FINDINGS.md.

**Teardown** (CoCo, when the spike ends): `DROP SERVICE IF EXISTS AI_PLATFORM.WORKBENCH.KW_SPIKE; DROP COMPUTE POOL IF EXISTS KW_SPIKE_POOL; DROP IMAGE REPOSITORY IF EXISTS AI_PLATFORM.WORKBENCH.KW_IMAGES;`
