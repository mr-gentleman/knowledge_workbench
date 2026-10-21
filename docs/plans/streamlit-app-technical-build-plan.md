> **Copied 2026-10-21** from `oracle_bi_agent/notes/streamlit-app-technical-build-plan.md` (the Oracle project repo, not in this repo). Read-only reference — the original is authoritative; relative links below point into that repo and will not resolve here. Where this plan conflicts with `docs/features.md` or `docs/handoff-2026-10-16.md` decisions, those newer files win.

# Streamlit Knowledge Interface — Technical Build Plan

Updated: 2026-09-15. AC Data Oracle.

Companion to [the master plan](streamlit-app-master-plan.md). This note captures the later technical discussion and governs where that discussion changes the earlier master plan. Planning only: live schemas, runtime capabilities, and implementation have not been verified.

## 1. First release: metrics only

Prove the application with `metric_core` (identity) and `metric_calc` (Metric Physical Implementation / PI). Fact-table, join, and dimension maintenance can remain on the legacy processes. Read/reference their existing assets where needed.

The five components are metric core, metric calculations, fact-table core (grain/hints), join list, and dimensional list. Moving all five into the app is not a prerequisite for the first release.

Goal: import a metric as a candidate → edit in Streamlit → check SQL → promote → expose eligible knowledge to a test Oracle consumer.

## 2. Current lifecycle decisions

### IDs and records

- One shared candidate sequence across all sources; source is explicit metadata.
- A separate canonical metric sequence. Never use source prefixes, names, or content hashes as semantic identity.
- Stable calculation IDs also required; exact allocation mechanism remains to be chosen.
- Separate candidate and canonical records are the proposed V1 baseline; exact DDL remains to be defined.
- A new candidate persists before promotion. A newly established identity receives a canonical metric ID at promotion.
- Routine edits revise established records; do not create a new candidate for every edit.
- Independent future proposals can resolve to an existing metric. They do not take ownership of its identity. Rich reconciliation workflows are deferred.

### PI attachment: fixed after acceptance in V1

| Situation | `metric_id` | `origin_candidate_id` |
|---|---|---|
| PI initially authored with candidate | Empty | Candidate ID |
| Candidate promotes | Resulting canonical metric ID | Preserved |
| PI added directly to canonical metric | Existing canonical metric ID | Empty |

The current canonical metric is the PI's meaningful attachment. The original candidate is immutable provenance. Do not derive ongoing PI ownership through the original candidate after acceptance.

Candidate promotion is the one automatic attachment transition. No reassignment/move operation in V1. To correct an attachment, create a new PI under the right metric and retire the mistaken PI, preserving history. Changing the original candidate also requires replacement. Ordinary SQL/context edits preserve the PI ID.

### Important correction to the master plan

The latest direction requires **at least one qualifying PI for initial canonical promotion**. Name/description alone may be saved as a candidate; SQL can remain unfinished there. This replaces the earlier allowance to establish a new canonical metric before any usable PI exists.

Once a canonical identity exists, loss or retirement of its last usable PI does not unmint it. Retain the canonical ID and show that no usable implementation is available.

### Save, promote, serve

- Save preserves imperfect work, subject only to minimal structural requirements such as a name for the candidate.
- Promotion applies deliberately light SME gates: identity/name checks and at least one PI passing the required SQL execution check.
- SQL must execute before that implementation is served. Placeholders that prevent execution fail naturally.
- Other checks may become warnings, pre-checks, or blockers later. Do not import the old seven-blocker policy automatically.
- SQL execution is not proof of business correctness.
- Validation applies to the exact SQL revision checked. Edited SQL does not inherit previous validation.
- Establishing identity and exposing a particular revision to consumers remain distinct even when bundled into one successful workflow.
- An unfinished edit must not replace the last eligible served revision. Explicit retirement must exclude the PI entirely rather than resurrect older eligible versions.

## 3. UX is a first-release requirement

The app must look coherent and polished, feel responsive, and materially improve on Sheets. Visual quality and the SQL editor are adoption requirements, not optional finishing touches.

