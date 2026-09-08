"""
LinkSnap / Acortador — SQLAlchemy Database Engine & Session

Provides the shared SQLAlchemy engine and session factory used by FastAPI.
Django uses its own ORM (separate connection pool) pointed at the same DB.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app_config import DATABASE_URL

# ── Engine ─────────────────────────────────────────────────────────────────
# Pool right-sized per worker (Slice 2 perf core): 4 persistent connections
# + 6 overflow. Sized together with the sync-`def` (threadpool) handlers so
# concurrent cache-miss redirects can't exhaust DB capacity.
# SQLite (local/dev) has no pool knobs and uses a single shared connection.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,               # set to True for SQL debugging
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,       # verify connections before using them
        pool_size=4,
        max_overflow=6,
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
