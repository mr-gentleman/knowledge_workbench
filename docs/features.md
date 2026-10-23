# Knowledge Workbench — shared backlog

Shared working list for Chris, Claude, and Codex. Update this file rather than keeping separate assistant to-do lists. Last organized: 2026-10-21.

Standing engineering philosophy and coding instructions: [AGENTS.md](../AGENTS.md). Both Claude and Codex use the same guidance. Every change gets the AGENTS.md bloat check; on request, add a dated whole-codebase review under "Engineering reviews" below and file actionable findings as backlog IDs.

## How to use this list

- Keep stable IDs; update an existing item instead of adding a duplicate. Keep completed items as the completion record.
- Status: **TODO**, **DOING**, **VERIFY** (implemented or suspected; acceptance check outstanding), **BLOCKED**, **DONE**.
- Priority: **P1** = correctness/reliability first; **P2** = core product workflow; **P3** = follow-on improvement. No confirmed production emergency is recorded here.
- Scope is separate from priority: **V1** = needed to retire Sheets; **Next** / **Later** = subsequent work.
- Origin tags identify who introduced the suggestion, not who owns implementation: **#codex**, **#claude**, **#chris**. **#existing** means carried from the previous feature list/design notes; authorship was not recorded. Do not retroactively guess it.
- When taking an item, add an owner tag and change its status to DOING. On completion, add a date and commit/test evidence. A source review alone does not establish a deployed feature is trusted.
- Evidence labels below distinguish **code observation**, **suspected defect**, **documented verification**, and **planned feature**.
- This file is the current task/status source of truth. Design rationale stays in [app-design-notes.md](app-design-notes.md); import constraints stay in [open-items.md](open-items.md). Their older next-step lists are historical. If moved to an issue board later, link the issues here and explicitly choose one status source.

## Plan of record — 2026-10-22 (pre-SME hardening, then V1)

**Hold SME onboarding** until Step 1–2 are done (Astra review, DEC-007).

1. **Hardening branch:** REL-08 txn cleanup → REL-09 lock all access → PLAT-05 LIMIT + history on demand →
   PLAT-04 query tags + op log (with lock-wait ms) → REL-10 create reset + token → HIST-06 KEEP_NULL +
   schema version → REL-11, REL-12, REL-07 → tests. One branch; independent review.
2. **Astra re-reviews that diff**; CoCo deploys and runs live checks (two-window conflict, duplicate
   retry, no-op save, an op-log row per outcome).
3. **In parallel:** PLAT-06 backups + restore drill; idle auto-shutdown on the app.
4. **V1 phases:** (1) core workspace — PIs on the metric screen, SQL editor, search (UX-01/02, FIND-01/02);
   (2) lifecycle — reject (clears ZZ_COCO_TEST rows), validation on its own connection bound to the exact
   revision, promotion with name normalization + registry (DEC-006), restore (HIST-04); (3) one-time import;
   (4) serving — publish last-passing definition + PIs together, test Oracle, shadow compare; (5) cutover,
   retire Sheets. Astra deep-reviews at the end of phases 2, 4 and 5.
5. **Process:** independent review required for persistence, identity, security and serving changes only;
   enforce merges with branch protection + a required test check wherever the repo settles (GitHub or GitLab).

## Next sprint / six-step delivery plan

Product priorities from **#chris**; sequencing and refinements by **#codex**, recorded 2026-10-21. This replaces the earlier five-step ordering. These steps organize the existing task IDs; they are not a second status tracker or a claim that the work is complete.

**Goal:** deliver the full metric workflow: find existing knowledge → create/edit identity and physical implementations → validate → promote to canon, then bring legacy knowledge through that system.

| Order | Work | Completion outcome | Backlog IDs |
|---|---|---|---|
| 1 | Stabilize saving and deployment | Concurrent edits cannot silently overwrite work; repeat submission cannot unintentionally create another candidate; saves/history remain consistent; the published code comes from an explicit, repeatable build/deploy path. | REL-01–05; PLAT-01–03; HIST-05 |
| 2 | Build the unified metric workspace | Tightened candidate identity form with implementations beneath it: Add implementation, SQL editing, and saved/validation status. Identity and PIs remain separate backend records but share a coherent editing experience. | UX-01–03 |
| 3 | Add validation and promotion | A readiness checklist gates promotion on a description and at least one PI passing checks for its current revision, linked to an active fact table. Promotion establishes canon; canon remains editable afterward. | CHECK-01–04; LIFE-01, LIFE-03 |
| 4 | Add a lean fact-table interface | Separate browse/create/edit screen for table name, definition, grain, key, time field, required filters, and gotchas. Maintain the table knowledge referenced by implementations; defer joins/dimensions. | UX-04 |
| 5 | Finish discovery and editing UX | Search candidates and canon across descriptive fields; provide clear status labels, useful result previews, readable history diffs, and a clear path from result to metric workspace. | FIND-01–02; HIST-01–02; UX-01, UX-03 |
| 6 | Import and verify legacy knowledge | Trial import of five representative metrics, then all legacy content with ID/reference translation. Verify definitions, PIs, authorship, and fact-table associations; surface exceptions clearly. | SERVE-02; CHECK-01–03; LIFE-01–02 |

