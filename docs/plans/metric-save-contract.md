# Metric page save — shared contract (DEC-020)

#claude 2026-10-23. The interface between the page (React, FE-02) and the backend (PLAT-09 procedure +
`app/services.py`). Agree changes here before either side diverges.

## Call

`services.save_metric(actor, op_id, candidate, calcs, change_note) -> Outcome`

- `candidate`: `{id | None (create), expected_revision, create_token (create only), fields}`
- `calcs`: list of `{calc_id, expected_revision | None (new), fields, retire: bool}`.
  New PIs carry an id reserved with `reserve_calc_id()` (DEC-019's retry key). Only send PIs the
  draft touched; untouched ones are omitted.
- `fields` hold the full draft values for that record; the backend decides what changed.

## Behaviour

1. Validate every record first (required fields, PI label rule when 2+ active, first active PI is
   default). Any problem → `invalid`, nothing written.
2. One transaction. For each record whose content changed: conditional UPDATE on `revision_no`
   (or idempotent INSERT), one snapshot. Unchanged records: no write, no revision.
3. Any conditional UPDATE hits 0 rows → roll back everything → `conflict`, listing every
   conflicting record with latest values, changed fields, who and when.
4. Replay (same `create_token` / reserved ids, same content) returns the first result; different
   content → warning, the caller keeps its draft as unsaved.
5. One op_log row per outcome. Actor is the viewer, never CURRENT_USER().
6. After commit, SQL that changed gets a run check bound to its new revision. Run failures show on
   the card; they never turn a committed save into a failure.

## Outcome

`{status: saved | no_change | invalid | conflict | failed, candidate_id, candidate_revision,
calc_revisions: {calc_id: rev}, problems: [{record, field, message}],
conflicts: [{record, latest, changed_fields, by, at}], warnings: []}`

## Acceptance (controlled demonstrations)

- Edit definition + one PI + add one PI → one Save → three records versioned once each, the
  untouched PI unchanged.
- Remove a PI → retired, snapshot written, gone from read mode; history keeps it.
- Another session saves one PI meanwhile → whole save refused, nothing written, draft intact,
  conflict names that PI.
- Invalid PI (missing label with 2+) → nothing written, error on that card.
- Retry after a lost acknowledgement → no duplicates.
- No-op Save → `no_change`, no revisions.
- Broken SQL → `saved` plus `✗ SQL failed · rev N` on the card.
