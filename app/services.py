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


def keep_mine(draft: dict, baseline: dict, latest: dict) -> dict:
    """Conflict resolution: my edited fields win; fields I didn't touch take their saved values,
    so keeping my edits never reverts theirs."""
    return {k: v if (v or None) != (baseline[k.upper()] or None) else latest[k.upper()]
            for k, v in draft.items()}


# ── physical implementations (PIs) ─────────────────────────────────────────

CALC_EDITABLE = ("sql_text", "source_table", "disambig")
CALC_LABELS = {"sql_text": "SQL", "source_table": "Source table", "disambig": "How it differs"}


def needs_label(sibling_count: int) -> bool:
    """One PI needs no label; with two or more, each says how it differs."""
    return sibling_count > 0


def validation_state(calc: dict) -> str:
    """A result counts only for the revision it checked: edited SQL is unvalidated again."""
    if calc.get("VALIDATED_REVISION_NO") != calc.get("REVISION_NO"):
        return "Not validated"
    return {"passed": "✓ Validated", "failed": "✗ SQL failed"}.get(calc.get("VALIDATION_STATUS"), "Not validated")


def _calc_problem(fields: dict, sibling_count: int) -> str | None:
    if not fields.get("sql_text"):
        return "Add SQL to save."
    if needs_label(sibling_count) and not fields.get("disambig"):
        return "With more than one implementation, say how this one differs."
    return None


def calc_changed(before: dict, fields: dict) -> list[str]:
    """Editable fields where fields differ from the saved row (UPPER-case keys)."""
    return [k for k in CALC_EDITABLE if (before[k.upper()] or None) != (fields.get(k) or None)]


def save_new_calc(candidate_id: int, calc_id: int, fields: dict, sibling_count: int,
                  actor: str) -> Outcome:
    """calc_id is reserved before the first attempt; retrying with it never inserts twice.
    The first PI of a candidate is its default."""
    fields = _clean(fields)
    if problem := _calc_problem(fields, sibling_count):
        return Outcome(False, problem)
    if repo.insert_calc(calc_id, candidate_id, fields, sibling_count == 0, actor):
        return Outcome(True, "SQL saved.", calc_id, 1)
    # An earlier attempt landed without its acknowledgement.
    landed = repo.get_calc(calc_id)
    warnings = [("Your earlier save did go through. Your newer changes are still in the "
                 "editor — Save again to apply them.")] if calc_changed(landed, fields) else []
    return Outcome(True, "SQL saved.", calc_id, landed["REVISION_NO"], warnings, latest=landed)


def save_calc_edit(baseline: dict, fields: dict, sibling_count: int, actor: str) -> Outcome:
    """Same contract as save_candidate_edit: the conditional UPDATE is the conflict guard."""
    fields = _clean(fields)
    calc_id, expected = baseline["CALC_ID"], baseline["REVISION_NO"]
    if not calc_changed(baseline, fields):
        return Outcome(True, "No changes to save.", calc_id, expected)
    if problem := _calc_problem(fields, sibling_count):
        return Outcome(False, problem, calc_id)
    try:
        rev = repo.update_calc(calc_id, expected, fields, actor)
    except repo.StaleEdit:
        latest = repo.get_calc(calc_id)
        if latest is None:
            return Outcome(False, "This implementation no longer exists.", calc_id)
        changed = [CALC_LABELS[k] for k in calc_changed(baseline, {k: latest[k.upper()] for k in CALC_EDITABLE})]
        return Outcome(False, _conflict_message(latest, changed), calc_id, latest["REVISION_NO"], latest=latest)
    return Outcome(True, "SQL saved.", calc_id, rev)


def _conflict_message(latest: dict, changed: list[str]) -> str:
    when = f"{latest['UPDATED_AT']:%b %d %H:%M}" if latest.get("UPDATED_AT") else "recently"
    return (f"**{latest['UPDATED_BY']}** saved a newer version (rev {latest['REVISION_NO']}, {when}) "
            f"while you were editing. Changed: {', '.join(changed) or 'nothing visible'}. "
            "Your edits are still in the form.")


def _conflict(baseline: dict) -> Outcome:
    candidate_id = baseline["CANDIDATE_ID"]
    latest = repo.get_candidate(candidate_id)
    if latest is None:
        return Outcome(False, f"Candidate #{candidate_id} no longer exists.", candidate_id)
    changed = [LABELS[k] for k in EDITABLE if (baseline[k.upper()] or None) != (latest[k.upper()] or None)]
    return Outcome(False, _conflict_message(latest, changed), candidate_id, latest["REVISION_NO"], latest=latest)
