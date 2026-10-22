# Engineering decision log

Shared history for Claude, Codex, and human contributors. Record meaningful design
choices and changes here: date, status, origin, context, decision, alternatives,
consequences, and related tasks/commits. Git records exact code diffs; this file
records why. Routine edits do not need an entry. Add a new superseding entry when
a decision changes; retain the original rationale. Task status lives in features.md.
Earlier context remains in app-design-notes.md; do not invent retrospective dates.

## DEC-001 — Revision-based optimistic concurrency

- Date: 2026-10-21. Origin: #codex, requested by #chris.
- Status: implemented in source; Snowflake deployment verification pending.
- Context: the editor fetched the latest revision during submission, which could
  let an older form overwrite a newer record despite the repository's revision guard.
- Decision: retain the opened snapshot/revision per candidate in Streamlit session
  state. Save using the existing conditional UPDATE. Preserve submitted drafts on
  conflict/failure. Offer explicit reload/discard; refresh the whole record after a
  successful save, with new widget keys. Use stable candidate IDs for navigation.
- Alternatives: last-write-wins loses edits; edit locks add expiry/ownership work;
  automatic merging and comparison UI add unnecessary V1 complexity.
- Consequences: no new Snowflake table or schema migration. Conflicts require manual
  recovery. Submitted drafts survive reruns/navigation within the session; unsent
  form changes are not autosaved and browser-session loss is not durable recovery.
  Reload deliberately discards edits. No force-save or silent retry with a new revision.
- Related: REL-01, REL-04, REL-05; tests/test_concurrency.py.

## DEC-002 — Bind persistence to one explicit transaction session

- Date: 2026-10-21. Origin: #codex.
- Status: implemented; actual database isolation/rollback still needs live testing.
- Context: BEGIN/COMMIT used one session variable while helper queries reacquired
  a session. Correctness should not depend on implicit connection reuse.
- Decision: transaction runner passes a session-bound execute function to the write
  and snapshot operations. Zero affected rows raise StaleEdit before snapshot insertion.
- Alternatives: relying on connection caching is less explicit; a new persistence
  framework or stored procedure is not needed for this fix.
- Consequences: candidate and history statements share the transaction session.
  Local mocks verify statement routing and rollback invocation, not Snowflake behavior.
- Related: REL-03; app/repositories.py.

## DEC-003 — Reproducible single-file deployment bundle

- Date: 2026-10-21. Origin: #codex.
- Status: generator implemented; existing Snowflake deployment path unchanged.
- Context: a single-file workaround exists alongside modular source with no checked-in generator.
- Decision: scripts/build_single.py assembles the known modules in dependency order,
  removes local imports, and flattens the existing repo/services references. Edit the
  modular source and regenerate the checked-in bundle before deployment.
- Alternatives: maintaining two independent implementations invites drift. Fixing
  multifile deployment remains a separate task; this does not claim Snowflake cannot use packages.
- Consequences: no new runtime dependency. This intentionally small builder is specific
  to the current modules/names, not a general Python bundler. Update it and its checks
  if module names/import patterns change. snowflake.yml still targets the modular app.
- Related: PLAT-01; scripts/build_single.py; streamlit_app_single.py.

## DEC-004 — One process-wide lock for transactions and editable-baseline reads

- Date: 2026-10-21. Origin: #claude (finding), #codex (dirty-baseline sequence and
  narrowed read scope), decided by #chris. Partially supersedes DEC-002.
