"""The SQL section of a candidate page: its physical implementations (PIs), one card each.

Each card saves on its own (own revision, own conflict). Card edits are kept in session state
on every rerun, so collapsing a card, switching records or a failed save loses nothing."""
import logging

import code_editor  # module import, so tests can swap the component for a text area
import streamlit as st

from app import repositories as repo
from app import services
from app.db import ConnectionQuarantined, viewer

log = logging.getLogger(__name__)

NEW = "new"  # card key of the not-yet-saved PI; saved cards are keyed by calc_id
PREVIEW_LINES = 3


def _state(cid: int, arrived: bool, guarded) -> dict:
    """rows: saved PIs as last loaded · new: the unsaved card ({"calc_id": reserved id or None})
    · drafts: card → edited fields · conflicts: card → Outcome · gen: bumps widget keys so
    cards reload from state · open: the expanded card."""
    key = f"pi:{cid}"
    s = st.session_state.get(key)
    # Like the identity form: reload on arrival unless there is unsaved work (REL-07).
    if s is None or (arrived and not s["drafts"] and s["new"] is None):
        rows = guarded(repo.list_calcs_for_candidate, cid)
        s = st.session_state[key] = {
            "rows": {r["CALC_ID"]: r for r in rows}, "new": None, "drafts": {}, "conflicts": {},
            "gen": (s or {"gen": 0})["gen"] + 1, "open": None}
    return s


def render(cid: int, arrived: bool, guarded, flash):
    s = _state(cid, arrived, guarded)
    st.subheader("SQL")
    feedback = st.session_state.pop("pi_feedback", None)
    if feedback:
        flash(feedback)
    keys = [*s["rows"], *([NEW] if s["new"] else [])]
    if not keys:
        st.caption("No SQL yet. Add the query that computes this metric.")
    # Clicks are applied only after every card has rendered: an open card records its
    # edits while it renders, so opening another card or adding one never drops them.
    opening = [key for key in keys if _card(cid, s, key, len(keys) > 1, guarded)]
    if s["new"] is None and st.button("+ Add SQL" if not keys else "+ Add another implementation",
                                      key=f"pi-add:{cid}"):
        s["new"], opening = {"calc_id": None}, [NEW]
    if opening:
        s["open"] = None if opening[0] == s["open"] else opening[0]
        st.rerun()


def _card(cid: int, s: dict, key, multiple: bool, guarded) -> bool:
    """Renders one PI card; True when its Edit/Collapse button was clicked."""
    base = s["rows"].get(key, {})
    is_open = not multiple or s["open"] == key
    with st.container(border=True):
        head, toggle = st.columns([6, 1])
        clicked = multiple and toggle.button("Collapse" if is_open else "Edit",
                                             key=f"pi-toggle:{cid}:{key}")
        if is_open:
            _editor(cid, s, key, base, _values(s, key, base), multiple, guarded)
        values = _values(s, key, base)  # after the editor, so the header reflects this run's edits
        if not is_open:
            lines = (values["sql_text"] or "").splitlines()
            st.code("\n".join(lines[:PREVIEW_LINES]) + ("\n…" if len(lines) > PREVIEW_LINES else ""),
                    language="sql")
        status = ["Not saved yet" if key == NEW else services.validation_state(base)]
        if key in s["drafts"] and key != NEW:
            status.append("● Unsaved changes")
        if multiple and base.get("IS_DEFAULT"):
            status.append("default")
        title = values["disambig"] or ("New implementation" if key == NEW else "Untitled implementation")
        head.markdown(f"**{title}** · " + " · ".join(status) if multiple else " · ".join(status))
    return clicked


def _values(s: dict, key, base: dict) -> dict:
    return s["drafts"].get(key) or {k: base.get(k.upper()) for k in services.CALC_EDITABLE}


