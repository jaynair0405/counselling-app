"""
Authentication helper for Counselling module.
Mirrors the auth pattern from RTIS app (get_current_user).

In production, copy or symlink from your shared auth module.
This reads the session cookie set by the Node.js BBTRO app.
"""

import os
import re
import json
from urllib.parse import unquote
from typing import Callable

from fastapi import HTTPException, Request
from db_config import get_db_connection


DEV_BYPASS_USER = {
    "user_id": "local-dev",
    "username": "local-dev",
    "role": "DEV",
    "office": "LOCAL",
    "auth_bypass": True,
}

DEFAULT_OPERATOR_ROLES = {
    "ADMIN",
    "SUPERADMIN",
    "DIVISIONADMIN",
    "OFFICEHR",
    "CLI",
    "JRINST",
    "SRINST",
    "ADEE",
    "TLC",
    "LPC",
}

DEFAULT_EDITOR_ROLES = {
    "ADMIN",
    "SUPERADMIN",
    "DIVISIONADMIN",
    "JRINST",
    "SRINST",
    "ADEE",
    "TLC",
}


def _auth_disabled() -> bool:
    return os.getenv("COUNSELLING_AUTH_DISABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


def _localhost_auth_bypass_enabled() -> bool:
    return os.getenv("COUNSELLING_LOCALHOST_AUTH_BYPASS", "1").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_role(role: str | None) -> str:
    if not role:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(role).upper())


def _extract_user_roles(user: dict) -> set[str]:
    roles = set()
    for field in ("role", "div_role"):
        raw_value = user.get(field)
        if not raw_value:
            continue

        for token in re.split(r"[,\|;/]+", str(raw_value)):
            normalized = _normalize_role(token)
            if normalized:
                roles.add(normalized)
    return roles


def _parse_allowed_roles(env_var: str, defaults: set[str]) -> set[str]:
    raw = os.getenv(env_var, "").strip()
    if not raw:
        return defaults
    return {
        normalized
        for normalized in (_normalize_role(token) for token in raw.split(","))
        if normalized
    }


def _extract_session_id(raw_token: str | None) -> str | None:
    """
    Express-session cookies are typically stored as:
      s:<session_id>.<signature>
    and may be URL-encoded by the browser.
    """
    if not raw_token:
        return None

    token = unquote(str(raw_token)).strip()
    if token.startswith("s:"):
        token = token[2:]
    if "." in token:
        token = token.split(".", 1)[0]

    return token or None


def _normalize_session_user(session_data: dict) -> dict | None:
    """
    Convert the Express session JSON payload into the user shape expected by
    the counselling routes.
    """
    if not isinstance(session_data, dict):
        return None

    raw_user = session_data.get("user", session_data)
    if not isinstance(raw_user, dict):
        return None

    username = raw_user.get("username")
    user_id = raw_user.get("id") or raw_user.get("user_id")
    if not username and not user_id:
        return None

    return {
        "user_id": user_id,
        "username": username,
        "role": raw_user.get("role"),
        "div_role": raw_user.get("div_role"),
        "office": raw_user.get("office") or raw_user.get("div_office_code") or raw_user.get("office_code"),
        "full_name": raw_user.get("full_name") or raw_user.get("name"),
        "realm": raw_user.get("realm"),
        "div_office_code": raw_user.get("div_office_code"),
    }


def get_current_user(request: Request) -> dict | None:
    """
    Extract current user from session cookie.
    The Node.js BBTRO app sets a session cookie that contains the user info.
    
    Adjust this to match your actual session/cookie mechanism.
    For now, this checks for a session token in cookies or Authorization header
    and looks it up in the sessions table.
    """
    if _auth_disabled():
        return DEV_BYPASS_USER.copy()

    # Try cookie first (web browser)
    session_token = request.cookies.get("connect.sid") or request.cookies.get("session_token")

    # Try Authorization header (API / mobile)
    if not session_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            session_token = auth_header[7:]

    if not session_token and _localhost_auth_bypass_enabled():
        hostname = (request.url.hostname or "").lower()
        if hostname in {"localhost", "127.0.0.1"}:
            return DEV_BYPASS_USER.copy()

    if not session_token:
        return None

    session_id = _extract_session_id(session_token)
    if not session_id:
        return None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # BBTRO uses express-session + express-mysql-session, which stores JSON
        # in sessions(session_id, expires, data). We read that payload and
        # extract req.session.user from it.
        cursor.execute(
            """SELECT data
               FROM sessions
               WHERE session_id = %s
                 AND expires > UNIX_TIMESTAMP()
               LIMIT 1""",
            (session_id,)
        )
        row = cursor.fetchone()

        if row and row.get("data"):
            raw_data = row["data"]
            if isinstance(raw_data, (bytes, bytearray)):
                raw_data = raw_data.decode("utf-8", errors="ignore")

            try:
                session_data = json.loads(raw_data)
            except (TypeError, json.JSONDecodeError):
                session_data = None

            user = _normalize_session_user(session_data)
        else:
            user = None

        cursor.close()
        conn.close()
        return user
    except Exception:
        return None


def require_auth(request: Request) -> dict:
    """
    Same as get_current_user but raises 401 if not authenticated.
    Use as a dependency in route handlers.
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_roles(allowed_roles: set[str], label: str) -> Callable[[Request], dict]:
    """
    Build a dependency that enforces role-based access using the `role` field
    returned by the parent BBTRO session lookup.
    """
    def dependency(request: Request) -> dict:
        user = require_auth(request)
        if user.get("auth_bypass"):
            return user

        user_roles = _extract_user_roles(user)
        if allowed_roles and user_roles.intersection(allowed_roles):
            return user

        raise HTTPException(status_code=403, detail=f"{label} access denied")

    return dependency


def require_counselling_operator(request: Request) -> dict:
    allowed_roles = _parse_allowed_roles("COUNSELLING_OPERATOR_ROLES", DEFAULT_OPERATOR_ROLES)
    return require_roles(allowed_roles, "Counselling operator")(request)


def require_counselling_editor(request: Request) -> dict:
    allowed_roles = _parse_allowed_roles("COUNSELLING_EDITOR_ROLES", DEFAULT_EDITOR_ROLES)
    return require_roles(allowed_roles, "Question management")(request)
