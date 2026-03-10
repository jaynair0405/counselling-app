"""
Question Bank Routes — CRUD for managing questions

Endpoints:
  GET    /api/questions/          → List questions (with filters)
  GET    /api/questions/{id}      → Get single question
  POST   /api/questions/          → Add new question
  PUT    /api/questions/{id}      → Update question
  DELETE /api/questions/{id}      → Soft-delete question (set active=0)
  GET    /api/questions/stats     → Question bank statistics
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from db_config import get_db_connection

router = APIRouter()


# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────

class QuestionCreate(BaseModel):
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str  # A, B, C, D
    staff_type: str = "COMMON"
    category_code: str
    subcategory_code: Optional[str] = None
    difficulty: str = "medium"
    section_group: Optional[str] = None
    targeted_desg: Optional[list[str]] = None
    created_by: Optional[str] = None


class QuestionUpdate(BaseModel):
    question_text: Optional[str] = None
    option_a: Optional[str] = None
    option_b: Optional[str] = None
    option_c: Optional[str] = None
    option_d: Optional[str] = None
    correct_option: Optional[str] = None
    staff_type: Optional[str] = None
    category_code: Optional[str] = None
    subcategory_code: Optional[str] = None
    difficulty: Optional[str] = None
    section_group: Optional[str] = None
    targeted_desg: Optional[list[str]] = None


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.get("/stats")
async def question_stats():
    """Get question bank statistics — counts by category, difficulty, staff_type."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Total active
        cursor.execute("SELECT COUNT(*) as total FROM div_runsafe_questions WHERE active = 1")
        total = cursor.fetchone()["total"]

        # By category
        cursor.execute(
            """SELECT category_code, COUNT(*) as count
               FROM div_runsafe_questions WHERE active = 1
               GROUP BY category_code ORDER BY count DESC"""
        )
        by_category = cursor.fetchall()

        # By difficulty
        cursor.execute(
            """SELECT difficulty, COUNT(*) as count
               FROM div_runsafe_questions WHERE active = 1
               GROUP BY difficulty"""
        )
        by_difficulty = cursor.fetchall()

        # By staff_type
        cursor.execute(
            """SELECT staff_type, COUNT(*) as count
               FROM div_runsafe_questions WHERE active = 1
               GROUP BY staff_type"""
        )
        by_staff_type = cursor.fetchall()

        return {
            "total_active": total,
            "by_category": by_category,
            "by_difficulty": by_difficulty,
            "by_staff_type": by_staff_type,
        }

    finally:
        cursor.close()
        conn.close()


@router.get("/")
async def list_questions(
    category: Optional[str] = None,
    staff_type: Optional[str] = None,
    difficulty: Optional[str] = None,
    subcategory: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
):
    """List questions with optional filters and pagination."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        sql = "SELECT * FROM div_runsafe_questions WHERE active = 1"
        count_sql = "SELECT COUNT(*) as total FROM div_runsafe_questions WHERE active = 1"
        params = []

        if category:
            sql += " AND category_code = %s"
            count_sql += " AND category_code = %s"
            params.append(category)
        if staff_type:
            sql += " AND staff_type = %s"
            count_sql += " AND staff_type = %s"
            params.append(staff_type)
        if difficulty:
            sql += " AND difficulty = %s"
            count_sql += " AND difficulty = %s"
            params.append(difficulty)
        if subcategory:
            sql += " AND subcategory_code = %s"
            count_sql += " AND subcategory_code = %s"
            params.append(subcategory)
        if search:
            sql += " AND question_text LIKE %s"
            count_sql += " AND question_text LIKE %s"
            params.append(f"%{search}%")

        # Count
        cursor.execute(count_sql, params)
        total = cursor.fetchone()["total"]

        # Paginate
        offset = (page - 1) * per_page
        sql += " ORDER BY id DESC LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        cursor.execute(sql, params)
        questions = cursor.fetchall()

        # Convert datetime fields
        for q in questions:
            for key in ["created_at", "updated_at"]:
                if q.get(key):
                    q[key] = q[key].isoformat()

        return {
            "questions": questions,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        }

    finally:
        cursor.close()
        conn.close()


@router.get("/{question_id}")
async def get_question(question_id: int):
    """Get a single question by ID."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM div_runsafe_questions WHERE id = %s", (question_id,))
        q = cursor.fetchone()
        if not q:
            raise HTTPException(status_code=404, detail="Question not found")
        for key in ["created_at", "updated_at"]:
            if q.get(key):
                q[key] = q[key].isoformat()
        return q
    finally:
        cursor.close()
        conn.close()


@router.post("/")
async def create_question(req: QuestionCreate):
    """Add a new question to the bank."""
    import json

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        targeted_json = json.dumps(req.targeted_desg) if req.targeted_desg else None

        cursor.execute(
            """INSERT INTO div_runsafe_questions
               (question_text, option_a, option_b, option_c, option_d, correct_option,
                staff_type, category_code, subcategory_code, difficulty, section_group,
                targeted_desg, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (req.question_text, req.option_a, req.option_b, req.option_c, req.option_d,
             req.correct_option.upper(), req.staff_type, req.category_code, req.subcategory_code,
             req.difficulty, req.section_group, targeted_json, req.created_by)
        )
        conn.commit()
        new_id = cursor.lastrowid

        return {"success": True, "id": new_id, "message": "Question added"}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@router.put("/{question_id}")
async def update_question(question_id: int, req: QuestionUpdate):
    """Update an existing question."""
    import json

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Build dynamic UPDATE
        fields = []
        params = []

        update_map = {
            "question_text": req.question_text,
            "option_a": req.option_a,
            "option_b": req.option_b,
            "option_c": req.option_c,
            "option_d": req.option_d,
            "correct_option": req.correct_option.upper() if req.correct_option else None,
            "staff_type": req.staff_type,
            "category_code": req.category_code,
            "subcategory_code": req.subcategory_code,
            "difficulty": req.difficulty,
            "section_group": req.section_group,
        }

        for col, val in update_map.items():
            if val is not None:
                fields.append(f"{col} = %s")
                params.append(val)

        if req.targeted_desg is not None:
            fields.append("targeted_desg = %s")
            params.append(json.dumps(req.targeted_desg))

        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")

        params.append(question_id)
        cursor.execute(
            f"UPDATE div_runsafe_questions SET {', '.join(fields)} WHERE id = %s",
            params
        )
        conn.commit()

        return {"success": True, "message": "Question updated"}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@router.delete("/{question_id}")
async def delete_question(question_id: int):
    """Soft-delete a question (set active=0). Does not remove from DB."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE div_runsafe_questions SET active = 0 WHERE id = %s",
            (question_id,)
        )
        conn.commit()
        return {"success": True, "message": "Question deactivated"}
    finally:
        cursor.close()
        conn.close()


@router.get("/subcategories/list")
async def list_subcategories(category: Optional[str] = None):
    """Get distinct subcategories, optionally filtered by category."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        sql = """SELECT DISTINCT category_code, subcategory_code, COUNT(*) as count
                 FROM div_runsafe_questions WHERE active = 1 AND subcategory_code IS NOT NULL"""
        params = []
        if category:
            sql += " AND category_code = %s"
            params.append(category)
        sql += " GROUP BY category_code, subcategory_code ORDER BY category_code, subcategory_code"

        cursor.execute(sql, params)
        return {"subcategories": cursor.fetchall()}
    finally:
        cursor.close()
        conn.close()
