# Knowledge Workbench — app design notes

Lessons learned + design decisions from building/deploying v1 (Sep 30 – Oct 20, 2026).
Companion docs: `handoff-2026-10-16.md` (state + settled schema decisions), `features.md`
(feature list), `open-items.md` (legacy import, schema placement).

## Status 2026-10-21 (supersedes the 2026-10-20 block below)

- App renamed **`AI_PLATFORM.WORKBENCH.KNOWLEDGE_WORKBENCH`** (owner `WORKBENCH_APP`, `BIZ_AI_WH`,
  `SYSTEM_COMPUTE_POOL_CPU`, container runtime). Stray personal copy dropped.
- **Deployed from this repo with the Snowflake CLI** — `~/.local/bin/snow` (3.30.0; 3.7.0 can't do
  container runtime) and connection `workbench_deploy` in `~/.snowflake/connections.toml`
  (login `clenzini`, browser SSO, role `WORKBENCH_APP`, chmod 600). Deployed 179b843, then the
  `pyproject.toml` fix (729bb7d): the container runtime **refuses to start without a dependency
  file**, and `--prune` had removed the Snowsight-generated one.
- **Multi-file app works when deployed** (`app/` on the stage) → single-file bundle can retire (PLAT-01).
- **All viewers share one Snowflake session** (observed: two windows, one SESSION_ID) →
  `db_lock` fix, DEC-004. Live as of this deploy.
- Pending: published-app smoke test (REL-01/03/06/07, test row `ZZ_COCO_TEST`), delete the
  Workspace copy, idle auto-shutdown (the app and Workspace preview poll LS/DESCRIBE every ~2.5 s,
  24/7), PLAT-06 backups (retention is 1 day).
- Process: Claude + Codex + CoCo work via `docs/collaboration.md`; `Agent:` commit trailers.

## Status at restart (2026-10-20)

- Schema, tables, sequences, grants: live and verified.
- App `AI_PLATFORM.WORKBENCH.VO0TBC_5CROCK7E6` (title "Knowledge_Workbench", owner `WORKBENCH_APP`).
- **Create + edit verified** via the workspace preview: candidate #1 "NRR Year-over-Year (YoY)",
  rev 1 create → rev 2 edit (one word in disambig, change note captured), attributed to CLENZINI.
- **Published app was stale**: only `VERSION$1` existed (first deploy, without `app/`). Fix in progress:
  save the single-file build in the workspace → **Deploy** → confirm `VERSION$2` via
  `DESCRIBE STREAMLIT AI_PLATFORM.WORKBENCH.VO0TBC_5CROCK7E6` (`last_version_name`).
- Still to smoke-test on the published app: no-op save → "No changes to save", no new revision.

## Deployment lessons (Snowsight)

- **Container runtime** (compute pool `SYSTEM_COMPUTE_POOL_CPU` + query warehouse `BIZ_AI_WH`).
  Compute pool runs Python; warehouse runs SQL. Owner role needs USAGE on both.
