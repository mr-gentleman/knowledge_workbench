# Handoff — one metric object (DEC-024)

For #chris (ACCOUNTADMIN in Snowsight) or CoCo. Branch `claude/unified-metric`, built on
`claude/implementations` (needs its sql/007 and sql/008 applied first, already done if PI checks work).
Nothing here has been run.

## Order matters

1. Apply `sql/009_one_metric_object.sql` whole with **Run All**, as ACCOUNTADMIN.
2. Deploy app code from this branch (or a merge containing it) right after.

Between 1 and 2 the deployed app (React on SPCS, and the frozen Streamlit app) can't list or save
metrics: it still reads `metric_candidate`. Code from this branch fails the same way before step 1.

## What 009 does

- Drops `AI_PLATFORM.WORKBENCH.metric_candidate` (5 test rows), `metric_core` (empty) and
  `seq_candidate_id`. Old revision/op_log rows stay (append-only), under record_type `metric_candidate`.
- Creates `AI_PLATFORM.WORKBENCH.metric` (status `candidate | canon | rejected | retired`, IDs from
  `seq_metric_id`, 100000 up) and `legacy_id_map`; recreates `metric_calc` (empty) with
  `metric_id NOT NULL` and no `origin_candidate_id`.
- Replaces `save_metric` (request key `metric`, result `metric_id` / `metric_revision`) and hands
  ownership to `WORKBENCH_APP`.

If the procedure fails to compile, send the error back; it is 008's body with names changed.

## Verify

Queries at the bottom of 009, then in the app: New metric → save → the header shows
Candidate · #100000 (or higher); edit it and save again → rev 2.
