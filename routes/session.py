"""
Session Routes — Quiz Session Lifecycle

Endpoints:
  POST /api/session/start      → Create session + generate quiz
  POST /api/session/submit     → Submit answers + get results
  GET  /api/session/{id}       → Get session details
  POST /api/session/{id}/notes → Add inspector notes
  GET  /api/session/active     → List active (incomplete) sessions
"""

from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from db_config import get_db_connection
from services.quiz_engine import generate_quiz, derive_lobby_from_cms_id
from services.scoring import evaluate_answers

router = APIRouter()


# ─────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    staff_id: str          # Can be CMS ID (KYN4310) or HRMS ID
    cli_id: str            # CLI CMS ID (CSTM0027) or HRMS ID
    category: str = "all_topics"
    difficulty: str = "mixed"
    question_count: int = 15
    staff_type: str = "MAINLINE"  # MAINLINE or SUBURBAN


class SubmitAnswersRequest(BaseModel):
    session_id: int
    answers: dict[int, str]
    # {question_id: "A"/"B"/"C"/"D"}


class InspectorNotesRequest(BaseModel):
    notes: str


# ─────────────────────────────────────────────
# Staff Lookup Helpers
# ─────────────────────────────────────────────

def lookup_staff(identifier: str) -> dict | None:
    """
    Look up staff from div_staff_master by hrms_id or current_cms_id.
    Never searches original_cms_id.
    Joins designations + div_cli_master for full details.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT s.hrms_id, s.current_cms_id, s.name,
                      s.current_office_code, s.designation_id, s.current_cli_id,
                      d.designation_code, d.designation_name,
                      c.cli_id, c.cmsid AS cli_cmsid, c.cli_name, c.cli_hrms_id
               FROM div_staff_master s
               LEFT JOIN designations d ON s.designation_id = d.id
               LEFT JOIN div_cli_master c ON s.current_cli_id = c.cli_id
               WHERE s.hrms_id = %s OR s.current_cms_id = %s
               LIMIT 1""",
            (identifier.upper(), identifier.upper())
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def search_staff(query: str, mode: str = None, limit: int = 10) -> list[dict]:
    """
    Search staff by name (partial) or current_cms_id (partial numeric).
    Used for autocomplete/typeahead in the UI.
    
    mode filtering:
      - SUBURBAN → only MOTORMAN (designation_id=8)
      - MAINLINE → exclude MOTORMAN, CLI, Instructors
      - None → no filter (for report lookup)
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        q = query.strip()
        
        # Build mode filter
        mode_filter = ""
        if mode == "SUBURBAN":
            mode_filter = "AND d.designation_code = 'MOTORMAN'"
        elif mode == "MAINLINE":
            mode_filter = "AND d.designation_code NOT IN ('MOTORMAN', 'CLI', 'Jr.INST', 'Sr.INST', 'ADEE', 'TLC', 'LPC')"
        
        if q.isdigit():
            cursor.execute(
                f"""SELECT s.hrms_id, s.current_cms_id, s.name,
                          s.current_office_code,
                          d.designation_code, d.designation_name
                   FROM div_staff_master s
                   LEFT JOIN designations d ON s.designation_id = d.id
                   WHERE (s.current_cms_id LIKE %s OR s.hrms_id = %s)
                     AND s.status = 'Active' {mode_filter}
                   ORDER BY s.name LIMIT %s""",
                (f"%{q}%", q.upper(), limit)
            )
        else:
            cursor.execute(
                f"""SELECT s.hrms_id, s.current_cms_id, s.name,
                          s.current_office_code,
                          d.designation_code, d.designation_name
                   FROM div_staff_master s
                   LEFT JOIN designations d ON s.designation_id = d.id
                   WHERE (s.name LIKE %s OR s.hrms_id = %s)
                     AND s.status = 'Active' {mode_filter}
                   ORDER BY s.name LIMIT %s""",
                (f"%{q}%", q.upper(), limit)
            )
        
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def lookup_cli(identifier: str) -> dict | None:
    """
    Look up CLI/Instructor from three sources:
      1. div_cli_master → active CLIs
      2. div_staff_master → permanent Jr.INST / Sr.INST
      3. div_staff_drafting_records → drafted instructors
    Searches by cmsid or hrms_id.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Check div_cli_master first
        cursor.execute(
            """SELECT cli_id, cli_hrms_id, cmsid, cli_name, current_office_code
               FROM div_cli_master
               WHERE (cmsid = %s OR cli_hrms_id = %s)
                 AND is_active = 1
               LIMIT 1""",
            (identifier.upper(), identifier.upper())
        )
        result = cursor.fetchone()
        if result:
            return result

        # 2. Check permanent instructors in div_staff_master
        cursor.execute(
            """SELECT NULL AS cli_id, s.hrms_id AS cli_hrms_id,
                      s.current_cms_id AS cmsid, s.name AS cli_name,
                      s.current_office_code
               FROM div_staff_master s
               JOIN designations d ON s.designation_id = d.id
               WHERE (s.current_cms_id = %s OR s.hrms_id = %s)
                 AND s.status = 'Active'
                 AND d.designation_code IN ('Jr.INST', 'Sr.INST')
               LIMIT 1""",
            (identifier.upper(), identifier.upper())
        )
        result = cursor.fetchone()
        if result:
            return result

        # 3. Check drafted instructors
        cursor.execute(
            """SELECT NULL AS cli_id, s.hrms_id AS cli_hrms_id,
                      s.current_cms_id AS cmsid, s.name AS cli_name,
                      s.current_office_code
               FROM div_staff_drafting_records dr
               JOIN div_staff_master s ON dr.staff_hrms_id = s.hrms_id
               JOIN designations d ON dr.drafted_to_designation_id = d.id
               WHERE (s.current_cms_id = %s OR s.hrms_id = %s)
                 AND dr.status = 'Active'
                 AND d.designation_code IN ('Jr.INST', 'Sr.INST')
               LIMIT 1""",
            (identifier.upper(), identifier.upper())
        )
        return cursor.fetchone()

    finally:
        cursor.close()
        conn.close()


