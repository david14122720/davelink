"""
daveLinK — FastAPI Application
Main entry point for the API server.
Also serves Django admin via WSGI middleware for administration.
"""

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from a2wsgi import WSGIMiddleware
from fastapi.staticfiles import StaticFiles

# ── Django setup (must be before any Django-related imports) ──────────────
backend_dir = Path(__file__).parent.parent
django_app_dir = backend_dir / "django_app"
sys.path.insert(0, str(django_app_dir))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application

django_wsgi_app = get_wsgi_application()

# ── FastAPI app ────────────────────────────────────────────────────────────
sys.path.insert(0, str(backend_dir))

from fastapi_app.routes import shorten, redirect, stats, qr

app = FastAPI(
    title="daveLinK API",
    description="URL Shortener with QR Codes and Analytics",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(shorten.router, tags=["shorten"])
app.include_router(redirect.router, tags=["redirect"])
app.include_router(stats.router, tags=["stats"])
app.include_router(qr.router, tags=["qr"])

# ── Django admin (via WSGI) ────────────────────────────────────────────────
app.mount("/admin", WSGIMiddleware(django_wsgi_app), name="admin")

# ── Django admin static files (colectados via collectstatic) ───────────────
django_static = django_app_dir / "staticfiles"
if django_static.exists():
    app.mount("/static", StaticFiles(directory=str(django_static)), name="static")

# ── Frontend (catch-all — va último) ──────────────────────────────────────
frontend_dir = backend_dir.parent / "frontend"
if frontend_dir.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(frontend_dir), html=True),
        name="frontend",
    )


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "daveLinK"}
