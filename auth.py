"""
Authentication helper for Counselling module.
Mirrors the auth pattern from RTIS app (get_current_user).

In production, copy or symlink from your shared auth module.
This reads the session cookie set by the Node.js BBTRO app.
"""

import os
import re
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
    raw_role = user.get("role")
    if not raw_role:
        return set()

    roles = set()
    for token in re.split(r"[,\|;/]+", str(raw_role)):
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

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Adjust this query to match your session storage
        # This assumes sessions are stored in a `sessions` table
        cursor.execute(
            "SELECT user_id, username, role, office FROM sessions WHERE session_id = %s AND expires_at > NOW()",
            (session_token,)
        )
        user = cursor.fetchone()
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
