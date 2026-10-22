"""Knowledge Workbench — slice 1: metric candidates (browse · create · edit · history)."""
import json
import logging

import streamlit as st

from app import repositories as repo
from app import services
from app.db import viewer

st.set_page_config(page_title="Knowledge Workbench", layout="wide")

DEPARTMENTS = ["", "finance", "marketing", "sales", "customer", "product", "bi_meta", "misc"]


def _flash(outcome: services.Outcome):
    (st.success if outcome.ok else st.error)(outcome.message)
    for w in outcome.warnings:
        st.warning(w)


def candidate_form(key: str, current: dict | None = None):
    c = current or {}
    with st.form(key):
        full_name = st.text_input("Name *", c.get("FULL_NAME") or "", key=f"{key}:full_name")
        dept = c.get("DEPARTMENT") or ""
        department = st.selectbox("Department", DEPARTMENTS, index=DEPARTMENTS.index(dept) if dept in DEPARTMENTS else 0, key=f"{key}:department")
        category = st.text_input("Category", c.get("CATEGORY") or "", key=f"{key}:category")
        description = st.text_area("Description", c.get("DESCRIPTION") or "", height=160, key=f"{key}:description")
        disambig = st.text_area("When to use / how it differs", c.get("DISAMBIG") or "", height=80, key=f"{key}:disambig")
        note = st.text_input("Change note (optional)", key=f"{key}:note") if current else None
        submitted = st.form_submit_button("Save", type="primary")
    fields = dict(full_name=full_name, category=category,
                  description=description, disambig=disambig,
                  department=department or None)
    return submitted, fields, note


# ── sidebar: search + pick ─────────────────────────────────────────────────
st.sidebar.title("Knowledge Workbench")
st.sidebar.caption(f"Signed in as **{viewer()}**")
search = st.sidebar.text_input("Search metrics")
rows = repo.list_candidates(search)
# Stable IDs keep a concurrent rename/reordering from selecting a different record.
labels = {r["CANDIDATE_ID"]: f"#{r['CANDIDATE_ID']} · {r['FULL_NAME']}" for r in rows}
# A just-created candidate opens on the next run. The radio's value can only be
# set before the widget renders, so the create flow parks the id here and reruns.
if st.session_state.get("just_created") in labels:
    st.session_state["selected_candidate"] = st.session_state.pop("just_created")
selected = st.sidebar.radio(
    "Candidates", [None, *labels],
    format_func=lambda cid: "➕ New metric" if cid is None else labels[cid],
    key="selected_candidate", label_visibility="collapsed",
)

if "edit_feedback" in st.session_state:
    _flash(st.session_state.pop("edit_feedback"))

# ── main ────────────────────────────────────────────────────────────────────
if selected is None:
    st.header("New metric")
    st.caption("Only a name is required. Save early; fill in the rest later.")
    submitted, fields, _ = candidate_form("new")
    if submitted:
        out = services.save_new_candidate(fields, viewer())
        if out.ok:
            # Open the new record: the sidebar lists it and the create form is gone,
            # so a repeat submit can't mint a second candidate (REL-02).
            st.session_state["just_created"] = out.record_id
            st.session_state["edit_feedback"] = out
            st.rerun()
        _flash(out)
else:
    editor_key = f"candidate-editor:{selected}"
    if editor_key not in st.session_state:
        st.session_state[editor_key] = {"baseline": repo.get_candidate(selected), "generation": 0}
    editor = st.session_state[editor_key]
    if editor.pop("refresh", False):
        editor["baseline"] = repo.get_candidate(selected)
    # Submission reruns the script. Never refresh this baseline implicitly:
    # it must remain the revision the user actually opened.
    cand = editor["baseline"]
    if cand is None:
        st.error("This candidate no longer exists.")
        st.stop()
    if st.button("Reload latest — discard my edits", key=f"reload:{selected}"):
        editor["baseline"] = repo.get_candidate(selected)
        editor["generation"] += 1  # New widget keys discard the old form values.
        editor.pop("draft", None)
        st.rerun()
    st.header(cand["FULL_NAME"])
    st.caption(
        f"Candidate #{cand['CANDIDATE_ID']} · rev {cand['REVISION_NO']} · {cand['STATUS']} · "
        f"author {cand['ORIGINAL_AUTHOR'] or 'unknown'} · last edit {cand['UPDATED_BY']} "
        f"{cand['UPDATED_AT']:%Y-%m-%d %H:%M}"
    )
    tab_edit, tab_hist = st.tabs(["Edit", "History"])
    with tab_edit:
        # Keep submitted drafts outside widget state too: Streamlit cleans up
        # widgets when navigating away from a record.
        form_record = dict(cand)
        if "draft" in editor:
            form_record.update({k.upper(): v for k, v in editor["draft"].items()})
        submitted, fields, note = candidate_form(
            f"edit-{selected}-{editor['generation']}", form_record)
        if submitted:
            editor["draft"] = fields
            try:
                out = services.save_candidate_edit(
                    selected, cand["REVISION_NO"], fields, viewer(), note)
            except Exception:
                logging.exception("Candidate save failed: %s", selected)
                st.error("Save could not be confirmed. Your draft is retained. "
                         "Check History before retrying, or reload the latest record.")
            else:
                if out.ok:
                    # Refresh the WHOLE record, not just its revision. If another
                    # edit already landed, show that coherent version to the user.
                    editor["generation"] += 1
                    editor.pop("draft", None)
                    editor["refresh"] = True
                    st.session_state["edit_feedback"] = out
                    st.rerun()
                _flash(out)
    with tab_hist:
        for h in repo.history("metric_candidate", selected):
            with st.expander(f"rev {h['REVISION_NO']} · {h['ACTION']} · {h['ACTOR']} · "
                             f"{h['ACTED_AT']:%Y-%m-%d %H:%M}" + (f" — {h['CHANGE_NOTE']}" if h["CHANGE_NOTE"] else "")):
                st.json(json.loads(h["SNAPSHOT"]))

