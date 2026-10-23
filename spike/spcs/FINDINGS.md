# SPCS spike — can the Knowledge Workbench be React on Snowpark Container Services?

#claude 2026-10-23 · branch `claude/spcs-spike` (from `claude/REL-08-m1-hardening`) · status: **deployed and live-checked 2026-10-23** (FE-01 verdict below).

## Verdict so far

**Live (2026-10-23): login and attribution pass. Search is fast. Save misses the proposed 1.5 s bar, at 2.8 s. That cost is the save transaction itself (SiS saves log 1.7–2.2 s), not the front end. See the FE-01 gate.** The earlier pre-deploy notes follow. The biggest risk turned out smaller than expected: **today's Streamlit app is already an SPCS service.** `KNOWLEDGE_WORKBENCH` runs as service `AI_PLATFORM.WORKBENCH.STPLATSTREAMLIT315687177` on `SYSTEM_COMPUTE_POOL_CPU`, from a Snowflake-managed image. React on SPCS is the same substrate with our own image, not a new platform.

| Criterion | Status | Evidence kind |
|---|---|---|
| Tolerable deploy loop | **Likely pass.** Local UI loop is instant; image build 1m19s cold / ~10s warm; push and rollout not yet measured | local run, local podman build + boot |
| Snowflake login works | **Pass** (see FE-01 gate 1) | published app |
| Viewer identity available (caller's rights) | **Pass.** Header identity = CLENZINI and can't be forged; the caller's-rights probe works but runs as the user's *default* role (`GLEAN_QUERY_SNOWFLAKE_ROLE`), not `WORKBENCH_USER` | published app |
| Idle cost acceptable | **~80 cr/mo, always on.** The shared pool refuses this service type, and auto-suspend is refused for services with public endpoints (see Deploy log). So the dedicated XS pool never idles down | live deploy |
| Feels fast | **Pass locally** (API round trip 8–53 ms against a fake repo). Real latency = Snowflake query time, same as SiS minus Streamlit reruns | local preview |

## Deploy log (2026-10-23, driven by Claude at Chris's request)

- Step 1 (grants, `KW_IMAGES` repo, `KW_SPIKE_POOL`) done by Chris/CoCo. Verified with `SHOW GRANTS TO ROLE WORKBENCH_APP`.
- **System pool is refused:** `SYSTEM_COMPUTE_POOL_CPU can only support services of type [NOTEBOOK, MODEL_SERVING, STREAMLIT, ML_JOB, APPLICATION_SERVICE, REMOTE_BUILD]`. So the idle cost is the dedicated XS pool (≈ 0.11 cr/hr), plus service auto-suspend.
- **Registry login gotcha:** the password is the *whole* `snow spcs image-registry token --format JSON` blob, not its `token` field. With just the field, login fails with "invalid username/password". `deploy.sh` is fixed.
- Service `AI_PLATFORM.WORKBENCH.KW_SPIKE` on `KW_SPIKE_POOL`, image `kw-spike:e61742c`: **build+push 22 s (warm), rollout 48 s to READY, including the pool resume.**
- Access: `WORKBENCH_USER` was created by SECURITYADMIN, granted to `CLENZINI` and to `SYSADMIN`, and holds `KW_SPIKE!KW_USER` (granted by WORKBENCH_APP).
- Endpoint: **https://fmje2s-activecampaign-fm00411.snowflakecomputing.app** (provisioning took a few minutes after READY).
- **First live read failed on paramstyle:** `/api/candidates` returned 500 because our own `snowflake.connector.connect()` defaulted to `pyformat` while the repository SQL uses `?` (the `'%' || ? || '%'` in `list_candidates` raised "unsupported format character"). Fixed by binding `qmark` (a01d545) in one redeploy: 29 s build+push, 64 s rollout.
- **Auto-suspend refused:** `ALTER SERVICE AI_PLATFORM.WORKBENCH.KW_SPIKE SET AUTO_SUSPEND_SECS = 1800` → `395101: Auto suspend is not supported for services with public endpoints`. `auto_suspend_secs` stays 0. Cost control = `ALTER SERVICE … SUSPEND` by hand, or a scheduled suspend/resume, or teardown.
- Live checks 1–5 run 2026-10-23; results in the FE-01 table.
- **Save → one CALL (merged `claude/save-proc`, PLAT-09):** `/api/metrics/save` now calls `services.save_metric`, which runs one `CALL AI_PLATFORM.WORKBENCH.save_metric(?)` in place of ~7 statements. The client may send `op_id` for safe retries. The branch estimates 2.4 s → ~1.8–2.2 s, with a floor of ~1.5 s on standard tables. **Blocked:** the procedure doesn't exist yet (`SHOW PROCEDURES` returns nothing). `sql/004_save_metric_proc.sql` must be created as ACCOUNTADMIN (docs/save-proc-handoff.md §1–2) *before* the next spike deploy, or every save fails. Re-measure gate 3's save after that.
- **One-call save measured (image 1826dfa, 3 saves on ZZ_M1_TEST, 18:02–18:05): slower, not faster.** The `CALL` takes 4745 / 4241 / 3970 ms, plus a 70–170 ms calc pre-read, against ~2.8 s for the old client path. Per call (from QUERY_HISTORY): about 400 ms from CALL start to the first statement; **~750 ms of dead time between `SYSDATE()` and the replay SELECT, every time** (likely the ~19 `:=` VARIANT assignments, each evaluated by the engine); the replay and change-check SELECTs, 250 ms; then the transaction BEGIN 110 + UPDATE 380 + revision INSERT 540–590 + op_log INSERT 280–315 + COMMIT 620–670 ≈ 2 s; plus 100–300 ms gaps between statements. Takeaway: on standard tables, the DML and COMMIT alone cost ~2 s whatever the call style. The procedure adds ~1.5–2 s on top. Attribution is still CLENZINI on op_log and revision.

## FE-01 gate (DEC-018): all three must pass

DEC-018 (2026-10-23, on `claude/product-focus`) makes React on SPCS the V1 front end, gated on this spike. **If attribution fails, React on SPCS is off and DEC-018 is reopened. It does not get downgraded.**

| Gate | Status | Measurement to record (live) |
|---|---|---|
| 1. Snowflake login works in the container | **Pass** (positive path) | Chris (CLENZINI, via `WORKBENCH_USER`) loaded the app after Okta SSO in his own browser. Okta fails inside the Claude Code browser pane (FastPass/VPN), so use a normal browser. Not tested: refusal for a user without `KW_USER` |
| 2. Write attributed to the signed-in user, not a service account | **Pass** | Save on `ZZ_M1_TEST` (candidate 4 → rev 3, 17:31 CDT): `metric_candidate.updated_by`, `revision.actor` and `op_log.actor` (`candidate.edit`, committed) are all `CLENZINI` (read-only SQL). `/api/me` → `user: CLENZINI`, `caller: CLENZINI / GLEAN_QUERY_SNOWFLAKE_ROLE`. Forged `Sf-Context-Current-User: NOT_ME` → `user` still `CLENZINI` |
| 3. One read + one write fast enough for search-as-you-type and save | **Search pass; save misses the proposed bar** | Search, 7 keystrokes from the browser: 184, 185, 219, **222 (p50)**, 262, 276, **531 (max)** ms, against a bar of ≲ 300. Save: the server-side transaction (`op_log.duration_ms`) took **2814 ms**, against a bar of ≲ 1.5 s, and the toast is ≥ that. The same transaction from SiS logged 1694–2227 ms today, so the cost is the multi-statement save, not SPCS or React. Chris decides whether that bar holds or the save gets cheaper first (FE-02 / one-call save) |

Search timing, run in the browser console on the deployed app. It calls the real server-side search (`repositories.list_candidates`, ILIKE, LIMIT 200) once per keystroke:
```js
const qs=['n','ne','net','net ','net n','net ne','net new'], t=[];
for (const q of qs) { const s=performance.now(); await fetch('/api/candidates?search='+encodeURIComponent(q)); t.push(Math.round(performance.now()-s)); }
t.sort((a,b)=>a-b); console.log('search ms', t, 'p50', t[3], 'max', t[6]);
```
Design note for FE-02: every database call shares one connection behind a process-wide lock (DEC-007). Keystroke searches therefore queue behind each other and behind saves. If the measured p50 is borderline, the fix is a client-side debounce, or filtering the already-loaded list (≤ 200 rows) in the browser. That isn't a reason to fail the gate.

## Access model (agreed with Chris, 2026-10-23): as simple as possible

- **Login:** Snowflake's own SSO on the public endpoint. We build no auth.
- **Who:** the attributed user is the Snowflake login name from `Sf-Context-Current-User` (e.g. `CLENZINI`), the same value the SiS app already writes to `updated_by`.
- **Gate:** one account role, `WORKBENCH_USER`, holds the service role `KW_USER`. Add a person by granting them `WORKBENCH_USER`.
- **Inside the app:** no permissions. Anyone who gets in can do everything. Data access is the service's own role (`WORKBENCH_APP`), so users need no table grants.
- **Live check:** does ingress honor `WORKBENCH_USER` as a *secondary* role, or only as the user's default role? If only the default role, users would need `DEFAULT_SECONDARY_ROLES = ('ALL')` (Snowflake's current default) or a different grant path.

