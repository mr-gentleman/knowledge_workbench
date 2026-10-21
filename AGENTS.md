# Shared engineering instructions

Applies throughout Knowledge Workbench to Codex, Claude, and human contributors.
Requested by #chris; recorded by #codex 2026-10-21; revised by #claude 2026-10-21.

## Philosophy

A reliable, understandable internal app with proportionate effort. Protect data
integrity; skip enterprise machinery for hypothetical needs.

**Implement the smallest coherent solution for the current requirement; justify
new dependencies and abstraction layers; remove superseded code.**

- One authoritative implementation of each business rule.
- Direct, readable code and clear names. No speculative frameworks, generic base
  classes, pass-through wrappers, or configuration for unused cases.
- Refactor only to remove a concrete obstacle or risk — not as a side quest
  during feature work.
- Remove paths your work made obsolete. Leave other contributors' work alone.

## Project facts

- Streamlit in Snowflake, **container runtime** (Python 3.11, Streamlit ≥ 1.50).
  Compute pool `SYSTEM_COMPUTE_POOL_CPU` runs Python; warehouse `BIZ_AI_WH` runs SQL.
- Connect with `st.connection("snowflake").session()` — not `get_active_session()`.
- Acting user comes from `st.user` — never a form field, never `CURRENT_USER()`
  (in the deployed app that can be the service user).
- The app runs with **owner's rights** as `WORKBENCH_APP`, which writes only
  `AI_PLATFORM.WORKBENCH`. Never grant it anything on `AI_PLATFORM.DICTIONARY`.
- No pip installs at runtime: without an attached artifact repository the app has
  only what ships with the runtime. A new package is a platform change, not a code change.
- **Streamlit reruns the whole page on every click.** Every query on the page runs
  on every interaction — that's the main latency lever.
- After editing `app/` or `streamlit_app.py`, run `python scripts/build_single.py`.
  `streamlit_app_single.py` is generated; never edit it by hand.
- Tests: `python -m unittest discover -s tests -v` (Python 3.11 + `streamlit>=1.50`). They use an
  in-memory fake for `app/repositories.py`, so they cover page and rule logic, not SQL.
- Schema changes: add a new numbered file in `sql/`; never edit a shipped one.

## Architecture boundaries

| Layer | Owns | Never contains |
|---|---|---|
| `streamlit_app.py` (page) | Layout, widgets, per-user draft + baseline state | SQL, business rules |
| `app/services.py` | Workflow rules: save, no-op, conflicts, readiness, promotion | SQL, Streamlit widgets |
| `app/repositories.py` | Parameterized SQL, conditional updates, transactions, history snapshots | Business decisions |
| `app/db.py` | Session, trusted identity | Anything else |
| `sql/` | Ordered migrations | Edits to shipped files |

All statements in one transaction use the same session. A screen may coordinate
several records without merging their layers.

## Bloat check — every change

Answer before calling a change done. In the commit/PR summary write
**"Bloat check: clean"**, or one line per item that isn't, with the reason.

| Check | Question | Red flags |
|---|---|---|
| **Separation of concerns** | Is each line in the layer that owns it (table above)? | SQL in the page; a rule decided in two places; services importing Streamlit |
| **Modularity** | Can this change be understood by reading one or two files? | A one-field change touching 4+ files; new module or class with a single caller |
| **Verbosity** | Could it be markedly shorter with nothing lost? | Wrappers that only forward; comments restating code; checks for impossible states; options nobody uses |
| **Complexity** | Can save → validate → write → history be followed in one read? | Nesting deeper than 3; boolean flags that switch a function's behavior; clever one-liners |
| **Latency** | How many queries does one click now cost? | Query in a loop; the same row fetched twice per rerun; unbounded `SELECT` with no `LIMIT`; loading data for a tab nobody opened |
| **Dependencies** | Is a new package worth a platform change? | Package for something ~20 lines of code would do |
| **Dead code** | Did anything become unused? | Old helpers left behind; commented-out code; a second copy of the same logic |

These are judgment calls, not thresholds. Don't chase line counts, complexity
scores, or coverage percentages, and don't split functions into meaningless
wrappers to hit a number.

## Periodic review — on request

When #chris asks (and before Oracle cutover), score the whole codebase on the same
seven checks: **Green** (fine), **Yellow** (specific weakness, not blocking),
**Red** (correctness risk or blocks planned work), or **Not assessed** (no evidence —
never infer Green from missing tests). Each Yellow/Red gets an example, the
consequence, and the smallest useful fix, filed as a backlog item. Record the dated
result in `docs/features.md`. Before cutover, go deeper on transactions, revision
handling, promotion, serving of last-passing revisions, and rollback.

## Verification

- Tests where the risk is real: concurrency, transactions, revision binding,
  promotion, serving. Not for copy or doc changes.
- Say which kind of evidence you have — source reading, automated test, local run
  against Snowflake, preview, or published app — and what remains unverified.
  Never claim runtime behavior you didn't observe.

## Collaboration

- [docs/features.md](docs/features.md) is the task/status source of truth; this
  file holds standing guidance only. Design rationale → `docs/app-design-notes.md`;
  import constraints → `docs/open-items.md`.
- Origin tags #codex / #claude / #chris (#existing when unknown). Origin ≠ owner.
  Keep stable IDs; add dated completion evidence.
- One branch per change: `codex/<topic>`, `claude/<topic>`. Merge to `main` via
  review unless #chris says otherwise. Fetch and read the latest before editing
  shared files; preserve others' concurrent changes.
- Never commit secrets — `.gitignore` excludes `*secret*`, `.env`, `.snowflake/`.
- Record meaningful architecture/code decisions in [docs/decisions.md](docs/decisions.md):
  date, origin, context, rationale, alternatives, consequences; link tasks and commits.
  Supersede entries explicitly rather than rewriting them. Routine changes need only Git history.