def search_cli(query: str, limit: int = 10) -> list[dict]:
    """
    Search conductors from three sources:
      1. div_cli_master → active CLIs
      2. div_staff_master → Junior Instructor / Senior Instructor designations
      3. div_staff_drafting_records → staff drafted as Jr.INST / Sr.INST (Active)

    Returns unified list with 'role' field: 'CLI', 'Jr.INST', 'Sr.INST'
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        q = query.strip()

        if q.isdigit():
            # Search by CMS ID number
            cursor.execute(
                """(SELECT cli_id, cli_hrms_id AS hrms_id, cmsid AS cms_id,
                          cli_name AS name, current_office_code AS office,
                          'CLI' AS role
                   FROM div_cli_master
                   WHERE cmsid LIKE %s AND is_active = 1)
                UNION ALL
                  (SELECT NULL AS cli_id, s.hrms_id, s.current_cms_id AS cms_id,
                          s.name, s.current_office_code AS office,
                          d.designation_code AS role
                   FROM div_staff_master s
                   JOIN designations d ON s.designation_id = d.id
                   WHERE s.current_cms_id LIKE %s AND s.status = 'Active'
                     AND d.designation_code IN ('Jr.INST', 'Sr.INST'))
                UNION ALL
                  (SELECT NULL AS cli_id, s.hrms_id, s.current_cms_id AS cms_id,
                          s.name, s.current_office_code AS office,
                          d.designation_code AS role
                   FROM div_staff_drafting_records dr
                   JOIN div_staff_master s ON dr.staff_hrms_id = s.hrms_id
                   JOIN designations d ON dr.drafted_to_designation_id = d.id
                   WHERE s.current_cms_id LIKE %s AND dr.status = 'Active'
                     AND d.designation_code IN ('Jr.INST', 'Sr.INST'))
                ORDER BY name LIMIT %s""",
                (f"%{q}%", f"%{q}%", f"%{q}%", limit)
            )
        else:
            # Search by name or HRMS ID
            cursor.execute(
                """(SELECT cli_id, cli_hrms_id AS hrms_id, cmsid AS cms_id,
                          cli_name AS name, current_office_code AS office,
                          'CLI' AS role
                   FROM div_cli_master
                   WHERE (cli_name LIKE %s OR cli_hrms_id = %s) AND is_active = 1)
                UNION ALL
                  (SELECT NULL AS cli_id, s.hrms_id, s.current_cms_id AS cms_id,
                          s.name, s.current_office_code AS office,
                          d.designation_code AS role
                   FROM div_staff_master s
                   JOIN designations d ON s.designation_id = d.id
                   WHERE (s.name LIKE %s OR s.hrms_id = %s) AND s.status = 'Active'
                     AND d.designation_code IN ('Jr.INST', 'Sr.INST'))
                UNION ALL
                  (SELECT NULL AS cli_id, s.hrms_id, s.current_cms_id AS cms_id,
                          s.name, s.current_office_code AS office,
                          d.designation_code AS role
                   FROM div_staff_drafting_records dr
                   JOIN div_staff_master s ON dr.staff_hrms_id = s.hrms_id
                   JOIN designations d ON dr.drafted_to_designation_id = d.id
                   WHERE (s.name LIKE %s OR s.hrms_id = %s) AND dr.status = 'Active'
                     AND d.designation_code IN ('Jr.INST', 'Sr.INST'))
                ORDER BY name LIMIT %s""",
                (f"%{q}%", q.upper(), f"%{q}%", q.upper(), f"%{q}%", q.upper(), limit)
            )

        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_next_test_number(staff_hrms_id: str) -> int:
    """Get the next test number for a staff member. Replaces GAS generateTestID()."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COALESCE(MAX(test_number), 0) FROM div_runsafe_sessions WHERE staff_hrms_id = %s",
            (staff_hrms_id.upper(),)
        )
        last = cursor.fetchone()[0]
        return last + 1
    finally:
        cursor.close()
        conn.close()


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.post("/start")
async def start_session(req: StartSessionRequest):
    """
    Start a new counselling session.

    1. Look up staff and CLI details
    2. Generate quiz questions
    3. Create session record
    4. Return session ID + questions (without correct answers)
    """
    # Validate
    if req.question_count < 5 or req.question_count > 30:
        raise HTTPException(status_code=400, detail="question_count must be between 5 and 30")

    # Look up staff details
    staff = lookup_staff(req.staff_id)
    if not staff:
        raise HTTPException(status_code=404, detail=f"Staff not found: {req.staff_id}")

    staff_hrms_id = staff["hrms_id"]
    staff_name = staff["name"]
    staff_cms_id = staff.get("current_cms_id")
    designation_code = staff.get("designation_code")  # from JOIN
    staff_office = staff.get("current_office_code")

    # CLI info from the staff's nominated CLI (from JOIN)
    nominated_cli_id = staff.get("current_cli_id")
    nominated_cli_name = staff.get("cli_name")
    nominated_cli_cmsid = staff.get("cli_cmsid")

    # Look up the CLI conducting this session
    cli = lookup_cli(req.cli_id)
    if not cli:
        raise HTTPException(status_code=404, detail=f"CLI not found: {req.cli_id}")

    cli_name = cli["cli_name"]
    cli_cmsid = cli.get("cmsid")
    cli_hrms_id = cli.get("cli_hrms_id")

    # Determine section group for sectional knowledge filtering
    section_group = staff_office  # simplified — can be refined

    # Get next test number
    test_number = get_next_test_number(staff_hrms_id)

    # Generate quiz
    questions = generate_quiz(
        staff_hrms_id=staff_hrms_id,
        staff_type=req.staff_type,
        category=req.category,
        designation=designation_code,
        section_group=section_group,
        difficulty=req.difficulty,
        question_count=req.question_count,
    )

    if not questions:
        raise HTTPException(status_code=404, detail="No questions found for the given criteria")

    # Create session in DB
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO div_runsafe_sessions
               (staff_hrms_id, staff_cms_id, staff_name, staff_designation,
                staff_type, staff_office,
                cli_id, cli_cms_id, cli_name,
                nominated_cli_id, nominated_cli_name,
                category_code, difficulty, question_count, test_number, total_questions)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (staff_hrms_id, staff_cms_id, staff_name, designation_code,
             req.staff_type, staff_office,
             cli_cmsid, cli_cmsid, cli_name,
             nominated_cli_cmsid, nominated_cli_name,
             req.category, req.difficulty, req.question_count, test_number, len(questions))
        )
        session_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

    # Return questions WITHOUT correct answers (for the quiz UI)
    quiz_questions = []
    for q in questions:
        quiz_questions.append({
            "id": q["id"],
            "question_text": q["question_text"],
            "option_a": q["option_a"],
            "option_b": q["option_b"],
            "option_c": q["option_c"],
            "option_d": q["option_d"],
            "category": q.get("category_code"),
            "difficulty": q.get("difficulty"),
            "is_reattempt": q.get("is_reattempt", False),
        })

    return {
        "session_id": session_id,
        "test_number": test_number,
        "staff": {
            "hrms_id": staff_hrms_id,
            "cms_id": staff_cms_id,
            "name": staff_name,
            "designation": designation_code,
            "office": staff_office,
        },
        "cli": {
            "cms_id": cli_cmsid,
            "hrms_id": cli_hrms_id,
            "name": cli_name,
        },
        "nominated_cli": {
            "cms_id": nominated_cli_cmsid,
            "name": nominated_cli_name,
        },
        "config": {
            "category": req.category,
            "difficulty": req.difficulty,
            "question_count": len(quiz_questions),
        },
        "questions": quiz_questions,
    }


