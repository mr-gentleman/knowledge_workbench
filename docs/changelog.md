# Changelog

The high-level view: what is live, what changed, and why. One row per deploy, newest first.
Details live elsewhere — **why** in [decisions.md](decisions.md) (DEC-…), **status** in
[features.md](features.md) (task IDs), **exact diffs** in git. Upkeep rules: AGENTS.md § Collaboration.

## Releases (deployed to `AI_PLATFORM.WORKBENCH.KNOWLEDGE_WORKBENCH`)

| Date | Commit (branch) | What changed — user-visible first | Why / refs | DDL applied | Verified |
|---|---|---|---|---|---|
| 2026-10-23 | `d1b6783` (claude/REL-08-m1-hardening — **not merged to main**) | Failed or interrupted saves can't leak into the next viewer's save; every database call takes the lock; create is safe to retry (same token → same record); sidebar capped at 200; history loads on request; op_log records every save with lock wait; snapshots keep NULL fields | DEC-007, DEC-008; REL-08..12, PLAT-04, PLAT-05, HIST-06 | sql/003 (create_token, op_log) | Chris UI checks pass; op_log + revision rows checked |
| 2026-10-22 | `8fff6ad` (main) | No user change. Deploy goes through `scripts/deploy.sh`; PyPI packages installable (artifact repo attached) | DEC-005; PLAT-01 | — | Not recorded whether this commit or a later spike was the deployed one |
| 2026-10-21 | `f597ce4` (main) | Multi-file app deployed from the repo; a new candidate opens right after create, so a second Save can't mint a duplicate | DEC-005; PLAT-01, REL-02 | — | Created #3 on the published app |
| 2026-10-21 | `729bb7d` (coco/plat-01) | First multi-file deploy; app starts on the container runtime (pyproject.toml shipped) | DEC-005; PLAT-01 | — | Created #2 and edited it: one edit revision |
| 2026-10-21 | earlier (single-file bundle) | Revision-based conflict checks; saves serialized on the shared connection | DEC-001, DEC-002, DEC-004; REL-01..06 | sql/001, sql/002 | Source + tests only |

Not recorded: whether `claude/ux-quick-fixes` (search as you type, conflict-only discard,
departments) has been deployed. Saves on 2026-10-23 15:12–15:29 came from the published app,
but no commit was noted.

## In flight (branches not merged to main) — snapshot 2026-10-23

Refresh when you merge to main or push a new branch. Live list:
`git fetch && git branch -r --no-merged origin/main`.

| Branch | What it does | Refs | State |
|---|---|---|---|
| claude/REL-08-m1-hardening | M1 hardening (see the 2026-10-23 release) | DEC-007, DEC-008 | **Deployed, not merged** |
| claude/ux-quick-fixes | Discard only on a conflict; search as you type; lighter save; department names | DEC-015..017 | Built on M1; deploy unknown |
| claude/sql-on-page | Add and edit SQL implementations (PIs) on the candidate page, save per card; run-status wording | UX-01, UX-02 | Built on ux-quick-fixes |
| claude/save-proc | Candidate saves are one CALL to a stored procedure (est. 20–30% faster) | DEC-018, PLAT-09 | Needs sql/004 applied by CoCo before deploy |
| claude/product-focus | Workflow-first V1, UX principles, journey contracts, walkthroughs, DEC-012..017 | DEC-012..017 | Docs only |
| claude/ux-exemplars | UX pattern library P1–P28 from outside sites | — | Docs only; built on product-focus |
| claude/PLAT-07-health-readout | Code-health readout script + PR template | PLAT-07 | Tooling |
| claude/PLAT-08-astra-review | One-shot Astra review script; DDL → CoCo handoff rule | PLAT-08 | Tooling; includes PLAT-07 |
| claude/comparison-slice, codex/frontend-independent-plan | Streamlit vs React comparison; authoring MVP; frontend portability | — | Docs only |
| codex/access-test-2026-10-21 | Work-configuration access test note | — | Docs only; likely stale |
