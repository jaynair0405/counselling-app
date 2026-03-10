"""
Import EMU Questions from CSV into div_runsafe_questions table.
Also inserts missing subcategories under EMU category.

Usage:
    python3 import_emu_questions.py

Source: EMU-questions.csv (316 questions, SUBURBAN, Motorman)
"""

import csv
import json
import mysql.connector
import sys

# ─── Config ───
CSV_FILE = "/Users/neeraja/counselling-app/EMU-questions.csv"
DB_CONFIG = {
    "host": "localhost",
    "user": "jay",
    "password": "4310jay",
    "database": "bbtro",
    "charset": "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
}

def main():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)

    # ─── Step 1: Ensure EMU subcategories exist ───
    # Get EMU category id
    cursor.execute("SELECT id FROM div_runsafe_categories WHERE code = 'emu'")
    emu_cat = cursor.fetchone()
    if not emu_cat:
        print("ERROR: EMU category not found in div_runsafe_categories. Run schema.sql first.")
        return
    emu_cat_id = emu_cat["id"]

    subcats_to_add = {
        "BT": "Bombardier (BT)",
        "SIEMENS": "Siemens",
        "BHEL AC": "BHEL AC",
        "AC RETRO": "AC Retro",
        "MEDHA": "Medha",
    }

    for code, name in subcats_to_add.items():
        cursor.execute(
            "SELECT id FROM div_runsafe_subcategories WHERE category_id = %s AND code = %s",
            (emu_cat_id, code)
        )
        if not cursor.fetchone():
            cursor.execute(
                """INSERT INTO div_runsafe_subcategories (category_id, name, code, display_order)
                   VALUES (%s, %s, %s, %s)""",
                (emu_cat_id, name, code, 0)
            )
            print(f"  Added subcategory: {code} ({name})")

    conn.commit()

    # ─── Step 2: Read CSV and import ───
    imported = 0
    skipped = 0

    with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 2):
            question_text = row["question_text"].strip()
            option_a = row["option_a"].strip()
            option_b = row["option_b"].strip()
            option_c = row["option_c"].strip()
            option_d = row["option_d"].strip()
            correct_option = row["correct_option"].strip().upper()
            category_code = row["category_code"].strip().lower()  # emu
            staff_type = row["staff_type"].strip().upper()        # SUBURBAN
            subcategory_code = row["subcategory_code"].strip()    # BT, SIEMENS, etc.
            difficulty = row["difficulty"].strip().lower() or "medium"
            targeted_desg_raw = row["targeted_desg"].strip()

            # Validate
            if not question_text or not correct_option:
                print(f"  Row {i}: SKIPPED — blank question or answer")
                skipped += 1
                continue

            if correct_option not in ("A", "B", "C", "D"):
                print(f"  Row {i}: SKIPPED — invalid correct_option '{correct_option}'")
                skipped += 1
                continue

            # Convert targeted_desg: "8" → '["MOTORMAN"]'
            targeted_desg = None
            if targeted_desg_raw == "8":
                targeted_desg = json.dumps(["MOTORMAN"])

            # Normalize category
            if category_code == "emu":
                category_code = "emu"
            
            if difficulty not in ("easy", "medium", "hard"):
                difficulty = "medium"

            if staff_type not in ("MAINLINE", "SUBURBAN", "COMMON"):
                staff_type = "SUBURBAN"

            # Insert
            cursor.execute(
                """INSERT INTO div_runsafe_questions
                   (question_text, option_a, option_b, option_c, option_d,
                    correct_option, category_code, staff_type, subcategory_code,
                    difficulty, targeted_desg)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (question_text, option_a, option_b, option_c, option_d,
                 correct_option, category_code, staff_type,
                 subcategory_code if subcategory_code else None,
                 difficulty, targeted_desg)
            )
            imported += 1

    conn.commit()

    # ─── Step 3: Summary ───
    print(f"\n{'='*50}")
    print(f"Import complete!")
    print(f"  Imported: {imported}")
    print(f"  Skipped:  {skipped}")
    print(f"{'='*50}")

    # Show totals
    cursor.execute(
        """SELECT category_code, subcategory_code, COUNT(*) as cnt
           FROM div_runsafe_questions
           WHERE category_code = 'emu' AND active = 1
           GROUP BY category_code, subcategory_code
           ORDER BY cnt DESC"""
    )
    print("\nEMU questions in DB:")
    for r in cursor.fetchall():
        print(f"  {r['subcategory_code'] or 'General':15s} → {r['cnt']}")

    cursor.execute("SELECT COUNT(*) as total FROM div_runsafe_questions WHERE active = 1")
    print(f"\nTotal questions in DB: {cursor.fetchone()['total']}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
