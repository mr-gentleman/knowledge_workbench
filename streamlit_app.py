"""Knowledge Workbench — slice 1: metric candidates (browse · create · edit · history)."""
import json
import logging
import time
import uuid

import streamlit as st
from st_keyup import st_keyup

from app import repositories as repo
from app import services
from app.db import ConnectionQuarantined, viewer

log = logging.getLogger(__name__)

st.set_page_config(page_title="Knowledge Workbench", layout="wide")

if st.sidebar.toggle("SQL editor spike", key="spike_editor"):  # throwaway — remove after
    from app import editor_spike
    editor_spike.render()
    st.stop()

DEPARTMENTS = ["", *services.DEPARTMENTS]
LIST_TTL_S = 30  # how stale the sidebar may be for saves made by other viewers


def _flash(outcome: services.Outcome):
    # Success is a toast: it can't scroll out of view (docs/ux-principles.md, rule 2).
    if outcome.ok:
        st.toast(f"✓ {outcome.message}")
    else:
        st.error(outcome.message)
    for w in outcome.warnings:
        st.warning(w)


def guarded(fn, *args):
    """A quarantined connection stops the page with a retry instead of a crash (DEC-008).
    Submitted drafts and a pending create live in session state, so they survive."""
    try:
        return fn(*args)
    except ConnectionQuarantined as exc:
        st.error(f"The database connection is recovering — nothing was saved. {exc}")
        st.button("Retry")
        st.stop()


def candidate_form(key: str, current: dict | None = None, with_note: bool = True,
                   save_disabled: bool = False):
    c = current or {}
    with st.form(key):
        full_name = st.text_input("Name *", c.get("FULL_NAME") or "", key=f"{key}:full_name")
        dept = services.department(c.get("DEPARTMENT")) or ""
        department = st.selectbox("Department", DEPARTMENTS, index=DEPARTMENTS.index(dept) if dept in DEPARTMENTS else 0, key=f"{key}:department")
        category = st.text_input("Category", c.get("CATEGORY") or "", key=f"{key}:category")
        description = st.text_area("Description", c.get("DESCRIPTION") or "", height=160, key=f"{key}:description")
        disambig = st.text_area("When to use / how it differs", c.get("DISAMBIG") or "", height=80, key=f"{key}:disambig")
        note = st.text_input("Change note (optional)", c.get("_NOTE") or "", key=f"{key}:note") if with_note else None
        submitted = st.form_submit_button("Save", type="primary", disabled=save_disabled)
    fields = dict(full_name=full_name, category=category,
                  description=description, disambig=disambig,
                  department=department or None)
    return submitted, fields, note


def recent_candidates():
    """Cached per browser session, so typing a search or switching records costs no query.
    Refreshed after LIST_TTL_S and after this viewer saves (forget_recent)."""
    cache = st.session_state.get("recent")
    if cache is None or time.monotonic() - cache[0] > LIST_TTL_S:
        cache = st.session_state["recent"] = (time.monotonic(), guarded(repo.list_candidates, ""))
    return cache[1]


def forget_recent():
    st.session_state.pop("recent", None)


def matching(search: str):
    rows, q = recent_candidates(), search.strip().lower()
    if not q:
        return rows
    if len(rows) == repo.LIST_LIMIT:  # the cap may hide older matches: search the table
        return guarded(repo.list_candidates, q)
    return [r for r in rows
            if q in " ".join(filter(None, (r["FULL_NAME"], r["DESCRIPTION"], r["DISAMBIG"]))).lower()]


# ── sidebar: search + pick ─────────────────────────────────────────────────
st.sidebar.title("Knowledge Workbench")
st.sidebar.caption(f"Signed in as **{viewer()}**")
with st.sidebar:
    # Searches as you type, after a 300 ms pause (st.text_input only reports on Enter).
    search = st_keyup("Search metrics", key="search", debounce=300,
                      placeholder="Name, description, when to use")
rows = matching(search)
if len(rows) == repo.LIST_LIMIT:
    st.sidebar.caption(f"Showing the {repo.LIST_LIMIT} most recently updated — search to narrow.")
