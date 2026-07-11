"""
LinkSnap / Acortador — FastAPI Database Dependency

Re-exports the shared engine and session factory so FastAPI
routes can do `from fastapi_app.database import get_db`.
"""

from backend.shared.database import SessionLocal, engine, get_db

__all__ = ["SessionLocal", "engine", "get_db"]