- Status: implemented in source; Snowflake/load verification pending.
- Context: DEC-002 gives each save "one explicit transaction session", but every viewer
  shares that session. Container runtime runs one app instance for all viewers, and
  `st.connection("snowflake")` is a process-wide cached resource; Snowpark sessions wrap
  its single connection, and transactions belong to the connection. Evidence: on
  2026-10-21 at about 17:44 CT, two browser windows on the published app ran all 8 of
  their queries under one Snowflake SESSION_ID (5296369438280563,
  ACCOUNT_USAGE.QUERY_HISTORY). So another viewer's statements can run inside an open
  transaction, and a COMMIT or ROLLBACK can take both. Second hazard (#codex): a save
  bumps rev 5 to 6 uncommitted; another viewer opens the editor and captures rev 6; the
  save rolls back; a later save creates a different rev 6; the stale draft's
  `revision_no = 6` check passes and silently overwrites it.
- Decision: `db.db_lock()` is an `RLock` held by `st.cache_resource` (one per process,
  surviving reruns in the single-file build too). `_in_txn` holds it for the whole
  transaction; `get_candidate` holds it because it loads the editable baseline. Lists,
  search and history stay unlocked: at worst they briefly show an in-flight change
  that may roll back, which self-corrects on the next rerun and never feeds a write.
- Rule: any future read that loads something editable or feeds a write check (PI editor,
  promotion checks) takes `db_lock()` too. A test enforces that BEGIN appears only in `_in_txn`.
- Alternatives: (1) connection per browser session: isolation, but we own token
  refresh, reconnects and cleanup outside `st.connection`; (2) pooled/per-save
  connection: same lifecycle work; (3) lock every read: simplest rule, but browsing
  viewers queue on each other for no safety gain.
- Consequences: saves serialize (rare, under 1 s each). Two viewers opening a metric in
  the same ~0.2 s wait ~0.1-0.3 s once; estimated ~3% of opens with 5 heavy users.
  Unlocked reads may execute inside another viewer's transaction; harmless because
  they never write.
- Upgrade triggers: noticeable open latency: reader-writer lock (readers never block
  readers) or per-save connection (removes read locking; then also consider an
  `updated_at` version token in the conditional UPDATE). More than one app instance, or
  long/frequent writes: per-save connection. SQL validation (CHECK) runs authored SQL
  for seconds: give it its own connection from the start; never run it under this lock
  or on the shared connection inside a transaction.
- Related: REL-03, REL-06, PLAT-04; app/db.py, app/repositories.py, tests/test_concurrency.py.

## DEC-005 — Deploy the multi-file app from the repo; retire the single-file bundle

- Date: 2026-10-22. Origin: #coco, requested by #chris. Supersedes DEC-003.
- Status: proposed on branch coco/plat-01-retire-single-file; multi-file deploy verified live.
- Context: the multi-file app failed with `ModuleNotFoundError: app` because the Workspace
  publish manifest listed only `pyproject.toml`, `streamlit_app.py` and `.streamlit/config.toml`
  — `app/` was never uploaded. DEC-003's bundle was a workaround, not a platform limit.
- Decision: `snowflake.yml` is the deploy manifest (artifacts: `pyproject.toml`,
  `streamlit_app.py`, `app/`); deploy with `snow streamlit deploy --replace -c workbench_deploy`
  (CLI >= 3.30; 3.7 rejects `runtime_name`/`compute_pool`). The Workspace copy is deleted.
  Remove `streamlit_app_single.py` and `scripts/build_single.py`.
- Evidence (2026-10-22): commit 729bb7d deployed to `AI_PLATFORM.WORKBENCH.KNOWLEDGE_WORKBENCH`
  (container runtime, owner WORKBENCH_APP); live stage holds `app/*`; published app loaded;
  candidate #2 created (rev 1) and edited (rev 2) with exactly one `edit` revision, actor CLENZINI.
- Consequences: one source, no bundle drift. The container runtime refuses to start without a
  dependency file, so `pyproject.toml` must stay in the artifacts (a `--prune` deploy without it
  took the app down once). No pip packages until an artifact repository is attached.
- Related: PLAT-01, PLAT-02; snowflake.yml, pyproject.toml.

## DEC-006 — Metric names: loose candidates, hard identity rules on canon, routed duplicates

- Date: 2026-10-21. Origin: #claude, agreed by #chris in session. Status: accepted; not implemented.
- Context: today an exact-name match (lower+trim, vs open candidates and active canon) only warns
  and the save proceeds; no DB uniqueness. Plans left "do unresolved collisions hold promotion?"
  open (recommended: yes). Oct-16 handoff already settled: duplicate of canon → reject the
  candidate with `duplicate_of_metric_id` and edit the canon instead.
- Decision:
  - **Candidates stay loose:** warnings only; the candidate pile is the inbox.
  - **Canon names are unique among active canon — a hard rule.** Enforced at promotion and on
    every canon save that changes the name (rename = identity edit). Per the metric ontology,
    same noun + contested definition = one metric (Variant); different computation = Sibling,
    which must carry a distinct name + disambiguation.
  - **Two kinds of canon check.** Identity rules (non-blank, unique name) → save refused, current
    canon untouched. Quality checks (SQL runs, etc.) → saved but not served; the Oracle keeps the
    last passing revision (`served_revision_no`). Either way canon never goes offline.
  - **Routed duplicate flow** when a draft matches/resembles active canon, showing both
    definitions: (1) "Same metric — edit that one": opens the canon editor pre-filled with the
    draft (incl. SQL), before→after view, saved as a normal canon revision; candidate closed as
    rejected + `duplicate_of_metric_id`. (2) "Different metric": distinct name + disambiguation
    required. (3) "Not sure": save as candidate; promotion blocked until 1 or 2 is chosen.
  - No automatic merge of candidate fields onto canon (silent canon change by someone who may
    be wrong); option 1 gives the convenience with one confirming look.
- Prerequisite: settle name normalization (case, whitespace, punctuation — plan open item #2)
  before building the gate.
- Consequences: PIs attached to a duplicate candidate can't be reassigned in V1 (technical plan);
  option 1 re-creates them under the canon metric via the pre-fill.
- Related: LIFE-01, LIFE-02, LIFE-03, LIFE-05, FIND-03.

## DEC-007 — Lock all database access; clean up failed transactions; one canon = one definition

- Date: 2026-10-22. Origin: GPT-6 Astra deep review ([reviews/2026-10-22-astra.md](reviews/2026-10-22-astra.md)),
  triaged by #claude, decided by #chris. **Supersedes DEC-004's unlocked-read rule and its
  "reader-writer lock" upgrade path; supersedes DEC-006's Variant wording.**
- Context: Astra showed (a) a failed or interrupted transaction (incl. Streamlit's StopException,
  which escapes `except Exception`) can leave BEGIN open on the shared connection, so the next
  viewer's COMMIT commits the abandoned change without its snapshot; (b) unlocked reads can show
  uncommitted revisions that later roll back (and the error copy says "check History"); (c) the
  Python driver allows sharing a connection but not safe concurrent use of its internal state;
  a reader-writer lock doesn't fix that.
- Decision:
  - **Every database operation takes `db_lock`**, held only during execute/fetch — never while
    rendering. Cap the list query (LIMIT) and load history on demand, so browsing doesn't hold it.
  - **`_in_txn` cleanup:** BEGIN inside the try; handle `BaseException` and re-raise; if the
    outcome is uncertain (rollback failed / interrupted), reset or quarantine the connection
    before releasing the lock; preserve both errors.
  - **Attribution/ops log:** keep owner's rights (service user) for writes; stamp the human via
    `st.user` in rows, a QUERY_TAG on every statement (op_id, viewer, record), and an op-log row
    written OUTSIDE the transaction (committed / conflict / rolled_back / rollback_failed /
    connection_reset / interrupted + lock wait ms). Caller's rights rejected for writes (SMEs
    would need direct table writes, bypassing app rules); revisit for reads after preview.
  - **Upgrade path:** if measured lock waits annoy → a small connection pool, leased exclusively
    per operation/transaction (not per tab). SQL validation gets its own connection from day one.
  - **Variants retired (Chris):** same number at a different grain/aggregation/source = a PI;
    a different calculation for a different purpose = **two separate canonical metrics** with
    distinct names and their own disambiguation. No `variant_of` links; confusability is found
    from eval/retrieval data later. One canon = one definition, so its PIs are interchangeable.
- Not decided here (later gates, see review §3/§5): enforced name registry before promotion
  (Snowflake UNIQUE isn't enforced), atomic idempotent promotion, coherent serving of definition +
  PIs, revision-bound validation, restore drills.
- Related: REL-08..REL-12, PLAT-04, PLAT-05, HIST-06, REL-07.

## DEC-008 — Streamlit MVP with frontend-independent application logic

- Date: 2026-10-22. Origin: #chris, summarized by #codex.
- Status: direction agreed with #chris in conversation; documentation proposed for merge.
- Context: the Workbench is a collaborative authoring and adjudication app, not only a
  reporting surface. Related-record editing, SQL inspection, navigation, retained drafts,
  and conflict handling may eventually justify React. Preserve the MVP investment without
  building speculative infrastructure or delaying the pre-SME hardening plan.
- Decision:
  - **V1 stays Streamlit.** Prove a representative metric workspace: inspect identity and
    PIs, edit related knowledge, validate/review, and save safely under concurrent edits.
    Revisit React if actual workflows repeatedly fight reruns, navigation, or editing state.
    React is a likely future option, not a committed rewrite or a V1 release dependency.
  - **Keep application logic frontend-independent.** Pages own widgets, navigation, feedback,
    and per-user drafts/baselines. Ordinary Python services own validation, authorization
    decisions, workflow transitions, and save orchestration. Repositories own parameterized
    SQL, conditional updates, transactions, and history persistence. Keep one authoritative
    implementation of each business rule; no SQL or policy duplicated in UI handlers.
  - **Make operation boundaries explicit.** Pass record IDs, intended changes, expected
    revisions, and verified actor context; return committed IDs/revisions and recognizable
    outcomes (including conflict, validation failure, and uncertain save). Services must not
    depend on Streamlit widgets, reruns, or session state. Isolate framework-specific identity
    and connection acquisition at the adapter boundary; evolve existing modules only when
    touched for a concrete need, rather than starting a wholesale refactor.
  - **Identity is trusted context, not form data.** Today obtain the actor from verified
    `st.user`; a future API must derive it from its authenticated request/session, never
    trust a browser-supplied username. Enforce applicable permissions in application
    operations, not just button visibility. Preserve DEC-007's owner-rights writes, human
    attribution, query tags, and operation logging; shared service credentials alone do
    not provide individual attribution.
  - **No API or second frontend solely for portability.** Streamlit can call Python services
    directly now. A future authenticated Python API can expose those same operations to
    React. Do not add generic interfaces, pass-through wrappers, a custom auth system, or a
    synchronization framework for hypothetical clients.
  - **Temporary coexistence is an option, not current scope.** Before enabling two writers,
    prove compatible permissions, revision checks, retry/idempotency behavior, atomic
    record/history writes, and audit semantics across both. Sharing code is insufficient.
    Process-local locks protect the shared connection within their process; they do not
    coordinate independent app instances. Follow DEC-007's exclusive connection-leasing
    direction when needed and verify cross-instance database correctness before rollout.
  - **Frontend and hosting are separate decisions.** Current Streamlit-in-Snowflake container
    runtime remains the MVP target. A custom React/API deployment on Snowpark Container
    Services is a candidate, not already selected or equivalent to the current deployment.
    Compare it with company hosting on authenticated identity, scoped write permissions,
    attributable operations, inspectable configuration/code/logs, deployment and recovery
    control, and maintenance ownership.
- Hosting rationale: #chris reports that the existing company React platform uses a shared
  read-only Snowflake service account for freehand SQL without individual attribution and has
  limited configuration transparency. These are reported constraints, not an audit performed
  here. Do not assume that platform fits Workbench writes merely because it hosts React.
  A shared account can be appropriate with application authorization and auditing; adopting
  custom hosting also means owning its operational maintenance.
- Alternatives: rewrite in React now (premature before proving workflows); couple rules to
  Streamlit (costly migration and duplicated rules later); build an API and two UIs now
  (unnecessary V1 complexity); automatically adopt company hosting (controls unverified).
- Consequences: preserve the existing schema/lifecycle decisions and hardening order. Apply
  these boundaries incrementally during feature work. React/hosting evaluation is deferred;
  no runtime code, grants, schema, deployment, or migration is changed by this decision.
- Related: AGENTS.md architecture boundaries; docs/features.md plan of record; DEC-001,
  DEC-002, DEC-007; REL-08–12, PLAT-03–05; technical build plan steps 3 and 5.
