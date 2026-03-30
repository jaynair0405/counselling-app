"""
Scoring Engine — Answer Evaluation & Category Scoring

Replaces GAS functions:
- answerEvaluator()
- calculateCategoryScores()
- calculateSubcategoryScores()
- combineTestScoresWithSubcategory()
- assessCategory()
- weakHistoryMapping()
"""

import mysql.connector
from mysql.connector import errorcode
from fastapi import HTTPException

from db_config import get_db_connection
from services.quiz_engine import get_assessment


def evaluate_answers(session_id: int, answers: dict[int, str]) -> dict:
    """
    Evaluate submitted answers against correct answers.

    Args:
        session_id: The counselling session ID
        answers: Dict of {question_id: selected_option} e.g., {32: "A", 246: "C"}

    Returns:
        Dict with total_score, total_questions, percentage, grade, results list
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            """SELECT id, status, staff_hrms_id
               FROM div_runsafe_sessions
               WHERE id = %s
               FOR UPDATE""",
            (session_id,)
        )
        session = cursor.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if session["status"] == "completed":
            raise HTTPException(status_code=409, detail="Session already completed")
        if session["status"] != "active":
            raise HTTPException(status_code=400, detail=f"Session is not active: {session['status']}")

        # Fetch the pre-assigned questions for this session. These rows are created
        # at session start, making the DB the source of truth for what was asked.
        question_ids = list(answers.keys())
        if not question_ids:
            raise HTTPException(status_code=400, detail="No answers submitted")

        cursor.execute(
            """SELECT ca.question_id, ca.correct_answer, ca.correct_answer_text, ca.is_reattempt,
                      cq.question_text, cq.option_a, cq.option_b, cq.option_c, cq.option_d,
                      cq.category_code, cq.subcategory_code
               FROM div_runsafe_answers ca
               JOIN div_runsafe_questions cq ON ca.question_id = cq.id
               WHERE ca.session_id = %s
               ORDER BY ca.id""",
            (session_id,)
        )
        assigned_questions = cursor.fetchall()
        if not assigned_questions:
            raise HTTPException(status_code=400, detail="No assigned questions found for session")

        assigned_ids = {q["question_id"] for q in assigned_questions}
        submitted_ids = set(question_ids)
        if submitted_ids != assigned_ids:
            missing = sorted(assigned_ids - submitted_ids)
            extra = sorted(submitted_ids - assigned_ids)
            parts = []
            if missing:
                preview = ", ".join(str(qid) for qid in missing[:5])
                suffix = "..." if len(missing) > 5 else ""
                parts.append(f"missing question IDs: {preview}{suffix}")
            if extra:
                preview = ", ".join(str(qid) for qid in extra[:5])
                suffix = "..." if len(extra) > 5 else ""
                parts.append(f"unexpected question IDs: {preview}{suffix}")
            raise HTTPException(
                status_code=400,
                detail=f"Submission does not match assigned session questions ({'; '.join(parts)})"
            )

        total_score = 0
        results = []
        valid_options = {"A", "B", "C", "D"}

        for q in assigned_questions:
            qid = q["question_id"]
            submitted_option = answers[qid].upper()
            if submitted_option not in valid_options:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid answer option for question {qid}: {submitted_option}"
                )

            correct_option = q["correct_answer"]
            is_correct = 1 if submitted_option == correct_option else 0
            total_score += is_correct

            # Get actual text of submitted and correct answers
            option_map = {"A": q["option_a"], "B": q["option_b"], "C": q["option_c"], "D": q["option_d"]}
            submitted_text = option_map.get(submitted_option, "")
            correct_text = q.get("correct_answer_text") or option_map.get(correct_option, "")

            # Update the pre-created answer record instead of inserting a new one.
            cursor.execute(
                """UPDATE div_runsafe_answers
                   SET submitted_answer = %s,
                       submitted_answer_text = %s,
                       is_correct = %s
                   WHERE session_id = %s AND question_id = %s""",
                (submitted_option, submitted_text, is_correct, session_id, qid)
            )
            if cursor.rowcount != 1:
                raise HTTPException(status_code=409, detail=f"Failed to update answer row for question {qid}")

            results.append({
                "question_id": qid,
                "question_text": q["question_text"],
                "submitted_answer": submitted_option,
                "submitted_answer_text": submitted_text,
                "correct_answer": correct_option,
                "correct_answer_text": correct_text,
                "is_correct": is_correct,
                "category": q["category_code"],
                "subcategory": q["subcategory_code"],
                "is_reattempt": q["is_reattempt"],
            })

        total_questions = len(assigned_questions)
        percentage = round((total_score / total_questions) * 100, 2) if total_questions > 0 else 0
        grade = get_assessment(percentage)

        # Update session with scores
        cursor.execute(
            """UPDATE div_runsafe_sessions
               SET total_score = %s, total_questions = %s, percentage = %s,
                   grade = %s, status = 'completed', completed_at = NOW(),
                   duration_seconds = TIMESTAMPDIFF(SECOND, started_at, NOW())
               WHERE id = %s AND status = 'active'""",
            (total_score, total_questions, percentage, grade, session_id)
        )
        if cursor.rowcount != 1:
            raise HTTPException(status_code=409, detail="Session was updated by another request")

        # Calculate and store category/subcategory scores
        category_scores = _store_category_scores(cursor, session_id, results)

        conn.commit()

        return {
            "total_score": total_score,
            "total_questions": total_questions,
            "percentage": percentage,
            "grade": grade,
            "results": results,
            "category_scores": category_scores,
        }

    except HTTPException:
        conn.rollback()
        raise
    except mysql.connector.IntegrityError as e:
        conn.rollback()
        if e.errno == errorcode.ER_DUP_ENTRY:
            raise HTTPException(status_code=409, detail="Duplicate submission detected")
        raise e
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()


def _store_category_scores(cursor, session_id: int, results: list[dict]) -> list[dict]:
    """
    Calculate and store per-category and per-subcategory scores.
    Replaces GAS combineTestScoresWithSubcategory().
    Returns list of category score dicts for the API response.
    """
    # Group by category + subcategory
    groups = {}
    for r in results:
        cat = r["category"] or "unknown"
        sub = r["subcategory"] or "General"
        key = (cat, sub)
        if key not in groups:
            groups[key] = {"score": 0, "count": 0}
        groups[key]["score"] += r["is_correct"]
        groups[key]["count"] += 1

    category_scores = []
    for (cat, sub), data in groups.items():
        pct = round((data["score"] / data["count"]) * 100, 2) if data["count"] > 0 else 0
        assessment = get_assessment(pct)

        cursor.execute(
            """INSERT INTO div_runsafe_category_scores
               (session_id, category, subcategory, question_count, score, percentage, assessment)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (session_id, cat, sub, data["count"], data["score"], pct, assessment)
        )

        category_scores.append({
            "category": cat,
            "subcategory": sub,
            "question_count": data["count"],
            "score": data["score"],
            "percentage": pct,
            "assessment": assessment,
        })

    return category_scores


def get_weak_history(staff_hrms_id: str, limit: int = 3) -> dict:
    """
    Get weak areas and development areas from recent sessions.
    Replaces GAS weakHistoryMapping().

    Returns: {"weak": [...], "development": [...]}
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        sql = """
            SELECT cs.session_id, s.test_number, cs.category, cs.subcategory,
                   cs.score, cs.question_count, cs.percentage, cs.assessment
            FROM div_runsafe_category_scores cs
            JOIN div_runsafe_sessions s ON cs.session_id = s.id
            WHERE s.staff_hrms_id = %s AND s.status = 'completed'
            ORDER BY s.completed_at DESC
        """
        cursor.execute(sql, (staff_hrms_id,))
        all_scores = cursor.fetchall()

        weak = [s for s in all_scores if s["assessment"] == "Weak"][:limit]
        development = [s for s in all_scores if s["assessment"] == "Development Area"][:limit]

        return {"weak": weak, "development": development}

    finally:
        cursor.close()
        conn.close()