## What was built (`spike/spcs/`)

- `web/`: Vite + React 18 port of the mockup artifact (CodeMirror 5 editor, IBM Plex/Instrument Serif fonts). Everything is bundled; nothing loads from a CDN. Canon entries are still sample data. **Candidates are live:** the list reads `AI_PLATFORM.WORKBENCH.metric_candidate`, opening one loads a fresh baseline. The page follows **DEC-020**: read mode (definition text, expandable SQL cards) → one **Edit** over the whole page (definition plus add/remove implementations, local draft only) → **Save changes** or **Cancel** (discards everything). For live candidates the spike persists only the definition; saving implementations waits for `services.save_metric` (the one-call-save lane). Toasts show round-trip ms.
- `api/main.py`: FastAPI, 5 routes (`/healthz`, `/api/me`, `GET /api/candidates[/{id}]`, `POST /api/metrics/save`). The save takes the request shape from `docs/plans/metric-save-contract.md` and returns the contract's `status` (`saved | no_change | invalid | conflict`). Until `save_metric` exists, it maps onto `services.save_candidate_edit` and refuses non-empty `calcs` with 501. It calls `app/repositories.py` and `app/services.py` **unchanged**, so revision checks, the no-op save, duplicate-name warnings, `op_log`, query tags and the DEC-007 lock/heal all apply as-is.
- `api/spcs.py`: the only SPCS-specific code. It covers the OAuth session from `/snowflake/session/token`, viewer identity from the ingress header `Sf-Context-Current-User`, and the caller's-rights probe (service token + `.` + `Sf-Context-Current-User-Token`).
- `Dockerfile` (node build → python:3.11-slim), `service.yaml` (public endpoint, `executeAsCaller: true`, service role `kw_user`), `deploy.sh` (build → push → `snow spcs service upgrade` → wait for READY, printing timings), `handoff.sql`.
- `api/test_api.py`: 6 tests. A save is attributed to the header user; no identity → 401; `KW_DEV_USER` is ignored inside SPCS; a stale revision returns `conflict` and never writes; an unchanged draft returns `no_change` and never writes; `calcs` are refused until `save_metric` exists.

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

