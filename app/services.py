"""Workflows + invariants. Pages call these; these call repositories."""
import logging
import re
import uuid
from dataclasses import dataclass, field

from app import repositories as repo
from app.db import ConnectionQuarantined

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


def _collisions(hits: list | None, exclude_id: int | None = None) -> list[str]:
    # Advisory only: the save procedure omits hits when its lookup failed, and that never
    # changes a save's outcome (REL-11).
    if hits is None:
        return ["Couldn't check for duplicate names right now."]
    return [
        f"Possible duplicate — {h['KIND']} #{h['ID']} is also named “{h['FULL_NAME']}”."
        for h in hits
        if h["ID"] != exclude_id
    ]


def save_new_metric(fields: dict, actor: str, token: str) -> Outcome:
    """token identifies this create attempt; retries with it return the first result."""
    fields = _clean(fields)
    if not fields.get("full_name"):
        return Outcome(False, "A name is required to save.")
    res = repo.save_metric(uuid.uuid4().hex, actor,
                           {"id": None, "create_token": token, "fields": _pick(fields, EDITABLE)},
                           [], check_name=normalize_name(fields["full_name"]))
    msg = "Saved." if fields.get("description") else "Saved — add a description to establish this metric."
    warnings = [] if res["outcome"] == "replayed" else _collisions(res.get("collisions"))
    return Outcome(True, msg, res["metric_id"], 1, warnings)


def save_metric_edit(baseline: dict, fields: dict, actor: str, note: str | None = None) -> Outcome:
    """baseline = the record as the user opened it. The conditional UPDATE is the conflict
    guard, so there is no pre-read; the latest version is fetched only on a conflict."""
    fields = _clean(fields)
    if not fields.get("full_name"):
        return Outcome(False, "A name is required to save.")
    metric_id, expected = baseline["METRIC_ID"], baseline["REVISION_NO"]
    before = {k: baseline[k.upper()] for k in EDITABLE}
    if all((before[k] or None) == (fields.get(k) or None) for k in EDITABLE):
        return Outcome(True, "No changes to save.", metric_id, expected)
    res = repo.save_metric(uuid.uuid4().hex, actor,
                           {"id": metric_id, "expected_revision": expected, "fields": _pick(fields, EDITABLE)},
                           [], note, normalize_name(fields["full_name"]))
    if res["outcome"] == "conflict":
        return _conflict(baseline)
    return Outcome(True, "Saved.", metric_id, res["metric_revision"],
                   _collisions(res.get("collisions"), metric_id))


def _pick(fields: dict, keys: tuple) -> dict:
    return {k: fields.get(k) for k in keys}


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
    """A result counts only for the revision it checked: edited SQL is "Not run" again.
    A pass means the SQL executed, not that it is right — never say "validated" (ux-principles)."""
    rev = calc.get("REVISION_NO")
    if calc.get("VALIDATED_REVISION_NO") != rev:
        return "Not run"
    return {"passed": f"✓ Runs · rev {rev}", "failed": f"✗ SQL failed · rev {rev}"}.get(
        calc.get("VALIDATION_STATUS"), "Not run")


@dataclass
class CheckOutcome:
    status: str  # passed | failed | moved | unavailable
    message: str
    revision_no: int | None = None
    ms: int | None = None
    row_count: int = 0
    truncated: bool = False  # row_count stopped at the check's row limit
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)  # the first CHECK_PREVIEW_ROWS, as text
    error: str | None = None


CHECK_PREVIEW_ROWS = 20
# Final semicolons and anything after them that is only whitespace or comments; run_check wraps the SQL.
_TRAILING_END = re.compile(r"(;|\s|--[^\n]*|/\*.*?\*/)*$", re.S)


def check_calc(actor: str, calc_id: int, revision_no: int) -> CheckOutcome:
    """Runs a PI's SQL as saved at revision_no and stamps the result on that revision (CHECK-01).
    It runs the stored SQL, never text from the page, so a pass is evidence about what was saved."""
    calc = repo.get_calc(calc_id)
    if calc is None or calc["STATUS"] != "active" or calc["REVISION_NO"] != revision_no:
        return CheckOutcome("moved", "This implementation changed since you opened it. Reload to check "
                            "the latest version.", revision_no)
    sql = _TRAILING_END.sub("", calc["SQL_TEXT"] or "").strip()
    try:
        res = repo.run_check(sql) if sql else {"ok": False, "ms": 0, "columns": [], "rows": [],
                                                 "query_id": None, "error": "There is no SQL to run."}
        recorded = repo.record_check(calc_id, revision_no, res["ok"], res["error"], res["query_id"])
    except Exception:
        log.exception("SQL check failed to run: calc %s rev %s", calc_id, revision_no)
        return CheckOutcome("unavailable", "Couldn't run the check right now. Nothing was recorded; "
                            "try again shortly.", revision_no)
    log.info("check calc %s rev %s by %s: ok=%s %sms recorded=%s",
             calc_id, revision_no, actor, res["ok"], res["ms"], recorded)
    if not recorded:
        return CheckOutcome("moved", "Someone saved this implementation while the check ran, so the "
                            "result wasn't recorded. Reload to check the latest version.", revision_no)
    status = "passed" if res["ok"] else "failed"
    label = validation_state({"REVISION_NO": revision_no, "VALIDATED_REVISION_NO": revision_no,
                              "VALIDATION_STATUS": status})
    return CheckOutcome(status, label, revision_no, res["ms"], len(res["rows"]),
                        len(res["rows"]) >= repo.CHECK_MAX_ROWS, res["columns"],
                        [[None if v is None else str(v) for v in r] for r in res["rows"][:CHECK_PREVIEW_ROWS]],
                        res["error"])


