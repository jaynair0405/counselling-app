-- One-time migration for existing counselling-app databases.
-- Apply after reviewing the duplicate-check queries below.

-- 1. Check for duplicate per-staff test numbers.
SELECT staff_hrms_id, test_number, COUNT(*) AS duplicate_count
FROM div_runsafe_sessions
GROUP BY staff_hrms_id, test_number
HAVING COUNT(*) > 1;

-- 2. Check for duplicate answers within the same session.
SELECT session_id, question_id, COUNT(*) AS duplicate_count
FROM div_runsafe_answers
GROUP BY session_id, question_id
HAVING COUNT(*) > 1;

-- 3. Check for duplicate category/subcategory score rows within the same session.
SELECT session_id, category, subcategory, COUNT(*) AS duplicate_count
FROM div_runsafe_category_scores
GROUP BY session_id, category, subcategory
HAVING COUNT(*) > 1;

-- 4. Add concurrency-safety constraints once the checks above return zero rows.
ALTER TABLE div_runsafe_sessions
    DROP INDEX idx_staff_test,
    ADD UNIQUE KEY uq_staff_test (staff_hrms_id, test_number);

ALTER TABLE div_runsafe_answers
    ADD UNIQUE KEY uq_session_question (session_id, question_id);

ALTER TABLE div_runsafe_category_scores
    ADD UNIQUE KEY uq_session_category_subcategory (session_id, category, subcategory);