# Stable IDs keep a concurrent rename/reordering from selecting a different record.
labels = {r["CANDIDATE_ID"]: f"#{r['CANDIDATE_ID']} · {r['FULL_NAME']}" for r in rows}
# A just-created candidate opens on the next run. The radio's value can only be
# set before the widget renders, so the create flow parks the id here and reruns.
# Always consume it: if a search filter hides the new record, a leftover id would
# yank the selection to it later, when the search is cleared.
just_created = st.session_state.pop("just_created", None)
if just_created in labels:
    st.session_state["selected_candidate"] = just_created
elif just_created is not None:
    st.sidebar.info(f"Saved as #{just_created} — clear the search to see it.")
selected = st.sidebar.radio(
    "Candidates", [None, *labels],
    format_func=lambda cid: "➕ New metric" if cid is None else labels[cid],
    key="selected_candidate", label_visibility="collapsed",
)

feedback = st.session_state.pop("edit_feedback", None)
if feedback:
    _flash(feedback)

# ── main ────────────────────────────────────────────────────────────────────
# Editor state persists per record for the browser session. On arriving at a record with
# no submitted draft, reload it so a save made elsewhere meanwhile shows up (REL-07).
# Unsubmitted widget edits don't survive leaving a record anyway (REL-12).
arrived = st.session_state.get("last_selected", "unset") != selected
st.session_state["last_selected"] = selected

if selected is None:
    st.header("New metric")
    st.caption("Only a name is required. Save early; fill in the rest later.")
    # One token per create attempt: a retry (even after a lost acknowledgement) returns
    # the first record instead of inserting again. Rotated, with a fresh empty form,
    # after every successful create (REL-10).
    create = st.session_state.setdefault(
        "create", {"token": uuid.uuid4().hex, "generation": 0, "payload": None})
    pending = create["payload"]  # submitted with this token, outcome not confirmed
    submitted, fields, _ = candidate_form(
        f"new-{create['generation']}",
        {k.upper(): v for k, v in pending.items()} if pending else None, with_note=False)
    if submitted:
        if pending is not None and pending != fields:
            # Never replay a token for different content: first find out whether the
            # unconfirmed attempt landed.
            prior = guarded(repo.candidate_for_token, create["token"])
            if prior is not None:
                create.update(token=uuid.uuid4().hex, generation=create["generation"] + 1, payload=None)
                st.session_state["just_created"] = prior
                st.session_state["edit_feedback"] = services.Outcome(
                    True, f"Saved earlier as #{prior}.", prior, warnings=[(
                        f"Your earlier save did go through as #{prior}. It's open now — "
                        "apply your newer changes here.")])
                forget_recent()
                st.rerun()
            # It didn't land, so the token is unused: the new entries can take it.
        create["payload"] = fields
        try:
            with st.spinner("Saving…"):
                out = services.save_new_candidate(fields, viewer(), create["token"])
        except ConnectionQuarantined as exc:
            st.error(f"Not saved: {exc}")
        except Exception:
            log.exception("Candidate create failed")
            st.error("Save could not be confirmed. Your entries are still in the form — "
                     "Save again is safe: it won't create a second copy.")
        else:
            if out.ok:
                # Open the new record: the sidebar lists it and the create form is gone,
                # so a repeat submit can't mint a second candidate (REL-02).
                create.update(token=uuid.uuid4().hex, generation=create["generation"] + 1, payload=None)
                st.session_state["just_created"] = out.record_id
                st.session_state["edit_feedback"] = out
                forget_recent()
                st.rerun()
            _flash(out)
