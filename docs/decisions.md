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

