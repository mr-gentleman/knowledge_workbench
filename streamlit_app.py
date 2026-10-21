"""Knowledge Workbench — slice 1: metric candidates (browse · create · edit · history)."""
import json

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
        full_name = st.text_input("Name *", c.get("FULL_NAME") or "")
        dept = c.get("DEPARTMENT") or ""
        department = st.selectbox("Department", DEPARTMENTS, index=DEPARTMENTS.index(dept) if dept in DEPARTMENTS else 0)
        category = st.text_input("Category", c.get("CATEGORY") or "")
        description = st.text_area("Description", c.get("DESCRIPTION") or "", height=160)
        disambig = st.text_area("When to use / how it differs", c.get("DISAMBIG") or "", height=80)
        note = st.text_input("Change note (optional)") if current else None
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
labels = {"➕ New metric": None} | {
    f"#{r['CANDIDATE_ID']} · {r['FULL_NAME']}": r["CANDIDATE_ID"] for r in rows
}
pick = st.sidebar.radio("Candidates", list(labels), label_visibility="collapsed")
selected = labels[pick]

# ── main ────────────────────────────────────────────────────────────────────
if selected is None:
    st.header("New metric")
    st.caption("Only a name is required. Save early; fill in the rest later.")
    submitted, fields, _ = candidate_form("new")
    if submitted:
        out = services.save_new_candidate(fields, viewer())
        _flash(out)
        if out.ok:
            st.session_state["just_created"] = out.record_id
else:
    cand = repo.get_candidate(selected)
    st.header(cand["FULL_NAME"])
    st.caption(
        f"Candidate #{cand['CANDIDATE_ID']} · rev {cand['REVISION_NO']} · {cand['STATUS']} · "
        f"author {cand['ORIGINAL_AUTHOR'] or 'unknown'} · last edit {cand['UPDATED_BY']} "
        f"{cand['UPDATED_AT']:%Y-%m-%d %H:%M}"
    )
    tab_edit, tab_hist = st.tabs(["Edit", "History"])
    with tab_edit:
        submitted, fields, note = candidate_form(f"edit-{selected}", cand)
        if submitted:
            _flash(services.save_candidate_edit(selected, cand["REVISION_NO"], fields, viewer(), note))
    with tab_hist:
        for h in repo.history("metric_candidate", selected):
            with st.expander(f"rev {h['REVISION_NO']} · {h['ACTION']} · {h['ACTOR']} · "
                             f"{h['ACTED_AT']:%Y-%m-%d %H:%M}" + (f" — {h['CHANGE_NOTE']}" if h["CHANGE_NOTE"] else "")):
                st.json(json.loads(h["SNAPSHOT"]))
