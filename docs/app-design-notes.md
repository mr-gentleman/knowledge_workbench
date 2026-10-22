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

## MVP comparison requirements — 2026-10-22

Requested by #chris; recorded by #codex. Requirements below describe the authoring
MVP to establish in Streamlit and then compare with a bounded React prototype.
DEC-010 settles shared candidate/canon discovery; other layout proposals remain
hypotheses to test. See DEC-008–011
and the active task IDs in features.md. No implementation or migration is claimed.

### Required scope

- **Real existing knowledge:** import five representative metrics first, then the
  intended legacy metric collection per SERVE-02. Preserve authorship, identity
  mappings, PI relationships, and fact-table references. Reconcile counts/content
  and report exceptions. Legacy records do not bypass validation/promotion gates.
  Test examples include an incomplete candidate, a ready candidate, a canonical
  metric, and a metric with three PIs (e.g. daily/monthly/source contexts).
- **Metric workspace:** view/edit metric identity and its zero-to-many PIs together.
  Support incomplete candidate saves, adding/editing SQL implementations, visible
  revision-bound validation results, and explicit promotion readiness/actions.
  Canon remains editable. Saved, validated, canonical, and served are distinct.
  SQL execution success does not establish business correctness.
- **Fact-table workspace:** separate browse/edit page for existing fact-table
  knowledge (definition, grain, key, time field, required filters, gotchas).
  Link from a PI to its fact-table context and provide a clear return path.
- **Discovery/navigation:** sidebar or equivalent persistent navigation between
  Metrics and Fact tables; searchable lists in both areas; distinguish candidates
  from canon in metric results. Users must find knowledge without first knowing
  its database table or lifecycle state.
- **Editing safety:** visibly define save scope for metric versus PI edits.
  Preserve submitted drafts on failed saves/conflicts. Specify and test what
  happens to unsubmitted changes when changing PIs, metrics, or workspaces; no
  unexplained loss or misleading saved indicator. Draft retention versus explicit
  save/discard navigation remains a design choice, not a promise of autosave.
- **Lifecycle:** apply existing promotion/identity gates (including description,
  qualifying PI and name rules), with understandable missing requirements.
  AI origin is provenance, separate from candidate/canon status. Automated intake
  and a full machine-adjudication workflow remain deferred; a clearly labeled
  fixture may test how a future AI proposal is presented.

### Information architecture — agreed structure, open presentation

Two primary destinations: **Metrics** and **Fact tables**. Candidates and canon
share discovery and the metric workspace (DEC-010), with unmistakable badges and
optional **All / Canon / Candidates** filtering. The default filter and whether
filters are tabs or controls remain open. Candidates provides a focused review
queue without requiring a different editor.

Within the metric workspace, show identity/definition and an implementation list;
select or expand a PI to edit its SQL, context, fact-table link, and validation.
Daily/monthly views are PIs only when they express the same metric definition;
different business meanings remain distinct metrics (DEC-007).

This organizes around what an SME is working on while showing lifecycle status.
It does not merge candidate/canon database identities: promotion navigates to the
resulting canonical record and preserves the candidate's resolution/provenance.

A separate Candidates review destination may become useful for volume/bulk
adjudication; a standalone Implementations browser may become useful for finding
SQL across metrics. Neither is required for this initial comparison. Any later
alternate entry point should reuse the same detail/edit workflow.

### Comparison script and evidence

Use the same representative imported dataset and backend rules for both versions.
Keep prototype writes isolated from live authoring until coexistence is verified.
Use fixtures where needed, but label mocked saves/authentication/latency explicitly.

1. Find a known canonical metric and explain its definition; find an incomplete
   candidate and explain why it is not canon.
2. Inspect three PIs, choose the appropriate context, edit one SQL definition,
   handle a failed check, correct it, and see which exact revision passed.
3. Edit identity and PI content; demonstrate which Save affects which records.
   Promote a qualifying candidate and show the resulting canonical workspace.
4. Follow a PI to a fact table, edit its knowledge, return to the metric, and
   verify navigation, search state, selection, and draft handling.
