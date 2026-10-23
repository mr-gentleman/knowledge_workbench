# Plan map — big picture → zoom

One page to orient. Zoom levels: **L0** why/where → **L1** V1 → **L2** what's being built now, where.
Updated 2026-10-23 (#claude). Details: [features.md](features.md) (status), [decisions.md](decisions.md) (why),
[ux-principles.md](ux-principles.md), [plans/v1-journeys.md](plans/v1-journeys.md).

## L0 — where the Workbench sits

```
 human knowledge ──► WORKBENCH (this app) ──► DICTIONARY (served) ──► AC Data Oracle
   SMEs, BI            candidates → canon        last-passing SQL          answers questions
 machine knowledge ─┘  (V2: review/adjudicate)
```

| Release | What it means | Status |
|---|---|---|
| M1 hardening | Saves can't corrupt or duplicate | Live (deployed d1b6783), branch unmerged |
| **V1** | One workflow, polished: find → understand → correct → candidate/canon | **Now** |
| V2 | Review machine-generated knowledge; adjudicate competing definitions; bless | Next |
| Cutover | Serve canon to the Oracle; import ~200–300 legacy metrics; retire Sheets | After V2 starts |
| Later | Dimensions, fact tables, joins, related metrics, usage, business concepts | — |

## L1 — V1

```
 LIST SCREEN                          METRIC PAGE
 ┌───────────────┐   open / create   ┌──────────────────────────────────┐
 │ search-as-you │ ────────────────► │ Name · Department   [Candidate]  │
 │ -type         │                   │ Description                      │
 │ department    │ ◄──────────────── │ When to use                      │
 │ filter        │   back / find     │ SQL ▸ card(s): editor, validate, │
 │ status badges │                   │       preview                    │
 └───────────────┘                   │ details rail: author · history   │
                                     │ [Promote] when the gate passes   │
                                     └──────────────────────────────────┘
```

| Journey | Contract | Built |
|---|---|---|
| J1 Is it there? If not, add it | Drafted; D1–D4 open | Search-as-you-type (unmerged) |
| J2 Look it up and understand it | Outline | — |
| J3 Fix it and make it canon | Outline | Conflict handling (unmerged) |

**Decisions waiting on #chris:** J1 D1–D4 · one Save per page vs per section (with SQL on the page) ·
"looks cool" reference mockup.

## L2 — work in flight (branches)

| Branch | What | State | Next step |
|---|---|---|---|
| `claude/REL-08-m1-hardening` | M1 hardening (REL-07..12, PLAT-04/05, HIST-06) | Deployed live; UI checks pass | Merge to main |
| `claude/ux-quick-fixes` (on top of REL-08) | Conflict-only discard, search as you type, lighter save, departments | Pushed; tests pass; **not deployed** | Deploy + walkthrough after REL-08 merges |
| `claude/product-focus` | Product focus, UX principles, journeys, walkthroughs, decisions, this map | Pushed (docs only) | Merge |
| `claude/PLAT-07-health-readout` | Health readout script + PR template | Open | Review/merge |
| `claude/PLAT-08-astra-review` | Single-shot Astra review script | Open | Review/merge |
| `codex/frontend-independent-plan` | DEC-008..011 (Streamlit MVP, discovery, history) | Open; DEC-008 number clash | Renumber, merge |
| `claude/comparison-slice` | Streamlit vs React comparison slice | Open | Fold into SPCS spike or close |
| `codex/access-test-2026-10-21` | Access test notes | Open, stale | Close or merge |

## Parallel lanes (proposal)

Two writers never touch the same files. `streamlit_app.py` is the bottleneck: one lane at a time owns it.

| Lane | Work | Touches | Parallel with |
|---|---|---|---|
| A — Page | SQL on the metric page (UX-01/02), then layout + visual language (UX-03/09) | `streamlit_app.py`, PI repo/service | B, C, D |
| B — One-call save | Save as one Snowflake procedure (speed; front-end independent) | `sql/`, `app/repositories.py` (candidate writes) | A if A keeps PI code in new functions |
| C — SPCS/React spike | Mockup on SPCS + login + one read + one attributed write | new folder only | everything |
| D — Merge + deploy | Merge open branches, deploy, live checks | git, deploy | after each lane lands |
| E — Docs/plan (this session) | Contracts, decisions, triage walkthrough notes | `docs/` | everything |
