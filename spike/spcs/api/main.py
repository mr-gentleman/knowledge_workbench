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


class CandidateEdit(BaseModel):
    expected_revision: int
    fields: CandidateFields
    note: str | None = None


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


@api.put("/api/candidates/{candidate_id}")
def edit_candidate(candidate_id: int, body: CandidateEdit, request: Request):
    actor = spcs.viewer(request)
    out = services.save_candidate_edit(candidate_id, body.expected_revision,
                                       body.fields.model_dump(), actor, body.note)
    return asdict(out)


dist = Path(os.getenv("KW_WEB_DIST", Path(__file__).resolve().parents[1] / "web" / "dist"))
if dist.is_dir():
    api.mount("/", StaticFiles(directory=dist, html=True), name="web")