def calc_changed(before: dict, fields: dict) -> list[str]:
    """Editable fields where fields differ from the saved row (UPPER-case keys)."""
    return [k for k in CALC_EDITABLE if (before[k.upper()] or None) != (fields.get(k) or None)]


# ── the metric page: one Save, all or nothing (DEC-020, docs/plans/metric-save-contract.md) ──

@dataclass
class MetricOutcome:
    status: str  # saved | no_change | invalid | conflict | failed
    message: str
    metric_id: int | None = None
    metric_revision: int | None = None
    calc_revisions: dict[int, int] = field(default_factory=dict)
    problems: list[dict] = field(default_factory=list)   # {record, field, message}
    conflicts: list[dict] = field(default_factory=list)  # {record, latest, changed_fields, by, at}
    warnings: list[str] = field(default_factory=list)
    checks_due: list[int] = field(default_factory=list)  # PIs whose SQL changed: run-check these


def save_metric(actor: str, op_id: str, metric: dict, calcs: list[dict],
                change_note: str | None = None) -> MetricOutcome:
    """metric: {id (None = create), expected_revision, create_token, fields}.
    calcs: only PIs the draft touched — {calc_id (reserved with repo.reserve_calc_id when new),
    expected_revision (None = new), fields, retire}. Reuse op_id when retrying the same draft."""
    mid = metric.get("id")
    draft = {**metric, "fields": _clean(_pick(metric.get("fields") or {}, EDITABLE))}
    calcs = [{"calc_id": c["calc_id"], "expected_revision": c.get("expected_revision"),
              "retire": bool(c.get("retire")),
              "fields": _clean(_pick(c.get("fields") or {}, CALC_EDITABLE))} for c in calcs]
    try:
        existing = repo.list_calcs(mid) if mid is not None else []
        if problems := _metric_problems(draft["fields"], calcs, existing):
            return MetricOutcome("invalid", "Nothing was saved — fix the marked fields.", mid,
                                 problems=problems)
        _mark_default(calcs, existing)
        res = repo.save_metric(op_id, actor, draft, calcs, change_note,
                               normalize_name(draft["fields"]["full_name"]))
        if res["outcome"] == "conflict":
            return _metric_conflict(draft, calcs)
        if res["outcome"] == "replayed":
            return _metric_replayed(res["metric_id"], draft, calcs)
    except ConnectionQuarantined as exc:
        return MetricOutcome("failed", f"Not saved: {exc} Your draft is kept.", mid)
    except Exception:
        log.exception("Metric save failed: metric %s, op %s", mid, op_id)
        return MetricOutcome("failed", "Save could not be confirmed. Your draft is kept; "
                             "saving again is safe.", mid)
    mid = res["metric_id"]
    if res["outcome"] == "no_change":
        return MetricOutcome("no_change", "No changes to save.", mid, res["metric_revision"],
                             {c["calc_id"]: c["expected_revision"] for c in calcs if c["expected_revision"]})
    changed, new = set(res.get("changed_calcs") or []), set(res.get("new_calcs") or [])
    revisions = {c["calc_id"]: 1 if c["calc_id"] in new else
                 c["expected_revision"] + (c["calc_id"] in changed)
                 for c in calcs if c["calc_id"] in new or c["expected_revision"]}
    return MetricOutcome("saved", "Saved.", mid, res["metric_revision"], revisions,
                         warnings=_collisions(res.get("collisions"), mid),
                         checks_due=res.get("checks_due") or [])


