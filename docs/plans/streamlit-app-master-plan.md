> **Copied 2026-10-21** from `oracle_bi_agent/notes/streamlit-app-master-plan.md` (the Oracle project repo, not in this repo). Read-only reference — the original is authoritative; relative links below point into that repo and will not resolve here. Where this plan conflicts with `docs/features.md` or `docs/handoff-2026-10-16.md` decisions, those newer files win.

# Streamlit Knowledge Interface — Master Plan

> **Later technical decisions:** [Technical Build Plan](streamlit-app-technical-build-plan.md) records the latest metric-only release scope, PI attachment rules, GitLab/logging requirements, and implementation sequence. It supersedes earlier guidance here where noted: initial canonical promotion requires at least one qualifying PI, and PI reassignment is deferred beyond V1.

Updated: 2026-09-15. Project: AC Data Oracle.

Status: consolidated planning baseline; implementation and live Snowflake state have not been verified by this review. Dates below are targets, not release commitments.

## Authority and reading order

This is the master Streamlit app plan consolidating the September 15 discussion. Where it conflicts with older app notes, this plan governs this build. Preserve older documents as historical context.

Related project notes (paths relative to this file in the project notes folder):

- [August MVP plan](knowledge-interface-mvp-plan-2026-08-19.md)
- [Knowledge-layer architecture](../docs/concepts/knowledge-interface-architecture.md)
- [Earlier SME app design](sme-entry-app-design-2026-08-11.md)
- [Knowledge-layer backlog](knowledge-layer-todo.md)

## 1. Objective and boundaries

Build a lean, maintainable Streamlit-in-Snowflake application for maintaining the human knowledge layer. Replace the Google Sheets maintenance path when the replacement is proven. Start with metrics, then fact tables and dimensions.

The app is the stewardship surface, not the entire knowledge system:

    Human authoring → durable human knowledge ─┐
                                              ├→ resolution → working dictionary → Oracle
    Automated generation → machine knowledge ─┘

Identity resolution asks which canonical metric an assertion describes. Knowledge resolution asks which assertions/revisions downstream systems should consume. Keep these separate. The working dictionary is a logical consumer representation, not a mandated physical table design.

Do not absorb automated generation, semantic resolution research, retrieval redesign, or quality evaluation into this app build.

## 2. Terminology and identity

- **Canonical Metric:** recognized organizational measurement with a clear meaning and purpose, independent of its SQL. Canonical status establishes identity, not quality.
- **Metric Physical Implementation:** calculation against physical data, bridging the logical metric to warehouse objects. Use this name instead of Metric Implementation.
- **Candidate:** a proposed knowledge assertion. All new metric submissions, including SME input, begin as candidates internally.
- **Revision:** a saved change to an existing durable record. Routine maintenance does not create a new candidate or canonical metric ID.

A canonical metric may have zero, one, or many physical implementations. Identity can be established with a name and meaningful description before SQL is ready. The Oracle needs an applicable usable implementation to calculate it.

Dimensional slices do not automatically become metrics. France ARR ordinarily means ARR filtered to France. Closely related but genuinely different metrics are valid if their distinctions are documented. Different SQL does not prove different identity; identical SQL does not prove identical meaning.

Physical assets have simpler natural identities: fact table = fully qualified table; dimension = fully qualified column. Do not force metric semantic-resolution machinery onto them.

## 3. Sources and promotion philosophy

Four sources are anticipated:

| Source | Meaning | Timing |
|---|---|---|
| Direct SME authoring | Intentional knowledge creation/maintenance | V1 |
| Automated extraction / reconnaissance | Robot reviews source assets and infers knowledge | Next source |
| Conversational discovery | Agent and human find useful knowledge during investigation | Future |
| Stakeholder feedback | Correction or challenge arising during use | Future |

Source is provenance, not a verdict on credibility. Use explicit metadata rather than inferring source from ID strings.

Direct SME input has deliberately light promotion checks to encourage contribution and control. Other sources can qualify for automatic promotion, but should face stronger evidence requirements. Do not build those policy engines in V1.

Promotion may establish a new identity or associate an assertion with an existing one. It must not automatically mint another metric merely because another candidate arrived.

## 4. Incremental authoring; no separate draft object

Use one candidate record that may be incomplete. “Draft” can be a UI label. Do not add a mandatory submission step or separate draft entity in V1.

