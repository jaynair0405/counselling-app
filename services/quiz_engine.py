"""
Quiz Engine — Question Selection & Assembly

Replaces the GAS functions:
- createFinalQuestionnaire()
- getCategory1Questions() through getCategory5Questions()
- combineQuestions()
- filterQuestionBankData()
- getLatestTestAttemptWithWrongAndRightAnswers()

Core logic:
1. Fetch eligible questions based on staff_type, category, designation, section
2. Exclude questions the staff answered correctly in their last session
3. Re-include questions they got wrong last time
4. Fill remaining slots with fresh questions, weighted by category
5. Shuffle and return
"""

import random
from typing import Optional
from db_config import get_db_connection


# ─────────────────────────────────────────────
# Category distribution for "all_topics" mode
# ─────────────────────────────────────────────
CATEGORY_WEIGHTS_MAINLINE = {
    "traffic_rules": 0.35,
    "electric_loco": 0.35,
    "diesel_loco": 0.30,
}

CATEGORY_WEIGHTS_SUBURBAN = {
    "emu": 0.70,
    "traffic_rules": 0.30,
}

# Assessment thresholds (percentage)
ASSESSMENT_THRESHOLDS = {
    "Proficient": 70,        # >= 70%
    "Development Area": 40,  # >= 40%
    "Weak": 0,               # < 40%
}


def get_assessment(percentage: float) -> str:
    """Determine assessment grade from percentage."""
    if percentage >= ASSESSMENT_THRESHOLDS["Proficient"]:
        return "Proficient"
    elif percentage >= ASSESSMENT_THRESHOLDS["Development Area"]:
        return "Development Area"
    else:
        return "Weak"


def derive_lobby_from_cms_id(cms_id: str) -> Optional[str]:
    """
    Extract lobby/office from CMS ID prefix.
    Replaces GAS getLobbyAndDesg() function.
    e.g., KYN4310 → KYN, CSMT5263 → CSMT, PNVL1234 → PNVL
    """
    if not cms_id:
        return None
    prefix = "".join(c for c in cms_id if c.isalpha()).upper()
    lobby_map = {
        "CSMT": "CSMT", "CSTM": "CSMT", "CSTS": "CSMT",
        "KYN": "KYN", "KYNS": "KYN",
        "PNVL": "PNVL", "PNVS": "PNVL",
        "BVT": "BVT",
        "IGP": "IGP",
        "LNL": "LNL", "LNLX": "LNL",
    }
    return lobby_map.get(prefix, prefix)


def get_previous_wrong_question_ids(staff_hrms_id: str, category: Optional[str] = None) -> list[int]:
    """
    Get question IDs that the staff answered incorrectly in their latest session.
    These will be re-included in the next quiz.
    Replaces GAS getLatestTestAttemptWithWrongAndRightAnswers().
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Find the latest completed session
        session_sql = """
            SELECT id FROM div_runsafe_sessions
            WHERE staff_hrms_id = %s AND status = 'completed'
            ORDER BY completed_at DESC LIMIT 1
        """
        cursor.execute(session_sql, (staff_hrms_id,))
        row = cursor.fetchone()
        if not row:
            return []

        last_session_id = row[0]

        # Get wrong answers from that session
        wrong_sql = """
            SELECT ca.question_id
            FROM div_runsafe_answers ca
            JOIN div_runsafe_questions cq ON ca.question_id = cq.id
            WHERE ca.session_id = %s AND ca.is_correct = 0
        """
        params = [last_session_id]

        if category and category != "all_topics":
            wrong_sql += " AND cq.category_code = %s"
            params.append(category)

        cursor.execute(wrong_sql, params)
        return [r[0] for r in cursor.fetchall()]

    finally:
        cursor.close()
        conn.close()


def get_previous_correct_question_ids(staff_hrms_id: str) -> set[int]:
    """
    Get question IDs that the staff answered correctly in their latest session.
    These are excluded from the fresh question pool.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        session_sql = """
            SELECT id FROM div_runsafe_sessions
            WHERE staff_hrms_id = %s AND status = 'completed'
            ORDER BY completed_at DESC LIMIT 1
        """
        cursor.execute(session_sql, (staff_hrms_id,))
        row = cursor.fetchone()
        if not row:
            return set()

        last_session_id = row[0]

        correct_sql = """
            SELECT question_id FROM div_runsafe_answers
            WHERE session_id = %s AND is_correct = 1
        """
        cursor.execute(correct_sql, (last_session_id,))
        return {r[0] for r in cursor.fetchall()}

    finally:
        cursor.close()
        conn.close()


