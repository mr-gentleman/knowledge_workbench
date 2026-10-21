# Shared engineering instructions

Applies throughout Knowledge Workbench to Codex, Claude, and human contributors.
Requested by #chris; recorded by #codex on 2026-10-21.

## Philosophy

Build a reliable, understandable internal app with proportionate engineering effort.
Favor delivery and simple, conventional structure. Protect data integrity without
adding enterprise-scale machinery for hypothetical needs.

**Implement the smallest coherent solution for the current requirement; justify
new dependencies and abstraction layers; remove superseded code.**

- Keep one authoritative implementation of each business rule.
- Prefer direct, readable code and clear names. Avoid speculative frameworks,
  generic base classes, pass-through wrappers, and configuration for unused cases.
- Split modules by responsibility when it makes changes easier to understand.
  Neither more files nor fewer lines is automatically better architecture.
- Refactor a concrete obstacle or risk; do not turn routine feature work into an
  unrelated rewrite. Explain the problem and smallest useful correction.
- Optimize observed friction or evident unnecessary work before adding caching,
  background jobs, or other infrastructure.
- Remove obsolete paths and unused helpers introduced or superseded by your work.
  Preserve unrelated work by other contributors.

## Architecture boundaries

The existing structure is the starting point, not a mandate for additional layers:

| Responsibility | Location / expectation |
|---|---|
| Presentation and editor state | Streamlit pages/forms; user-specific draft and baseline state |
| Workflow rules and invariants | Services; save, no-op, readiness, promotion, and validation rules |
| Persistence | Repositories; parameterized SQL, conditional updates, transaction boundaries, snapshots |
| Connection and identity | Database/session helpers; trusted actor identity |
| Schema changes | Ordered SQL migrations; do not edit shipped migrations |

A unified metric editing screen may coordinate multiple backend records without
collapsing their responsibilities. Keep transaction ownership explicit and use the
same session for all statements in a transaction.

Treat the single-file deployment as a build artifact if that path is retained.
Make generation reproducible and keep deployment configuration aligned with the
actual entry point. Do not independently maintain two implementations.

## Lightweight engineering scorecard

At sprint end, assess these dimensions against current needs:

| Dimension | Evidence to inspect |
|---|---|
| Separation of concerns | UI, workflow rules, and persistence have clear ownership; rules are not duplicated |
| Understandability | Save → validate → write → history can be traced without excessive indirection |
| Complexity | Branching/nesting is manageable; complex workflows are explicit and ordinary operations stay simple |
| Duplication / dead code | No divergent source copies, unused helpers, abandoned paths, or speculative features |
| Correctness | Conflicts, failed writes, revisions, validation, promotion, and serving behave predictably |
| Efficiency | Query count and data volume suit the interaction; avoid repeated queries and unbounded loading |
| Changeability | A field or rule change affects a small, predictable set of places |

Use **Green** (appropriate), **Yellow** (specific weakness, not blocking), or **Red**
(correctness risk or materially obstructs planned work), with evidence. Use
**Not assessed** when evidence is missing; do not infer Green from absence of tests.
For every Yellow/Red, include the example, consequence, and smallest useful fix.

Lint findings, complexity hotspots, and duplication measurements are review signals,
not quality scores. Do not chase arbitrary line counts, complexity thresholds,
coverage percentages, or a composite numeric grade. Do not split functions into
meaningless wrappers merely to lower a metric.

## Verification and cadence

- For each meaningful change, briefly check duplication, new abstractions, error
  handling, and verification proportional to the actual risk. Explain what changed,
  why, what was checked, and what remains unverified.
- Use focused regression tests for concurrency, transaction rollback, revision
  binding, promotion, and serving. Avoid tests that merely mirror implementation
  or add ceremony to trivial document/UI-copy changes.
- Distinguish source inspection, automated tests, preview verification, and
  published-app verification. Do not claim runtime behavior was tested when it was not.
- At sprint end, record a compact dated scorecard in the shared backlog and add
  actionable findings as normal tasks. Reuse existing IDs rather than duplicating them.
- Before Oracle cutover, review transactions, revision handling, promotion,
  serving of last-passing revisions, and rollback more deeply.
- Reviews should improve the app without becoming a separate bureaucracy or a
  standing excuse to stop delivery.

## Collaboration and task tracking

[docs/features.md](docs/features.md) is the shared task/status source of truth.
These instructions contain standing philosophy; keep implementation tasks there.
Use origin tags #codex / #claude / #chris; retain #existing when authorship is unknown.
Origin is not ownership. Keep stable IDs and add completion evidence.

Read the current file before editing shared work; preserve concurrent changes and
resolve version conflicts against the latest content. Keep design rationale in
docs/app-design-notes.md and import constraints in docs/open-items.md.


Record meaningful architecture/code decisions in docs/decisions.md with date, origin,
context, rationale, alternatives, and consequences. Link tasks and commits when known.
Keep historical entries; supersede them explicitly instead of rewriting the past.
Routine changes need only Git history, not a decision entry.