| Action | Minimum rule |
|---|---|
| Save metric candidate | Nonblank name |
| Establish canonical identity | Meaningful description plus lightweight identity checks |
| Save physical implementation | Link to its metric; SQL may be unfinished |
| Serve implementation for calculation | SQL and agreed execution/context checks pass |

Check on explicit save and immediately report the outcome. Do not unexpectedly promote an incomplete SME record later through an invisible background process.

Primary checks discussed: exact-name collision and whether SQL runs. Keep structural requirements and safe execution controls. Do not import the old seven-blocker policy wholesale. SQL execution is an implementation check; failure need not invalidate an otherwise established metric identity.

Examples of UI outcomes:

- Saved — add a description to establish this metric.
- Possible duplicate — review the existing definition.
- Metric created — add a physical implementation.
- SQL saved — execution check failed; this revision is not served.

SQL execution proves executability, not business correctness. Validation must attach to the SQL revision actually checked; editing SQL invalidates its earlier validation result.

## 5. Duplicates, cousins, and disambiguation

V1: exact-name checks, search, readable existing definitions, and optional disambiguation guidance. Define name normalization and collision behavior before implementing the gate.

Future: lightweight semantic suggestions before creation and deeper post-save review. Show the suspected overlap and relevant definition; do not describe an uncalibrated similarity score as “95% probability of duplicate.” Semantic similarity should usually warn rather than block SME authoring.

Useful responses: use an existing metric; explain why the new concept differs; save unfinished. Preserve the explanation as useful disambiguation for people and the Oracle.

Post-save findings need an owner and closure: duplicate, justified cousin, slice, alternate implementation, or insufficient evidence. Confirmed duplicate consolidation must preserve history and references. Merge tooling is future scope; stable IDs are required now.

## 6. ID strategy

Recommended V1 baseline:

- One Snowflake sequence for candidate IDs across all sources.
- A separate Snowflake sequence for canonical metric IDs.
- Allocate a candidate ID on first persistence; allocate a metric ID only for a newly established identity.
- Many candidates may map to one metric ID.
- Keep physical implementation identifiers stable independently of metric IDs; exact DDL is to be defined.
- Never reuse or casually renumber IDs. Do not reset sequences during imports or generation runs.
- IDs are opaque identifiers, not names, semantic hashes, source codes, or chronological counters. Use timestamps for chronology; gaps are acceptable.

Source-specific candidate sequences add composite-key/prefix complexity without enough benefit here. Optional display labels C-101 / M-27 are separate from source metadata.

Sequence reference: https://docs.snowflake.com/en/user-guide/querying-sequences

## 7. Isolation and the one-time import

Develop against an entirely separate set of base tables. Preserve existing field shapes where useful; do not redesign everything. Configure the destination explicitly and ensure the app write role cannot modify the old production dictionary.

Import the current predominantly human-authored dictionary as **new human-authored candidates**, preserving original authors. Run lightweight promotion checks and review exceptions. Do not silently grandfather imported rows around that path.

This is a one-time import. Do not build a reusable migration framework, recurring migration system, or bidirectional synchronization. If rerunning a failed batch is necessary, inspect what committed before inserting again; the one-off operation should not create accidental duplicates.

Retain whatever simple legacy references are needed to reconnect implementations and audit the import. Old IDs are source references; new identities use the new namespace. Do not infer that production IDs are clean from historical notes.

Keep production running on the old dictionaries until verification. At cutover, briefly pause old-path edits and reconcile any intervening changes manually. Switch the Oracle dictionary pointer and retire the replaced authoring path. Retain the old data/configuration for rollback. New edits made after cutover need preservation if rollback occurs.

Metric-only cutover must preserve fact-table/dimension access: use component switches or verified copies, depending on the actual consumer contract.

## 8. Authorship and objective provenance

Distinguish:

- **Original author:** person who originally authored the bulk of the content; import and routine edits do not overwrite this attribution.
- **Updated by / at:** latest content change actor/time.
- **Revision actor / time:** actor/time for each recorded action.
- **Import/entry actor:** who entered somebody else's content.

Preserve known original authors and dates. Unknown history stays unknown; import time is not original creation time. Record the importer separately. Do not automatically transfer original authorship when somebody edits meaning-bearing fields.

Use trusted viewer identity for action attribution, not editable form values. Verify actual viewer identity separately from execution rights. No custom authentication system is needed.