def _metric_problems(draft: dict, calcs: list[dict], existing: list[dict]) -> list[dict]:
    """Every problem at once, so the page can mark each card. Nothing is written if any."""
    problems = []
    if not draft.get("full_name"):
        problems.append({"record": "metric", "field": "full_name", "message": "A name is required to save."})
    touched = {c["calc_id"]: c for c in calcs}
    # The PIs that will be active after this save: untouched existing ones keep their saved values.
    active = [touched.get(e["CALC_ID"], {"calc_id": e["CALC_ID"],
                                         "fields": {k: e[k.upper()] for k in CALC_EDITABLE}})
              for e in existing]
    active += [c for c in calcs if c["expected_revision"] is None]
    active = [c for c in active if not c.get("retire")]
    for c in active:
        if not c["fields"].get("sql_text"):
            problems.append({"record": c["calc_id"], "field": "sql_text", "message": "Add SQL to save."})
        if needs_label(len(active) - 1) and not c["fields"].get("disambig"):
            problems.append({"record": c["calc_id"], "field": "disambig",
                             "message": "With more than one implementation, say how this one differs."})
    return problems


def _mark_default(calcs: list[dict], existing: list[dict]) -> None:
    """The first active PI of a metric is its default (DEC-019): a new PI is default only when
    no existing PI stays active."""
    retiring = {c["calc_id"] for c in calcs if c["retire"]}
    has_active = any(e["CALC_ID"] not in retiring for e in existing)
    for c in calcs:
        c["is_default"] = False
        if c["expected_revision"] is None and not c["retire"] and not has_active:
            c["is_default"] = has_active = True


def _metric_conflict(draft: dict, calcs: list[dict]) -> MetricOutcome:
    """Nothing was written. Re-read every record the draft touched to say which moved and how."""
    conflicts = []
    if draft.get("id") is not None:
        latest = repo.get_metric(draft["id"])
        if latest is None or latest["REVISION_NO"] != draft["expected_revision"]:
            conflicts.append(_conflict_entry("metric", draft["id"], draft["expected_revision"], latest,
                                             "metric", LABELS))
    for c in calcs:
        if c["expected_revision"] is None:
            continue
        latest = repo.get_calc(c["calc_id"])
        if latest is None or latest["REVISION_NO"] != c["expected_revision"] or latest["STATUS"] != "active":
            conflicts.append(_conflict_entry(c["calc_id"], c["calc_id"], c["expected_revision"], latest,
                                             "metric_calc", CALC_LABELS))
    parts = [f"{e['by'] or 'someone'} changed "
             + ("the definition" if e["record"] == "metric" else f"implementation #{e['record']}")
             + f" ({', '.join(e['changed_fields']) or 'nothing visible'})" for e in conflicts]
    return MetricOutcome("conflict", "Nothing was saved: " + ("; ".join(parts) or "a record changed")
                         + " while you were editing. Your edits are still in the draft.",
                         draft.get("id"), conflicts=conflicts)


def _conflict_entry(record, record_id, expected: int, latest: dict | None,
                    record_type: str, labels: dict) -> dict:
    opened = repo.snapshot_at(record_type, record_id, expected) or {}
    changed = [label for k, label in labels.items()
               if latest is not None and (opened.get(k.upper()) or None) != (latest[k.upper()] or None)]
    if latest is not None and latest.get("STATUS") == "retired":
        changed.append("Removed")
    return {"record": record, "latest": latest, "changed_fields": changed,
            "by": latest and latest.get("UPDATED_BY"), "at": latest and latest.get("UPDATED_AT")}


def _metric_replayed(mid: int, draft: dict, calcs: list[dict]) -> MetricOutcome:
    """Confirm a retry only when its content matches the revisions returned as its baseline.
    A replay marker proves an earlier write landed, not that today's rows still match it."""
    landed = repo.get_metric(mid)
    differs = landed is None or any(
        (landed[k.upper()] or None) != (draft["fields"].get(k) or None) for k in EDITABLE)
    revisions = {}
    for c in calcs:
        if c["expected_revision"] is None and c["retire"]:
            continue  # added and removed in the same draft: the repository never wrote it
        row = repo.get_calc(c["calc_id"])
        if row is None or row["METRIC_ID"] != mid:
            differs = True
            continue
        revisions[c["calc_id"]] = row["REVISION_NO"]
        differs = differs or row["STATUS"] != ("retired" if c["retire"] else "active") or (
            not c["retire"] and bool(calc_changed(row, c["fields"])))
    if differs:
        # No revision numbers: the client must not bless old draft content with a newer revision.
        return MetricOutcome("conflict", REPLAY_CONFLICT, mid)
    return MetricOutcome("saved", "Saved.", mid, landed["REVISION_NO"], revisions)


REPLAY_CONFLICT = ("Your earlier save went through, but the current saved version differs from this "
                   "draft. Your draft is kept; reload and review the saved version before saving again.")


# ── fact tables (UX-04): one record, keyed on its 3-part name ─────────────────