else:
    editor_key = f"candidate-editor:{selected}"
    if editor_key not in st.session_state:
        st.session_state[editor_key] = {"baseline": guarded(repo.get_candidate, selected), "generation": 0}
    elif arrived and "draft" not in st.session_state[editor_key]:
        st.session_state[editor_key]["refresh"] = True
        st.session_state[editor_key]["generation"] += 1
    editor = st.session_state[editor_key]
    if editor.get("refresh"):
        editor["baseline"] = guarded(repo.get_candidate, selected)
        del editor["refresh"]  # only once it worked, so Retry refreshes too
    # Submission reruns the script. Never refresh this baseline mid-edit (only on arrival,
    # above): it must remain the revision the user actually opened.
    cand = editor["baseline"]
    if cand is None:
        st.error("This candidate no longer exists.")
        st.stop()
    st.header(cand["FULL_NAME"])
    just_saved = feedback is not None and feedback.ok and feedback.record_id == selected
    st.caption(
        (f"✓ Saved · rev {cand['REVISION_NO']} · just now  \n" if just_saved else "")
        + f"Candidate #{cand['CANDIDATE_ID']} · rev {cand['REVISION_NO']} · {cand['STATUS']} · "
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
            form_record["_NOTE"] = editor.get("draft_note")
        st.caption("Edits are kept only after you press Save — switching records discards unsaved changes.")
        conflict = editor.get("conflict")  # an Outcome; Save stays off until the user picks an action
        submitted, fields, note = candidate_form(
            f"edit-{selected}-{editor['generation']}", form_record, save_disabled=conflict is not None)
        if submitted:
            editor["draft"], editor["draft_note"] = fields, note
            try:
                with st.spinner("Saving…"):
                    out = services.save_candidate_edit(cand, fields, viewer(), note)
            except ConnectionQuarantined as exc:
                st.error(f"Not saved: {exc} Your draft is retained.")
            except Exception:
                log.exception("Candidate save failed: %s", selected)
                st.error("Save could not be confirmed. Your draft is retained. "
                         "Check History before retrying, or reload the latest record.")
            else:
                if out.ok:
                    # Refresh the WHOLE record, not just its revision. If another
                    # edit already landed, show that coherent version to the user.
                    editor["generation"] += 1
                    editor.pop("draft", None)
                    editor.pop("draft_note", None)
                    editor["refresh"] = True
                    st.session_state["edit_feedback"] = out
                    forget_recent()
                    st.rerun()
                if out.latest is not None:
                    editor["conflict"] = out
                    st.rerun()
                _flash(out)
        if conflict is not None:
            # Next to Save, only when a save was refused. Keeping my edits is the default;
            # discarding them is the secondary choice (docs/ux-principles.md, Conflict).
            st.error(conflict.message)
            latest = conflict.latest
            with st.expander("Their version", expanded=True):
                for k in services.EDITABLE:
                    if (cand[k.upper()] or None) != (latest[k.upper()] or None):
                        st.markdown(f"**{services.LABELS[k]}**")
                        st.text(latest[k.upper()] or "(empty)")
            st.caption("Keeping your edits applies them to the latest version: fields you didn't "
                       "change take their values. Review, then Save.")
            keep, discard = st.columns(2)
            if keep.button("Keep my edits on the latest version", type="primary", key=f"keep:{selected}"):
                editor["draft"] = services.keep_mine(editor["draft"], cand, latest)
                editor["baseline"] = latest
                editor["generation"] += 1  # reload the form from the merged draft
                del editor["conflict"]
                st.rerun()
            if discard.button("Discard mine, load theirs", key=f"discard:{selected}"):
                editor["baseline"] = latest
                editor["generation"] += 1  # New widget keys discard the old form values.
                for k in ("draft", "draft_note", "conflict"):
                    editor.pop(k, None)
                st.rerun()
    with tab_hist:
        # Tabs all render on every rerun, so history (full JSON snapshots) loads only on request (PLAT-05).
        if st.toggle("Show history", key=f"hist:{selected}"):
            for h in guarded(repo.history, "metric_candidate", selected):
                with st.expander(f"rev {h['REVISION_NO']} · {h['ACTION']} · {h['ACTOR']} · "
                                 f"{h['ACTED_AT']:%Y-%m-%d %H:%M}" + (f" — {h['CHANGE_NOTE']}" if h["CHANGE_NOTE"] else "")):
                    if h["SCHEMA_VERSION"] == 1:
                        st.caption("Older snapshot: empty fields weren't recorded.")
                    st.json(json.loads(h["SNAPSHOT"]))

