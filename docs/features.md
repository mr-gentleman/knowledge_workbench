# Knowledge Workbench — shared backlog

Shared working list for Chris, Claude, and Codex. Update this file rather than keeping separate assistant to-do lists. Last organized: 2026-10-21.

## How to use this list

- Keep stable IDs; update an existing item instead of adding a duplicate. Keep completed items as the completion record.
- Status: **TODO**, **DOING**, **VERIFY** (implemented or suspected; acceptance check outstanding), **BLOCKED**, **DONE**.
- Priority: **P1** = correctness/reliability first; **P2** = core product workflow; **P3** = follow-on improvement. No confirmed production emergency is recorded here.
- Scope is separate from priority: **V1** = needed to retire Sheets; **Next** / **Later** = subsequent work.
- Origin tags identify who introduced the suggestion, not who owns implementation: **#codex**, **#claude**, **#chris**. **#existing** means carried from the previous feature list/design notes; authorship was not recorded. Do not retroactively guess it.
- When taking an item, add an owner tag and change its status to DOING. On completion, add a date and commit/test evidence. A source review alone does not establish a deployed feature is trusted.
- Evidence labels below distinguish **code observation**, **suspected defect**, **documented verification**, and **planned feature**.
- This file is the current task/status source of truth. Design rationale stays in [app-design-notes.md](app-design-notes.md); import constraints stay in [open-items.md](open-items.md). Their older next-step lists are historical. If moved to an issue board later, link the issues here and explicitly choose one status source.

## First pass / suggested order

1. Reproduce and fix stale-edit protection (REL-01); protect create/save flow (REL-02).
2. Make the deployed source/build path explicit and repeatable (PLAT-01).
3. Build the metric workspace with physical implementations on the same screen (UX-01, UX-02).
4. Make existing candidates and canon discoverable (FIND-01, FIND-02).
5. Complete validation → promotion → serving before cutover (CHECK / LIFE / SERVE).

Correctness work can proceed alongside UX work. Search/discovery and the unified editor are explicit product priorities from Chris, not incidental polish.

## Reliability / possible data-loss or duplicate-write defects

These are separate from history presentation improvements. An overwritten edit is a correctness issue; making a small edit easier to see in history is a UX issue.

| ID | Status | Priority / scope | Task and acceptance check | Origin / evidence |
|---|---|---|---|---|
| REL-01 | TODO | P1 / V1 | Preserve the revision originally loaded into the editor. Currently the page re-fetches `cand` during submit and supplies its latest revision to the edit service. Reproduce with two sessions: A opens rev 1; B saves rev 2; A submits. A must receive a conflict, retain its draft, and leave B's row unchanged. Persist the baseline until explicit reload or successful save. | #codex — suspected defect from code review; not reproduced in Snowflake |
| REL-02 | TODO | P1 / V1 | Prevent repeat creation on resubmit and navigate to the saved record. `just_created` is written but not consumed; the new form stays active. A repeated submit/retry must not create an unintended second candidate. Deliberate creation of another candidate remains possible. | #existing #codex — code observation |
| REL-03 | VERIFY | P1 / V1 | Verify no-op handling and atomic record/history saves in the deployed app. Unchanged Save creates no revision; a content change creates exactly one matching snapshot; a failed snapshot write must not leave the content update committed. | #existing — implementation present; deployed acceptance outstanding |
| REL-04 | TODO | P2 / V1 | Refresh the header, revision, sidebar label, and editor baseline after successful save without losing feedback. Failed saves retain draft inputs. | #existing — code observation |
| REL-05 | TODO | P1 / V1 | Add focused regression coverage for REL-01/02/03 and the later validation/promotion invariants. Record deployed smoke-test evidence as well as automated checks. | #existing #codex — tests directory currently only a placeholder |

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
| UX-02 | TODO | P2 / V1 | Add/list/edit PIs within that workspace. Start with an empty state and Add implementation; show existing implementations as expandable entries. Spike a SQL editor with highlighting while typing, line numbers, and reliable paste. Preserve separate saved/validated states. | #chris #codex #existing — proposed layout; editor feasibility outstanding |
| UX-03 | TODO | P2 / V1 | Tighten the identity form: clearer grouping/help text, obvious required fields, and hide free-text category until a controlled list exists. Keep name-only draft creation. | #chris #existing — planned improvement |
| UX-04 | TODO | P3 / Next | Add fact-table create/edit UI. V1 still needs an available active fact-table registry for PI validation/import; a full editor can follow. | #existing — planned feature |
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

## History / attribution UX

**Keep full snapshots in storage. Display diffs by default.** Do not rewrite historical records to make the screen easier to read.

| ID | Status | Priority / scope | Task and acceptance check | Origin / evidence |
|---|---|---|---|---|
| HIST-01 | TODO | P2 / V1 | Show changed fields with old → new values; use word/line diffs for long descriptions and SQL. A one-word edit should be easy to spot. | #existing #chris — planned presentation improvement |
| HIST-02 | TODO | P2 / V1 | Offer a readable full-record view as of revision N alongside the diff. Raw snapshot JSON already exists. | #existing — planned improvement |
| HIST-03 | TODO | P3 / Next | Combine metric and PI events into one timeline while preserving each record's revision identity. | #existing — planned feature |
| HIST-04 | TODO | P2 / V1 | Document and test restoring an earlier revision as a new audited change; no historical snapshot mutation. Fancy restore UI is not required for V1. | #existing — planned procedure |
| HIST-05 | VERIFY | P1 / V1 | Confirm trusted viewer attribution in the published app. Use st.user rather than a form value or service-user identity. | #existing — preview identity verification documented; published check outstanding |

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
| PLAT-01 | TODO | P1 / V1 | Establish a reproducible source → deployed app path. Single-file header says generated, but no generator is checked in; snowflake.yml targets the multifile app. Choose/document the deployment path, add generation if keeping the bundle, and prevent source/bundle drift. Diagnose package inclusion before concluding multiple files are unsupported. | #codex — repository observation; runtime cause not established |
| PLAT-02 | TODO | P2 / V1 | Complete Git-backed deployment (existing plan: GitLab-backed workspace; CI later). Define how this GitHub collaboration repo stays aligned with the actual deployment source. Verify published version, not only workspace preview. | #existing #codex — planned feature |
| PLAT-03 | VERIFY | P1 / V1 | Confirm deployed owner-role isolation from DICTIONARY, revoke UPDATE on revision, and confirm the intended SYSADMIN role linkage. Review documented broad CoCo write grants before SME rollout. | #existing — isolation documented; remaining grants/checks need current verification |
| PLAT-04 | TODO | P3 / Next | Add operational logging: operation ID, actor, outcome, duration, query ID. | #existing — planned feature |

## Current baseline / completion evidence

- Candidate browse/name search, create/edit, exact-name warnings, no-op logic, and full snapshot history exist in source.
- Design notes report preview create/edit verification for candidate #1, revisions 1 → 2, attributed to CLENZINI on 2026-10-20.
- Schema/tables/sequences and isolation were documented as verified. This backlog does not claim a new live verification.
- Published deployment, no-op, concurrency, and duplicate-submit behavior still need the acceptance checks above.
- No items were marked DONE merely by reorganizing this file. Add dated completion evidence here or in the corresponding row as work closes.
