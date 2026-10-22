"""Throwaway SQL-editor spike — sidebar toggle 'SQL editor spike'. No DB writes.

Compares streamlit-code-editor and streamlit-ace against st.text_area. "Save"
only echoes what Python received, to expose lost last keystrokes.
"""
import importlib.metadata as md

import streamlit as st

SAMPLE_SQL = """-- Paste a real 80-line Finance query (e.g. NRR) over this.
WITH base AS (
    SELECT account_id,
           DATE_TRUNC('month', invoice_date) AS month,
           SUM(mrr) AS mrr
    FROM finance.invoices
    WHERE invoice_date >= DATEADD('month', -24, CURRENT_DATE)
    GROUP BY 1, 2
)
SELECT month,
       SUM(mrr) AS total_mrr
FROM base
GROUP BY 1
ORDER BY 1;
"""


def _version(pkg: str) -> str:
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return "not installed"


def _saved(label: str, text: str | None):
    if st.button(f"Save ({label})", key=f"save:{label}"):
        st.session_state[f"saved:{label}"] = text or ""
    saved = st.session_state.get(f"saved:{label}")
    if saved is not None:
        st.caption(f"Python received {len(saved.splitlines())} lines / {len(saved)} chars. Last line:")
        st.code(saved.splitlines()[-1] if saved.strip() else "(empty)", language="sql")


def render():
    st.title("SQL editor spike")
    st.caption(
        f"streamlit {st.__version__} · streamlit-code-editor {_version('streamlit-code-editor')} · "
        f"streamlit-ace {_version('streamlit-ace')} · reruns this session: "
        f"{st.session_state.setdefault('spike_runs', 0)}"
    )
    st.session_state["spike_runs"] += 1
    with st.expander("Checklist"):
        st.markdown(
            "- Highlighting while typing; Tab/Shift-Tab; line numbers; undo/redo; find\n"
            "- Paste a real 80-line query: no lost lines, no lag; copy back out and run in Snowsight\n"
            "- Type, then click Save **without clicking away** — is the last edit in 'Last line'?\n"
            "- Does the rerun counter jump while typing?\n"
            "- Click another widget — does each editor keep content and cursor?"
        )

    a, b, c = st.columns(3)
    with a:
        st.subheader("streamlit-code-editor")
        try:
            from code_editor import code_editor
            resp = code_editor(SAMPLE_SQL, lang="sql", height=[20, 30], key="ce")
            _saved("code-editor", (resp or {}).get("text") or None)
            st.caption(f"Last response type: {(resp or {}).get('type') or '(none)'}")
        except ImportError:
            st.error("streamlit-code-editor not installed")
    with b:
        st.subheader("streamlit-ace")
        try:
            from streamlit_ace import st_ace
            live = st.toggle("auto_update (send on every change)", key="ace_live")
            text = st_ace(SAMPLE_SQL, language="sql", keybinding="vscode",
                          auto_update=live, height=480, key=f"ace:{live}")
            _saved("ace", text)
        except ImportError:
            st.error("streamlit-ace not installed")
    with c:
        st.subheader("st.text_area (baseline)")
        text = st.text_area("SQL", SAMPLE_SQL, height=480, key="ta", label_visibility="collapsed")
        _saved("text_area", text)