### Sequencing refinements

- **Design discovery from the start.** Step 5 is completion/polish, not the first consideration of navigation. During step 2 establish “Find a metric → open its workspace,” plus a clear New metric action. Search/discovery and the unified editor are explicit product priorities.
- **Seed the fact-table registry before testing promotion.** Step 3 requires active fact-table records, even if the separate interface arrives in step 4. Populate the initial registry through a controlled seed/import; a sophisticated editor is not a prerequisite for proving the metric workflow.
- **Bring the lean fact-table interface into this sprint.** UX-04 was previously Next; its basic interface is now part of this plan. Richer table workflows, joins, and dimensions remain deferred.
- **Start the five-record import trial early.** Run it as soon as the relevant schema/workflow supports it, alongside workspace development, so representative legacy data exposes missing fields and awkward UX. Step 6 completes the full migration; do not wait until all polish is finished to inspect real examples.
- **Do not assume legacy means validated.** Preserve original authorship and relationships, run checks, promote qualifying records, and leave exceptions as candidates with clear reasons. Load fact tables → candidates plus PIs → validate → promote. Follow [open-items.md](open-items.md) for ID translation and downstream reference remapping.
- **Canonical means established and usable, not permanently finished.** Continue editing canonical definitions and adding implementations after promotion. Keep the last passing PI revision available for serving while later edits are unfinished or broken.
- **Keep the first release focused.** Defer semantic search, automatic merging, tags, elaborate combined timelines, and advanced fact-table features. Deliver good text search, a coherent editor, visible readiness, and reliable saves first.
- Correctness work and UX design can proceed alongside one another. The sequence expresses delivery dependencies rather than requiring every task in a row to finish before any work starts on the next.

### Two release milestones

**A — Usable authoring app:** the published app supports discovery, candidate/canon editing, PIs, validation/promotion, and the lean fact-table interface; legacy migration and exception handling are verified. Complete the relevant reliability and access checks. This milestone does not mean the Oracle has switched sources.

**B — Oracle cutover / Sheets replacement:** additionally complete DICTIONARY publishing from last-passing PI snapshots (SERVE-01), test Oracle configuration and representative questions (SERVE-03), and exercise cutover/rollback (SERVE-04). Preserve remaining V1 lifecycle/restore requirements in the backlog; this sprint sequence does not silently remove them.

At sprint end, record the lightweight engineering scorecard from [AGENTS.md](../AGENTS.md), with evidence and any actionable follow-up IDs.

## Reliability / possible data-loss or duplicate-write defects

These are separate from history presentation improvements. An overwritten edit is a correctness issue; making a small edit easier to see in history is a UX issue.

