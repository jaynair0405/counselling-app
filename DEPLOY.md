# ============================================================================
# DEPLOYMENT GUIDE — Counselling Module
# ============================================================================

## 1. Nginx Proxy Addition

Add this block inside your existing server block in:
/etc/nginx/sites-available/railway-system

```nginx
    # Counselling Module
    location /counselling/ {
        proxy_pass http://127.0.0.1:5003/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
```

Then reload:
```bash
sudo nginx -t
sudo systemctl reload nginx
```


## 2. Database Setup

Run the schema on your MySQL server:
```bash
mysql -u root -p bbtro < schema.sql
```


## 3. Application Setup

```bash
# Copy to server
cd /home/railway/counselling-app

# Install dependencies
pip install -r requirements.txt

# Update db_config.py with your actual credentials

# Test locally
uvicorn main:app --reload --port 5003

# Start with PM2
pm2 start ecosystem.config.js
pm2 save
```


## 4. Access URLs

- Quiz UI:       https://crtms.in/counselling/ui/
- Report Page:   https://crtms.in/counselling/ui/report.html?session_id={id}
- API Docs:      https://crtms.in/counselling/docs
- Health Check:  https://crtms.in/counselling/health


## 5. API Endpoint Summary

### Session Lifecycle
POST   /counselling/api/session/start           → Start quiz session
POST   /counselling/api/session/submit          → Submit answers
GET    /counselling/api/session/{id}            → Get session details
POST   /counselling/api/session/{id}/notes      → Add inspector notes
GET    /counselling/api/session/staff/{id}/lookup → Staff name lookup

### Question Bank (CLI/Instructor)
GET    /counselling/api/questions/              → List questions
POST   /counselling/api/questions/              → Add question
PUT    /counselling/api/questions/{id}          → Edit question
DELETE /counselling/api/questions/{id}          → Deactivate question
GET    /counselling/api/questions/stats         → Bank statistics

### History
GET    /counselling/api/history/staff/{cms_id}         → Staff history
GET    /counselling/api/history/staff/{cms_id}/latest   → Latest session
GET    /counselling/api/history/staff/{cms_id}/weak     → Weak areas
GET    /counselling/api/history/cli/{cms_id}            → CLI's sessions
GET    /counselling/api/history/dashboard               → Dashboard stats

### Reports
GET    /counselling/api/reports/session/{id}            → Full report data
POST   /counselling/api/reports/session/{id}/dev-plan   → Add dev plan
GET    /counselling/api/reports/staff/{cms_id}/summary  → Staff summary


## 6. GAS → Flask/FastAPI Function Mapping

| GAS Function                      | New Location                          |
|-----------------------------------|---------------------------------------|
| getStaffID()                      | routes/session.py → start_session()   |
| getData() / combineQuestions()    | services/quiz_engine.py → generate_quiz() |
| getCategory1-5Questions()         | services/quiz_engine.py → fetch_eligible_questions() |
| answerEvaluator()                 | services/scoring.py → evaluate_answers() |
| generateTestID()                  | routes/session.py → get_next_test_number() |
| getLatestTestResults()            | routes/history.py → staff_latest_session() |
| getTestAttemptHistory()           | routes/history.py → staff_history() |
| combineTestScoresWithSubcategory()| services/scoring.py → _store_category_scores() |
| weakHistoryMapping()              | services/scoring.py → get_weak_history() |
| createCurrentTestReports()        | routes/reports.py → session_report() |
| reportHeaderDatas()               | routes/reports.py → session_report() |
| getStaffName() / lpLookUp()      | routes/session.py → staff_lookup() |
| getLobbyAndDesg()                 | services/quiz_engine.py → derive_lobby_from_cms_id() |
| assessCategory()                  | services/quiz_engine.py → get_assessment() |
