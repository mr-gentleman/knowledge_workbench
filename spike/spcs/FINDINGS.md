# SPCS spike — can the Knowledge Workbench be React on Snowpark Container Services?

#claude 2026-10-23 · branch `claude/spcs-spike` (from `claude/REL-08-m1-hardening`) · status: **built and checked locally; not deployed** (needs Chris's OK + the grants in [handoff.sql](handoff.sql)).

## Verdict so far

**Provisionally passes on everything that can be checked from here. The two criteria that decide it (login, then the identity header and caller's rights) can only be proven with a live deploy.** Nothing found so far argues against React-first. The biggest risk turned out smaller than expected: **today's Streamlit app is already an SPCS service.** `KNOWLEDGE_WORKBENCH` runs as service `AI_PLATFORM.WORKBENCH.STPLATSTREAMLIT315687177` on `SYSTEM_COMPUTE_POOL_CPU`, from a Snowflake-managed image. React on SPCS is the same substrate with our own image, not a new platform.

| Criterion | Status | Evidence kind |
|---|---|---|
| Tolerable deploy loop | **Likely pass.** Local UI loop is instant; image build 1m19s cold / ~10s warm; push and rollout not yet measured | local run, local podman build + boot |
| Snowflake login works | **Unverified.** Public endpoint = Snowflake login by design | docs + spec only |
| Viewer identity available (caller's rights) | **Wired, unverified live.** Header identity + caller's-rights probe built and unit-tested | unit tests (fake repo) |
| Idle cost acceptable | **Pass on the shared pool (≈ today's cost); ~80 cr/mo worst case on a dedicated XS pool** | measured account metering |
| Feels fast | **Pass locally** (API round trip 8–53 ms against a fake repo). Real latency = Snowflake query time, same as SiS minus Streamlit reruns | local preview |

## What was built (`spike/spcs/`)

- `web/`: Vite + React 18 port of the mockup artifact (CodeMirror 5 editor, IBM Plex/Instrument Serif fonts). Everything is bundled; nothing loads from a CDN. Canon entries are still sample data. **Candidates are live:** the list reads `AI_PLATFORM.WORKBENCH.metric_candidate`, opening one loads a fresh baseline, and **Save** edits name, category, description and when-to-use through the API. Toasts show round-trip ms.
- `api/main.py`: FastAPI, 5 routes (`/healthz`, `/api/me`, `GET/PUT /api/candidates[/{id}]`). It calls `app/repositories.py` and `app/services.py` **unchanged**, so revision checks, the no-op save, duplicate-name warnings, `op_log`, query tags and the DEC-007 lock/heal all apply as-is.
- `api/spcs.py`: the only SPCS-specific code. It covers the OAuth session from `/snowflake/session/token`, viewer identity from the ingress header `Sf-Context-Current-User`, and the caller's-rights probe (service token + `.` + `Sf-Context-Current-User-Token`).
- `Dockerfile` (node build → python:3.11-slim), `service.yaml` (public endpoint, `executeAsCaller: true`, service role `kw_user`), `deploy.sh` (build → push → `snow spcs service upgrade` → wait for READY, printing timings), `handoff.sql`.
- `api/test_api.py`: 4 tests. A save is attributed to the header user; no identity → 401; `KW_DEV_USER` is ignored inside SPCS; a stale revision returns the conflict outcome and never writes.

**The one seam.** `app/db.py` imports Streamlit (`st.connection`, `st.cache_resource`). The API swaps `app.db.session` for the SPCS session and reuses the rest. That means the image carries `streamlit` as a dependency it barely uses. A real React build should split `db.py` into a framework-free core plus a Streamlit adapter, about 20 lines. That's the DEC-008 "isolate at the adapter boundary" point, and it held up: services and repositories needed **zero** changes.

## Criteria in detail

### 1. Deploy loop
Local run, from the repo root. The API reads and writes live data through `workbench_deploy` (role `WORKBENCH_APP`, browser SSO):
```
pip install -r spike/spcs/api/requirements.txt
cd spike/spcs/web && npm ci && npm run build && cd -
PYTHONPATH=.:spike/spcs KW_DEV_USER=<you> uvicorn api.main:api --port 8080   # serves web/dist + /api
PYTHONPATH=.:spike/spcs python -m unittest api.test_api -v
```
- **Inner loop (UI work):** `npm run dev` (Vite HMR) proxies `/api` to a local `uvicorn api.main:api`. Edits show instantly. `npm run build` takes 1.2 s. This loop is far faster than SiS's, which requires a deploy to see a change.
- **Outer loop (to Snowflake):** `spike/spcs/deploy.sh`. Image build with podman (`--platform linux/amd64`, emulated on Apple Silicon): **1m19s cold, ~10s warm after a UI-only change** (layer cache). Image is 726 MB, mostly pandas/pyarrow pulled in by snowpark + streamlit, so the first push will be slow and later pushes upload only changed layers. The container boots locally (`podman run`): `/healthz` returns 200 and the React index is served. Push and rollout aren't measured yet (no repository yet). SPCS rollout is a rolling restart, typically 1–3 min per the docs. Expect roughly 3–6 min end to end, against about 1 min for `scripts/deploy.sh` on SiS today. That's tolerable, because most iteration happens in the inner loop.
- Podman works. `snow spcs image-registry login` shells out to `docker`, so `deploy.sh` pipes `snow spcs image-registry token` into `podman login` instead. Docker Desktop is installed but its daemon wasn't running.

### 2. Snowflake login
A `public: true` endpoint sits behind Snowflake's own login (SSO/Okta, as for Snowsight). No auth code of ours is involved. **To verify on deploy:** open the URL from `SHOW ENDPOINTS`, sign in, and confirm the page loads for a user whose role holds `KW_SPIKE!KW_USER` and is refused for one whose role doesn't. **Open question:** does ingress check only the user's default role, or secondary roles too? Test it with a second person.

### 3. Viewer identity / caller's rights
- **Attribution (needed for writes):** ingress sets `Sf-Context-Current-User` on every request. `spcs.viewer()` uses only that header and refuses the save without it; the browser never supplies the actor. This meets the DEC-008 requirement that identity is trusted context, not form data. **Must verify on deploy:** send a request with a forged `Sf-Context-Current-User` through the public endpoint and confirm ingress overwrites or strips it. Run `curl -H 'Sf-Context-Current-User: NOT_ME' …` with a valid session cookie, then check `updated_by`. If ingress passes it through, the design needs a different identity source; this is the single most important live check.
- **Writes stay owner's-rights** as `WORKBENCH_APP`, the same isolation as the SiS app. No new write paths open up on `AI_PLATFORM.DICTIONARY`.
- **Caller's rights:** `executeAsCaller: true` is in the spec. `GET /api/me` opens a caller's-rights connection and returns `CURRENT_USER()` / `CURRENT_ROLE()`. Effective privileges are the intersection of the caller's privileges and the caller grants given to `WORKBENCH_APP`. This is a better fit than SiS for the future **Validate SQL / Run preview** feature: SME SQL could run with the SME's own read privileges instead of a shared role. This is a real advantage of SPCS over SiS owner's-rights.

### 4. Idle cost
Measured from `SNOWFLAKE.ACCOUNT_USAGE.SNOWPARK_CONTAINER_SERVICES_HISTORY`, last 30 days:

| Pool | Shape | Credits/30d | ≈ credits/node-hr |
|---|---|---|---|
| `SYSTEM_COMPUTE_POOL_CPU` (runs SiS today, 49 services, 4 active nodes) | CPU_X64_S, 1–150 nodes | 171.6 | 0.23 |
| `TUTORIAL_COMPUTE_POOL` (1 always-on node) | CPU_X64_XS | 80.0 | 0.11 |

- **Option A, run on `SYSTEM_COMPUTE_POOL_CPU`:** marginal idle cost ≈ zero; the container bin-packs onto nodes that are already up for SiS and notebooks. This matches today's SiS cost profile. Unverified whether user-created services are allowed on a system pool. `WORKBENCH_APP` already has USAGE on it.
- **Option B, dedicated XS pool:** ≈ 0.11 cr/hr, ≈ 80 credits/month always-on. Less with service `AUTO_SUSPEND_SECS` plus the pool's auto-suspend, at the cost of a cold start (minutes) after idle.
- Warehouse cost for queries is unchanged from SiS (same `BIZ_AI_WH`, same queries).
- Aside, not part of this spike: `TUTORIAL_COMPUTE_POOL` used 80 credits in the last 30 days keeping one node up for `SLACKBOT_SERVICE3` (RUNNING, owner `TEST_ROLE`, created May 2025; `SLACKBOT_SERVICE_DEV` beside it is FAILED). Worth checking whether it's still wanted.

### 5. Feels fast
Locally (fake repository), list/open/save round trips took 8–53 ms, with no rerun and no flicker; switching metrics is instant because the explorer, editor state and drafts live in the browser. Against Snowflake, each action costs exactly its own query or queries, with no whole-page rerun. **To verify on deploy:** the toast/meta ms values on a real open and save. Expect a few hundred ms (warehouse time).

## What Chris must do or approve (nothing here has been run)

1. **Approve the grants in [handoff.sql](handoff.sql)** (ACCOUNTADMIN / CoCo):
   - `CREATE IMAGE REPOSITORY` and `CREATE SERVICE` on `AI_PLATFORM.WORKBENCH`
   - `BIND SERVICE ENDPOINT ON ACCOUNT`, account-level, needed for a browser-reachable endpoint
   - `CALLER USAGE ON WAREHOUSE BIZ_AI_WH`, only for the caller's-rights check
2. **Pick compute.** Option A, `SYSTEM_COMPUTE_POOL_CPU` (no new pool, try first), or option B, `KW_SPIKE_POOL` (XS, ≈ 80 cr/mo worst case, drop after the spike).
3. **As `WORKBENCH_APP`:** `CREATE IMAGE REPOSITORY AI_PLATFORM.WORKBENCH.KW_IMAGES`, then `spike/spcs/deploy.sh --create` (podman machine running). Then grant `KW_SPIKE!KW_USER` to your role.
4. **Live checks (about 30 min):** login, forged-header test, `/api/me` caller's-rights output, one real Save on a `ZZ_*` test candidate. For the save, confirm the `updated_by`, `revision` and `op_log` rows. Then record the deploy-loop timings `deploy.sh` prints.
5. **Teardown** lines are at the bottom of `handoff.sql`.

## If it passes: what React-first costs beyond the spike
- Split `app/db.py` (framework-free core + Streamlit adapter); drop `streamlit` from the image.
- Session lifecycle: the spike holds one cached owner's-rights session, matching SiS's single shared connection. The SPCS token file rotates. A long-idle session will need reconnect-on-expiry, folded into `_heal`. Not built here.
- A process-wide lock means one uvicorn worker, as today. Fine for SME scale; multi-instance needs DEC-007's connection leasing first (DEC-008).
- The editor moves to CodeMirror 6 for real autocomplete against fact-table columns. CM5 was kept to port the mockup as-is.
- Ops ownership (DEC-008): image builds, a base-image refresh cadence, and service logs (`snow spcs service logs`) become ours. SiS hides these today.
