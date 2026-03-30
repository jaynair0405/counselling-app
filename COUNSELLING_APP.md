# CRTMS RUNSAFE Module

**RUNSAFE: Running Staff Assessment Framework for Enhanced Familiarization & Evaluation**
Central Railway, Mumbai Division — Training Department

---

## Overview

A standalone FastAPI web application for conducting computer-based counselling (knowledge assessment) of Loco Pilots, Assistant Loco Pilots, and Motormen. Replaces the legacy Google Apps Script (GAS) + Google Sheets system with a modern MySQL-backed architecture.

**Port:** 5003
**Database:** `bbtro` (shared with BBTRO main app)
**Domain:** crtms.in (production, via Nginx reverse proxy)
**Local:** http://localhost:5003

---

## Architecture

```
counselling-app/
├── main.py                  # FastAPI entry point, mounts routes + static
├── db_config.py             # MySQL connection pool (bbtro database)
├── auth.py                  # BBTRO session auth + local dev bypass helpers
├── requirements.txt         # Python deps: fastapi, uvicorn, mysql-connector
├── ecosystem.config.js      # PM2 config for production
├── schema.sql               # 7 tables + 2 views + seed data
├── CONCURRENCY_HARDENING.sql # Migration for existing DBs adding new constraints
├── import_questions.py      # One-time CSV import script
├── routes/
│   ├── session.py           # Start session, submit answers, staff/CLI search
│   ├── questions.py         # CRUD for question bank management
│   ├── history.py           # Staff history, weak areas, dashboard stats
│   └── reports.py           # Session reports, dev plans, staff summary
├── services/
│   ├── quiz_engine.py       # Question selection, category weighting, reattempts
│   └── scoring.py           # Answer evaluation, category scores, grade
├── tests/
│   ├── test_session_routes.py
│   ├── test_scoring.py
│   ├── test_quiz_engine.py
│   └── test_auth.py
└── ui/
    ├── index.html           # Single-page quiz interface (setup → quiz → results)
    └── report.html          # Detailed session report page
```

---

## Database Schema

All tables prefixed with `div_runsafe_` following the BBTRO naming convention.

### External Tables (read-only, from BBTRO)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `div_staff_master` | All loco running staff | `hrms_id` (PK), `current_cms_id`, `name`, `designation_id` (FK), `current_cli_id` (FK), `current_office_code`, `status` |
| `div_cli_master` | Chief Loco Inspectors | `cli_id` (PK, auto), `cli_hrms_id`, `cmsid`, `cli_name`, `current_office_code`, `is_active` |
| `designations` | Staff designations | `id` (PK), `designation_code` (ALP, Sr.ALP, LPG, LPP, LPM, LPS, MOTORMAN, Jr.INST, Sr.INST), `designation_name` |

### RUNSAFE Tables

| Table | Rows | Purpose |
|-------|------|---------|
| `div_runsafe_categories` | 9 | Category lookup (mainline + suburban) |
| `div_runsafe_subcategories` | 15 | Subcategory lookup within each category |
| `div_runsafe_questions` | 825 | MCQ question bank (509 mainline + 316 suburban) |
| `div_runsafe_sessions` | per-quiz | One row per quiz session |
| `div_runsafe_answers` | per-question | One row per question assigned to a session; seeded at start, updated on submit |
| `div_runsafe_category_scores` | per-session | Category/subcategory score breakdown |
| `div_runsafe_dev_plans` | per-session | CLI action items for weak areas |

### Views

| View | Purpose |
|------|---------|
| `v_runsafe_history` | All completed sessions with scores |
| `v_runsafe_weak_areas` | Weak/Development areas across sessions |

### Concurrency and Integrity Guards

- `div_runsafe_sessions` has a unique per-staff test-number constraint on `(staff_hrms_id, test_number)`
- `div_runsafe_answers` has a unique constraint on `(session_id, question_id)`
- `div_runsafe_category_scores` has a unique constraint on `(session_id, category, subcategory)`
- Existing databases should apply `CONCURRENCY_HARDENING.sql` after confirming the duplicate-check queries return zero rows

---

## Categories & Question Bank

### Mainline Categories

| Code | Name | Questions | Status | Weight in Mixed |
|------|------|-----------|--------|-----------------|
| `traffic_rules` | Traffic Rules | 147 | ✅ Active | 35% |
| `electric_loco` | Electric Loco | 154 | ✅ Active | 35% |
| `diesel_loco` | Diesel Loco | 208 | ✅ Active | 30% |
| `sectional_knowledge` | Sectional Knowledge | 0 | ❌ Disabled | — |
| `e_case_study` | e-Case Study | 0 | ❌ Disabled | — |

