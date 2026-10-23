"""Throwaway SQL-editor spike — sidebar toggle 'SQL editor spike'. No DB writes.

Chosen editor: streamlit-code-editor (Ace). This page is a display-options
playground. "Save" only echoes what Python received. (streamlit-ace lost the
comparison; streamlit-monaco loads Monaco from cdn.jsdelivr.net, which SiS
blocks.) Ctrl+Enter compiles the SQL with EXPLAIN (never runs it) as WORKBENCH_APP — so tables that role can't see fail as "not authorized".
"""
import importlib.metadata as md

import streamlit as st

from app.db import locked_session

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


def _compile(sql: str):
    """EXPLAIN only compiles — no rows read, no DML executed."""
    try:
        with locked_session() as s:
            s.sql(f"EXPLAIN USING TEXT {sql.strip().rstrip(';')}").collect()
        st.success("Compiles OK")
    except Exception as e:  # surface the Snowflake error as-is
        st.error(str(e).splitlines()[0] if str(e) else repr(e))


THEMES = ["default", "light", "dark", "contrast"]
ACE_THEMES = ["(none)", "sqlserver", "github", "github_dark", "chrome", "xcode", "tomorrow",
              "tomorrow_night", "monokai", "dracula", "one_dark", "nord_dark", "solarized_light",
              "solarized_dark", "cloud_editor", "cloud_editor_dark", "gruvbox"]


def render():
    st.title("SQL editor — display options")
    st.caption(f"streamlit {st.__version__} · streamlit-code-editor {_version('streamlit-code-editor')}")
    from code_editor import code_editor

    opts, ed = st.columns([1, 3])
    with opts:
        theme = st.selectbox("Base theme", THEMES, key="o_theme")
        ace = st.selectbox("Color theme (overrides base)", ACE_THEMES, key="o_ace")
        font = st.slider("Font size", 11, 20, 14, key="o_font")
        lines = st.slider("Height (lines)", 10, 50, (20, 30), key="o_h")
        wrap = st.toggle("Wrap long lines", key="o_wrap")
        gutter = st.toggle("Line numbers", True, key="o_gutter")
        active = st.toggle("Highlight current line", True, key="o_active")
        margin = st.toggle("Print margin (80-col line)", False, key="o_margin")
        tab = st.radio("Tab size", [2, 4], index=1, horizontal=True, key="o_tab")
    with ed:
        st.caption("Ctrl+Enter = compile check (EXPLAIN). Changing an option keeps your text.")
        props = {"theme": ace} if ace != "(none)" else {}
        options = {"fontSize": font, "wrap": wrap, "showGutter": gutter, "tabSize": tab,
                   "highlightActiveLine": active, "showPrintMargin": margin}
        # Options are part of the key so the editor remounts with them; feed back the
        # last text so a remount doesn't reset what you typed.
        sig = f"{theme}|{ace}|{font}|{lines}|{wrap}|{gutter}|{active}|{margin}|{tab}"
        resp = code_editor(st.session_state.get("ce_text", SAMPLE_SQL), lang="sql", theme=theme,
                           height=list(lines), props=props, options=options, key=f"ce:{sig}")
        if resp and resp.get("text"):
            st.session_state["ce_text"] = resp["text"]
        _saved("code-editor", (resp or {}).get("text") or None)
        # Compile once per Ctrl+Enter, not on every later rerun.
        if resp and resp.get("type") == "submit" and resp.get("id") != st.session_state.get("ce_done"):
            st.session_state["ce_done"] = resp.get("id")
            _compile(resp.get("text") or "")
