"""FastAPI layer for the SPCS spike: serves the React build and exposes metric
read/edit over app/services.py and app/repositories.py — no business rules here."""
import os
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import app.db
from api import spcs

app.db.session = spcs.session  # the one seam: everything below db.locked_session is reused as-is
app.db.check_connection = spcs.check_connection  # SQL checks only (DEC-022)

from app import repositories as repo, services  # noqa: E402  (after the session swap)

api = FastAPI(title="Knowledge Workbench (SPCS spike)")


class MetricFields(BaseModel):
    full_name: str
    description: str | None = None
    disambig: str | None = None
    department: str | None = None
    category: str | None = None


class MetricDraft(BaseModel):
    id: int | None = None
    expected_revision: int | None = None
    create_token: str | None = None
    fields: MetricFields


class CheckRequest(BaseModel):
    revision_no: int  # the revision the page shows; a check never stamps a different one


class MetricSave(BaseModel):
    """Request shape of docs/plans/metric-save-contract.md (DEC-020). Send the same op_id
    when retrying a draft so a save that landed reports replayed, not a conflict."""
    op_id: str | None = None
    metric: MetricDraft
    calcs: list[dict] = []
    change_note: str | None = None


@api.get("/healthz")
def healthz():
    return {"ok": True}


@api.get("/api/me")
def me(request: Request):
    return {"user": request.headers.get(spcs.USER_HEADER) or os.getenv("KW_DEV_USER"),
            "in_spcs": spcs.IN_SPCS, "caller": spcs.caller_identity(request)}


@api.get("/api/metrics")
def list_metrics(search: str = ""):
    return [r.as_dict() for r in repo.list_metrics(search)]


@api.get("/api/metrics/{metric_id}")
def get_metric(metric_id: int):
    row = repo.get_metric(metric_id)
    if row is None:
        raise HTTPException(404, f"Metric #{metric_id} not found.")
    return {**row, "CALCS": repo.list_calcs(metric_id)}


@api.post("/api/pis/reserve")
def reserve_pi(request: Request):
    """A new PI's id, taken before its first save so the id is that create's retry key (DEC-019)."""
    spcs.viewer(request)
    return {"calc_id": repo.reserve_calc_id()}


@api.post("/api/pis/{calc_id}/check")
def check_pi(calc_id: int, body: CheckRequest, request: Request):
    return asdict(services.check_calc(spcs.viewer(request), calc_id, body.revision_no))


class FactTableDraft(BaseModel):
    table_name: str
    expected_revision: int | None = None  # None = create
    fields: dict = {}


class FactTableSave(BaseModel):
    op_id: str | None = None  # resend the same op_id when retrying a draft
    table: FactTableDraft
    change_note: str | None = None


def _lower(row: dict | None) -> dict | None:
    return row and {k.lower(): v for k, v in row.items()}


@api.get("/api/fact-tables")
def list_fact_tables():
    """The fact-table registry, lower-case keys; table_name is AC.SCHEMA.TABLE."""
    return [_lower(r.as_dict()) for r in repo.list_fact_tables()]


@api.get("/api/fact-tables/{table_name}")
def get_fact_table(table_name: str):
    row = repo.get_fact_table(table_name)
    if row is None:
        raise HTTPException(404, f"Fact table {table_name} not found.")
    return {**_lower(row), "table_name": row["TABLE_NAME_FULL"]}


@api.post("/api/fact-tables/save")
def save_fact_table(body: FactTableSave, request: Request):
    actor = spcs.viewer(request)
    out = asdict(services.save_fact_table(actor, body.op_id or str(uuid.uuid4()), body.table.model_dump(),
                                          body.change_note))
    if out["conflict"]:
        out["conflict"]["latest"] = _lower(out["conflict"]["latest"])
    return out


@api.post("/api/metrics/save")
def save_metric(body: MetricSave, request: Request):
    actor = spcs.viewer(request)
    out = services.save_metric(actor, body.op_id or str(uuid.uuid4()), body.metric.model_dump(),
                               body.calcs, body.change_note)
    return asdict(out)


dist = Path(os.getenv("KW_WEB_DIST", Path(__file__).resolve().parents[1] / "web" / "dist"))
if dist.is_dir():
    api.mount("/", StaticFiles(directory=dist, html=True), name="web")
