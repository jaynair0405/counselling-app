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
        # Fetch the questions for this session (from the quiz that was generated)
        question_ids = list(answers.keys())
        if not question_ids:
            return {"total_score": 0, "total_questions": 0, "percentage": 0, "grade": "Weak", "results": []}

        placeholders = ",".join(["%s"] * len(question_ids))
        cursor.execute(
            f"""SELECT id, question_text, option_a, option_b, option_c, option_d,
                       correct_option, category_code, subcategory_code
                FROM div_runsafe_questions WHERE id IN ({placeholders})""",
            question_ids
        )
        questions_map = {q["id"]: q for q in cursor.fetchall()}

        total_score = 0
        results = []

        for qid, submitted_option in answers.items():
            q = questions_map.get(qid)
            if not q:
                continue

            correct_option = q["correct_option"]
            is_correct = 1 if submitted_option.upper() == correct_option else 0
            total_score += is_correct

            # Get actual text of submitted and correct answers
            option_map = {"A": q["option_a"], "B": q["option_b"], "C": q["option_c"], "D": q["option_d"]}
            submitted_text = option_map.get(submitted_option.upper(), "")
            correct_text = option_map.get(correct_option, "")

            # Check if this was a reattempt
            cursor.execute(
                """SELECT COUNT(*) as cnt FROM div_runsafe_answers ca
                   JOIN div_runsafe_sessions cs ON ca.session_id = cs.id
                   WHERE cs.staff_hrms_id = (SELECT staff_hrms_id FROM div_runsafe_sessions WHERE id = %s)
                     AND ca.question_id = %s AND ca.is_correct = 0
                     AND ca.session_id != %s""",
                (session_id, qid, session_id)
            )
            is_reattempt = cursor.fetchone()["cnt"] > 0

            # Insert answer record
            cursor.execute(
                """INSERT INTO div_runsafe_answers
                   (session_id, question_id, submitted_answer, correct_answer,
                    is_correct, submitted_answer_text, correct_answer_text, is_reattempt)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (session_id, qid, submitted_option.upper(), correct_option,
                 is_correct, submitted_text, correct_text, is_reattempt)
            )

            results.append({
                "question_id": qid,
                "question_text": q["question_text"],
                "submitted_answer": submitted_option.upper(),
                "submitted_answer_text": submitted_text,
                "correct_answer": correct_option,
                "correct_answer_text": correct_text,
                "is_correct": is_correct,
                "category": q["category_code"],
                "subcategory": q["subcategory_code"],
            })

        total_questions = len(results)
        percentage = round((total_score / total_questions) * 100, 2) if total_questions > 0 else 0
        grade = get_assessment(percentage)

        # Update session with scores
        cursor.execute(
            """UPDATE div_runsafe_sessions
               SET total_score = %s, total_questions = %s, percentage = %s,
                   grade = %s, status = 'completed', completed_at = NOW(),
                   duration_seconds = TIMESTAMPDIFF(SECOND, started_at, NOW())
               WHERE id = %s""",
            (total_score, total_questions, percentage, grade, session_id)
        )

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