FACT_EDITABLE = ("display_name", "description", "disambig", "gotchas", "required_filter", "grain",
                 "primary_key", "time_dimension", "department", "status")
FACT_LABELS = {"display_name": "Display name", "description": "Definition", "disambig": "When to use",
               "gotchas": "Gotchas", "required_filter": "Required filters", "grain": "Grain",
               "primary_key": "Key", "time_dimension": "Time field", "department": "Department",
               "status": "Status"}
_TABLE_NAME = re.compile(r"AC\.[A-Z0-9_$]+\.[A-Z0-9_$]+")


def fact_table_name(value: str | None) -> str | None:
    """The stored form of a table name (AC.SCHEMA.TABLE, upper case), or None if it isn't one.
    Unquoted Snowflake identifiers are upper case, so this is the name PIs' SQL resolves to."""
    name = (value or "").strip().upper()
    return name if _TABLE_NAME.fullmatch(name) else None


@dataclass
class FactTableOutcome:
    status: str  # saved | no_change | invalid | conflict | failed
    message: str
    table_name: str | None = None
    revision_no: int | None = None
    problems: list[dict] = field(default_factory=list)  # {field, message}
    conflict: dict | None = None  # {latest, changed_fields, by, at}


def save_fact_table(actor: str, op_id: str, table: dict, change_note: str | None = None) -> FactTableOutcome:
    """table: {table_name, expected_revision (None = create), fields}. Reuse op_id when retrying."""
    expected = table.get("expected_revision")
    name = fact_table_name(table.get("table_name"))
    fields = _clean(_pick(table.get("fields") or {}, FACT_EDITABLE))
    fields["status"] = fields["status"] or "active"
    problems = []
    if name is None:
        problems.append({"field": "table_name", "message": "Use the full name: AC.SCHEMA.TABLE."})
    if fields["status"] not in ("active", "retired"):
        problems.append({"field": "status", "message": "Status is active or retired."})
    if problems:
        return FactTableOutcome("invalid", "Nothing was saved: " + " ".join(p["message"] for p in problems),
                                name, problems=problems)
    try:
        res = repo.save_fact_table(op_id, actor, {"table_name": name, "expected_revision": expected,
                                                  "fields": fields}, change_note)
        if res["outcome"] == "exists":
            return FactTableOutcome("invalid", f"{name} is already registered — open it instead.", name,
                                    problems=[{"field": "table_name", "message": "Already registered."}])
        if res["outcome"] == "conflict":
            entry = _conflict_entry("table", name, expected, repo.get_fact_table(name),
                                    "fact_table_core", FACT_LABELS)
            return FactTableOutcome("conflict", f"Nothing was saved: {entry['by'] or 'someone'} changed {name} "
                                    f"({', '.join(entry['changed_fields']) or 'nothing visible'}) while you "
                                    "were editing. Your edits are still in the draft.", name, conflict=entry)
        if res["outcome"] == "replayed":
            landed = repo.get_fact_table(name)
            if landed is None or any((landed[k.upper()] or None) != (fields.get(k) or None)
                                     for k in FACT_EDITABLE):
                return FactTableOutcome("conflict", REPLAY_CONFLICT, name)
            return FactTableOutcome("saved", "Saved.", name, landed["REVISION_NO"])
    except ConnectionQuarantined as exc:
        return FactTableOutcome("failed", f"Not saved: {exc} Your draft is kept.", name)
    except Exception:
        log.exception("Fact table save failed: %s, op %s", name, op_id)
        return FactTableOutcome("failed", "Save could not be confirmed. Your draft is kept; "
                                "saving again is safe.", name)
    if res["outcome"] == "no_change":
        return FactTableOutcome("no_change", "No changes to save.", name, expected)
    return FactTableOutcome("saved", "Saved.", name, res["revision_no"])


def _conflict_message(latest: dict, changed: list[str]) -> str:
    when = f"{latest['UPDATED_AT']:%b %d %H:%M}" if latest.get("UPDATED_AT") else "recently"
    return (f"**{latest['UPDATED_BY']}** saved a newer version (rev {latest['REVISION_NO']}, {when}) "
            f"while you were editing. Changed: {', '.join(changed) or 'nothing visible'}. "
            "Your edits are still in the form.")


def _conflict(baseline: dict) -> Outcome:
    metric_id = baseline["METRIC_ID"]
    latest = repo.get_metric(metric_id)
    if latest is None:
        return Outcome(False, f"Metric #{metric_id} no longer exists.", metric_id)
    changed = [LABELS[k] for k in EDITABLE if (baseline[k.upper()] or None) != (latest[k.upper()] or None)]
    return Outcome(False, _conflict_message(latest, changed), metric_id, latest["REVISION_NO"], latest=latest)
