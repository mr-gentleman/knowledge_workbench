# V1 journeys — UX contracts

#chris #claude 2026-10-23. Rules and vocabulary: [../ux-principles.md](../ux-principles.md).
Status: J1 drafted for #chris review; J2/J3 outlined.

## V1 shape

- **Scope:** human-entered metrics, one at a time. Machine-generated review, adjudication and
  blessing are V2. Dimensions, fact-table UI, joins, related metrics, usage ranking are later.
- **Two screens:** the **list** (search + department filter) and the **metric page**
  (empty → editing → viewing). Polish concentrates there.
- **Validation:** runs only when the SQL changed; a pass sticks to that SQL revision. Show a
  row preview. Periodic re-checks (CHECK-05) are later.
- **Promotion gate (human source, default):** SQL validated, description present, "when to use"
  present. Fact-table linkage waits until fact tables are in the app. Any author may promote
  once the gate passes.

## J1 — "Is it there? If not, add it."

**Scenario:** Chris needs *Net New ARR*. He thinks it might already exist under another name.

| # | Question | Contract |
|---|---|---|
| 1 | Accomplish | Confirm whether the metric exists; if not, leave a candidate with working SQL. |
| 2 | Understand first | Results show name, knowledge pill, validated mark, and the first line of the description — enough to recognize a match without opening it. Exact-name matches are flagged. |
| 3 | Obvious next action | List screen opens with search focused. No results → primary **Create "Net New ARR"**. A quiet **New metric** is always available. |
| 4 | What changes | Create opens the metric page in editing, name prefilled. Save → header shows `✓ Saved · rev 1`, toast, `Candidate` pill; the record appears **selected** in the list (search cleared if it would hide it). If SQL was entered, validation runs: `Validating…` → `✓ Validated` + preview, or `✗ SQL failed` + message. |
| 5 | Hesitate / fail | Leaving with unsaved edits asks first (Keep editing default). Save failure keeps every input and says why. Exact duplicate name → inline, non-blocking warning linking to the existing record. Double submit creates one record (REL-10). Failed validation ≠ failed save. |
| 6 | Done | Header reads name · `Candidate` · `✓ Validated` · `✓ Saved`. A readiness line shows what promotion still needs, or **Promote** if ready (J3). |

**Decisions for #chris** (defaults recommended):

| ID | Decision | Default |
|---|---|---|
| D1 | Metric page: always-editable document, or **view mode with an Edit button** (⌘E)? | View mode by default; new records open in editing. Reading is the common case, and canon shouldn't look casually editable. Becomes an app-wide rule. |
| D2 | Validation trigger: automatic on save when SQL changed, or a Validate button? | Automatic on save — matches "only when the code changes". Supersedes CHECK-01's "saving SQL does not execute it"; validation still runs on its own connection, bound to the revision. |
| D3 | Preview size | 10 rows, LIMIT enforced server-side. |
| D4 | After first save: stay in editing or switch to viewing? | Switch to viewing — confirms the save visibly and shows the record as others will see it. |

**Acceptance checks (walkthrough):**
- Typing a query filters results as you type; a result shows name, pill, validated mark, description line.
- Zero results shows **Create "<query>"**; clicking it opens the page with the name prefilled.
- After Save, without scrolling: `✓ Saved · rev 1` is visible in the header and a toast appears.
- The new record is selected in the list even if a search was active.
- With valid SQL: `✓ Validated` and a ≤10-row preview appear. With broken SQL: `✗ SQL failed`, the
  message, the SQL intact, and the record still shows `✓ Saved`.
- An exact duplicate name shows a warning with a link; Save still works.
- Navigating away mid-edit asks first; **Keep editing** leaves everything as it was.
- A fast double-click on Save creates one record.

## J2 — "Look it up and understand it." (outline)

Search → open → read. Description and "when to use" lead; SQL readable with highlighting;
validation + preview; author, created/changed, provenance and history in a quiet side panel.
Open decisions: what "provenance" shows in V1 (UX-08); history as a list vs diffs (HIST-01/02).

## J3 — "Fix it and make it canon." (outline)

Edit → save (conflict pattern) → revalidate if SQL changed → readiness checklist → Promote →
`Canon` pill. Open decisions: post-promotion edit flow for canon (LIFE-03); whether promotion asks
for confirmation (default: one short confirm naming what changes — it mints a metric ID).