Pasteable step-by-step for CoCo: [COCO_HANDOFF.md](COCO_HANDOFF.md).

1. **Approve the grants in [handoff.sql](handoff.sql)** (ACCOUNTADMIN / CoCo):
   - `CREATE IMAGE REPOSITORY` and `CREATE SERVICE` on `AI_PLATFORM.WORKBENCH`
   - `BIND SERVICE ENDPOINT ON ACCOUNT`, account-level, needed for a browser-reachable endpoint
   - `CALLER USAGE ON WAREHOUSE BIZ_AI_WH`, only for the caller's-rights check
2. **Pick compute.** Option A, `SYSTEM_COMPUTE_POOL_CPU` (no new pool, try first), or option B, `KW_SPIKE_POOL` (XS, ≈ 80 cr/mo worst case, drop after the spike).
3. **As `WORKBENCH_APP`:** `CREATE IMAGE REPOSITORY AI_PLATFORM.WORKBENCH.KW_IMAGES`, then `spike/spcs/deploy.sh --create` (podman machine running). Then grant `KW_SPIKE!KW_USER` to your role.
4. **Live checks (about 30 min):** login, forged-header test, `/api/me` caller's-rights output, one real Save on a `ZZ_*` test candidate. For the save, confirm the `updated_by`, `revision` and `op_log` rows. Then record the deploy-loop timings `deploy.sh` prints.
5. **Teardown** lines are at the bottom of `handoff.sql`.

