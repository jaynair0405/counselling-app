"""
Counselling Module — FastAPI Application
Central Railway Train Management System (CRTMS)
Computer-Based Counselling for Loco Pilots

Run locally:  uvicorn main:app --reload --port 5003
Run on server: PM2 + Uvicorn (see ecosystem.config.js)
"""

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from routes.session import router as session_router
from routes.questions import router as questions_router
from routes.history import router as history_router
from routes.reports import router as reports_router


def get_cors_origins() -> list[str]:
    raw = os.getenv("COUNSELLING_CORS_ORIGINS", "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    return [
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5003",
        "http://127.0.0.1:5003",
        "https://crtms.in",
        "https://www.crtms.in",
    ]


def get_base_path() -> str:
    """
    Default to the reverse-proxy production path so the deployed app keeps its
    current behavior. Local direct testing can set COUNSELLING_BASE_PATH="".
    """
    raw = os.getenv("COUNSELLING_BASE_PATH", "/counselling").strip()
    if not raw:
        return ""
    trimmed = raw.rstrip("/")
    return trimmed if trimmed.startswith("/") else f"/{trimmed}"


class BasePathCompatibilityMiddleware:
    """
    Allow direct access to /counselling/... without requiring an external reverse
    proxy. This keeps the deployed contract unchanged while making local testing
    work for both prefixed and unprefixed paths.
    """
    def __init__(self, app: ASGIApp, base_path: str):
        self.app = app
        self.base_path = base_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in {"http", "websocket"} and self.base_path:
            path = scope.get("path", "")
            if path == self.base_path or path.startswith(f"{self.base_path}/"):
                rewritten_scope = dict(scope)
                stripped_path = path[len(self.base_path):] or "/"
                rewritten_scope["path"] = stripped_path

                raw_path = scope.get("raw_path")
                if raw_path:
                    raw_prefix = self.base_path.encode()
                    rewritten_scope["raw_path"] = raw_path[len(raw_prefix):] or b"/"

                await self.app(rewritten_scope, receive, send)
                return

        await self.app(scope, receive, send)

# ─────────────────────────────────────────────
# App Setup
# ─────────────────────────────────────────────
app = FastAPI(
    title="CRTMS Counselling API",
    description="Computer-Based Counselling System for Loco Pilots — Central Railway Mumbai Division",
    version="1.0.0"
)

# CORS for local dev and the reverse-proxied production app
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(BasePathCompatibilityMiddleware, base_path=get_base_path())

# ─────────────────────────────────────────────
# Static UI files
# ─────────────────────────────────────────────
app.mount("/ui", StaticFiles(directory="ui", html=True), name="ui")

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
    return RedirectResponse(url=f"{get_base_path()}/ui/" or "/ui/")


@app.get("/health")
def health():
    return {"status": "ok", "service": "counselling"}