def fetch_eligible_questions(
    staff_type: str,
    category: Optional[str],
    designation: Optional[str] = None,
    section_group: Optional[str] = None,
    difficulty: Optional[str] = None,
    exclude_ids: set[int] = None,
    staff_hrms_id: Optional[str] = None,
) -> list[dict]:
    """
    Fetch questions from the bank matching the given filters.
    Replaces GAS getCategory*Questions() functions.

    If staff_hrms_id is provided, questions are ordered by:
      1. times_asked ASC (least asked to this staff first)
      2. last_asked ASC NULLS FIRST (never asked or oldest first)

    Returns list of dicts: [{id, question_text, option_a, ..., category, subcategory, ...}]
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        if staff_hrms_id:
            # Prioritized query: least asked and oldest questions first
            sql = """
                SELECT q.id, q.question_text, q.option_a, q.option_b, q.option_c, q.option_d,
                       q.correct_option, q.category_code, q.subcategory_code, q.difficulty,
                       q.staff_type, q.section_group, q.targeted_desg,
                       COUNT(a.id) as times_asked,
                       MAX(sess.started_at) as last_asked
                FROM div_runsafe_questions q
                LEFT JOIN div_runsafe_answers a ON q.id = a.question_id
                LEFT JOIN div_runsafe_sessions sess ON a.session_id = sess.id
                    AND sess.staff_hrms_id = %s
                WHERE q.active = 1
                  AND q.staff_type IN (%s, 'COMMON')
            """
            params = [staff_hrms_id, staff_type]
        else:
            sql = """
                SELECT id, question_text, option_a, option_b, option_c, option_d,
                       correct_option, category_code, subcategory_code, difficulty,
                       staff_type, section_group, targeted_desg
                FROM div_runsafe_questions
                WHERE active = 1
                  AND staff_type IN (%s, 'COMMON')
            """
            params = [staff_type]

        if category and category != "all_topics":
            sql += " AND category_code = %s" if not staff_hrms_id else " AND q.category_code = %s"
            params.append(category)

        if difficulty and difficulty != "mixed":
            sql += " AND difficulty = %s" if not staff_hrms_id else " AND q.difficulty = %s"
            params.append(difficulty)

        if section_group:
            col = "section_group" if not staff_hrms_id else "q.section_group"
            sql += f" AND ({col} IS NULL OR {col} = %s)"
            params.append(section_group)

        if exclude_ids:
            placeholders = ",".join(["%s"] * len(exclude_ids))
            col = "id" if not staff_hrms_id else "q.id"
            sql += f" AND {col} NOT IN ({placeholders})"
            params.extend(exclude_ids)

        if staff_hrms_id:
            # Group by question and order by priority
            sql += " GROUP BY q.id ORDER BY times_asked ASC, last_asked ASC"

        cursor.execute(sql, params)
        questions = cursor.fetchall()

        # Filter by targeted designation (JSON column)
        if designation:
            filtered = []
            for q in questions:
                targeted = q.get("targeted_desg")
                if targeted is None:
                    # NULL means all designations
                    filtered.append(q)
                elif isinstance(targeted, list) and designation in targeted:
                    filtered.append(q)
                elif isinstance(targeted, str):
                    # Handle case where JSON wasn't auto-parsed
                    import json
                    try:
                        desg_list = json.loads(targeted)
                        if designation in desg_list:
                            filtered.append(q)
                    except (json.JSONDecodeError, TypeError):
                        filtered.append(q)
            questions = filtered

        return questions

    finally:
        cursor.close()
        conn.close()


def generate_quiz(
    staff_hrms_id: str,
    staff_type: str = "MAINLINE",
    category: str = "all_topics",
    designation: str = None,
    section_group: str = None,
    difficulty: str = "mixed",
    question_count: int = 15,
) -> list[dict]:
    """
    Generate a quiz for the given staff member.

    Logic:
    1. Get wrong answers from last session → re-include them (reattempts)
    2. Fetch fresh questions prioritized by:
       - Least asked to this staff (never asked first)
       - Oldest asked (if same count)
    3. If all_topics: distribute by category weights
    4. If single category: just pick from that category
    5. Combine reattempts + fresh questions up to question_count
    6. Shuffle and return

    Returns list of question dicts ready for the quiz UI.
    """
    # Step 1: Previous wrong answers (to re-include as reattempts)
    wrong_ids = get_previous_wrong_question_ids(staff_hrms_id, category)

    # Step 2: Fetch wrong questions full data
    reattempt_questions = []
    if wrong_ids:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            placeholders = ",".join(["%s"] * len(wrong_ids))
            cursor.execute(
                f"""SELECT id, question_text, option_a, option_b, option_c, option_d,
                           correct_option, category_code, subcategory_code, difficulty
                    FROM div_runsafe_questions
                    WHERE id IN ({placeholders}) AND active = 1""",
                wrong_ids
            )
            reattempt_questions = cursor.fetchall()
            for q in reattempt_questions:
                q["is_reattempt"] = True
        finally:
            cursor.close()
            conn.close()

    # Cap reattempts at question_count
    reattempt_questions = reattempt_questions[:question_count]
    reattempt_ids = {q["id"] for q in reattempt_questions}

    # Remaining slots
    remaining_needed = question_count - len(reattempt_questions)
    if remaining_needed <= 0:
        random.shuffle(reattempt_questions)
        return reattempt_questions[:question_count]

    # Step 3: Exclude only reattempt IDs from fresh pool (to avoid duplicates)
    exclude_ids = reattempt_ids

    # Step 4: Fetch fresh questions (prioritized: least asked, oldest first)
    if category == "all_topics":
        # Pick weights based on staff type
        weights = CATEGORY_WEIGHTS_SUBURBAN if staff_type == "SUBURBAN" else CATEGORY_WEIGHTS_MAINLINE

        # Distribute across categories by weight, ensuring total = remaining_needed
        fresh_questions = []
        cat_counts = {}
        for cat, weight in weights.items():
            cat_counts[cat] = max(1, round(remaining_needed * weight))

        # Fix rounding: adjust largest category to fill any gap
        total_assigned = sum(cat_counts.values())
        if total_assigned != remaining_needed:
            largest_cat = max(cat_counts, key=cat_counts.get)
            cat_counts[largest_cat] += remaining_needed - total_assigned

        for cat, cat_count in cat_counts.items():
            # Fetch prioritized by least asked / oldest for this staff
            cat_questions = fetch_eligible_questions(
                staff_type=staff_type,
                category=cat,
                designation=designation,
                section_group=section_group if cat == "sectional_knowledge" else None,
                difficulty=difficulty,
                exclude_ids=exclude_ids,
                staff_hrms_id=staff_hrms_id,
            )
            # Questions already ordered by priority, take first N
            selected = cat_questions[:cat_count]
            for q in selected:
                q["is_reattempt"] = False
            fresh_questions.extend(selected)
            # Add selected to exclude set to avoid cross-category duplicates
            exclude_ids.update(q["id"] for q in selected)
    else:
        # Single category mode
        cat_questions = fetch_eligible_questions(
            staff_type=staff_type,
            category=category,
            designation=designation,
            section_group=section_group if category == "sectional_knowledge" else None,
            difficulty=difficulty,
            exclude_ids=exclude_ids,
            staff_hrms_id=staff_hrms_id,
        )
        # Questions already ordered by priority, take first N
        fresh_questions = cat_questions[:remaining_needed]
        for q in fresh_questions:
            q["is_reattempt"] = False

    # Step 5: Combine
    final = reattempt_questions + fresh_questions[:remaining_needed]

    # Deduplicate (safety net)
    seen = set()
    unique_final = []
    for q in final:
        if q["id"] not in seen:
            seen.add(q["id"])
            unique_final.append(q)

    # Step 6: Shuffle
    random.shuffle(unique_final)

    return unique_final