### Suburban Categories (Motormen)

| Code | Name | Questions | Status |
|------|------|-----------|--------|
| `emu` | EMU | 316 | ✅ Active |
| `aws` | AWS | 0 | Awaiting questionnaire |
| `automatic_signalling` | Automatic Signalling | 0 | Awaiting questionnaire |
| `tsr` | TSR | 0 | Awaiting questionnaire |

### EMU Subcategories

| Code | Name | Questions |
|------|------|-----------|
| `SIEMENS` | Siemens | 189 |
| `BT` | Bombardier (BT) | 52 |
| `BHEL AC` | BHEL AC | 25 |
| `AC RETRO` | AC Retro | 25 |
| `MEDHA` | Medha | 25 |

### Question Structure

Each question has:
- `question_text`, `option_a/b/c/d`, `correct_option` (A/B/C/D)
- `staff_type` (MAINLINE / SUBURBAN / COMMON)
- `category_code`, `subcategory_code` (nullable)
- `difficulty` (easy / medium / hard)
- `targeted_desg` (JSON array of designation codes, NULL = all)
- `section_group` (for sectional knowledge, e.g., "CSMT-KJT")

---

## Quiz Engine Logic

### Question Selection (`services/quiz_engine.py`)

1. **Reattempts first:** Fetch questions the staff got wrong in their latest completed session
2. **Exclude latest correct by default:** Keep questions answered correctly in that latest session out of the fresh pool first
3. **Fresh questions:** Fill remaining slots from the least-asked, oldest-asked eligible pool for that same staff member
4. **Backfill if needed:** If exclusions make the pool too small, previously-correct questions are allowed back in so the requested question count can still be met
4. **Category distribution** (for `all_topics` mode):
   - traffic_rules: 35% (~5 of 15)
   - electric_loco: 35% (~5 of 15)
   - diesel_loco: 30% (~5 of 15)
   - Rounding correction applied to largest category
5. **Shuffle** final question list

### Single Category Mode

When user selects a specific category (e.g., `electric_loco`), all questions come from that one category. The same reattempt-first, exclude-latest-correct-first, and backfill-if-needed logic applies.

### Assessment Grades

| Grade | Percentage |
|-------|-----------|
| Proficient | ≥ 70% |
| Development Area | 40% – 69% |
| Weak | < 40% |

---

## API Endpoints

### Authentication and Access

- `/health` is open
- All `/api/...` routes require an authenticated operator from the parent BBTRO session model
- Question bank create/update/delete routes require editor roles
- The backend accepts either:
  - BBTRO session cookies (`connect.sid` / `session_token`)
  - `Authorization: Bearer <token>`
- For local direct testing only, requests from `localhost` / `127.0.0.1` can use the built-in bypass controlled by `COUNSELLING_LOCALHOST_AUTH_BYPASS`

### Session (`/api/session`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/start` | Create session + generate quiz |
| POST | `/submit` | Submit answers, get scored results |
| GET | `/{session_id}` | Get full session details |
| POST | `/{session_id}/notes` | Add inspector/CLI notes |
| GET | `/staff/search?q=` | Search staff by name or CMS ID |
| GET | `/staff/{id}/lookup` | Full staff details by exact ID |
| GET | `/cli/search?q=` | Search CLI + Instructors |

#### Start Session Request
```json
{
  "staff_id": "KYN5611",       // current_cms_id or hrms_id
  "cli_id": "CSTM0027",        // CLI CMS ID or hrms_id
  "category": "all_topics",    // or specific category code
  "difficulty": "mixed",       // easy / medium / hard / mixed
  "question_count": 15,        // 5-30
  "staff_type": "MAINLINE"     // MAINLINE / SUBURBAN
}
```

#### Start Session Response
```json
{
  "session_id": 1,
  "test_number": 1,
  "staff": { "hrms_id", "cms_id", "name", "designation", "office" },
  "cli": { "cms_id", "hrms_id", "name" },
  "nominated_cli": { "cms_id", "name" },
  "config": { "category", "difficulty", "question_count" },
  "questions": [
    {
      "id": 509,
      "question_text": "...",
      "option_a": "...", "option_b": "...", "option_c": "...", "option_d": "...",
      "category": "traffic_rules",
      "difficulty": "medium",
      "is_reattempt": false
    }
  ]
}
```

#### Submit Answers Request
```json
{
  "session_id": 1,
  "answers": { "509": "C", "364": "A", "327": "B" }
}
```

