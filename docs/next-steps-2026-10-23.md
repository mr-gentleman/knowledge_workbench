# KW app — next steps packet (2026-10-23)

For #chris to sign off, then one Astra review (`scripts/review.sh claude/next-steps`).
Written by #claude from the lanes' branches and notes. Nothing below is merged or deployed unless it says so.

## 1. Where each lane stands

| Lane / branch | What it does | State |
|---|---|---|
| `claude/implementations` | Live PIs load/save, oldest active PI = default, labels with 2+, read-only Run check (DEC-022, DEC-023); PI fact table typed, filled from the SQL | Pushed. Needs sql/007 + 008 live (not verified). PR next. |
| `claude/left-panel` | Ranked search with highlights, keyboard nav, status dots, folder memory; live list replaces sample | Pushed. Conflicts with implementations in `App.jsx`. |
| `claude/fact-tables` | Fact tables screen (browse/create/edit), `GET /api/fact-tables`, revision-checked save | Pushed. **Live:** sql/005 proc created, sql/006 seeded 61 tables; no-change and conflict saves checked live. |
| `claude/unified-metric` | Candidate + canon → one `metric` row, one ID, status `candidate · canon · rejected · retired`; `legacy_id_map` (DEC-024) | Pushed, built on implementations. sql/009 **held**. |
| `claude/hybrid-tables` | Bench: Python save + hybrid ≈ 0.55–0.8 s server vs procedure + hybrid 2.2–2.8 s | Bench pushed. Python port of the save is local WIP. |

Live in `AI_PLATFORM.WORKBENCH` today: old `metric_candidate` (5 test rows), `metric_core` (empty), `metric_calc` (0 PIs),
`fact_table_core` (61), procedures `save_metric` (004 or 008 — not verified) and `save_fact_table`.

## 2. Decisions on record (and one that needs writing)

- **DEC-018** React + FastAPI on SPCS; Streamlit frozen.
- **DEC-020** one all-or-nothing save per page. **DEC-021** save = one CALL to a procedure.
- **DEC-022** SQL check runs through a read-only owner's-rights procedure (`WORKBENCH_SQLCHECK`, inherits `BI_RO`).
- **DEC-023** a check survives edits that don't change the SQL; the oldest active PI is always the default.
- **DEC-024** one metric object, one ID for life; legacy IDs only in `legacy_id_map`.
- **To write — DEC-025:** #chris chose hybrid tables + the save back in Python. That **supersedes DEC-021** (keeps DEC-020's
  all-or-nothing). Decided: the metric save (`save_metric`, 004/008/009) becomes a Python transaction in
  `app/repositories.py`. **Pending §4.2:** whether `save_fact_table` (005) moves too; until then it stays a procedure.

## 3. Proposal — merge and ship order

1. **implementations** → main (clean; also brings the React split to main).
2. **left-panel** → main (left-panel lane resolves `App.jsx` against PI loading; keep both changelog rows).
3. **fact-tables** → main (#claude resolves 5 small conflicts: shared save call, `metricSave.js`, `api.js`, API test, changelog;
   then the PI picker switches to `/api/fact-tables`).
4. **unified-metric + hybrid as one ship** (recommended): hybrid lane builds on unified-metric, ports its save to Python,
   creates `metric` / `metric_calc` as hybrid tables directly, and drops the `save_metric` procedure from sql/009
   (it would be replaced within a day). Then **one** migration (009 + hybrid's 010) and **one** deploy, back to back.
   - Alternative: ship unified-metric with the procedure first, hybrid later — two migrations, two deploys, throwaway proc.
5. hybrid's bench docs can merge any time.

Between the migration and the deploy the live app can't list or save metrics — run them together.

## 4. Decisions needed from #chris

1. **Approve step 4 as one ship** (unified + hybrid together, no procedure in 009)?
2. **Port `save_fact_table` to Python** with the metric save (one pattern), or leave the fact-table procedure as is?
3. **UX-09:** keep, rename or hide *category* on the metric page?
4. **Streamlit:** delete at the step-4 deploy (it only gets renames now), or keep until a set cutover date?
5. **Legacy import trial** (5 metrics, via `legacy_id_map`): start after step 4? Card is up.

## 5. Open items (owner)

- Promotion (LIFE-01) is unbuilt: now a status flip candidate → canon + `promote` revision, gated on description,
  ≥1 passing PI, unique canon name (#claude, after step 4).
- CI's Python jobs likely fail: `api/requirements.txt` lacks `httpx2` (FastAPI TestClient) and `streamlit-keyup` (tests). Add a test requirements file (any lane).
- Is sql/007 + 008 live? Names alone can't tell 008 from 004. Check the definition:
  `SELECT GET_DDL('procedure', 'AI_PLATFORM.WORKBENCH.save_metric(VARCHAR)') ILIKE '%validated_revision_no = IFF(%';` → TRUE means 008;
  `SHOW PROCEDURES LIKE 'RUN_CHECK' IN SCHEMA AI_PLATFORM.WORKBENCH;` → one row means 007. Stays "not verified" until both pass (#chris).
- Evals: keyed on legacy IDs today, quality poor; free to redesign, remap via `legacy_id_map` (later).
- UX-08 "Suggest" button (AI-drafted department/description): idea, not scheduled.

## 6. Not verified

sql/009 and the Python save have never run against Snowflake. No real committed edit of a fact table through the app yet.
Phone layout of the Fact tables screen unchecked. Hybrid timings are a bench, not the app.

## 7. What Astra should check

1. Does one metric object (DEC-024) lose anything we'll need for multi-source suggestions later?
2. Python transaction on hybrid tables vs the procedure: does it keep DEC-020 (all-or-nothing, replay by `op_id`) and
   DEC-008 (an uncertain transaction never leaks to the next viewer) on SPCS's shared connection?
3. Is the merge/ship order in §3 the lowest-risk one?
