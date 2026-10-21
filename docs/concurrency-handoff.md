# Concurrency fix — Claude review and Snowflake verification

2026-10-21 · #codex · REL-01 is VERIFY, not deployed/confirmed.

## Changes

- Editor retains the opened candidate revision and submitted draft in session state.
- Explicit reload discards draft; successful save refreshes the whole baseline and widget keys.
- Candidate navigation uses IDs. Conditional UPDATE is retained as the final guard.
- Candidate writes and history INSERT use the same explicitly bound session.
- Unexpected save errors retain the draft and advise checking history before retrying
  (commit outcome may be uncertain after a connection failure).
- No schema/table changes. Repeat creation (REL-02) remains a separate open task.
- V1 conflict UI is a message plus reload/discard. Copy draft text before reloading
  if you want to reapply it; comparison/merge UI is deferred.

## Local verification

Run with Streamlit installed: `python -m unittest discover -s tests -v`.
Six tests passed: stale baseline/draft/reload, success and no-op, conditional-write
conflict, generic database failure, snapshot failure rollback routing, zero-row
rollback without snapshot. UI tests use Streamlit AppTest with mocked persistence.
These do not prove real Snowflake concurrency or rollback behavior.

Regenerate: `python scripts/build_single.py`.
Syntax check: `python -m compileall -q app streamlit_app.py streamlit_app_single.py scripts`.

## Review/deploy checklist

1. Inspect source and generated bundle; confirm the actual app runtime supports the
   Streamlit APIs used. Deploy streamlit_app_single.py through the existing workspace
   process, or the modular source if package deployment has since been fixed.
2. Record deployed commit and published app version. Test the published app, not only preview.
3. Use a disposable candidate in two browser sessions. Both open rev N. Save A,
   then submit B without refreshing. Expect a conflict, retained B draft, A's data
   unchanged, and no extra history revision for B.
4. Reload B explicitly: expect A's current values. Edit/save again successfully.
   Verify unchanged Save adds no revision and header/revision refresh after success.
5. Test near-simultaneous saves with separate database sessions. At most one write
   based on N may succeed; the other must be handled without an automatic overwrite.
6. In a controlled test environment, inject a failure in the history INSERT and
   verify the candidate update also rolls back. Do not revoke shared production grants
   to manufacture this test. Check METRIC_CANDIDATE and REVISION directly.
7. Verify submitted drafts do not leak between candidates. Unsubmitted form changes
   are not autosaved; do not promise persistence across navigation/browser closure.
8. Record results in features.md; mark REL-01 DONE only after live verification.

Rationale: [decisions.md](decisions.md). Existing detailed acceptance scope remains
in [features.md](features.md).