## 9. Rich history without major/minor workflow

Record every successful save that changes persisted content. One save is one revision, even when several fields change. No revision for keystrokes, no-op saves, or failed saves.

Baseline: mutable current record plus append-only complete revision snapshots, written atomically. Each snapshot contains record ID, revision number, content, actor, timestamp, action, and optional change note. Ensure older payloads remain interpretable as the schema evolves.

Maintain metric and physical implementation histories separately. The metric detail page may combine them into a timeline: Gabe changed the definition; Matt changed the monthly SQL. Show prior content and simple before/after comparisons.

Capture all changes now. Filtering, collapsing minor edits, significance classification, generated summaries, and polished restore controls are future display features. A one-character SQL edit can be consequential; size is not significance.

A tested recovery procedure is V1; a sophisticated restore UI is not.

## 10. Machine lineage and human approval — future-ready direction

Machine pools may be regenerated; human-maintained knowledge must survive. A shared candidate namespace does not mean a shared durability policy.

When automated extraction arrives, record generation run, source reference, source candidate/version, and actual derivation where known. New generation outputs get new candidate IDs and may resolve to existing canonical metric IDs. Similarity between outputs does not by itself imply derivation.

Explicit human approval or edit-and-approval creates a durable human-maintained snapshot of the **complete approved state**, with provenance showing machine origin and human interaction. A derived human candidate can link to the exact machine candidate/revision. Later maintenance revises that durable record.

Preserve the supporting source snapshot; a pointer to a deleted machine artifact is not sufficient lineage. Also retain stable underlying source references where possible. Historical project guidance to anchor adjudications in durable source assets remains compatible with recording which generation was reviewed.

No full lineage graph, machine review UI, or retention engine in V1. Final machine retention policy and exact tables remain open.

## 11. Engineering rules and consumer contract

    Streamlit pages → Services → Repositories → Snowflake
                         Shared structured models

Pages handle interaction; services own workflows/invariants; repositories own persistence and transaction boundaries. Do not mechanically create every possible class or build an arbitrary-schema CRUD framework. Abstract after the second real use case.

V1 invariants:

- Current state and revision history commit together or neither commits.
- Stale edits cannot silently overwrite newer revisions; use expected revision checks.
- Repeated/uncertain submissions must not duplicate records or revisions accidentally.
- Physical implementations reference existing metrics and appropriate physical assets.
- Authorship fields distinguish original authors from trusted action actors.
- SQL is content when saved, not an executable persistence command. Parameterize persistence values.
- Any SQL validation execution is restricted and bounded.
- Preserve entered content after failures; distinguish conflict, validation, permissions, write failure, and unknown outcome.

Expose a thin consumer view/adapter in the shape the Oracle expects. Exclude incomplete candidates and ineligible implementations. An unfinished edit must not silently replace the last eligible revision. Explicit deprecation must withdraw according to policy rather than accidentally falling back forever.

Define implementation context and default selection. Do not build a full resolution engine just to supply the existing consumer contract.

## 12. V1 versus future

### V1 release requirements

- Isolated tables/configuration and safe permissions.
- One-time human-candidate import with preserved authorship.
- Browse/search/detail/create/edit for metrics and physical implementations first.
- Incremental saving and lightweight promotion; exact-name check.
- Multiline SQL editing/viewing/copying and safe execution checks before serving.
- Multiple physical implementations, with clear selection context/defaults.
- Atomic snapshots, stable IDs, concurrency and retry handling.
- Visible authorship, revision history, and useful failure messages.
- Verified Oracle consumer representation and cutover/rollback procedure.
- Fact-table and dimension maintenance next; retain their existing paths if first release is metric-only.

### Defer

- Automated extraction, conversational discovery, and feedback intake integrations.
- Machine review/approval UI and source-specific automatic promotion engines.
- Semantic duplicate detection, post-save quality queues, merge/split tooling.
- Major/minor history classification, polished SQL diffs, generated change summaries.
- Quality/contribution dashboards, retrieval/generation scorecards, advanced observability.
- Generic CRUD engines, synchronization frameworks, elaborate private draft/approval workflows.
- SQL formatting if it threatens delivery of the core editor.

## 13. Order of operations and milestones

### Tuesday September 15 — 1–2 hours: contract and isolation