@router.post("/submit")
async def submit_answers(req: SubmitAnswersRequest):
    """
    Submit quiz answers and get results.

    1. Evaluate each answer against correct answer
    2. Store results in div_runsafe_answers
    3. Calculate category scores
    4. Update session with final score/grade
    5. Return full marksheet
    """
    # Verify session exists and is active
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, status, staff_hrms_id FROM div_runsafe_sessions WHERE id = %s",
            (req.session_id,)
        )
        session = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] == "completed":
        raise HTTPException(status_code=400, detail="Session already completed")

    # Evaluate
    result = evaluate_answers(req.session_id, req.answers)

    return {
        "session_id": req.session_id,
        "total_score": result["total_score"],
        "total_questions": result["total_questions"],
        "percentage": result["percentage"],
        "grade": result["grade"],
        "category_scores": result.get("category_scores", []),
        "marksheet": result["results"],
    }


@router.get("/{session_id}")
async def get_session(session_id: int):
    """Get full session details including answers and category scores."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Session details
        cursor.execute("SELECT * FROM div_runsafe_sessions WHERE id = %s", (session_id,))
        session = cursor.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Convert datetime fields to strings
        for key in ["started_at", "completed_at"]:
            if session.get(key):
                session[key] = session[key].isoformat()

        # Answers with question text
        cursor.execute(
            """SELECT ca.*, cq.question_text, cq.category_code, cq.subcategory_code
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

        # Dev plans
        cursor.execute(
            "SELECT * FROM div_runsafe_dev_plans WHERE session_id = %s",
            (session_id,)
        )
        dev_plans = cursor.fetchall()

        return {
            "session": session,
            "answers": answers,
            "category_scores": category_scores,
            "dev_plans": dev_plans,
        }

    finally:
        cursor.close()
        conn.close()


