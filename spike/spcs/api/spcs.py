"""SPCS adapter: Snowflake connections and the viewer's identity. The only SPCS-specific module.

Inside SPCS, Snowflake mounts an OAuth token at TOKEN_PATH and sets SNOWFLAKE_HOST/ACCOUNT.
Ingress adds Sf-Context-Current-User (who signed in) and, with executeAsCaller, a
Sf-Context-Current-User-Token that turns a connection into a caller's-rights one.
Outside SPCS (local dev) the session comes from ~/.snowflake/connections.toml.
"""
import os

import snowflake.connector
from fastapi import HTTPException, Request
from snowflake.snowpark import Session

TOKEN_PATH = "/snowflake/session/token"
IN_SPCS = os.path.exists(TOKEN_PATH)
USER_HEADER = "Sf-Context-Current-User"
USER_TOKEN_HEADER = "Sf-Context-Current-User-Token"

_session = None


def _connect(token: str):
    return snowflake.connector.connect(
        host=os.environ["SNOWFLAKE_HOST"], account=os.environ["SNOWFLAKE_ACCOUNT"],
        authenticator="oauth", token=token,
        database="AI_PLATFORM", schema="WORKBENCH", warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        client_session_keep_alive=True,
    )


def _service_token() -> str:
    # Snowflake refreshes this file; read it fresh for every new connection.
    with open(TOKEN_PATH) as f:
        return f.read()


def session() -> Session:
    """Owner's-rights session (the service's role). Replaces app.db.session, so all of
    db.locked_session's lock/heal/tag logic applies unchanged. Called under db_lock."""
    global _session
    if _session is None:
        if IN_SPCS:
            _session = Session.builder.configs({"connection": _connect(_service_token())}).create()
        else:
            _session = Session.builder.config("connection_name", os.getenv("KW_CONNECTION", "workbench_deploy")).create()
    return _session


def viewer(request: Request) -> str:
    """Who is acting: set by SPCS ingress after Snowflake login — never a form field.
    KW_DEV_USER stands in only when running outside SPCS."""
    user = request.headers.get(USER_HEADER)
    if user:
        return user
    if not IN_SPCS and os.getenv("KW_DEV_USER"):
        return os.environ["KW_DEV_USER"]
    raise HTTPException(401, "Can't determine who you are — saves are disabled.")


def caller_identity(request: Request) -> dict:
    """Spike check: open a caller's-rights connection and ask Snowflake who it runs as."""
    user_token = request.headers.get(USER_TOKEN_HEADER)
    if not (IN_SPCS and user_token):
        return {"available": False, "reason": "no caller token (executeAsCaller off, or not in SPCS)"}
    try:
        with _connect(_service_token() + "." + user_token) as conn:
            user, role = conn.cursor().execute("SELECT CURRENT_USER(), CURRENT_ROLE()").fetchone()
        return {"available": True, "current_user": user, "current_role": role}
    except Exception as exc:  # the spike wants the error text, not a 500
        return {"available": False, "reason": repr(exc)[:500]}
