"""
Reports Routes — Session report generation

Endpoints:
  GET  /api/reports/session/{id}        → Full report data for a session (JSON for UI rendering)
  POST /api/reports/session/{id}/dev-plan → Add development plan items
  GET  /api/reports/staff/{cms_id}/summary → Staff-level summary across all sessions
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db_config import get_db_connection
from services.scoring import get_weak_history

router = APIRouter()


class DevPlanItem(BaseModel):
    subcategory: str
    action_text: str


class AddDevPlanRequest(BaseModel):
    items: list[DevPlanItem]


@router.get("/session/{session_id}")
async def session_report(session_id: int):
    """
    Get full report data for a counselling session.
    Returns all data needed to render the report HTML template.

    This replaces GAS:
    - reportHeaderDatas()
    - sendMarkSheetToReports()
    - pasteDataToReportsSheet()
    - createCurrentTestReports()
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # ── Session details ──
        cursor.execute("SELECT * FROM div_runsafe_sessions WHERE id = %s", (session_id,))
        session = cursor.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        for key in ["started_at", "completed_at"]:
            if session.get(key):
                session[key] = session[key].isoformat()

        # ── Marksheet (answers with question text) ──
        cursor.execute(
            """SELECT ca.question_id, cq.question_text,
                      ca.submitted_answer, ca.submitted_answer_text,
                      ca.correct_answer, ca.correct_answer_text,
                      ca.is_correct, ca.is_reattempt,
                      cq.category_code, cq.subcategory_code, cq.difficulty
               FROM div_runsafe_answers ca
               JOIN div_runsafe_questions cq ON ca.question_id = cq.id
               WHERE ca.session_id = %s ORDER BY ca.id""",
            (session_id,)
        )
        marksheet = cursor.fetchall()

        # ── Category/subcategory score breakdown ──
        cursor.execute(
            """SELECT category, subcategory, question_count, score, percentage, assessment
               FROM div_runsafe_category_scores WHERE session_id = %s
               ORDER BY category, subcategory""",
            (session_id,)
        )
        category_scores = cursor.fetchall()

        # ── Counselling history (all past sessions for this staff) ──
        staff_id = session["staff_hrms_id"]
        cursor.execute(
            """SELECT test_number, category_code, total_score, total_questions,
                      percentage, grade, started_at
               FROM div_runsafe_sessions
               WHERE staff_hrms_id = %s AND status = 'completed'
               ORDER BY test_number""",
            (staff_id,)
        )
        history = cursor.fetchall()
        for h in history:
            if h.get("started_at"):
                h["started_at"] = h["started_at"].isoformat()

        # ── Weak area history ──
        weak_data = get_weak_history(staff_id)

        # ── Development plans ──
        cursor.execute(
            """SELECT subcategory, action_text, status
               FROM div_runsafe_dev_plans WHERE session_id = %s""",
            (session_id,)
        )
        dev_plans = cursor.fetchall()

        # ── Previous wrong questions (for the "wrongly answered previously" line) ──
        wrong_reattempts = [m for m in marksheet if m.get("is_reattempt")]

        # ── Duration formatting ──
        duration_str = ""
        if session.get("duration_seconds"):
            mins = session["duration_seconds"] // 60
            secs = session["duration_seconds"] % 60
            duration_str = f"{mins}m {secs}s"

        return {
            "session": session,
            "marksheet": marksheet,
            "category_scores": category_scores,
            "history": history,
            "weak_history": weak_data["weak"],
            "development_areas": weak_data["development"],
            "dev_plans": dev_plans,
            "previous_wrong_reattempts": len(wrong_reattempts),
            "duration_formatted": duration_str,
            "summary": {
                "total_questions": session["total_questions"],
                "total_score": session["total_score"],
                "percentage": float(session["percentage"]) if session["percentage"] else 0,
                "grade": session["grade"],
                "correct": session["total_score"],
                "incorrect": (session["total_questions"] or 0) - (session["total_score"] or 0),
                "category_mix": ", ".join(
                    sorted(set(
                        cs["subcategory"] or cs["category"]
                        for cs in category_scores
                    ))
                ),
            },
        }

    finally:
        cursor.close()
        conn.close()