Inspect actual dictionary fields/consumer expectations. Define minimum models, ID allocation, author/import/updater fields, save/promotion rules, and history structure. Create isolated storage and connect the app. Verify production write isolation.

**Milestone:** isolated connection and concrete V1 contract. No production cutover.

### Wednesday September 16 — one complete metric slice

Import a small representative set through the candidate path. Build browse → detail → create/edit → save → reload → history. Include exact-name checks, trusted attribution, atomic history, stale-edit rejection, and preserved input on failure.

**Milestone:** create and revise a canonical metric with an explainable history.

### Thursday September 17 — physical implementations

Add one-to-many implementations, SQL editor, safe validation, revision-bound validation outcomes, context/default selection, implementation history, and metric navigation.

**Milestone:** edit SQL, validate it, and clearly distinguish saved from usable by the Oracle.

### Friday September 18 — test consumer and dogfood

Finish the thin read view/adapter, load remaining intended records, review promotion failures, and verify a test Oracle configuration. Have one or two SMEs find NRR, inspect calculations, edit guidance, create an incomplete metric, and inspect history. Remove test data from release contents.

**Milestone:** an eligible authored change reaches the test consumer; incomplete work does not. Friday is a target for this proof, not mandatory production release.

### Week of September 21 — coverage, hardening, cutover

Add fact tables/dimensions using proven patterns. Resolve user friction, verify imports and recovery, finish deployment/configuration notes, then pause old edits, reconcile once, verify, switch the pointer, and retire the replaced authoring path.

**Milestone:** normal maintenance uses Streamlit and production consumes the new dictionary successfully.

## 14. Required tests and release gates

- Two editors: stale update rejected and entered content retained.
- No-op save: no revision. Double submit/refresh: no duplicate create.
- Failed audit write: current record unchanged. Interrupted connection: outcome can be checked before retry.
- Trusted viewer identity differs correctly from original imported author.
- Nulls, arrays/synonyms, Unicode, apostrophes, long descriptions and long SQL round-trip correctly.
- Exact-name collision behavior matches documented normalization/policy.
- No implementation, multiple implementations, and default/context selection behave predictably.
- Invalid, unsafe, slow, permission-denied SQL produce clear outcomes and preserve work.
- SQL changed after validation does not inherit the old result.
- Incomplete edit stays out of serving; explicit retirement does not resurrect an old revision.
- Import content and relationships reconcile; test rows excluded; physical references remain grounded.
- Representative consumer queries use the intended dictionary and implementation.
- Previous revision is recoverable and rollback configuration is understood.

Protect isolation, integrity, attribution, usability, consumption, and recovery before declaring release. Cut polish before these gates.

## 15. Changes from older notes and unresolved details

Current decisions replace: old Monday–Friday deadline; Metric Implementation terminology; source-local candidate sequences; author-versus-enterer deferral; direct canonical import; elaborate migration proposals; seven hard promotion blockers; major/minor recording decisions; absence of candidates on SME input.

The August mutable-current-plus-history architecture remains the baseline. The older claim that append-only writes automatically eliminate concurrent lost updates/idempotency problems must not be used as a substitute for explicit checks.

Historical notes report three legacy ID schemes, synthetic view-only IDs, and physical implementation grounding in fact tables. These are inspection leads, not verified current production facts. Do not require repairing the entire old ID system before building isolated replacements, but preserve needed relationships during import and cutover.

Details to settle during implementation, not by expanding scope now:

1. Exact columns/types and production consumer compatibility.
2. Exact-name normalization and whether unresolved exact collisions hold promotion (recommended) or have a deliberate override.
3. Physical implementation context/default selection and serving pointer representation.
4. Safe SQL validation interface, execution identity, timeout, and when checks rerun.
5. How existing source relationships map into newly allocated IDs in the one-time import.
6. Older project rule “physical implementation implies different base fact table” versus current examples allowing multiple calculation contexts: do not silently enforce it without reconciling the actual intended semantics.
7. Explicit deprecation and last-eligible-revision behavior.

Project operational guardrail: existing project instructions require Chris's explicit confirmation before each paid AC Data Oracle invocation, with the exact question stated. Planning consumer tests here does not itself authorize those calls. No agent, Snowflake writes, or production tests were run when creating this note.

## Guiding principle

Keep the interface simple, identities stable, provenance explicit, and every committed change recoverable. Build the smallest safe path from human contribution to verified Oracle consumption.
