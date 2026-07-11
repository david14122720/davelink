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
from slowapi.errors import RateLimitExceeded

from backend.fastapi_app.cache import cache_status
from backend.fastapi_app.rate_limit import limiter

# ── Django setup ──────────────────────────────────────────────────────────
backend_dir = Path(__file__).parent.parent
django_app_dir = backend_dir / "django_app"
sys.path.insert(0, str(django_app_dir))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application

django_wsgi_app = get_wsgi_application()

# ── FastAPI app ────────────────────────────────────────────────────────────
from backend.fastapi_app.routes import shorten, redirect, stats, qr

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

# Rate limiting setup
app.state.limiter = limiter


async def rate_limit_handler(request, exc: RateLimitExceeded):
    """Custom 429 handler that adds Retry-After header and detail field."""
    from fastapi.responses import JSONResponse

    # Calculate retry-after from limit info stored in request state
    retry_after = 1  # default for "10/second" limit
    limit_info = getattr(request.state, "view_rate_limit", None)
    if limit_info:
        limit_obj, _ = limit_info
        # Parse the limit window from the limit string (e.g. "10 per 1 second")
        limit_str = str(getattr(limit_obj, "limit", ""))
        parts = limit_str.split(" per ")
        if len(parts) == 2:
            try:
                retry_after = int(parts[1].split()[0])
            except (ValueError, IndexError):
                pass

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Límite de solicitudes excedido. Intenta de nuevo.",
        },
        headers={"Retry-After": str(retry_after)},
    )


app.add_exception_handler(RateLimitExceeded, rate_limit_handler)


# ── Startup ──────────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup_log_cache_status():
    """Log DragonflyDB connection status on startup."""
    connected, message = cache_status()
    status = "✅" if connected else "⚠️"
    print(f"[Cache] {status} {message}")


# API routes
@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "daveLinK"}


@app.get("/api/cache/status")
async def cache_status_endpoint():
    """Return DragonflyDB connection status."""
    connected, message = cache_status()
    return {"connected": connected, "message": message}

app.include_router(shorten.router, tags=["shorten"])
app.include_router(stats.router, tags=["stats"])
app.include_router(qr.router, tags=["qr"])
app.include_router(redirect.router, tags=["redirect"])

# ── Django admin (via WSGI) ────────────────────────────────────────────────
app.mount("/admin", WSGIMiddleware(django_wsgi_app), name="admin")

# ── Django admin static files ──────────────────────────────────────────────
django_static = django_app_dir / "staticfiles"
if django_static.exists():
    app.mount("/static", StaticFiles(directory=str(django_static)), name="static")

# ── Frontend (catch-all — goes last) ──────────────────────────────────────
frontend_dir = backend_dir.parent / "frontend"
if frontend_dir.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(frontend_dir), html=True),
        name="frontend",
    )