#### Submit Answers Response
```json
{
  "session_id": 1,
  "total_score": 5,
  "total_questions": 15,
  "percentage": 33.33,
  "grade": "Weak",
  "category_scores": [
    { "category": "traffic_rules", "score": 3, "question_count": 5, "percentage": 60.0 },
    { "category": "electric_loco", "score": 1, "question_count": 5, "percentage": 20.0 },
    { "category": "diesel_loco", "score": 1, "question_count": 5, "percentage": 20.0 }
  ],
  "marksheet": [
    {
      "question_id": 509,
      "question_text": "...",
      "submitted_answer": "C",
      "submitted_answer_text": "Every 6 Months",
      "correct_answer": "C",
      "correct_answer_text": "Every 6 Months",
      "is_correct": 1,
      "category": "traffic_rules",
      "subcategory": null
    }
  ]
}
```

#### CLI Search (`/api/session/cli/search`)

Returns merged results from two sources:
- `div_cli_master` → active CLIs (role: `CLI`)
- `div_staff_master` → Jr.INST / Sr.INST designations (role: `Jr.INST` / `Sr.INST`)

This allows both CLIs conducting counselling in lobbies and Instructors conducting in training centres to use the system.

### Question Bank (`/api/questions`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | List questions (filterable by category, difficulty, staff_type) |
| GET | `/{id}` | Get single question |
| POST | `/` | Add new question |
| PUT | `/{id}` | Update question |
| DELETE | `/{id}` | Soft-delete (set active=0) |
| GET | `/stats` | Question bank statistics by category |

### History (`/api/history`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/staff/{id}` | All sessions for a staff member |
| GET | `/staff/{id}/latest` | Latest session details |
| GET | `/staff/{id}/weak` | Weak area history |
| GET | `/cli/{id}` | All sessions conducted by a CLI |
| GET | `/dashboard` | Overview stats |

### Reports (`/api/reports`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/session/{id}` | Full session report data |
| POST | `/session/{id}/dev-plan` | Add development plan items |
| GET | `/staff/{id}/summary` | Staff-level summary across all sessions |

---

## UI Flow

Single-page app (`ui/index.html`) with 3 screens:

### Screen 1: Setup
- CLI/Instructor searches themselves (persists across sessions)
- Search staff by name or CMS ID (autocomplete from `div_staff_master`)
- Select category: All Topics / Traffic Rules / Electric Loco / Diesel Loco
- Set question count (10/15/20/25) and difficulty
- Start Quiz button (enabled when both staff and CLI selected)

### Screen 2: Quiz
- One question at a time with large touch-friendly option cards
- Option cards: min 64px height, 44px letter badges
- Progress bar + question counter + timer
- Session log sidebar (desktop only, shows answered questions)
- "Next Question" → last question shows "Submit Quiz"

### Screen 3: Results
- Score percentage (large gradient text)
- Grade badge (Proficient/Development Area/Weak)
- Stats cards: Correct, Wrong, Total, Duration
- Category-wise score bars with color coding
- Full marksheet table (question, your answer, correct answer, result)
- "New Session" (keeps CLI, clears staff) + "View Full Report"

### Touch Screen Support
- Designed for dual-screen setup: CLI desktop + staff-facing touch monitor
- Large tap targets, clear selection feedback, no small buttons
- Responsive: stacks to single column on mobile (< 960px)

---

## Conductor Types

The system supports two types of conductors:

| Type | Source Table | Designation Codes | Use Case |
|------|-------------|-------------------|----------|
| CLI | `div_cli_master` | — | Lobbies, monitoring duty |
| Instructor | `div_staff_master` | Jr.INST, Sr.INST | Training centres |

Both appear in the CLI/Instructor search dropdown with role tags.

---

## Staff Type Detection (Planned)

| Indicator | Staff Type | Categories |
|-----------|-----------|------------|
| designation_code = 'MOTORMAN' | SUBURBAN | EMU, AWS, TSR, Automatic Signalling |
| CMS ID starts with KYNS, PNVS, CSTS | SUBURBAN | (same) |
| CLI office ends with '-SUB' | SUBURBAN | (same) |
| All other staff | MAINLINE | Traffic Rules, Electric Loco, Diesel Loco |

Not yet implemented — awaiting suburban questionnaire.

---

## Scoring Flow

1. `start_session()` creates the parent row in `div_runsafe_sessions`
2. The assigned question set is immediately seeded into `div_runsafe_answers`
3. `submit_answers()` calls `evaluate_answers()` inside a transaction that locks the session row
4. The submitted question IDs must match the pre-assigned question set exactly, otherwise the request is rejected
5. Each pre-created answer row is updated with `submitted_answer`, `submitted_answer_text`, and `is_correct`
6. The session row is updated with total score, percentage, grade, completion time, and duration
7. Category-wise scores are stored in `div_runsafe_category_scores`
8. Duplicate submit attempts fail cleanly instead of writing a second result set

