"""Snowflake session + trusted viewer identity."""
import os
import threading

import streamlit as st

SCHEMA = "AI_PLATFORM.WORKBENCH"


def session():
    # Container runtime + local dev both use st.connection (local: ~/.snowflake/connections.toml).
    conn = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL"))
    return conn.session()


@st.cache_resource
def db_lock() -> threading.RLock:
    """One lock per app process (cache_resource survives reruns, even in the single-file build).
    Every viewer shares one Snowflake connection, so an open transaction is visible to —
    and joinable by — any other statement on it. Hold this for every transaction and for
    every read that loads an editable baseline. See docs/decisions.md DEC-004."""
    return threading.RLock()


def viewer() -> str:
    """Who is acting. Never taken from a form field, never CURRENT_USER() —
    in the container runtime that can be the app's service user, not the person."""
    user = getattr(st, "user", None)
    for attr in ("user_name", "email"):
        name = getattr(user, attr, None) if user else None
        if name:
            return name
    st.error("Can't determine who you are — saves are disabled.")
    st.stop()


def query(sql: str, params: list | None = None):
    return session().sql(sql, params=params or []).collect()
