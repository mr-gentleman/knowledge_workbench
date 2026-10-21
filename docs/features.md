# Knowledge Workbench — feature list

Organized by **what a user is trying to do** (capability areas), not by file or table.
Each item: **state** (empty → sketched → working → trusted, same as the Oracle pillar board)
and **priority** (V1 = needed to retire Google Sheets · Next · Later).
Scope test for anything new: *does its absence stop us retiring Sheets?* No → Later.

## 1. Find — what already exists?
| Feature | State | Priority |
|---|---|---|
| Search candidates by name | working | V1 |
| Search name + description + disambig; typo-tolerant; semantic (see app-design-notes) | empty | V1 (tiers 1–2), Next (semantic) |
| Browse/search canon metrics (not just candidates) | empty | V1 |
| Metric detail page: definition + its PIs + fact table | empty | V1 |
| Filter by department / status | empty | Next |
| Tags as browse filters (first real consumer of tags) | empty | Later |

## 2. Author — create and edit
| Feature | State | Priority |
|---|---|---|
| Create/edit candidate (name, description, disambig, department) | working | V1 |
| Hide free-text category until it has a defined list | empty | V1 |
| PI create/edit with a real SQL editor (highlighting while editing) | empty | V1 — editor spike first |
| Fact table create/edit | empty | Next |
| Synonyms (separate table) | empty | Next |
| Double-submit protection; refresh after save | empty | V1 |

## 3. Check — is it sane?
| Feature | State | Priority |
|---|---|---|
| Exact-name duplicate warning | working | V1 |
| No-op save detection; stale-edit rejection | working | V1 |
| SQL validation, bound to the revision checked | empty | V1 |
| Readiness checklist (description ✓, passing PI ✓ → Promote) | empty | V1 |
| PI source_table must match an active fact table | empty | V1 |
| Semantic duplicate suggestions (same matcher as search) | empty | Next |
| Scheduled re-validation (SQL that broke in month Y) | empty | Later |

## 4. Lifecycle — move things between states
| Feature | State | Priority |
|---|---|---|
| Promote candidate → canon (mint metric_id, attach PIs, set served_revision_no) | empty | V1 |
| Reject candidate (+ duplicate_of, reason) | empty | V1 |
| Retire canon / PI (+ superseded_by, reason) | empty | V1 |
| Merge tooling | empty | Later |

## 5. History & attribution — who changed what?
| Feature | State | Priority |
|---|---|---|
| Full snapshot per save, atomic with the record | working | V1 |
| Trusted viewer identity (st.user) | working | V1 |
| History shows only changed fields (old → new) | empty | V1 |
| View full record as of rev N (from stored snapshot) | empty | V1 |
| Combined metric + PI timeline | empty | Next |
| Restore a prior revision (tested procedure, not fancy UI) | empty | V1 (procedure) |

## 6. Serve — get it to the Oracle
| Feature | State | Priority |
|---|---|---|
| Build DICTIONARY consumables from WORKBENCH (PIs at served_revision_no) | empty | V1 |
| Test Oracle config against the new dictionary | empty | V1 |
| One-time legacy import with ID translation (`open-items.md`) | empty | V1 |
| Cutover + rollback procedure | empty | V1 |

## 7. Platform — run it safely
| Feature | State | Priority |
|---|---|---|
| Isolated schema + WORKBENCH_APP sole writer | working | V1 |
| GitLab repo + Git-backed workspace deploy | empty | V1 — next session |
| Revoke UPDATE on revision; role → SYSADMIN | empty | V1 |
| Operational logging (op id, actor, outcome, duration, query id) | empty | Next |
| Workflow/persistence tests | empty | Next |