- Connect with `st.connection("snowflake").session()` — not `get_active_session()` (older runtime).
- **Viewer identity from `st.user`**, never `CURRENT_USER()` (can be the app's service user here).
  Verified: `st.user` returned CLENZINI.
- App runs with **owner's rights** → owner = `WORKBENCH_APP` (writes WORKBENCH only, nothing on DICTIONARY).
- Workspace: files **auto/manually save in the workspace**; **Deploy** creates a new app version.
  Unsaved edits → Deploy ships the old files. "Edit" opens a *preview* that runs from workspace files with
  **your** rights — it can work while the deployed app is broken. Always smoke-test the deployed app.
- Multi-file `app/` package failed on the first deploy (`ModuleNotFoundError: app`) → using
  **`streamlit_app_single.py`** (generated from the multi-file source; edit the source, regenerate).
  Root cause was `VERSION$1` shipping **without `app/`**, not a SiS limit on packages — the stage root
  is the import root, so `from app import …` works when `app/` is uploaded next to `streamlit_app.py`.
  Retry multi-file; once a published deploy is smoke-tested, delete the single-file build.
- **Dependencies (container runtime):** read from `pyproject.toml` / `requirements.txt` only —
  `environment.yml` is the warehouse-runtime (conda) format and was ignored, so it's removed.
  Without an attached artifact repository the app gets only what ships with the runtime
  (Python 3.11, Streamlit ≥1.50, Snowpark) — enough today. Add `pyproject.toml` + an artifact
  repository when a pip package is needed (e.g. the SQL-editor spike).
  - #coco 2026-10-22 — supersedes "add `pyproject.toml` when a pip package is needed": the
    container runtime refuses to start without a dependency file ("pyproject.toml file does
    not exist"), so a minimal unpinned `pyproject.toml` is always deployed (729bb7d).
  - #coco 2026-10-22 — supersedes "without an attached artifact repository": the app now has
    `snowflake.snowpark.pypi_shared_repository` attached (visible in SHOW STREAMLITS), and
    `SNOWFLAKE.PYPI_REPOSITORY_USER` is granted to PUBLIC, so WORKBENCH_APP can use it. PyPI
    packages and `==` pins in `pyproject.toml` now work. Syntax is plural:
    `ALTER STREAMLIT … SET ARTIFACT_REPOSITORIES = (…)`. CLI 3.30 has no snowflake.yml field
    for it; `--replace` on an existing app only ALTERs diffs so it survives, and
    `scripts/deploy.sh` re-sets it in case the app is ever recreated.
  - #coco 2026-10-22 — component check: a component must ship its whole JS bundle. SiS blocks
    runtime script loads from outside (streamlit-monaco fetches Monaco from cdn.jsdelivr.net and
    hangs on "Loading..."). Before adding one, grep its package for `https://cdn`. Ace-based
    streamlit-code-editor / streamlit-ace are self-contained and work.
- Deploy target needs the schema set explicitly (was the "unable to deploy" error).
- A second personal copy exists in `USER$CLENZINI.PUBLIC` (workspace's own app) — safe to drop.
  - #coco 2026-10-22 — done: that copy is dropped, and the live app was renamed
    `VO0TBC_5CROCK7E6` → `KNOWLEDGE_WORKBENCH` (owner unchanged).
- **Next: GitLab repo + Git-backed workspace** so deploys come from git, not hand uploads.
  Later: GitLab CI → `snow streamlit deploy`.

## Design decision: history / changelog

**Store full snapshots, display changes.** (Storage is already right — keep it.)

- Default History view = **only the fields that changed vs the previous revision**, old → new
  (e.g. `disambig: "Primary NRR…" → "The primary NRR…"`). A one-word edit is otherwise invisible.
- On demand: **"View full record as of rev N"** — the stored snapshot answers "what did it say on date X"
  with no reconstruction. Diffs-only storage would make that hard and fragile; full snapshots make both cheap.
- Long text fields (description, SQL): show a word/line-level diff, not two blobs.
- Later: combined metric + PI timeline ("Gabe changed the definition; Matt changed the monthly SQL").

## Docket: discovery + search

Today: `full_name ILIKE '%term%'` — substring on name only. Misses typos, synonyms, meaning, descriptions.
Search is also the front line of duplicate prevention: people can't avoid duplicating what they can't find.

Tiered plan (cheap → rich):
1. **Search all text fields** — name + description + disambig (+ synonyms once that table exists). Trivial.
2. **Typo tolerance** — Snowflake `JAROWINKLER_SIMILARITY` / `EDITDISTANCE` on names; rank by score.
3. **Semantic** — "net retention" finds "NRR YoY". Options: **Cortex Search service** over
   candidate + core (hybrid keyword + semantic, managed index) or `AI_EMBED` + `VECTOR_COSINE_SIMILARITY`.
   Cortex Search is likely the least code; check cost/refresh lag.
4. **One matcher, two consumers**: the same similarity search powers browse/search *and* the
   "possible duplicate" warning at save time (currently exact-name only). Warn, never block, show the
   suspected match's definition — no fake "95% duplicate" scores.

## Docket: other UX items
- Hide free-text `category` until it has a defined list (people won't know what to type).
- Tags: deferred until a consumer exists (browse filter is the likely first one); if prototyped,
  multiselect that suggests existing tags first.
- Double-submit protection on create; refresh header/revision after save.

## Work tracking plan
- **GitLab Issues + Boards = system of record** for granular work (next to the code; MRs `Closes #N`).
  Labels mirror `features.md`: `area::*` (find/author/check/lifecycle/history/serve/platform),
  `priority::v1|next|later`, optional `state::*`. Board columns = areas (domain view, drag to order);
  second board Open/Doing/Done. Milestone `V1` = progress toward retiring Sheets.
  Scoped `key::value` labels need Premium (likely available — verify by creating a `test::a` label).
- **Jira = stakeholder visibility only**: one ticket per milestone linking to the GitLab board. Never mirror
  individual issues. Optional GitLab↔Jira integration links commits/MRs mentioning a Jira key.
- After the repo exists: Claude bulk-creates labels, milestone, and one issue per `features.md` row (glab/API).
- Later: group-level board with `pillar::*` labels = cheap first cut of the 8-pillar dashboard.
