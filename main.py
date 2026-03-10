"""
Counselling Module — FastAPI Application
Central Railway Train Management System (CRTMS)
Computer-Based Counselling for Loco Pilots

Run locally:  uvicorn main:app --reload --port 5003
Run on server: PM2 + Uvicorn (see ecosystem.config.js)
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os

from routes.session import router as session_router
from routes.questions import router as questions_router
from routes.history import router as history_router
from routes.reports import router as reports_router

# ─────────────────────────────────────────────
# App Setup
# ─────────────────────────────────────────────
ROOT_PATH = os.getenv("ROOT_PATH", "")
app = FastAPI(
    title="CRTMS Counselling API",
    description="Computer-Based Counselling System for Loco Pilots — Central Railway Mumbai Division",
    version="1.0.0",
    root_path=ROOT_PATH
)

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Static UI files
# ─────────────────────────────────────────────
UI_DIR = Path(__file__).parent / "ui"
if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")

# ─────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────
app.include_router(session_router, prefix="/api/session", tags=["Session"])
app.include_router(questions_router, prefix="/api/questions", tags=["Question Bank"])
app.include_router(history_router, prefix="/api/history", tags=["History & Results"])
app.include_router(reports_router, prefix="/api/reports", tags=["Reports"])

# ─────────────────────────────────────────────
# Root redirect
# ─────────────────────────────────────────────
@app.get("/")
def root():
    return RedirectResponse(url=f"{ROOT_PATH}/ui/")


@app.get("/health")
def health():
    return {"status": "ok", "service": "counselling"}
