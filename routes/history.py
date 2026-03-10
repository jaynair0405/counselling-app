"""
History Routes — Counselling history, test records, weak area tracking

Endpoints:
  GET /api/history/staff/{identifier}         → All sessions for a staff member
  GET /api/history/staff/{identifier}/latest   → Latest session details
  GET /api/history/staff/{identifier}/weak     → Weak area history
  GET /api/history/cli/{identifier}            → All sessions conducted by a CLI
  GET /api/history/dashboard                   → Overview stats for dashboard
"""

from fastapi import APIRouter, Query
from typing import Optional
from db_config import get_db_connection
from services.scoring import get_weak_history

router = APIRouter()


def resolve_staff_hrms_id(identifier: str) -> str:
    """Resolve current_cms_id or HRMS ID to staff_hrms_id. Never searches original_cms_id."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT hrms_id FROM div_staff_master
               WHERE hrms_id = %s OR current_cms_id = %s
               LIMIT 1""",
            (identifier.upper(), identifier.upper())
        )
        row = cursor.fetchone()
        return row["hrms_id"] if row else identifier.upper()
    finally:
        cursor.close()
        conn.close()


@router.get("/staff/{identifier}")
async def staff_history(
    identifier: str,
    limit: int = Query(20, ge=1, le=100),
):
    """Get counselling history for a staff member. Accepts CMS ID or HRMS ID."""
    hrms_id = resolve_staff_hrms_id(identifier)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT id, test_number, category_code, total_score, total_questions,
                      percentage, grade, cli_name, duration_seconds,
                      started_at, completed_at
               FROM div_runsafe_sessions
               WHERE staff_hrms_id = %s AND status = 'completed'
               ORDER BY completed_at DESC LIMIT %s""",
            (hrms_id, limit)
        )
        sessions = cursor.fetchall()

        for s in sessions:
            for key in ["started_at", "completed_at"]:
                if s.get(key):
                    s[key] = s[key].isoformat()

        return {"staff_hrms_id": hrms_id, "sessions": sessions, "total": len(sessions)}

    finally:
        cursor.close()
        conn.close()


@router.get("/staff/{identifier}/latest")
async def staff_latest_session(identifier: str):
    """Get the latest completed session with full marksheet."""
    hrms_id = resolve_staff_hrms_id(identifier)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT * FROM div_runsafe_sessions
               WHERE staff_hrms_id = %s AND status = 'completed'
               ORDER BY completed_at DESC LIMIT 1""",
            (hrms_id,)
        )
        session = cursor.fetchone()
        if not session:
            return {"found": False, "staff_hrms_id": hrms_id}

        session_id = session["id"]
        for key in ["started_at", "completed_at"]:
            if session.get(key):
                session[key] = session[key].isoformat()

        # Get answers with question text
        cursor.execute(
            """SELECT ca.question_id, cq.question_text,
                      ca.submitted_answer, ca.submitted_answer_text,
                      ca.correct_answer, ca.correct_answer_text,
                      ca.is_correct, ca.is_reattempt,
                      cq.category_code, cq.subcategory_code
               FROM div_runsafe_answers ca
               JOIN div_runsafe_questions cq ON ca.question_id = cq.id
               WHERE ca.session_id = %s ORDER BY ca.id""",
            (session_id,)
        )
        answers = cursor.fetchall()

        # Category scores
        cursor.execute(
            "SELECT * FROM div_runsafe_category_scores WHERE session_id = %s",
            (session_id,)
        )
        category_scores = cursor.fetchall()

        return {
            "found": True,
            "session": session,
            "answers": answers,
            "category_scores": category_scores,
        }

    finally:
        cursor.close()
        conn.close()


@router.get("/staff/{identifier}/weak")
async def staff_weak_areas(identifier: str):
    """Get weak area history for a staff member."""
    hrms_id = resolve_staff_hrms_id(identifier)
    result = get_weak_history(hrms_id)
    return {"staff_hrms_id": hrms_id, **result}


@router.get("/cli/{identifier}")
async def cli_sessions(
    identifier: str,
    limit: int = Query(50, ge=1, le=200),
):
    """Get all sessions conducted by a specific CLI. Accepts CMS ID or HRMS ID."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT id, staff_hrms_id, staff_cms_id, staff_name, staff_designation,
                      test_number, category_code, total_score, total_questions,
                      percentage, grade, started_at, completed_at
               FROM div_runsafe_sessions
               WHERE cli_cms_id = %s AND status = 'completed'
               ORDER BY completed_at DESC LIMIT %s""",
            (identifier.upper(), limit)
        )
        sessions = cursor.fetchall()

        for s in sessions:
            for key in ["started_at", "completed_at"]:
                if s.get(key):
                    s[key] = s[key].isoformat()

        return {"cli_id": identifier.upper(), "sessions": sessions, "total": len(sessions)}

    finally:
        cursor.close()
        conn.close()


@router.get("/dashboard")
async def dashboard_stats():
    """Overview statistics for the counselling dashboard."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        stats = {}

        cursor.execute("SELECT COUNT(*) as count FROM div_runsafe_sessions WHERE status = 'completed'")
        stats["total_sessions"] = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) as count FROM div_runsafe_sessions WHERE status = 'active'")
        stats["active_sessions"] = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT ROUND(AVG(percentage), 1) as avg FROM div_runsafe_sessions WHERE status = 'completed'"
        )
        row = cursor.fetchone()
        stats["avg_score"] = row["avg"] if row["avg"] else 0

        cursor.execute("SELECT COUNT(*) as count FROM div_runsafe_questions WHERE active = 1")
        stats["question_count"] = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT COUNT(DISTINCT staff_hrms_id) as count FROM div_runsafe_sessions WHERE status = 'completed'"
        )
        stats["unique_staff"] = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT COUNT(*) as count FROM div_runsafe_sessions WHERE DATE(started_at) = CURDATE()"
        )
        stats["today_sessions"] = cursor.fetchone()["count"]

        cursor.execute(
            """SELECT grade, COUNT(*) as count
               FROM div_runsafe_sessions WHERE status = 'completed' AND grade IS NOT NULL
               GROUP BY grade"""
        )
        stats["grade_distribution"] = cursor.fetchall()

        return stats

    finally:
        cursor.close()
        conn.close()