| ID | Status | Priority / scope | Task and acceptance check | Origin / evidence |
|---|---|---|---|---|
| REL-01 | VERIFY | P1 / V1 | Preserve the revision originally loaded into the editor. Currently the page re-fetches `cand` during submit and supplies its latest revision to the edit service. Reproduce with two sessions: A opens rev 1; B saves rev 2; A submits. A must receive a conflict, retain its draft, and leave B's row unchanged. Persist the baseline until explicit reload or successful save. | #codex — fix implemented; local regression tests passed; published Snowflake verification pending |
| REL-02 | VERIFY | P1 / V1 | Prevent repeat creation on resubmit and navigate to the saved record. `just_created` is written but not consumed; the new form stays active. A repeated submit/retry must not create an unintended second candidate. Deliberate creation of another candidate remains possible. | #existing #codex — code observation; #coco 2026-10-22 — branch coco/rel-02-open-created-candidate: successful create parks the id in `just_created`, reruns, and selects it before the sidebar renders (new record listed + opened, create form gone, "Saved" kept). Local test `CreateTests` passes; live check pending after deploy. #coco 2026-10-22 (review fix) — `just_created` is consumed on the next run even when a search filter hides the new record ("Saved as #N — clear the search to see it"), so the selection never jumps later; tested. Not DONE: a fast double-click *during* the save (form still rendered mid-run) can still create two — fix with a one-time form token if it shows up. #coco 2026-10-22 (live) — deployed f597ce4; created ZZ_COCO_TEST_2 (#3) on the published app: exactly one row, sidebar listed + selected it, editor opened, "Saved" kept. |
| REL-03 | VERIFY | P1 / V1 | Verify no-op handling and atomic record/history saves in the deployed app. Unchanged Save creates no revision; a content change creates exactly one matching snapshot; a failed snapshot write must not leave the content update committed. | #existing — implementation present; deployed acceptance outstanding |
| REL-04 | TODO | P2 / V1 | Refresh the header, revision, sidebar label, and editor baseline after successful save without losing feedback. Failed saves retain draft inputs. | #existing — code observation |
| REL-05 | TODO | P1 / V1 | Add focused regression coverage for REL-01/02/03 and the later validation/promotion invariants. Record deployed smoke-test evidence as well as automated checks. | #existing #codex — six concurrency/UI/transaction-routing tests now pass locally; create protection and future workflow tests remain open |
| REL-06 | VERIFY | P1 / V1 | Serialize transactions and editable-baseline reads on the shared app connection (DEC-004). All viewers share one Snowflake session, so without this another viewer's statements can join an open transaction, and an editor can capture an uncommitted revision that later rolls back. Acceptance: two published-app sessions saving within the same second both land intact with one snapshot each; opening the editor during a save waits rather than reading uncommitted state. | #claude #codex — shared session observed 2026-10-21 (two windows, one SESSION_ID); lock + 2 tests written, not yet run |
| REL-07 | VERIFY | P2 / V1 | Refresh the editable baseline on reopening a record. Editor state persists per record for the browser session, so: open #1, leave, someone else saves #1, return → stale content and revision shown (History shows newer) and the next save fails as a conflict with no visible reason. Refetch on arrival when no submitted draft exists; keep the baseline fixed while editing. | #claude — code observation on cece660; owner #claude 2026-10-23 (M1 hardening branch). Branch claude/REL-08-m1-hardening: Reopening a record with no submitted draft reloads it (test_reopening_a_record_shows_saves_made_meanwhile). Local tests only; live check pending (needs sql/003 applied + deploy). Live 2026-10-23 (deployed d1b6783, sql/003 applied): Chris ran the UI checks on the published app — pass. |
| REL-08 | VERIFY | P1 / V1 (pre-SME) | Failed-transaction cleanup in `_in_txn`: BEGIN inside try; handle BaseException (Streamlit StopException) and re-raise; on uncertain outcome reset/quarantine the connection before releasing the lock; keep both errors. Test: snapshot fails + rollback fails → next save does not commit the abandoned change. | #astra #claude — Astra review 2026-10-22 (reviews/2026-10-22-astra.md), DEC-007; owner #claude 2026-10-23 (M1 hardening branch). Branch claude/REL-08-m1-hardening: _in_txn: BEGIN inside try, BaseException handled + re-raised, failed ROLLBACK adds a note and quarantines the connection until ROLLBACK + CURRENT_TRANSACTION() prove it clean (DEC-008); quarantine set before any bookkeeping; page reads show Retry instead of crashing. Transaction tests incl. interrupted bookkeeping. Local tests only; live check pending (needs sql/003 applied + deploy). Live 2026-10-23 (deployed d1b6783, sql/003 applied): Chris ran the UI checks on the published app — pass. (Failure paths are covered by local tests only; not reproducible live.) |
| REL-09 | VERIFY | P1 / V1 (pre-SME) | Every DB operation under `db_lock`, held only during execute/fetch. Test: no `query()` path runs without the lock. | #astra #claude — Astra review 2026-10-22 (reviews/2026-10-22-astra.md), DEC-007; owner #claude 2026-10-23 (M1 hardening branch). Branch claude/REL-08-m1-hardening: All DB access via db.locked_session()/db.query; static test forbids other session() callers; a list read now waits behind an open transaction (test). Local tests only; live check pending (needs sql/003 applied + deploy). Live 2026-10-23 (deployed d1b6783, sql/003 applied): Chris ran the UI checks on the published app — pass. |
| REL-10 | VERIFY | P1 / V1 (pre-SME) | Duplicate create beyond double-click: with search hiding the new record, the filled create form stays and a normal second Save inserts again (Astra reproduced IDs [1,2]). Reset the create form after any successful create; add a request token persisted with the create so retries return the first result. | #astra #claude — Astra review 2026-10-22 (reviews/2026-10-22-astra.md), DEC-007; owner #claude 2026-10-23 (M1 hardening branch). Branch claude/REL-08-m1-hardening: create_token column (sql/003) + idempotent insert; create form resets with a new token after success; retry after a lost ack reuses the token; changed entries after an unconfirmed attempt never replay it (opens the landed record instead). Astra repro now inserts once (tests). Local tests only; live check pending (needs sql/003 applied + deploy). Live 2026-10-23 (deployed d1b6783, sql/003 applied): Chris ran the UI checks on the published app — pass. Second Save on the reset create form refused; one ZZ_M1_TEST row (#4). |
| REL-11 | VERIFY | P2 / V1 (pre-SME) | Duplicate-name warning lookup runs after commit (`services.py`); if it fails, a successful save looks failed. Make advisory checks unable to affect save outcome. | #astra #claude — Astra review 2026-10-22 (reviews/2026-10-22-astra.md), DEC-007; owner #claude 2026-10-23 (M1 hardening branch). Branch claude/REL-08-m1-hardening: Duplicate-name lookup failures become a warning; a committed save stays a success (test). Local tests only; live check pending (needs sql/003 applied + deploy). Live 2026-10-23 (deployed d1b6783, sql/003 applied): Chris ran the UI checks on the published app — pass. |
| REL-12 | VERIFY | P2 / V1 (pre-SME) | Draft keeps the change note; UI states plainly that unsubmitted edits are not saved on navigation. | #astra #claude — Astra review 2026-10-22 (reviews/2026-10-22-astra.md), DEC-007; owner #claude 2026-10-23 (M1 hardening branch). Branch claude/REL-08-m1-hardening: Change note kept with the submitted draft; editor says unsaved edits are discarded on navigation (test). Local tests only; live check pending (needs sql/003 applied + deploy). Live 2026-10-23 (deployed d1b6783, sql/003 applied): Chris ran the UI checks on the published app — pass. |

