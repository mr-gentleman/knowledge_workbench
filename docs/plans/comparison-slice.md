# Comparison slice: Streamlit vs React

Requested by #chris; written by #claude 2026-10-22. Narrows DEC-009's comparison from
"two MVPs" to **two lean builds of one slice**: navigation/discovery, search, and the
metric editor with its PIs. Status stays in [features.md](../features.md) (UX-01/02,
FIND-01/04); this file only defines what both builds must do and how they're judged.

**Why this slice:** it's the most common task, it's being built first anyway (manual
editing comes before adjudication of auto-derived assets), and it already exercises
what separates the frameworks: multi-pane navigation, related-record editing, a
real SQL editor, drafts across navigation, and click latency. Adjudication / A-vs-B
review comes later and isn't part of this comparison.

## Step zero: the SQL editor check (before building anything else)

The technical build plan requires highlighting **while typing**, line numbers,
indentation, and reliable paste. Plain `st.text_area` doesn't meet that: no
highlighting, Tab leaves the field, and the value syncs only on blur.

Resolve one contradiction first: the Oct-16 handoff says container runtime installs
from pip (try `streamlit-code-editor` / `streamlit-ace`), while AGENTS.md says no
packages beyond what ships with the runtime unless an artifact repository is attached.

1. Find out whether this account can attach an artifact repository (PyPI) to the
   Workbench, and what that takes. That's a platform change, per AGENTS.md.
2. If yes: deploy one throwaway page with a candidate editor component in the real
   app (not local). Check highlighting while typing, Tab/Shift-Tab indent, line
   numbers, undo, and pasting the 80-line test query (below) with no reflow or loss.
3. Record the outcome in UX-02.

**If no acceptable editor runs in SiS, that alone is a strong React signal.** React's
equivalents (Monaco or CodeMirror 6) meet the requirement out of the box.

## Layout: three panes

| Pane | Contents |
|---|---|
| **Nav rail** | Metrics · Fact tables (later: Queue) |
| **Explorer** | Search box; filters (All / Canon / Candidates; include closed/retired); department groups as collapsible folders (Finance open). Folders are a presentation of `department`, not ownership (DEC-010). |
| **Detail / editor** | The selected metric: identity and definition on top, PI list below |

In Streamlit this is sidebar + columns, with a rerun per click. How that feels is part
of what's being tested.

## Metric editor

**Top: identity and definition.** Candidate vs canon badge; editable fields
(name, description, disambiguation, department, category) visually distinct from
read-only ones (ids, source, author, revision, promoted/duplicate links).

**Below: the PI list.** A list with **+ Add implementation**, no fixed slots or
maximum. Legacy data is exactly one PI per metric (342 of 342), so the common case
must look like a simple single form:

- One compact row per PI. If there's only one, it starts expanded.
- Click a row to expand it; one expanded at a time.
- **Row title is generated, not typed:** fact-table grain + table, e.g.
  "Daily · ssa_daily_mrr_consolidation_rollup". No name field.

### PI row fields (all exist in `WORKBENCH.METRIC_CALC`)

| Field | Edit | Column | Notes |
|---|---|---|---|
| SQL | Yes, required | `sql_text` | The SQL editor |
| When to use | Yes, required once there are 2+ PIs | `disambig` | Carries the meaning a name would have |
| Fact table | Pick from active fact tables | `source_table` | Three-part name (CHECK-03); links to the fact-table page; grain for the row title comes from there |
| Default | Yes, exactly one per metric | `is_default` | What the agent uses when nothing says otherwise |
| Validation | Read-only + **Validate** button | `validation_*`, `validated_revision_no` | "✓ passed on rev 4" / "✗ message"; shown as stale once the SQL is edited after passing |
| Served | Read-only | `served_revision_no` | "Agent uses rev 3; you're editing rev 5": saved ≠ served |
| Source | Read-only badge | `source` | SME / auto-gen |
| Retire | Action, not a field | `status` | With reason (LIFE-03) |
| Author / updated | Read-only footer | `original_author`, `updated_*` | |

**Not carried over from legacy `DICTIONARY.METRIC_CALC`:** `key_filter` (empty on all
rows; filters belong in the SQL), `grain` (empty on all rows; lives on the fact table),
`confidence` (a constant per source), `definition_label` (duplicated the metric name).

**Open, decide on paper before building (it matters in both frameworks):** save scope.
Is it one Save for identity + all PIs, or a Save per PI? It must be obvious which records
a click writes, and what happens to an unsaved PI edit when you switch metrics.

## Test checklist (both builds, same data)

Data: the five-metric import trial from SERVE-02, plus fixtures for one incomplete
candidate and one canon metric with three PIs. Writes go to an isolated test schema.
Mocked parts are labeled.

1. Browse Finance via folders; search across departments; filter Candidates vs Canon.
2. Open a canon metric and an incomplete candidate. Status and editable vs read-only
   are obvious without explanation.
3. Edit the definition; add a second PI; set its "when to use"; switch the default.
4. SQL editor: highlighting while typing, Tab indent, line numbers, undo; paste the
   80-line test query (a real de-Lookerified Finance query, e.g. NRR).
5. Validate: break the SQL, see the failure, fix it, see which revision passed.
6. Save: it's clear what got saved. Switch metrics with an unsaved edit and record what happens.
7. Follow a PI to its fact table and back. Search text, filters, and selection survive.
8. Second session saves first; the stale save keeps the draft and explains the conflict.
9. **React only:** deployed on SPCS (not localhost): permitted and denied users, two
   distinct actors, one attributed test write.
10. One follow-up change after both work (e.g. add a field to the PI row): note the
    files touched and the effort.

**Measure:** warm click → detail and save → confirmation times (separately from cold
start, SQL execution, and lock waits); backend calls per click; framework workarounds;
places a tester hesitated or lost context. Time-box: about two days per build.

## Deferred (not in this comparison)

Bulk add / AI-assisted intake · adjudication and A-vs-B review · Needs-attention
stewardship view (STEW-01) · separate implementations browser · dimensions and joins.
