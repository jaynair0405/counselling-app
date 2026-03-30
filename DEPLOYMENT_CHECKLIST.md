# SATARK Counselling App - Deployment Checklist

## Pre-Deployment
- [x] Database tables created on server
- [x] App code ready and committed
- [x] bbtro sidebar link updated and committed

---

## Deployment Steps

### Step 1: Push bbtro changes to server
- [x] Git push bbtro to origin
- [x] SSH to server and pull bbtro
- [x] Restart bbtro with PM2

### Step 2: Create counselling app folder on server
- [x] Create `/home/railway/counselling-app/` directory (with routes, services, ui subfolders)

### Step 3: Upload counselling app files (via GitHub)
- [x] Created GitHub repo: jaynair0405/counselling-app
- [x] Pushed code to GitHub
- [x] Cloned on server

### Step 4: Create .env file on server
- [x] Create .env with production credentials (railway_user)

### Step 5: Setup Python virtual environment
- [x] Create `.venv`
- [x] Activate venv
- [x] Install dependencies

### Step 6: Test app manually
- [x] Run uvicorn manually to check for errors
- [x] App started successfully on port 5003

### Step 7: Add Nginx configuration
- [x] Add location block for /counselling/ in railway-system
- [x] Test nginx config (syntax ok)
- [x] Reload nginx

### Step 8: Start app with PM2
- [x] Start counselling app with PM2 (id: 9)
- [x] Save PM2 config

### Step 9: Final verification
- [x] Test https://crtms.in/counselling/ui/
- [ ] Test sidebar link from bbtro dashboard
- [ ] Test a sample quiz flow

---

## Troubleshooting Log

| Step | Issue | Fix Applied |
|------|-------|-------------|
| 9 | `/ui/` returning 404 Not Found | Do not use `ROOT_PATH`. Use `COUNSELLING_BASE_PATH` instead; the app now keeps `/counselling` as the production default and uses base-path compatibility middleware for direct local testing. |

---

## Current Runtime Notes

- New databases: apply `schema.sql`
- Existing databases: review and then apply `CONCURRENCY_HARDENING.sql`
- Production default base path: `COUNSELLING_BASE_PATH=/counselling`
- Local direct testing: `COUNSELLING_BASE_PATH=` and run `uvicorn main:app --reload --port 5003`
- Local regression tests: `.venv/bin/python -m pytest -q`
- Production should keep `COUNSELLING_LOCALHOST_AUTH_BYPASS=0`

---

## Server Details
- **Server IP:** 93.127.198.125
- **User:** railway
- **App Port:** 5003
- **App Path:** /home/railway/counselling-app/
- **PM2 Name:** counselling