### REL-01 implementation handoff — optimistic concurrency

Suggested and implemented by **#codex**, 2026-10-21; requested by **#chris**. Status: VERIFY. See [concurrency-handoff.md](concurrency-handoff.md) for implemented scope, local checks, and Claude’s live verification steps. The following original design records the fuller proposal; V1 uses conflict messaging plus explicit reload/discard, with comparison/reconciliation UI deferred. See [decisions.md](decisions.md) for rationale.

**Problem:** the page currently calls `get_candidate(selected)` on every rerun, including form submission, then passes that freshly fetched `REVISION_NO` to `save_candidate_edit`. This does not reliably represent the version the person originally edited.

**Implementation steps:**

1. In `streamlit_app.py`, store an editor baseline (record snapshot plus revision) in per-user `st.session_state`, keyed by record type and ID. Initialize it when opening the record; do not replace it merely because the script reran or Save was clicked.
2. Keep draft widget values separate from that baseline, with explicit record-specific widget keys. Render and submit against the retained baseline. Preserve the draft on conflicts and other failed saves.
3. Pass the baseline revision as `expected_revision` to `app/services.py:save_candidate_edit`. A preliminary read may provide friendly feedback, but the repository's conditional UPDATE is the authoritative guard:
   ```sql
   -- Schematic: retain the existing parameterized field assignments.
   UPDATE metric_candidate
   SET ..., revision_no = revision_no + 1
   WHERE candidate_id = ?
     AND revision_no = ?; -- baseline revision originally opened
   ```
4. In `app/repositories.py:update_candidate`, retain the affected-row check and transactional snapshot write. Zero updated rows means a conflict; do not append history or silently retry with a newer revision. Verify all transaction statements use the same Snowflake session. Handle any database concurrent-update error without losing the draft.
5. On conflict, show: "This metric changed while you were editing. Review the latest version before saving." Fetch latest values separately for comparison; do not silently replace the baseline or draft. Show the saved version beside the user's draft. V1 needs manual reconciliation, not automatic merging or a force-overwrite button.
6. Provide explicit actions: **Reload latest (discard my draft)**, clearly labeled; or **Review and reconcile**, preserving the draft while the user chooses the intended values. Only after explicit acceptance of the reviewed version should it become the new baseline. The next save must still use its revision, so another intervening save is detected.
7. After a successful content-changing save, advance the baseline to the exact committed snapshot/revision, refresh the UI, and preserve success feedback. Do not pair an old draft with an unrelated newer revision from a later read. A no-op save should not invent a revision. On record switching, keep state scoped to each record so one metric's draft/baseline cannot leak into another.
8. Apply the fix in the modular source and regenerate/update `streamlit_app_single.py` through the agreed build path (PLAT-01). The deployed single-file app must receive the fix too.

