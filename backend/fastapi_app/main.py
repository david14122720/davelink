"""
daveLinK — FastAPI Application
Main entry point for the API server.
"""

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Add backend directory to path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from fastapi_app.routes import shorten, redirect, stats, qr

# Create FastAPI app
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

# Include routers
app.include_router(shorten.router, tags=["shorten"])
app.include_router(redirect.router, tags=["redirect"])
app.include_router(stats.router, tags=["stats"])
app.include_router(qr.router, tags=["qr"])

# Mount frontend static files
frontend_dir = Path(__file__).parent.parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "daveLinK"}
