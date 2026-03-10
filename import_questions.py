"""
Import RUNSAFE QuestionBank CSV into div_runsafe_questions table (from legacy DACS export).

Imports:
  GAS Category 2 → traffic_rules    (147 questions)
  GAS Category 3 → electric_loco    (154 questions)
  GAS Category 4 → diesel_loco      (209 questions)

Skips:
  GAS Category 1  → sectional_knowledge (disabled until LRD sorting)
  GAS Category 5  → e_case_study (too few questions, excluded for now)
  GAS Category 20 → signal layouts (not in v1)

All imported as:
  staff_type = MAINLINE
  targeted_desg = NULL (all designations)
  subcategory_code = NULL
  difficulty = medium

Usage:
  cd counselling-app
  python3 import_questions.py
"""

import csv
import mysql.connector
import sys
import os

DB_CONFIG = {
    "host": "localhost",
    "user": os.getenv("DB_USER", "jay"),
    "password": os.getenv("DB_PASSWORD", "4310jay"),
    "database": "bbtro",
    "charset": "utf8mb4",
}

CSV_PATH = "DACS_-_QuestionBank.csv"

CATEGORY_MAP = {
    "2": "traffic_rules",
    "3": "electric_loco",
    "4": "diesel_loco",
}

SKIP_CATEGORIES = {"1", "5", "20"}


def main():
    if not os.path.exists(CSV_PATH):
        print(f"CSV not found: {CSV_PATH}")
        print("Place the CSV in the same folder as this script.")
        sys.exit(1)

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    inserted = 0
    skipped = 0
    errors = 0

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row_num, row in enumerate(reader, start=2):
            gas_category = row.get("Category", "").strip()
            question_text = row.get("Questions", "").strip()

            if not question_text or gas_category in SKIP_CATEGORIES:
                skipped += 1
                continue

            category_code = CATEGORY_MAP.get(gas_category)
            if not category_code:
                print(f"  Row {row_num}: Unknown category '{gas_category}' — skipping")
                skipped += 1
                continue

            option_a = row.get("Option A", "").strip()
            option_b = row.get("Option B", "").strip()
            option_c = row.get("Option C", "").strip()
            option_d = row.get("Option D", "").strip()
            correct_answer = row.get("Correct Answer", "").strip().upper()

            if correct_answer not in ("A", "B", "C", "D"):
                print(f"  Row {row_num}: Invalid correct answer '{correct_answer}' — skipping")
                skipped += 1
                continue

            if not all([option_a, option_b, option_c, option_d]):
                print(f"  Row {row_num}: Missing option(s) — skipping")
                skipped += 1
                continue

            try:
                cursor.execute(
                    """INSERT INTO div_runsafe_questions
                       (question_text, option_a, option_b, option_c, option_d,
                        correct_option, staff_type, category_code, subcategory_code,
                        difficulty, targeted_desg, active)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (question_text, option_a, option_b, option_c, option_d,
                     correct_answer, "MAINLINE", category_code, None,
                     "medium", None, 1)
                )
                inserted += 1
            except Exception as e:
                print(f"  Row {row_num}: Error — {e}")
                errors += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\n{'='*40}")
    print(f"Import complete!")
    print(f"  Inserted: {inserted}")
    print(f"  Skipped:  {skipped} (cat 1, 5, 20)")
    print(f"  Errors:   {errors}")
    print(f"{'='*40}")

    # Verify
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT category_code, COUNT(*) as cnt
           FROM div_runsafe_questions WHERE active = 1
           GROUP BY category_code ORDER BY cnt DESC"""
    )
    print(f"\nQuestions by category:")
    for code, cnt in cursor.fetchall():
        print(f"  {code}: {cnt}")
    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
