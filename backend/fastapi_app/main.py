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
from fastapi.middleware.gzip import GZipMiddleware
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


class NoPngGzipMiddleware(GZipMiddleware):
    """GZip everything except pre-compressed PNG payloads.

    Spec (redirect-performance): JSON and SVG responses MUST be
    gzip-compressed; PNG MUST NOT be double-compressed. Starlette's
    stock middleware only excludes ``text/event-stream``, so ``.png``
    binary routes (Slice 4: ``GET /api/qr/{code}.png``) bypass
    compression entirely here.
    """

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and (scope.get("path") or "").lower().endswith(".png"):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


# GZip for JSON/SVG (spec); PNG excluded above (no double-compress).
app.add_middleware(NoPngGzipMiddleware, minimum_size=500)

# Rate limiting setup
app.state.limiter = limiter


async def rate_limit_handler(request, exc: RateLimitExceeded):
    """Custom 429 handler that adds Retry-After header and detail field."""
    from fastapi.responses import JSONResponse

    # Calculate retry-after from limit info stored in request state
    retry_after = 1  # default for "10/second" limit
    limit_amount = None
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
        # Surface the quota alongside Retry-After (rate-limiting spec headers)
        try:
            item = getattr(limit_obj, "limit", limit_obj)
            limit_amount = int(getattr(item, "amount", str(item).split()[0]))
        except (ValueError, TypeError, IndexError, AttributeError):
            limit_amount = None

    headers = {"Retry-After": str(retry_after)}
    if limit_amount is not None:
        headers["X-RateLimit-Limit"] = str(limit_amount)
        headers["X-RateLimit-Remaining"] = "0"
        headers["X-RateLimit-Reset"] = str(retry_after)

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Límite de solicitudes excedido. Intenta de nuevo.",
        },
        headers=headers,
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
def cache_status_endpoint():
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
