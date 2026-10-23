"""Workflows + invariants. Pages call these; these call repositories."""
import logging
from dataclasses import dataclass, field

from app import repositories as repo

log = logging.getLogger(__name__)

EDITABLE = ("full_name", "description", "disambig", "department", "category")


@dataclass
class Outcome:
    ok: bool
    message: str
    record_id: int | None = None
    revision_no: int | None = None
    warnings: list[str] = field(default_factory=list)


def normalize_name(name: str) -> str:
    # V1 rule: case- and edge-whitespace-insensitive. Open decision #2 — tighten here only.
    return (name or "").strip().lower()


def _clean(fields: dict) -> dict:
    out = {k: (v.strip() if isinstance(v, str) else v) for k, v in fields.items()}
    return out


def _collisions(name: str, exclude_candidate: int | None = None) -> list[str]:
    # Advisory only: a failed lookup must never change a save's outcome (REL-11).
    try:
        hits = repo.find_by_exact_name(normalize_name(name))
    except Exception:
        log.exception("Duplicate-name check failed")
        return ["Couldn't check for duplicate names right now."]
    return [
        f"Possible duplicate — {h['KIND']} #{h['ID']} is also named “{h['FULL_NAME']}”."
        for h in hits
        if not (h["KIND"] == "candidate" and h["ID"] == exclude_candidate)
    ]


def save_new_candidate(fields: dict, actor: str, token: str) -> Outcome:
    """token identifies this create attempt; retries with it return the first result."""
    fields = _clean(fields)
    if not fields.get("full_name"):
        return Outcome(False, "A name is required to save.")
    warnings = _collisions(fields["full_name"])
    cid = repo.insert_candidate(fields, actor, token)
    msg = "Saved." if fields.get("description") else "Saved — add a description to establish this metric."
    return Outcome(True, msg, cid, 1, warnings)


def save_candidate_edit(candidate_id: int, expected_revision: int, fields: dict,
                        actor: str, note: str | None = None) -> Outcome:
    fields = _clean(fields)
    if not fields.get("full_name"):
        return Outcome(False, "A name is required to save.")
    current = repo.get_candidate(candidate_id)
    if current is None:
        return Outcome(False, f"Candidate #{candidate_id} not found.")
    if current["REVISION_NO"] != expected_revision:
        return Outcome(False, "Someone saved a newer version since you opened this. "
                              "Your edits are still in the form — reload to compare.")
    before = {k: current[k.upper()] for k in EDITABLE}
    if all((before[k] or None) == (fields.get(k) or None) for k in EDITABLE):
        return Outcome(True, "No changes to save.", candidate_id, expected_revision)
    try:
        rev = repo.update_candidate(candidate_id, expected_revision, fields, actor, note)
    except repo.StaleEdit:
        return Outcome(False, "Someone saved a newer version since you opened this. "
                              "Your edits are still in the form — reload to compare.")
    return Outcome(True, "Saved.", candidate_id, rev, _collisions(fields["full_name"], candidate_id))
