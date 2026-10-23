"""FastAPI layer for the SPCS spike: serves the React build and exposes candidate
read/edit over app/services.py and app/repositories.py — no business rules here."""
import os
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import app.db
from api import spcs

app.db.session = spcs.session  # the one seam: everything below db.locked_session is reused as-is

from app import repositories as repo, services  # noqa: E402  (after the session swap)

api = FastAPI(title="Knowledge Workbench (SPCS spike)")


class CandidateFields(BaseModel):
    full_name: str
    description: str | None = None
    disambig: str | None = None
    department: str | None = None
    category: str | None = None


class CandidateDraft(BaseModel):
    id: int
    expected_revision: int
    fields: CandidateFields


class MetricSave(BaseModel):
    """Request shape of docs/plans/metric-save-contract.md (DEC-020). The spike persists only
    the definition; calcs are accepted in shape but refused until services.save_metric exists."""
    candidate: CandidateDraft
    calcs: list[dict] = []
    change_note: str | None = None


@api.get("/healthz")
def healthz():
    return {"ok": True}


@api.get("/api/me")
def me(request: Request):
    return {"user": request.headers.get(spcs.USER_HEADER) or os.getenv("KW_DEV_USER"),
            "in_spcs": spcs.IN_SPCS, "caller": spcs.caller_identity(request)}


@api.get("/api/candidates")
def list_candidates(search: str = ""):
    return [r.as_dict() for r in repo.list_candidates(search)]


@api.get("/api/candidates/{candidate_id}")
def get_candidate(candidate_id: int):
    row = repo.get_candidate(candidate_id)
    if row is None:
        raise HTTPException(404, f"Candidate #{candidate_id} not found.")
    return row


@api.post("/api/metrics/save")
def save_metric(body: MetricSave, request: Request):
    actor = spcs.viewer(request)
    if body.calcs:
        raise HTTPException(501, "Saving implementations needs services.save_metric (one-call-save lane).")
    c = body.candidate
    out = services.save_candidate_edit(c.id, c.expected_revision, c.fields.model_dump(), actor, body.change_note)
    # Spike-only mapping of today's Outcome onto the contract's statuses; save_metric returns them directly.
    if out.ok:
        status = "no_change" if out.message == "No changes to save." else "saved"
    else:
        status = "conflict" if "newer version" in out.message else "invalid"
    return {"status": status, "message": out.message, "candidate_id": out.record_id,
            "candidate_revision": out.revision_no, "calc_revisions": {}, "warnings": out.warnings}


dist = Path(os.getenv("KW_WEB_DIST", Path(__file__).resolve().parents[1] / "web" / "dist"))
if dist.is_dir():
    api.mount("/", StaticFiles(directory=dist, html=True), name="web")
