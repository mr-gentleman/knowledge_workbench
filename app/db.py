"""Snowflake session + trusted viewer identity."""
import os

import streamlit as st

SCHEMA = "AI_PLATFORM.WORKBENCH"


def session():
    # Container runtime + local dev both use st.connection (local: ~/.snowflake/connections.toml).
    conn = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL"))
    return conn.session()


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
