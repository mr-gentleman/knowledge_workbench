"""Snowflake session, the process-wide lock, and trusted viewer identity."""
import logging
import os
import threading
from contextlib import contextmanager

import streamlit as st

SCHEMA = "AI_PLATFORM.WORKBENCH"
log = logging.getLogger(__name__)


class ConnectionQuarantined(RuntimeError):
    """A transaction's outcome was uncertain and the connection could not be proven clean."""


def session():
    # Container runtime + local dev both use st.connection (local: ~/.snowflake/connections.toml).
    # In SiS this is the app's one active session: it cannot be reset, only cleaned (_heal).
    conn = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL"))
    return conn.session()


@st.cache_resource
def _state() -> dict:
    """One per app process (cache_resource survives reruns). Every viewer shares one
    Snowflake connection, so an open transaction is visible to — and joinable by — any
    other statement on it. See docs/decisions.md DEC-004, DEC-007."""
    return {"lock": threading.RLock(), "dirty": False}


def db_lock() -> threading.RLock:
    """Held for every database operation, only while executing/fetching (DEC-007)."""
    return _state()["lock"]


def mark_dirty():
    """A transaction's outcome is uncertain; nothing else runs until _heal proves it clean."""
    _state()["dirty"] = True


def is_dirty() -> bool:
    return _state()["dirty"]


def _heal(s):
    # Called under the lock. ROLLBACK is harmless when no transaction is open.
    try:
        s.sql("ROLLBACK").collect()
        open_txn = s.sql("SELECT CURRENT_TRANSACTION()").collect()[0][0]
    except Exception as exc:
        raise ConnectionQuarantined("Database connection is not usable yet; try again shortly.") from exc
    if open_txn is not None:
        raise ConnectionQuarantined(f"Transaction {open_txn} is still open; try again shortly.")
    _state()["dirty"] = False
    log.warning("Connection recovered after an uncertain transaction.")


@contextmanager
def locked_session():
    """The only way to reach the database: under the lock, on a proven-clean connection."""
    with db_lock():
        s = session()
        if _state()["dirty"]:
            _heal(s)
        yield s


def check_connection(timeout_s: int):
    """A fresh connection for one SQL check (sql/007), used outside db_lock so a slow check never
    blocks saves; it opens no transaction and writes nothing. api/main.py provides it (DEC-022);
    the frozen Streamlit app has none."""
    raise NotImplementedError("SQL checks run only in the React app.")


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
    with locked_session() as s:
        return s.sql(sql, params=params or []).collect()