5. Attempt a stale save from a second session; preserve the draft, explain the
   conflict, and demonstrate explicit recovery without overwriting another edit.
6. For the deployed React feasibility spike, verify permitted/denied app access,
   two distinct authenticated actors, and a scoped test write with correct human
   attribution. This gate is unverified until exercised in the actual account.
7. After the first slice works, make one realistic change (e.g. add a PI while
   retaining an identity draft) to sample maintenance effort.

Record task completion, confusion about status/meaning, navigation effort,
lost context, and user feedback. Measure warm interaction/save times separately
from cold start, SQL execution, and lock waiting; record backend calls per action.
Note implementation effort, framework workarounds, and files/rules touched by the
follow-up change. A two-day spike samples maintainability; it does not prove it.

Continue Streamlit to the usable authoring MVP (milestone A); then time-box the
React comparison to roughly two days initially. Oracle production cutover
(milestone B) is not required for the comparison. Switch only if workflow gains
and a credible authenticated deployment path justify the extra operating cost.


## Discovery and stewardship guidance — 2026-10-22

#chris direction, summarized by #codex; DEC-010/011 govern. Status and tasks stay in
features.md. This supplements the earlier MVP comparison rather than expanding it
to a full feedback platform.

- **V1 discovery:** combine text search with department and lifecycle filters.
  Verify a Finance-only search, mixed candidate/canon results, candidate-only review,
  and explicit discovery of rejected/retired records. Filters should compose and
  have an obvious clear action. Collapsible department groups are an optional
  alternative presentation of metadata, not filesystem-style ownership.
- **Candidate review:** show why attention is needed (unfinished content, failed
  checks, or pending human review) separately from source (SME, AI, other).
  Automated intake remains later scope; do not imply a source becomes trusted
  merely because SQL executes. Promotion still uses the established gates.
- **Future Needs attention:** candidate review, negative feedback, repeated confusion,
  usage/impact, recent additions, quality findings, and possible knowledge gaps.
  Positive feedback helps identify useful examples; it is not proof of correctness.
  Reuse the metric/fact-table editors and later dimension editors.
- **Evidence before scores:** where available, link feedback to the originating
  question/report, SQL/result, affected knowledge revision, timestamp, and complaint.
  Distinguish an actual missing metric from failed retrieval or ambiguous wording.
  Prioritization and quality-grade definitions are undecided; no invented scores.
- **Retirement acceptance:** reject a test candidate and confirm default search
  excludes it, explicit closed-record search finds it, and actor/reason/history
  remain available. Test canon/PI retirement in both UI and serving, including
  exclusion of older passing revisions. Fact-table dependency behavior needs an
  explicit rule before implementing its retirement flow. No cleanup executed here.

## Authentication learning for the future React spike — 2026-10-22

Documentation finding, not an account-level verification: custom SPCS browser apps
can use Snowflake ingress sign-in and service-role access; ingress supplies the
authenticated username to the backend. SPCS also supplies service credentials for
SQL execution. Thus a custom React app does not inherently require a custom login
system or manually managed database password.

Keep three concerns separate: permission to open the app, application authorization
to edit/review/promote, and SQL execution privileges. Preserve the scoped service
write model plus trusted human attribution (DEC-007/008); caller's rights is a
separate choice, not a prerequisite for attribution. Trust identity only at the
authenticated ingress boundary, never from a browser form.

Sources consulted in the discussion:
[Ingress authentication and identity](https://docs.snowflake.com/en/developer-guide/snowpark-container-services/working-with-services#ingress-authentication);
[SQL execution credentials](https://docs.snowflake.com/en/developer-guide/snowpark-container-services/spcs-execute-sql).

Expected tradeoff: some additional endpoint/grant setup; the larger ownership cost
is container/backend deployment and connection lifecycle. This is an engineering
estimate, not a measured effort claim. The existing comparison script requires
authorized/denied access, two distinct actors, and an attributable scoped test write
in the actual deployment before considering authentication proven.