@router.post("/{session_id}/notes")
async def add_inspector_notes(session_id: int, req: InspectorNotesRequest):
    """Add or update inspector notes for a session."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE div_runsafe_sessions SET inspector_notes = %s WHERE id = %s",
            (req.notes, session_id)
        )
        conn.commit()
        return {"success": True, "message": "Notes saved"}
    finally:
        cursor.close()
        conn.close()


@router.get("/staff/search")
async def staff_search(
    q: str = Query(..., min_length=2, description="Name or CMS ID (partial)"),
    mode: str = Query(None, description="MAINLINE or SUBURBAN — filters by designation"),
):
    """
    Search staff by name or CMS ID for autocomplete.
    
    mode filtering:
      - SUBURBAN → only Motormen
      - MAINLINE → only ALP/LPG/LPP/LPM/LPS etc.
      - (none) → all staff (for report lookup)
    """
    results = search_staff(q, mode=mode)
    return {
        "query": q,
        "results": [
            {
                "hrms_id": r["hrms_id"],
                "cms_id": r["current_cms_id"],
                "name": r["name"],
                "designation": r.get("designation_code"),
                "designation_name": r.get("designation_name"),
                "office": r.get("current_office_code"),
            }
            for r in results
        ],
        "count": len(results),
    }


@router.get("/staff/{identifier}/lookup")
async def staff_lookup_endpoint(identifier: str):
    """
    Direct staff lookup by exact current_cms_id or hrms_id.
    Returns full details including nominated CLI.
    """
    staff = lookup_staff(identifier.upper())
    if not staff:
        return {"found": False, "id": identifier.upper(), "name": None}
    return {
        "found": True,
        "hrms_id": staff["hrms_id"],
        "cms_id": staff.get("current_cms_id"),
        "name": staff["name"],
        "designation": staff.get("designation_code"),
        "designation_name": staff.get("designation_name"),
        "office": staff.get("current_office_code"),
        "nominated_cli": staff.get("cli_name"),
        "nominated_cli_cmsid": staff.get("cli_cmsid"),
    }


@router.get("/cli/search")
async def cli_search_endpoint(q: str = Query(..., min_length=2, description="CLI name or CMS ID (partial)")):
    """
    Search CLI + Instructors for autocomplete.
    
    Sources:
      - div_cli_master → active CLIs (role: 'CLI')
      - div_staff_master → Jr/Sr Instructors (role: 'JR.INSTR' / 'SR.INSTR')
    
    Examples:
      /api/session/cli/search?q=Vinod
      /api/session/cli/search?q=0027
    """
    results = search_cli(q)
    return {
        "query": q,
        "results": [
            {
                "cli_id": r.get("cli_id"),
                "hrms_id": r.get("hrms_id"),
                "cms_id": r.get("cms_id"),
                "name": r["name"],
                "office": r.get("office"),
                "role": r.get("role", "CLI"),
            }
            for r in results
        ],
        "count": len(results),
    }