- Consistent typography, spacing, colors, navigation, and action placement.
- Search-first browsing, readable metric definition, PI list, and comfortable editing space.
- SQL syntax highlighting **while editing**, indentation, line numbers, monospaced text, reliable keyboard/copy/paste behavior.
- Clearly distinguish editor content, saved status, validation result, and promotion/serving outcome.
- Useful loading, empty, success, and failure states.
- Preserve editing context and unsaved content on reruns and failed saves.
- Avoid unnecessary database calls on each interaction; make slow operations visibly bounded.

Early feasibility spike: confirm the intended editor component works inside the actual Streamlit-in-Snowflake runtime. A highlighted read-only preview alone does not meet the requirement. Do not assume runtime support without testing it.

## 4. Technical order of operations

### Step 1 — inspect the system; establish GitLab home

Inspect actual schemas, existing relationships/IDs, authorship fields, consumer views, dictionary-switch behavior, and safe SQL execution capability. Collect representative simple, complex, incomplete, duplicate-name, and multi-PI examples.

Choose an existing suitable GitLab repository or a dedicated app repository. Store app code, versioned DDL, tests, architecture/decision notes, configuration guidance, and deployment instructions together.

Suggested layout:

    app/     UI, services, repositories, models
    sql/     Ordered schema changes and consumer views
    tests/   Workflow and persistence tests
    docs/    Architecture, decisions, deployment

Configure formatter/linter and relevant tests in GitLab CI. A documented manual deployment is sufficient initially; no elaborate deployment platform needed.

**Milestone:** reproducible source-controlled project, known deployment target, explicit consumer expectations.

### Step 2 — define and create isolated storage

Use separate base objects/schema and explicit configuration. App write permissions must not permit modification of old production dictionaries.

Minimum logical structures:

- Candidate sequence.
- Canonical metric sequence.
- `metric_candidate`: proposed identity/content, source, author, resolution outcome.
- `metric_core`: accepted identity/definition.
- `metric_calc`: PI, SQL, physical context, canonical attachment, candidate origin.
- Revision history: complete snapshots and actors.

Define exact columns/types, minimum save fields, promotion requirements, editability, and identity effects. Preserve existing useful field shapes. Define how candidate proposed content and canonical accepted content differ; do not silently keep both synchronized on every edit.

**Milestone:** versioned DDL creates the isolated structures; IDs and relationships have explicit rules.

### Step 3 — build central write services

Operations: save candidate, add/edit PI, validate PI, promote candidate, edit canonical definition, retire PI, inspect history.

Each meaningful save checks expected revision, writes current state plus history atomically, and returns the committed ID/revision. No history revision for a no-op save or failed save. Preserve user input on errors. Handle retries and uncertain commit outcomes.

Promotion checks the latest relevant content and revision-bound validation. Atomically create the new canonical identity, record candidate resolution, attach its PIs, and record history. Repeated promotion must return the existing outcome rather than mint again. Attached but failing PIs remain ineligible individually.

**Milestone:** core operations work independently of Streamlit, including failure cases.

### Step 4 — one-time sample import

Import representative human-authored entries as new candidates, with their PIs. Preserve original authors and record the importer separately. Run normal checks/promotion. Review failures; never silently bypass checks because data is legacy.

This is a one-time script, not a generalized migration framework. If a batch must be rerun, inspect what committed first. Carry only the legacy references needed to audit and reconnect relationships.

**Milestone:** real source examples pass through the new lifecycle with correct authorship and history.

### Step 5 — prove editor; build polished vertical slice

Build search → metric detail → create/edit → save/check/promote → reload → history. Include a PI list and rich SQL editor. Establish the visual standard on this first workspace before broadening.

**Milestone:** one metric is genuinely comfortable to maintain without Sheets.

### Step 6 — validation and consumer representation

Use restricted execution permissions and timeout for SQL checks. Return understandable diagnostics and bind results to the checked revision.

Build a thin read view/adapter matching the Oracle contract. Exclude unresolved candidates and ineligible PI revisions. Define default/context selection for multiple PIs. Preserve last eligible content during unfinished edits, while honoring retirement.

**Milestone:** saved, accepted, and served content are distinguishable and predictable.

### Step 7 — operational logging and robustness review

