"""Workflows + invariants. Pages call these; these call repositories."""
import logging
from dataclasses import dataclass, field

from app import repositories as repo

log = logging.getLogger(__name__)

EDITABLE = ("full_name", "description", "disambig", "department", "category")
DEPARTMENTS = ("Finance", "Marketing", "Sales", "Customer", "Product", "Analytics", "Other")
# Values saved before 2026-10-23 (and the Oracle categorizer's enum) are lowercase;
# bi_meta became Analytics (the team's new name) and misc became Other.
_OLD_DEPARTMENTS = {d.lower(): d for d in DEPARTMENTS} | {"bi_meta": "Analytics", "misc": "Other"}


def department(value: str | None) -> str | None:
    """The current name for a stored department value; unknown values pass through."""
    return _OLD_DEPARTMENTS.get((value or "").strip().lower(), value) or None


LABELS = {"full_name": "Name", "description": "Description", "disambig": "When to use",
          "department": "Department", "category": "Category"}


@dataclass
class Outcome:
    ok: bool
    message: str
    record_id: int | None = None
    revision_no: int | None = None
    warnings: list[str] = field(default_factory=list)
    latest: dict | None = None  # set on a conflict: the version that was saved meanwhile


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


def save_candidate_edit(baseline: dict, fields: dict, actor: str, note: str | None = None) -> Outcome:
    """baseline = the record as the user opened it. The conditional UPDATE is the conflict
    guard, so there is no pre-read; the latest version is fetched only on a conflict."""
    fields = _clean(fields)
    if not fields.get("full_name"):
        return Outcome(False, "A name is required to save.")
    candidate_id, expected = baseline["CANDIDATE_ID"], baseline["REVISION_NO"]
    before = {k: baseline[k.upper()] for k in EDITABLE}
    if all((before[k] or None) == (fields.get(k) or None) for k in EDITABLE):
        return Outcome(True, "No changes to save.", candidate_id, expected)
    try:
        rev = repo.update_candidate(candidate_id, expected, fields, actor, note)
    except repo.StaleEdit:
        return _conflict(baseline)
    renamed = normalize_name(fields["full_name"]) != normalize_name(before["full_name"])
    return Outcome(True, "Saved.", candidate_id, rev,
                   _collisions(fields["full_name"], candidate_id) if renamed else [])


def _conflict(baseline: dict) -> Outcome:
    candidate_id = baseline["CANDIDATE_ID"]
    latest = repo.get_candidate(candidate_id)
    if latest is None:
        return Outcome(False, f"Candidate #{candidate_id} no longer exists.", candidate_id)
    changed = [LABELS[k] for k in EDITABLE if (baseline[k.upper()] or None) != (latest[k.upper()] or None)]
    when = f"{latest['UPDATED_AT']:%b %d %H:%M}" if latest.get("UPDATED_AT") else "recently"
    return Outcome(
        False,
        f"**{latest['UPDATED_BY']}** saved a newer version (rev {latest['REVISION_NO']}, {when}) "
        f"while you were editing. Changed: {', '.join(changed) or 'nothing visible'}. "
        "Your edits are still in the form.",
        candidate_id, latest["REVISION_NO"], latest=latest)