**Acceptance checks (REL-05):**

- A and B open revision 5. B saves revision 6. A submits: conflict shown, A's draft retained, database still contains B's values, and no revision 7/history row is created by A's rejected save.
- Repeat with both saves issued at nearly the same time, using separate sessions. Verify in Snowflake that at most one update based on revision 5 succeeds, the other receives a handled conflict/error, and successful content and history remain consistent.
- After A reviews/reconciles against revision 6, A can save revision 7. If someone saves revision 7 first, A receives another conflict instead of overwriting it.
- Ordinary reruns do not advance the baseline or erase draft inputs. Switching records does not mix their editor state.
- Explicit reload replaces the draft with the latest saved version; successful save refreshes the baseline; unchanged Save creates no revision.
- Verify the published app as well as source-level tests. Record evidence before marking REL-01 DONE.

## Search / discovery of existing knowledge

| ID | Status | Priority / scope | Task and acceptance check | Origin / evidence |
|---|---|---|---|---|
| FIND-01 | TODO | P2 / V1 | Browse/search both candidates and canonical metrics. Clearly distinguish status; selecting a result opens the appropriate metric workspace. | #existing #chris — planned feature |
| FIND-02 | TODO | P2 / V1 | Search name, description, and disambiguation; add typo tolerance with ranked results. Show enough definition context to recognize an existing metric before creating another. Name-only substring search already exists. | #existing #chris — planned extension |
| FIND-03 | TODO | P3 / Next | Add semantic search and duplicate suggestions using the same matcher. Warn without blocking; show the matching definition, not an invented duplicate probability. | #existing — planned feature |
| FIND-04 | TODO | P3 / Next | Filter by department and lifecycle status. | #existing — planned feature |
| FIND-05 | TODO | P3 / Later | Add tag-based browse filters only when a defined tag workflow and consumer exist. | #existing — deferred |

## Entry / editing UX

| ID | Status | Priority / scope | Task and acceptance check | Origin / evidence |
|---|---|---|---|---|
| UX-01 | TODO | P2 / V1 | Create one metric workspace: identity/definition plus its physical implementations (PIs), with fact-table context. Keep separate backend records but a coherent user-facing screen for candidate and canon. | #chris #codex #existing — planned feature |
| UX-02 | DOING | P2 / V1 | Add/list/edit PIs within that workspace. Start with an empty state and Add implementation; show existing implementations as expandable entries. Spike a SQL editor with highlighting while typing, line numbers, and reliable paste. Preserve separate saved/validated states. | #chris #codex #existing — proposed layout; editor feasibility outstanding. #claude 2026-10-23, branch claude/sql-on-page (DEC-019): backend building blocks — list/get/reserve/insert/update/retire PI in repositories; label/default/run-status rules in services. One atomic save is DEC-020 (claude/save-proc); local tests only (tests/test_pi.py). UI moves to React (DEC-018, FE-02); Streamlit card UI parked on claude/sql-on-page-streamlit-ui. |
| UX-03 | TODO | P2 / V1 | Tighten the identity form: clearer grouping/help text, obvious required fields, and hide free-text category until a controlled list exists. Keep name-only draft creation. | #chris #existing — planned improvement |
| UX-04 | TODO | P2 / V1 | Add a lean separate fact-table browse/create/edit interface for name, definition, grain, key, time field, required filters, and gotchas. Seed/import active registry records before promotion testing; defer richer table workflows, joins, and dimensions. Included in the six-step sprint plan. | #existing #chris #codex — scope advanced from Next on 2026-10-21 |
| UX-05 | TODO | P3 / Next | Add synonyms as separate records and include them in discovery. | #existing — planned feature |

## Validation / readiness

| ID | Status | Priority / scope | Task and acceptance check | Origin / evidence |
|---|---|---|---|---|
| CHECK-01 | TODO | P2 / V1 | Validate SQL against the exact PI revision checked. A later edit cannot inherit that pass; a late check result cannot approve a different revision. Saving SQL does not execute it. | #existing — planned feature |
| CHECK-02 | TODO | P2 / V1 | Show computed readiness: description present, at least one currently passing PI, and valid active source-table linkage. Explain why Promote is unavailable. | #existing — planned feature |
| CHECK-03 | TODO | P2 / V1 | Enforce PI source_table matching an active fact_table_core entry at the required gate, using the agreed three-part name. | #existing — planned feature |
| CHECK-04 | VERIFY | P2 / V1 | Verify exact-name duplicate warnings across open candidates and active canon, excluding the edited candidate itself. Warnings remain nonblocking. | #existing — implementation present |
| CHECK-05 | TODO | P3 / Later | Schedule revalidation to detect SQL that becomes invalid after upstream changes. | #existing — deferred |

