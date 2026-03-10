-- ============================================================================
-- COUNSELLING MODULE — MySQL Schema
-- Database: bbtro (existing)
-- Prefix: div_runsafe_ (to avoid conflicts with existing tables)
-- ============================================================================

-- 1A. CATEGORY & SUBCATEGORY LOOKUP TABLES
-- Training centre can add new categories/subcategories from the UI
-- No ALTER TABLE needed — just INSERT a new row
-- ============================================================================

CREATE TABLE IF NOT EXISTS div_runsafe_categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    -- e.g., "Sectional Knowledge", "Traffic Rules", "EMU", "AWS", "TSR"
    code VARCHAR(50) NOT NULL UNIQUE,
    -- e.g., "sectional_knowledge", "traffic_rules", "emu", "aws", "tsr"
    staff_type ENUM('MAINLINE','SUBURBAN','COMMON') NOT NULL DEFAULT 'COMMON',
    -- Which staff type this category applies to
    display_order SMALLINT NOT NULL DEFAULT 0,
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_staff_type (staff_type),
    INDEX idx_active (active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS div_runsafe_subcategories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    -- e.g., "Normal Working", "Abnormal Working", "3Phase Loco", "Power Circuit"
    code VARCHAR(50) NOT NULL,
    -- e.g., "normal_working", "abnormal_working"
    display_order SMALLINT NOT NULL DEFAULT 0,
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (category_id) REFERENCES div_runsafe_categories(id),
    UNIQUE KEY uq_cat_subcat (category_id, code),
    INDEX idx_category (category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- Seed: Mainline categories (from your GAS system)
INSERT INTO div_runsafe_categories (name, code, staff_type, display_order) VALUES
    ('Sectional Knowledge',  'sectional_knowledge',  'MAINLINE',  1),
    ('Traffic Rules',        'traffic_rules',        'COMMON',    2),
    ('Electric Loco',        'electric_loco',        'MAINLINE',  3),
    ('Diesel Loco',          'diesel_loco',          'MAINLINE',  4),
    ('e-Case Study',         'e_case_study',         'COMMON',    5);

-- Seed: Suburban categories (new)
INSERT INTO div_runsafe_categories (name, code, staff_type, display_order) VALUES
    ('EMU',                  'emu',                  'SUBURBAN',  1),
    ('AWS',                  'aws',                  'SUBURBAN',  2),
    ('Automatic Signalling', 'automatic_signalling', 'SUBURBAN',  3),
    ('TSR',                  'tsr',                  'SUBURBAN',  4);

-- Seed: Subcategories for Traffic Rules
INSERT INTO div_runsafe_subcategories (category_id, name, code, display_order) VALUES
    ((SELECT id FROM div_runsafe_categories WHERE code='traffic_rules'), 'Normal Working',   'normal_working',   1),
    ((SELECT id FROM div_runsafe_categories WHERE code='traffic_rules'), 'Abnormal Working', 'abnormal_working', 2),
    ((SELECT id FROM div_runsafe_categories WHERE code='traffic_rules'), 'General',          'general',          3);

-- Seed: Subcategories for Electric Loco
INSERT INTO div_runsafe_subcategories (category_id, name, code, display_order) VALUES
    ((SELECT id FROM div_runsafe_categories WHERE code='electric_loco'), '3Phase Loco',      'three_phase_loco',  1),
    ((SELECT id FROM div_runsafe_categories WHERE code='electric_loco'), 'Power Circuit',    'power_circuit',     2),
    ((SELECT id FROM div_runsafe_categories WHERE code='electric_loco'), 'Auxiliary Circuit', 'auxiliary_circuit', 3),
    ((SELECT id FROM div_runsafe_categories WHERE code='electric_loco'), 'General',          'general',           4);

-- Seed: Subcategories for Diesel Loco
INSERT INTO div_runsafe_subcategories (category_id, name, code, display_order) VALUES
    ((SELECT id FROM div_runsafe_categories WHERE code='diesel_loco'), 'HHP Loco',          'hhp_loco',          1),
    ((SELECT id FROM div_runsafe_categories WHERE code='diesel_loco'), 'Conventional Locos', 'conventional_locos', 2),
    ((SELECT id FROM div_runsafe_categories WHERE code='diesel_loco'), 'General',            'general',           3);


-- ============================================================================
-- 1B. QUESTION BANK
-- Replaces the Google Sheets "QuestionBank" sheet
-- Stores all MCQ questions with category/subcategory/difficulty tagging
-- Now uses VARCHAR references to lookup tables (not ENUM)
-- ============================================================================

CREATE TABLE IF NOT EXISTS div_runsafe_questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    question_text TEXT NOT NULL,
    option_a VARCHAR(500) NOT NULL,
    option_b VARCHAR(500) NOT NULL,
    option_c VARCHAR(500) NOT NULL,
    option_d VARCHAR(500) NOT NULL,
    correct_option ENUM('A','B','C','D') NOT NULL,

    -- Classification (references lookup tables by code)
    staff_type ENUM('MAINLINE','SUBURBAN','COMMON') NOT NULL DEFAULT 'COMMON',
    category_code VARCHAR(50) NOT NULL,
    -- e.g., "traffic_rules", "emu", "aws" — matches div_runsafe_categories.code
    subcategory_code VARCHAR(50) DEFAULT NULL,
    -- e.g., "normal_working" — matches div_runsafe_subcategories.code

    -- Filtering
    difficulty ENUM('easy','medium','hard') NOT NULL DEFAULT 'medium',
    section_group VARCHAR(100) DEFAULT NULL,
    -- e.g., "CSMT-KJT", "KYN-IGP", "PNVL-ROHA" (for sectional_knowledge)

    targeted_desg JSON DEFAULT NULL,
    -- JSON array: ["ALP","LPG","LPP","LPM","MotorMan"] or NULL for all
    -- Replaces the complex targetedGroup numeric codes from GAS

    -- Metadata
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_by VARCHAR(20) DEFAULT NULL,   -- CMS ID of CLI/instructor who added
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Indexes
    INDEX idx_category (category_code),
    INDEX idx_subcategory (subcategory_code),
    INDEX idx_staff_type (staff_type),
    INDEX idx_difficulty (difficulty),
    INDEX idx_active (active),
    INDEX idx_section_group (section_group)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- 2. COUNSELLING SESSIONS
-- One row per quiz session (replaces GAS "StaffID" sheet + Results aggregation)
-- Created when CLI clicks "Start Session"
-- ============================================================================

CREATE TABLE IF NOT EXISTS div_runsafe_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    
    -- Who is being counselled
    staff_hrms_id VARCHAR(10) NOT NULL,       -- e.g., "MLKXLZ" (PK in div_staff_master)
    staff_cms_id VARCHAR(15) DEFAULT NULL,     -- e.g., "KYN4310" (display/legacy)
    staff_name VARCHAR(100) DEFAULT NULL,
    staff_designation VARCHAR(10) DEFAULT NULL, -- designation_code: ALP, LPG, LPP, LPM, MOTORMAN, LPS
    staff_type ENUM('MAINLINE','SUBURBAN') NOT NULL DEFAULT 'MAINLINE',
    staff_office VARCHAR(15) DEFAULT NULL,     -- current_office_code: CSMT-ML, KYN-SUB etc.

    -- Who is conducting the session
    cli_id VARCHAR(15) DEFAULT NULL,           -- CLI CMS ID (CSTM0027)
    cli_cms_id VARCHAR(15) DEFAULT NULL,       -- same (for display)
    cli_name VARCHAR(100) DEFAULT NULL,
    nominated_cli_id VARCHAR(15) DEFAULT NULL,  -- Staff's nominated CLI CMS ID
    nominated_cli_name VARCHAR(100) DEFAULT NULL,

    -- Session config
    category_code VARCHAR(50) NOT NULL DEFAULT 'all_topics',
    -- matches div_runsafe_categories.code, or 'all_topics' for mixed quiz
    difficulty ENUM('easy','medium','hard','mixed') NOT NULL DEFAULT 'mixed',
    question_count SMALLINT NOT NULL DEFAULT 15,

    -- Test tracking (replaces GAS testID generation)
    test_number SMALLINT NOT NULL DEFAULT 1,
    -- Auto-incremented per staff: staff's 1st test = 1, 2nd = 2, etc.

    -- Scoring
    total_score SMALLINT DEFAULT 0,
    total_questions SMALLINT DEFAULT 0,
    percentage DECIMAL(5,2) DEFAULT 0.00,
    grade VARCHAR(30) DEFAULT NULL,
    -- "Proficient" / "Development Area" / "Weak"

    -- Timing
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL DEFAULT NULL,
    duration_seconds INT DEFAULT NULL,

    -- Inspector notes (NEW — not in GAS)
    inspector_notes TEXT DEFAULT NULL,

    -- Status
    status ENUM('active','completed','abandoned') NOT NULL DEFAULT 'active',

    -- Indexes
    INDEX idx_staff (staff_hrms_id),
    INDEX idx_staff_cms (staff_cms_id),
    INDEX idx_cli (cli_cms_id),
    INDEX idx_status (status),
    INDEX idx_started (started_at),
    INDEX idx_staff_test (staff_hrms_id, test_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- 3. COUNSELLING ANSWERS
-- One row per question answered in a session
-- Replaces GAS "Results" sheet
-- ============================================================================

CREATE TABLE IF NOT EXISTS div_runsafe_answers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    question_id INT NOT NULL,

    submitted_answer ENUM('A','B','C','D') DEFAULT NULL,
    -- NULL = unanswered / skipped
    correct_answer ENUM('A','B','C','D') NOT NULL,
    is_correct TINYINT(1) NOT NULL DEFAULT 0,
    -- 1 = correct, 0 = wrong

    -- For display: store the actual text of submitted answer
    submitted_answer_text VARCHAR(500) DEFAULT NULL,
    correct_answer_text VARCHAR(500) DEFAULT NULL,

    -- Was this a re-asked wrong question from previous session?
    is_reattempt TINYINT(1) NOT NULL DEFAULT 0,

    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (session_id) REFERENCES div_runsafe_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES div_runsafe_questions(id),

    INDEX idx_session (session_id),
    INDEX idx_question (question_id),
    INDEX idx_correct (is_correct)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- 4. COUNSELLING CATEGORY SCORES
-- Per-session category/subcategory breakdown
-- Computed after quiz completion, stored for fast report generation
-- Replaces GAS combineTestScoresWithSubcategory() output
-- ============================================================================

CREATE TABLE IF NOT EXISTS div_runsafe_category_scores (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,

    category VARCHAR(50) NOT NULL,
    subcategory VARCHAR(100) DEFAULT NULL,
    question_count SMALLINT NOT NULL DEFAULT 0,
    score SMALLINT NOT NULL DEFAULT 0,
    percentage DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    assessment VARCHAR(30) DEFAULT NULL,
    -- "Proficient" / "Development Area" / "Weak"

    FOREIGN KEY (session_id) REFERENCES div_runsafe_sessions(id) ON DELETE CASCADE,
    INDEX idx_session (session_id),
    INDEX idx_assessment (assessment)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- 5. COUNSELLING DEVELOPMENT PLANS (NEW — not in GAS)
-- CLI writes action items during/after counselling
-- Carries forward to next session
-- ============================================================================

CREATE TABLE IF NOT EXISTS div_runsafe_dev_plans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    staff_hrms_id VARCHAR(10) NOT NULL,

    subcategory VARCHAR(100) NOT NULL,
    action_text TEXT NOT NULL,
    -- e.g., "Revisit T/409 forms; practical demo in yard"

    status ENUM('pending','in_progress','completed') NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL DEFAULT NULL,

    FOREIGN KEY (session_id) REFERENCES div_runsafe_sessions(id) ON DELETE CASCADE,
    INDEX idx_staff (staff_hrms_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- VIEWS (for common queries)
-- ============================================================================

-- Staff counselling history: all sessions with scores
CREATE OR REPLACE VIEW v_runsafe_history AS
SELECT
    s.id AS session_id,
    s.staff_hrms_id,
    s.staff_cms_id,
    s.staff_name,
    s.staff_designation,
    s.cli_name,
    s.test_number,
    s.category_code,
    s.total_score,
    s.total_questions,
    s.percentage,
    s.grade,
    s.duration_seconds,
    s.started_at,
    s.completed_at
FROM div_runsafe_sessions s
WHERE s.status = 'completed'
ORDER BY s.staff_hrms_id, s.test_number;


-- Weak areas across all sessions for a staff member
CREATE OR REPLACE VIEW v_runsafe_weak_areas AS
SELECT
    s.staff_hrms_id,
    s.staff_cms_id,
    s.staff_name,
    s.test_number,
    cs.category,
    cs.subcategory,
    cs.score,
    cs.question_count,
    cs.percentage,
    cs.assessment,
    s.started_at
FROM div_runsafe_category_scores cs
JOIN div_runsafe_sessions s ON cs.session_id = s.id
WHERE cs.assessment IN ('Weak', 'Development Area')
  AND s.status = 'completed'
ORDER BY s.staff_hrms_id, s.started_at DESC;