## Prior art in this account: Chris's Slackbot (SPCS, Apr–May 2025)

Read-only inspection, 2026-10-23: `TUTORIAL_DB.DATA_SCHEMA.SLACKBOT_SERVICE3` (live spec, grants, EAI, network rule, logs). Source is in `~/Downloads/Chris_Third`, matching image `slackbot3:v2`.

| | Slackbot | Workbench spike |
|---|---|---|
| **Ingress** | Public endpoint `slackendpoint:3000`, but it serves only a stub readiness server. Slack traffic arrives through **Socket Mode**, an outbound websocket, so nothing uses the URL. No service role is granted, so no person can open it either. | Public endpoint `ui:8080` is the product: browser → Snowflake login → service role `KW_USER` → React and the API. |
| **Egress** | External access integration `SLACK_DEBUG_INTEGRATION` with network rule `SLACK_API_RULE` (EGRESS to `slack.com`, `wss-primary.slack.com`, `*.slack.com`, `*.slack-msgs.com` on :443). Slack tokens come from Snowflake **secrets**, mounted as env vars. | **None needed.** Snowflake is reached internally, and fonts and JS are bundled, so there's no network rule, no integration and no secrets. |
| **Snowflake auth** | `/snowflake/session/token` OAuth, owner's rights as `TEST_ROLE`. The warehouse is hardcoded (`TEAM_DATA_LARGE`). | Same token-file pattern (owner's rights as `WORKBENCH_APP`); the warehouse comes from the spec env. |
| **Per-user identity** | Slack user ID only; every query runs as `TEST_ROLE`. | `Sf-Context-Current-User` for attribution, plus an optional caller's-rights connection. |
| **Image** | `python:3.11-slim`, `COPY . .`, which ships every draft and legacy `main*.py`. Unpinned version ranges. | Multi-stage build; copies only `app/`, `api/` and the built `dist/`; pinned versions. |
| **Activity** | The last 40 log lines are all readiness probes (`GET /` every 5 s). No bot traffic is visible. | n/a |

Takeaways: the token-file connection, the readiness probe and the podman → registry → `CREATE SERVICE` loop are already proven here by Chris. The Workbench is *simpler* on the network side, since it needs no egress at all. What's new is real browser ingress: the login, the service-role gate and identity headers. Those are exactly the unverified live checks above.

## If it passes: what React-first costs beyond the spike
- Split `app/db.py` (framework-free core + Streamlit adapter); drop `streamlit` from the image.
- Session lifecycle: the spike holds one cached owner's-rights session, matching SiS's single shared connection. The SPCS token file rotates. A long-idle session will need reconnect-on-expiry, folded into `_heal`. Not built here.
- A process-wide lock means one uvicorn worker, as today. Fine for SME scale; multi-instance needs DEC-007's connection leasing first (DEC-008).
- The editor moves to CodeMirror 6 for real autocomplete against fact-table columns. CM5 was kept to port the mockup as-is.
- Ops ownership (DEC-008): image builds, a base-image refresh cadence, and service logs (`snow spcs service logs`) become ours. SiS hides these today.