---

## Deployment

### Local Development
```bash
cd ~/counselling-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export COUNSELLING_BASE_PATH=
uvicorn main:app --reload --port 5003

# Run tests
.venv/bin/python -m pytest -q
```

### Production (Hostinger VPS)
```bash
# PM2 managed
pm2 start ecosystem.config.js
# Nginx reverse proxy: crtms.in/counselling → localhost:5003
```

### Environment Variables
```
DB_HOST=localhost
DB_USER=...
DB_PASSWORD=...
DB_NAME=bbtro
COUNSELLING_BASE_PATH=/counselling
COUNSELLING_CORS_ORIGINS=https://crtms.in,https://www.crtms.in
COUNSELLING_UVICORN_WORKERS=2
MYSQL_POOL_SIZE=10
MYSQL_CONNECT_TIMEOUT=10
COUNSELLING_LOCALHOST_AUTH_BYPASS=0
COUNSELLING_AUTH_DISABLED=0
```

---

## Current Open Items

- [ ] **Mainline/Suburban toggle** in setup UI (auto-detect from staff designation)
- [ ] **Sectional Knowledge** — requires `lrd_eligible` column in div_staff_master
- [ ] **Question Bank Manager UI** — CRUD interface for adding/editing questions
- [ ] **Dashboard UI** — backend stats exist, but no dedicated dashboard frontend yet
- [ ] **Staff history UI** — backend history exists, but no dedicated history frontend yet
- [ ] **Inspector notes UI polish** — backend support exists, but workflow can be improved
- [ ] **Development plan UI** — action items for weak areas
- [ ] **PWA** — manifest.json + service worker for "Add to Home Screen"
- [ ] **PDF report export** — generate downloadable counselling report
- [ ] **Bulk import** — upload CSV to add questions
- [ ] **Analytics** — trends, weak area heatmaps, CLI performance
- [ ] **Signal layout questions** — category 20, section-specific signal maps
- [ ] **e-Case Study** — interactive scenario-based questions
- [ ] **Multi-language** — Hindi + English toggle for question display
- [ ] **Timer per question** — optional countdown with auto-skip
- [ ] **Offline mode** — not implemented; requires an explicit sync/idempotency design before any PWA offline rollout

### Known Issues

| Issue | Details | Status |
|-------|---------|--------|
| 1 question missing answer | Row 157 has blank correct_answer — skipped during import | Fix in Question Bank Manager |
| Subcategories unused | All questions imported with `subcategory_code = NULL` | Assign later via UI |
| `targeted_desg` unused | All questions imported with `targeted_desg = NULL` | Assign later via UI |
| CLA staff indistinguishable | CLA merged into CSMT office — no field to separate | Add `lrd_eligible` column |

---

## GAS → FastAPI Migration Reference

| GAS Function | New Location |
|-------------|-------------|
| `createFinalQuestionnaire()` | `services/quiz_engine.py → generate_quiz()` |
| `getCategory1Questions()` – `getCategory5Questions()` | `services/quiz_engine.py → fetch_eligible_questions()` |
| `answerEvaluator()` | `services/scoring.py → evaluate_answers()` |
| `calculateCategoryScores()` | `services/scoring.py → _store_category_scores()` |
| `assessCategory()` | `services/quiz_engine.py → get_assessment()` |
| `weakHistoryMapping()` | `services/scoring.py → get_weak_history()` |
| `generateTestID()` | `routes/session.py → allocate_next_test_number()` |
| `reportHeaderDatas()` | `routes/reports.py → session_report()` |
| `lobbySubcategoryMappings` | `div_runsafe_subcategories` table |
| Google Sheets "QuestionBank" | `div_runsafe_questions` table |
| Google Sheets "Results" | `div_runsafe_answers` table |
| Google Sheets "StaffID" | `div_runsafe_sessions` table |

---

## File Sizes

| File | Lines | Description |
|------|-------|-------------|
| `schema.sql` | 324 | Full schema with seed data |
| `routes/session.py` | 676 | Session lifecycle + search |
| `services/quiz_engine.py` | 441 | Question selection engine |
| `routes/questions.py` | 370 | Question bank CRUD |
| `routes/reports.py` | 264 | Report endpoints |
| `routes/history.py` | 256 | History & dashboard |
| `services/scoring.py` | 253 | Evaluation & grading |
| `ui/index.html` | 1141 | Full quiz interface |
| `main.py` | 123 | App entry point |
| `import_questions.py` | 95 | CSV import script |

---

*Last updated: 30 Mar 2026 — docs aligned with concurrency, integrity, auth, routing, validation, and test fixes*