## Lifecycle

| ID | Status | Priority / scope | Task and acceptance check | Origin / evidence |
|---|---|---|---|---|
| LIFE-01 | TODO | P2 / V1 | Promote candidate → canon atomically: enforce readiness, mint metric ID, attach PIs while preserving origin, record history, and initialize serving pointers appropriately. Repeated promotion cannot mint multiple canon records. | #existing — planned feature |
| LIFE-02 | TODO | P2 / V1 | Reject candidate with reason and optional duplicate_of_metric_id. Direct the user to the existing canon when applicable. | #existing — planned feature |
| LIFE-03 | TODO | P2 / V1 | Edit canon directly after promotion; retire canon/PIs with reason and appropriate replacement linkage. Retired content must not be served. Preserve the agreed schema distinction: superseded_by is currently on canon, not PI. | #existing — planned feature |
| LIFE-04 | TODO | P3 / Later | Add merge tooling only after the basic lifecycle is established. | #existing — deferred |
| LIFE-05 | TODO | P2 / V1 | Canon name uniqueness + routed duplicate flow (DEC-006). Settle name normalization; refuse promotion or a canon rename onto a name used by another active canonical metric; on a match, offer Same metric → edit canon pre-filled / Different → distinct name + disambiguation / Not sure → candidate with promotion blocked. Candidates keep warnings only. | #claude #chris — decided 2026-10-21 |

## History / attribution UX

**Keep full snapshots in storage. Display diffs by default.** Do not rewrite historical records to make the screen easier to read.

| ID | Status | Priority / scope | Task and acceptance check | Origin / evidence |
|---|---|---|---|---|
| HIST-01 | TODO | P2 / V1 | Show changed fields with old → new values; use word/line diffs for long descriptions and SQL. A one-word edit should be easy to spot. | #existing #chris — planned presentation improvement |
| HIST-02 | TODO | P2 / V1 | Offer a readable full-record view as of revision N alongside the diff. Raw snapshot JSON already exists. | #existing — planned improvement |
| HIST-03 | TODO | P3 / Next | Combine metric and PI events into one timeline while preserving each record's revision identity. | #existing — planned feature |
| HIST-04 | TODO | P2 / V1 | Document and test restoring an earlier revision as a new audited change; no historical snapshot mutation. Fancy restore UI is not required for V1. | #existing — planned procedure |
| HIST-05 | VERIFY | P1 / V1 | Confirm trusted viewer attribution in the published app. Use st.user rather than a form value or service-user identity. | #existing — preview identity verification documented; published check outstanding |
| HIST-06 | VERIFY | P1 / V1 (pre-SME) | Snapshots use `OBJECT_CONSTRUCT_KEEP_NULL(*)` (plain OBJECT_CONSTRUCT drops NULL fields, so a cleared value vanishes) + a snapshot schema version; define how older snapshots are read. | #astra #claude — Astra review 2026-10-22 (reviews/2026-10-22-astra.md), DEC-007; owner #claude 2026-10-23 (M1 hardening branch). Branch claude/REL-08-m1-hardening: Snapshots use OBJECT_CONSTRUCT_KEEP_NULL(*) and schema_version 2; v1 rule: a missing key = NULL (shown in History). Test. Local tests only; live check pending (needs sql/003 applied + deploy). Live 2026-10-23 (deployed d1b6783, sql/003 applied): Chris ran the UI checks on the published app — pass. Revisions for #4: schema_version 2, all 17 columns in each snapshot. |

## Serving / migration to the Oracle

| ID | Status | Priority / scope | Task and acceptance check | Origin / evidence |
|---|---|---|---|---|
| SERVE-01 | TODO | P2 / V1 | Build DICTIONARY consumables from each eligible PI's served_revision_no snapshot, not the live draft row. A broken edit leaves the previous passing implementation served; a new pass advances it. | #existing — planned feature |
| SERVE-02 | TODO | P2 / V1 | Import five representative metrics first, then complete the one-time legacy migration with ID translation and source-table normalization. Remap dependent evaluation/exemplar references. Follow open-items.md. | #existing — planned feature |
| SERVE-03 | TODO | P2 / V1 | Test Oracle configuration against the new dictionary and representative questions before cutover. | #existing — planned verification |
| SERVE-04 | TODO | P2 / V1 | Write and exercise cutover/rollback procedure before retiring Sheets. | #existing — planned procedure |