Revision history answers who changed the knowledge and what changed. Operational logs answer why an operation failed or ran slowly.

Log operation/request ID, actor, relevant record IDs, operation type, outcome, duration, available Snowflake query ID, and diagnostic category/details. Avoid duplicating full SQL, content, results, or credentials into general logs unnecessarily.

Code review focuses on transaction correctness, identity invariants, authorization versus viewer attribution, serving semantics, error handling, and maintainability. Use meaningful tests rather than arbitrary coverage targets.

**Milestone:** failures are diagnosable and required invariants have been demonstrated.

### Step 8 — verify test consumer; expand import and dogfood

Verify representative Oracle questions and deliberate before/after dictionary changes through a test configuration. Ensure legacy fact/join/dimension dependencies still resolve correctly. Finish the intended import, review exceptions, and ask one or two SMEs to perform ordinary maintenance without coaching.

**Milestone:** the metric-only replacement works end to end for another user.

### Step 9 — metric cutover

Remove experimental release data. Verify recovery and rollback configuration. Pause legacy metric edits briefly, reconcile intervening changes once, switch the metric dictionary pointer, and retire the replaced authoring path. Preserve any new-system edits if rollback becomes necessary.

Fact-table, join, and dimension authoring follow later using lessons from the metric slice.

**Milestone:** production consumes the new metric dictionary; Streamlit owns metric maintenance.

## 5. Required robustness checks

- Two editors: stale save rejected, entered content retained.
- Atomicity: failed audit/history write rolls back current-state mutation.
- No-op saves create no revision; duplicate creates/promotions are prevented on retries.
- Connection interruption has a checkable outcome before retry.
- Validation of old SQL cannot approve edited SQL.
- At least one qualifying PI required for initial promotion; failing additional PIs excluded from serving.
- Retirement excludes the whole PI, including older revisions; last-PI retirement retains canonical identity.
- Canonical PI attachment cannot be changed through ordinary edit operations.
- Original author, importer, updater, and revision actor remain correctly distinguished.
- Nulls, synonym arrays, Unicode, apostrophes, long descriptions and SQL round-trip safely.
- Unsafe, invalid, slow, permission-denied SQL yields bounded, useful errors without losing content.
- Default/context selection for multiple PIs is deterministic and matches consumer expectations.
- Prior content can be reconstructed and recovered.
- Imported physical references remain valid; test records do not leak into serving.

## 6. Architecture and implementation principles

    UI → Services → Repositories → Snowflake
              Shared models

Keep business rules centralized and promotion policy adjustable. Parameterize persistence; authored SQL is content until explicitly validated. Separate viewer attribution from execution authorization. No custom authentication system, arbitrary-schema CRUD framework, source-specific ID taxonomy, or candidate-per-edit workflow.

Record every meaningful save; major/minor display classification is future scope. Preserve original authorship and use trusted action actors. Human edits/approvals of future machine outputs must survive regeneration with full approved snapshots and provenance; do not implement that entire pipeline now.

## 7. Open choices before DDL or relevant implementation

1. Actual field contracts and accepted-versus-latest revision representation.
2. Exact-name normalization/collision outcome and any deliberate override.
3. Calculation ID allocation and exact history-table structure.
4. SQL validator integration, timeout, identity, and action triggering.
5. PI physical context/default-selection rules and old consumer compatibility.
6. Editor component/runtime feasibility and practical performance acceptance targets.
7. Existing versus dedicated GitLab repository; log destination and retention.
8. Later handling of independent candidates matching existing canonical identities.

Avoid enforcing the historical “different PI requires different base table” rule in V1 without explicit reconciliation. Additional implementation purpose/context is more useful than an unverified structural restriction; same-table alternatives are a niche issue, not a reason to delay this build.

## 8. Operational guardrail

Existing project instructions require Chris's confirmation for each paid AC Data Oracle invocation, with the exact question stated. Prepare concrete tests before requesting those runs. Creating this planning note did not execute the Oracle, write Snowflake objects, create a GitLab repository, or deploy an app.

## First meaningful checkpoint

GitLab home + isolated schema/sequences + safe save/promotion services + representative imported candidates + one polished metric/SQL workspace. Prove this before expanding all five components.
