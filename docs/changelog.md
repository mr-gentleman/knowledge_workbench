# Changelog

The high-level view: what is live, what changed, and why. One row per deploy, newest first.
Details live elsewhere — **why** in [decisions.md](decisions.md) (DEC-…), **status** in
[features.md](features.md) (task IDs), **exact diffs** in git. Upkeep rules: AGENTS.md § Collaboration.

## Releases (deployed to `AI_PLATFORM.WORKBENCH.KNOWLEDGE_WORKBENCH`)

| Date | Commit (branch) | What changed — user-visible first | Why / refs | DDL applied | Verified |
|---|---|---|---|---|---|
| 2026-10-23 | `153e9e3` (main) | Every lane on main: left-panel search and navigation; Fact tables screen (browse, create, edit, retire) saving through one Python transaction like metrics; live PIs with Run check | DEC-022..025; UX-02, UX-04, PLAT-11 | — (sql/005 and 006 were already live; procedures not dropped yet) | Service READY on image 153e9e3 (rollout 50 s); all local checks pass; no UI check or live fact-table save yet |
| 2026-10-23 | `fa4dd80` (claude/hybrid-tables — not merged to main at deploy; merged 2026-10-23) | Saves via one Python transaction on hybrid tables; candidate and canon are one metric row with one ID; nightly backup copy | DEC-024, DEC-025; PLAT-06, PLAT-10 | sql/009, 010, 011 — run by #claude as ACCOUNTADMIN with #chris's approval | Post-checks: 5 hybrid tables, 3 indexes, counts 87 revisions / 26 op_log / 61 fact tables, grants; first backup SUCCEEDED; service READY |
| 2026-10-23 | `de4516c` (claude/left-panel — merged to main 2026-10-23; replaced on KW_SPIKE by fa4dd80) | Sidebar shows live candidates only (sample only if the API is down); live candidates land in their department folder; ranked search with highlights over name/category/definition/SQL; `/` ⌘K ↑↓ Enter Esc; status dots incl. unsaved; folder state remembered | — | — | SPCS service KW_SPIKE READY on image de4516c; page not yet checked live by Chris |
| 2026-10-23 | `d1b6783` (claude/REL-08-m1-hardening — merged to main 2026-10-23) | Failed or interrupted saves can't leak into the next viewer's save; every database call takes the lock; create is safe to retry (same token → same record); sidebar capped at 200; history loads on request; op_log records every save with lock wait; snapshots keep NULL fields | DEC-007, DEC-008; REL-08..12, PLAT-04, PLAT-05, HIST-06 | sql/003 (create_token, op_log) | Chris UI checks pass; op_log + revision rows checked |
| 2026-10-22 | `8fff6ad` (main) | No user change. Deploy goes through `scripts/deploy.sh`; PyPI packages installable (artifact repo attached) | DEC-005; PLAT-01 | — | Not recorded whether this commit or a later spike was the deployed one |
| 2026-10-21 | `f597ce4` (main) | Multi-file app deployed from the repo; a new candidate opens right after create, so a second Save can't mint a duplicate | DEC-005; PLAT-01, REL-02 | — | Created #3 on the published app |
| 2026-10-21 | `729bb7d` (coco/plat-01) | First multi-file deploy; app starts on the container runtime (pyproject.toml shipped) | DEC-005; PLAT-01 | — | Created #2 and edited it: one edit revision |
| 2026-10-21 | earlier (single-file bundle) | Revision-based conflict checks; saves serialized on the shared connection | DEC-001, DEC-002, DEC-004; REL-01..06 | sql/001, sql/002 | Source + tests only |

Not recorded: whether `claude/ux-quick-fixes` (search as you type, conflict-only discard,
departments) has been deployed. Saves on 2026-10-23 15:12–15:29 came from the published app,
but no commit was noted.

## In flight (branches not merged to main) — snapshot 2026-10-23

Merged to main 2026-10-23: next-steps, left-panel, hybrid-tables (includes unified-metric), implementations, fact-tables, REL-08-m1-hardening, ux-quick-fixes (deploy still unrecorded), PLAT-08-astra-review (includes PLAT-07; its branch can be deleted).

Refresh when you merge to main or push a new branch. Live list:
`git fetch && git branch -r --no-merged origin/main`.

| Branch | What it does | Refs | State |
|---|---|---|---|
| claude/sql-on-page | PI backend (create/edit/retire, run status); Streamlit SQL card dropped per DEC-018 | UX-01, UX-02, DEC-019 | Built on ux-quick-fixes |
| claude/sql-on-page-streamlit-ui | Same PI backend plus Streamlit PI cards | UX-01, UX-02 | Likely superseded while Streamlit stays frozen (DEC-018) |
| claude/spcs-spike | React + FastAPI on SPCS; whole-page Edit with PIs; optimistic save; hybrid-table benchmark (2.7 s → 1.0 s) | DEC-018, FE-01, HYBRID_BENCH.md | Live spike; includes save-proc |
| claude/save-proc | Candidate saves are one CALL to a stored procedure | DEC-020, DEC-021, PLAT-09 | Measured slower live (CALL ~4 s vs ~2.8 s); don't deploy for speed |
| claude/product-focus | Workflow-first V1, UX principles, journey contracts, walkthroughs, DEC-012..017 | DEC-012..017 | Docs only |
| claude/ux-exemplars | UX pattern library P1–P28 from outside sites | — | Docs only; built on product-focus |
| claude/comparison-slice, codex/frontend-independent-plan | Streamlit vs React comparison; authoring MVP; frontend portability | — | Docs only |
| codex/access-test-2026-10-21 | Work-configuration access test note | — | Docs only; likely stale |

| codex/engineering-review-2026-10-23 | Core engineering review at 99a6068; grades, evidence and prioritized fixes | REV-01..08; PLAT-12 | Documentation only; no runtime fixes. Existing main Python CI is red. |