@router.post("/session/{session_id}/dev-plan")
async def add_dev_plan(session_id: int, req: AddDevPlanRequest):
    """
    Add development plan items to a session.
    CLI fills these in during or after counselling.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Get staff_hrms_id from session
        cursor.execute("SELECT staff_hrms_id FROM div_runsafe_sessions WHERE id = %s", (session_id,))
        session = cursor.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        for item in req.items:
            cursor.execute(
                """INSERT INTO div_runsafe_dev_plans
                   (session_id, staff_hrms_id, subcategory, action_text)
                   VALUES (%s, %s, %s, %s)""",
                (session_id, session["staff_hrms_id"], item.subcategory, item.action_text)
            )

        conn.commit()
        return {"success": True, "message": f"{len(req.items)} dev plan items added"}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@router.get("/staff/{identifier}/summary")
async def staff_summary(identifier: str):
    """
    Staff-level summary across all sessions.
    Shows trends, overall weak areas, improvement over time.
    Accepts CMS ID or HRMS ID.
    """
    from routes.history import resolve_staff_hrms_id
    hrms_id = resolve_staff_hrms_id(identifier)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Total sessions
        cursor.execute(
            "SELECT COUNT(*) as count FROM div_runsafe_sessions WHERE staff_hrms_id = %s AND status = 'completed'",
            (hrms_id,)
        )
        total = cursor.fetchone()["count"]

        # Average score trend (last 10 sessions)
        cursor.execute(
            """SELECT test_number, percentage, grade, category_code,
                      DATE_FORMAT(completed_at, '%%d/%%m/%%Y') as date
               FROM div_runsafe_sessions
               WHERE staff_hrms_id = %s AND status = 'completed'
               ORDER BY test_number DESC LIMIT 10""",
            (hrms_id,)
        )
        recent = cursor.fetchall()

        # Overall average
        cursor.execute(
            "SELECT ROUND(AVG(percentage), 1) as avg FROM div_runsafe_sessions WHERE staff_hrms_id = %s AND status = 'completed'",
            (hrms_id,)
        )
        avg_row = cursor.fetchone()
        overall_avg = avg_row["avg"] if avg_row["avg"] else 0

        # Persistent weak areas (appearing in >= 2 sessions)
        cursor.execute(
            """SELECT cs.subcategory, COUNT(*) as occurrences,
                      ROUND(AVG(cs.percentage), 1) as avg_pct
               FROM div_runsafe_category_scores cs
               JOIN div_runsafe_sessions s ON cs.session_id = s.id
               WHERE s.staff_hrms_id = %s AND s.status = 'completed'
                 AND cs.assessment IN ('Weak', 'Development Area')
               GROUP BY cs.subcategory
               HAVING COUNT(*) >= 2
               ORDER BY occurrences DESC""",
            (hrms_id,)
        )
        persistent_weak = cursor.fetchall()

        # Pending dev plan items
        cursor.execute(
            """SELECT dp.subcategory, dp.action_text, dp.status,
                      DATE_FORMAT(dp.created_at, '%%d/%%m/%%Y') as date
               FROM div_runsafe_dev_plans dp
               WHERE dp.staff_hrms_id = %s AND dp.status != 'completed'
               ORDER BY dp.created_at DESC""",
            (hrms_id,)
        )
        pending_actions = cursor.fetchall()

        return {
            "staff_hrms_id": hrms_id,
            "total_sessions": total,
            "overall_avg_percentage": overall_avg,
            "recent_sessions": list(reversed(recent)),
            "persistent_weak_areas": persistent_weak,
            "pending_dev_actions": pending_actions,
        }

    finally:
        cursor.close()
        conn.close()
