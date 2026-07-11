"""
LinkSnap / Acortador — SQLAlchemy Database Engine & Session

Provides the shared SQLAlchemy engine and session factory used by FastAPI.
Django uses its own ORM (separate connection pool) pointed at the same DB.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app_config import DATABASE_URL

# ── Engine ─────────────────────────────────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # verify connections before using them
    pool_size=5,
    max_overflow=10,
    echo=False,               # set to True for SQL debugging
)

# ── Session Factory ─────────────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Dependency for FastAPI ─────────────────────────────────────────────────
def get_db():
    """FastAPI dependency that yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
