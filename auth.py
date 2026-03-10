"""
Authentication helper for Counselling module.
Mirrors the auth pattern from RTIS app (get_current_user).

In production, copy or symlink from your shared auth module.
This reads the session cookie set by the Node.js BBTRO app.
"""

from fastapi import Request
from db_config import get_db_connection


def get_current_user(request: Request) -> dict | None:
    """
    Extract current user from session cookie.
    The Node.js BBTRO app sets a session cookie that contains the user info.
    
    Adjust this to match your actual session/cookie mechanism.
    For now, this checks for a session token in cookies or Authorization header
    and looks it up in the sessions table.
    """
    # Try cookie first (web browser)
    session_token = request.cookies.get("connect.sid") or request.cookies.get("session_token")

    # Try Authorization header (API / mobile)
    if not session_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            session_token = auth_header[7:]

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
    from fastapi import HTTPException
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user
