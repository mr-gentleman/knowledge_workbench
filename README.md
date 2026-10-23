# Knowledge Workbench

Streamlit-in-Snowflake app for maintaining the AC Data Oracle's human-authored knowledge layer.
Replaces the Google Sheets path once proven. Metrics first; fact tables / joins / dimensions later.

Plans (in the oracle_bi_agent workspace): `notes/streamlit-app-master-plan.md`,
`notes/streamlit-app-technical-build-plan.md` (the latter wins on conflicts).

## Layout

    streamlit_app.py   entry page
    pyproject.toml     dependency file the container runtime requires (packages via the PyPI artifact repo)
    app/db.py          session + trusted viewer identity
    app/repositories.py SQL + transactions, no business rules
    app/services.py    workflows + invariants (save, no-op, stale-edit, name collision)
    sql/               ordered DDL — run in order, never edit a shipped file, add a new one
    tests/             workflow + persistence tests
    docs/              decisions, deployment

## Isolation

Everything lives in `AI_PLATFORM.WORKBENCH`. The app role has no grants on
`AI_PLATFORM.DICTIONARY`. Nothing here is served to the Oracle until cutover.

## Setup

1. Run `sql/001_workbench_schema.sql` (and `002_grants.sql` once the role is decided).
2. Deploy from the repo (the only source; no Snowsight Workspace copy):
   `scripts/deploy.sh` (runs `snow streamlit deploy --replace -c workbench_deploy`, then
   re-attaches the PyPI artifact repository) — that connection uses role
   `WORKBENCH_APP`, so the app stays owned by it. Needs Snowflake CLI >= 3.30.
3. Local dev: add a `workbench` connection to `~/.snowflake/connections.toml`, then
   `streamlit run streamlit_app.py`. Python environment (needs [uv](https://docs.astral.sh/uv/)):
   `uv venv --python 3.11 .venv && uv pip install --python .venv -r pyproject.toml`.
   Tests and the health readout then run with `scripts/health.sh`.

## Status

- [x] Slice 1 code: candidate browse / create / edit / history, stale-edit + no-op handling (smoke test pending — see docs/handoff-2026-10-16.md)
- [ ] SQL editor feasibility spike in SiS (highlighting while editing)
- [ ] PIs (`metric_calc`) + validation bound to revision
- [ ] Promotion (candidate → `metric_core`, needs ≥1 passing PI)
- [ ] One-time import of 5 representative metrics
- [ ] Build DICTIONARY consumables from WORKBENCH (PIs at served_revision_no) → test Oracle config