## Build / deployment / access

| ID | Status | Priority / scope | Task and acceptance check | Origin / evidence |
|---|---|---|---|---|
| PLAT-01 | VERIFY | P1 / V1 | Establish a reproducible source → deployed app path. Single-file header says generated, but no generator is checked in; snowflake.yml targets the multifile app. Choose/document the deployment path, add generation if keeping the bundle, and prevent source/bundle drift. Diagnose package inclusion before concluding multiple files are unsupported. | #codex — repository observation; runtime cause not established; #coco 2026-10-22 — cause established: `app/` was missing from the Workspace manifest. Resolved by DEC-005: deploy the multi-file app from the repo with the snow CLI; this branch retires the single-file bundle. Multi-file deploy of 729bb7d verified live. Acceptance: merge this branch, then one more deploy from main still loads and saves. #coco 2026-10-22 — acceptance met: merged, deployed f597ce4 from main, published app loaded and created #3. |
| PLAT-02 | TODO | P2 / V1 | Complete Git-backed deployment (existing plan: GitLab-backed workspace; CI later). Define how this GitHub collaboration repo stays aligned with the actual deployment source. Verify published version, not only workspace preview. | #existing #codex — planned feature |
| PLAT-03 | VERIFY | P1 / V1 | Confirm deployed owner-role isolation from DICTIONARY, revoke UPDATE on revision, and confirm the intended SYSADMIN role linkage. Review documented broad CoCo write grants before SME rollout. | #existing — isolation documented; remaining grants/checks need current verification |
| PLAT-04 | VERIFY | P1 / V1 (pre-SME, per DEC-007: QUERY_TAG + op log outside txn) | Add operational logging: operation ID, actor, outcome, duration, query ID. Include `db_lock` wait time so DEC-004's latency cost is measured, not estimated. Today only failed edit saves are logged (`logging.exception`). | #existing — planned feature; owner #claude 2026-10-23 (M1 hardening branch). Branch claude/REL-08-m1-hardening: op_log table (sql/003), one row per write attempt with a certain outcome, after the txn ends (uncertain outcomes: app log only): outcome, actor, lock_wait_ms, duration_ms, LAST_QUERY_ID. QUERY_TAG {op_id, op, actor, record_id} on the statements of the op, unset after. Best effort: logging cannot change an outcome (tests). Local tests only; live check pending (needs sql/003 applied + deploy). Live 2026-10-23 (deployed d1b6783, sql/003 applied): Chris ran the UI checks on the published app — pass. OP_LOG: committed rows for create + edit, actor CLENZINI, lock_wait 1 ms, duration 2227/1694 ms. GAP (not DONE): a conflict caught by the service pre-check (services.save_candidate_edit, before any transaction) writes no op_log row — log it as `conflict`. Saves take ~2 s with ~1 ms lock wait: Snowflake round trips (~8 statements per create); measure before optimizing. QUERY_TAG in query history not yet checked. |
| PLAT-05 | VERIFY | P1 / V1 (pre-SME, per DEC-007: LIMIT + history on demand so reads don't hold the lock) | Cut per-click query load. Every interaction reruns the page: `list_candidates` (no `LIMIT`), `get_candidate`, and the full revision history with JSON snapshots, even when the History tab isn't opened. Smallest fix: `LIMIT` the sidebar list; load history only when asked for (toggle/button). Revisit when record counts grow or clicks feel slow. | #claude — code observation, 2026-10-21 review; no latency measured; owner #claude 2026-10-23 (M1 hardening branch). Branch claude/REL-08-m1-hardening: Sidebar list LIMIT 200 with a search-to-narrow note; History loads only when toggled (tests). Local tests only; live check pending (needs sql/003 applied + deploy). Live 2026-10-23 (deployed d1b6783, sql/003 applied): Chris ran the UI checks on the published app — pass. History toggle works. |
| PLAT-06 | TODO | P1 / V1 | Data backup and tested recovery for `AI_PLATFORM.WORKBENCH`. Today `DATA_RETENTION_TIME_IN_DAYS` = 1 (default), so a dropped table, bad bulk import, or `CREATE OR REPLACE TABLE` is recoverable (Time Travel / `UNDROP`) for only 24 h; after that only Snowflake-support Fail-safe. Smallest fix: (1) raise retention on the schema (e.g. 30 days, if the account edition allows) — `ALTER SCHEMA ... SET DATA_RETENTION_TIME_IN_DAYS = 30`; (2) a scheduled zero-copy `CLONE` of the schema to a dated backup schema, keeping a few, before imports and on a weekly cadence; (3) write and exercise the restore runbook once (clone back a table, verify row counts + latest revision). The `revision` table's full snapshots are history, not a backup — same schema, same blast radius. Owner-rights and grants: backups must not give `WORKBENCH_APP` write access outside WORKBENCH. Master plan §9: a tested recovery procedure is V1. | #claude #chris — retention verified 1 day via SHOW PARAMETERS, 2026-10-21 |
| PLAT-07 | DOING | P2 / V1 | Add a one-command health readout (`scripts/health.sh`: size, complexity, lint, tests, docs-to-code ratio, feature maturity, change since last run) and a PR template whose first section tells Chris what to look at. Acceptance: script runs clean from a fresh checkout after the documented dev install; template appears on new PRs. | #claude #chris — owner #claude, 2026-10-23 |
| PLAT-08 | DOING | P2 / V1 | Single-shot Astra review: `scripts/review.sh <branch> --yes` sends the branch diff plus AGENTS.md review criteria to Astra (Cortex Code CLI, read-only tools) once and saves findings to `docs/reviews/`. Chris approves each run; no automatic re-review. | #claude #chris — owner #claude, 2026-10-23 |

## Current baseline / completion evidence

- Candidate browse/name search, create/edit, exact-name warnings, no-op logic, and full snapshot history exist in source.
- Design notes report preview create/edit verification for candidate #1, revisions 1 → 2, attributed to CLENZINI on 2026-10-20.
- Schema/tables/sequences and isolation were documented as verified. This backlog does not claim a new live verification.
- Published deployment, no-op, concurrency, and duplicate-submit behavior still need the acceptance checks above.
- No items were marked DONE merely by reorganizing this file. Add dated completion evidence here or in the corresponding row as work closes.


## Implementation evidence — 2026-10-21 (#codex)

- REL-01: retained editor baseline, explicit reload, draft-preserving error handling; six focused local tests passed with mocked persistence. Snowflake tests pending.
- REL-03: writes/snapshots now use one explicit session; rollback routing tested locally, database behavior unverified.
- REL-04: edit-save refresh implemented; create flow remains unchanged.
- PLAT-01: reproducible single-file generator added; actual deployment/package troubleshooting remains open.
- [Claude verification handoff](concurrency-handoff.md) · [Engineering decision history](decisions.md).

## Implementation evidence — 2026-10-21 (#claude)

- REL-06: `db_lock()` added; `_in_txn` and `get_candidate` hold it (DEC-004). Two tests added (baseline read waits for an open transaction; BEGIN only in `_in_txn`). Not run locally: this machine lacks Python 3.10+/Streamlit. Reviewer: run `python -m unittest discover -s tests -v`.

## Engineering reviews

### 2026-10-21 — baseline (#claude; source reading only)

Scope: `main` at f1800e7 plus a since-dropped Claude REL-01 branch (superseded by Codex's cece660), ~400 lines of app source. Evidence: source reading and fake-repository tests. Nothing was checked against Snowflake or the published app.

| Check | Rating | Evidence → smallest fix |
|---|---|---|
| Separation of concerns | Green | SQL only in `repositories.py`, rules only in `services.py`, page holds UI + editor state. Minor: the department list (`DEPARTMENTS`) lives in the page; move it to services or a table when a second screen needs it. |
| Modularity | Green | REL-01 touched the page and one service; the layers held. |
| Verbosity | Green | Small, direct code; no wrappers or frameworks. |
| Complexity | Yellow | `streamlit_app.py` now carries editor-state logic (~140 lines). Fine today. When the PI editor lands (UX-01/02), give each screen its own module instead of growing one file. |
| Latency | Yellow | 3 queries per click, one unbounded, plus full history loaded every time → PLAT-05. No timings measured. |
| Dependencies | Green | Runtime-shipped packages only. |
| Dead code / duplication | Yellow | `streamlit_app_single.py` is now generated (now `scripts/build_single.py`), but nothing checks bundle drift before deploy → PLAT-01. `just_created` is written and never read → REL-02. |
| Correctness | Yellow | REL-01 fixed (cece660), not yet verified in Snowflake or the published app; REL-02 open. Later the same day: shared-connection transactions found (REL-06, DEC-004) and stale baseline on reopen (REL-07). |
