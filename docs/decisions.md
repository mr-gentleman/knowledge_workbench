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