def _editor(cid: int, s: dict, key, base: dict, values: dict, multiple: bool, guarded):
    wk = f"pi:{cid}:{key}:{s['gen']}"
    saved_siblings = len(s["rows"]) - (key != NEW)
    disambig = values["disambig"]
    if multiple:
        label = "How it differs" + (" *" if services.needs_label(saved_siblings) else "")
        disambig = st.text_input(label, disambig or "", key=f"{wk}:disambig",
                                 placeholder="e.g. monthly · by cohort · excludes trials")
    resp = code_editor.code_editor(
        values["sql_text"] or "", lang="sql", height=[6, 25], key=f"{wk}:sql",
        response_mode=["debounce", "blur"], options={"showPrintMargin": False})
    # The component returns an empty event until the user edits; until then the seed stands.
    sql_text = resp["text"] if resp and resp.get("id") else values["sql_text"] or ""
    source_table = st.text_input("Source table (optional)", values["source_table"] or "",
                                 key=f"{wk}:source_table", placeholder="DB.SCHEMA.TABLE")
    fields = dict(sql_text=sql_text, source_table=source_table, disambig=disambig)
    if key == NEW or services.calc_changed(base, fields):
        s["drafts"][key] = fields
    else:
        s["drafts"].pop(key, None)

    conflict = s["conflicts"].get(key)
    save, cancel = st.columns([1, 6])
    if save.button("Save SQL", type="primary", key=f"{wk}:save", disabled=conflict is not None):
        _save(cid, s, key, fields, saved_siblings, guarded)
    if key == NEW and cancel.button("Cancel", key=f"{wk}:cancel"):
        s["new"] = None
        s["drafts"].pop(NEW, None)
        st.rerun()
    if conflict is not None:
        _conflict(cid, s, key, base, conflict)


def _save(cid: int, s: dict, key, fields: dict, saved_siblings: int, guarded):
    try:
        with st.spinner("Saving…"):
            if key == NEW:
                if s["new"]["calc_id"] is None:
                    s["new"]["calc_id"] = repo.reserve_calc_id()
                out = services.save_new_calc(cid, s["new"]["calc_id"], fields, saved_siblings, viewer())
            else:
                out = services.save_calc_edit(s["rows"][key], fields, saved_siblings, viewer())
    except ConnectionQuarantined as exc:
        st.error(f"Not saved: {exc} Your SQL is kept.")
        return
    except Exception:
        log.exception("PI save failed: %s", key)
        st.error("Save could not be confirmed. Your SQL is kept — Save again is safe: "
                 "it won't create a second copy.")
        return
    if out.ok:
        calc_id = out.record_id
        # Reload only this card: another card's baseline must stay the revision its user opened.
        if key == NEW or out.revision_no != s["rows"][key]["REVISION_NO"]:  # not a no-op
            s["rows"][calc_id] = out.latest or guarded(repo.get_calc, calc_id)
        draft = s["drafts"].pop(key, None)
        if key == NEW:
            s["new"], s["open"] = None, calc_id
            if out.warnings:  # an earlier attempt landed with different content: keep the newer
                s["drafts"][calc_id] = draft
        st.session_state["pi_feedback"] = out
    elif out.latest is not None:
        s["conflicts"][key] = out
    else:
        st.error(out.message)
        return
    s["gen"] += 1
    st.rerun()


def _conflict(cid: int, s: dict, key, base: dict, conflict):
    # Same pattern as the identity form (docs/ux-principles.md, Conflict).
    st.error(conflict.message)
    latest = conflict.latest
    with st.expander("Their version", expanded=True):
        for k in services.calc_changed(base, {f: latest[f.upper()] for f in services.CALC_EDITABLE}):
            st.markdown(f"**{services.CALC_LABELS[k]}**")
            st.code(latest[k.upper()] or "(empty)", language="sql" if k == "sql_text" else None)
    st.caption("Keeping your edits applies them to the latest version: fields you didn't "
               "change take their values. Review, then Save.")
    keep, discard = st.columns(2)
    if keep.button("Keep my edits on the latest version", type="primary", key=f"pi-keep:{cid}:{key}"):
        s["drafts"][key] = services.keep_mine(s["drafts"][key], base, latest)
        _resolve(s, key, latest)
    if discard.button("Discard mine, load theirs", key=f"pi-discard:{cid}:{key}"):
        s["drafts"].pop(key, None)
        _resolve(s, key, latest)


def _resolve(s: dict, key, latest: dict):
    s["rows"][key] = latest
    del s["conflicts"][key]
    s["gen"] += 1  # reload the card from state
    st.rerun()
