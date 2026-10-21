# Open items

## Legacy import — ID translation (decide before the first real import)

When legacy `AI_PLATFORM.DICTIONARY` content is imported (expected once, possibly
again later — mechanism TBD), every reference to an old ID must be translated to the
new IDs and stay bundled correctly:

- old `metric_id` → new `candidate_id` / `metric_id`
- old `calc_id` → new `calc_id`, still attached to the right metric
- PI `source_table` (legacy 2-part `SCHEMA.TABLE`) → 3-part `AC.SCHEMA.TABLE` matching `fact_table_core`
- downstream artifacts keyed on old IDs (eval Test Q&A, exemplars) remapped at cutover

Load order: fact tables → candidates + PIs → validate → promote.

Before the first real import the schema is disposable (drop/recreate is fine, test
rows burn IDs harmlessly). After real canon exists: never reset sequences, never reuse IDs.

## Schema placement / serving

- `WORKBENCH` = authoring (dev for now). Long-term home may be `GUIDANCE` (manual entry)
  alongside `CORPUS` (auto-scraped) — a schema rename/move is a one-liner later.
- Consumable end-state dictionaries live in `DICTIONARY`. No served view in WORKBENCH.
- Whatever builds `DICTIONARY` from here must read each PI at `served_revision_no`
  (last passing revision, from `revision.snapshot`), not the live row — so in-progress
  or broken edits never reach the Oracle.
