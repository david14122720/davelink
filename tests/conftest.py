import pytest
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

# Path setup
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.fastapi_app.main import app
from backend.shared.database import get_db
from backend.shared.models import Base

# In-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session")
def setup_database():
    """Create tables for the session."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session(setup_database):
    """Provides a clean session per test."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def client(db_session, monkeypatch):
    """FastAPI TestClient with overridden database dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    # Slice 2: the redirect analytics BackgroundTask opens its OWN session
    # (request `get_db` is torn down before it runs). Point that factory at
    # the test engine so background writes land in sqlite, never live PG.
    import backend.fastapi_app.routes.redirect as redirect_module

    monkeypatch.setattr(redirect_module, "SessionLocal", TestingSessionLocal)

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def isolated_memory_limiter():
    """Swap the shared limiter's storage for a fresh in-memory backend.

    Makes rate-limit tests deterministic and Dragonfly-free: fixed-window
    counters live in-process and start empty for every test. Restores the
    production storage afterwards.
    """
    from limits.strategies import STRATEGIES

    from limits.storage import MemoryStorage

    import backend.fastapi_app.rate_limit as rate_limit_module

    limiter = rate_limit_module.limiter
    old_storage, old_strategy = limiter._storage, limiter._limiter
    old_dead = limiter._storage_dead
    memory = MemoryStorage()
    limiter._storage = memory
    limiter._limiter = STRATEGIES["fixed-window"](memory)
    limiter._storage_dead = False
    try:
        yield limiter
    finally:
        limiter._storage = old_storage
        limiter._limiter = old_strategy
        limiter._storage_dead = old_dead


@pytest.fixture(scope="session", autouse=True)
def _purge_test_owned_redirect_keys():
    """Delete stale redirect/stats-cache keys left by previous test sessions.

    Tests run against the shared live Dragonfly and cache entries by
    deterministic code (`statvia`, `nolimit`, ...). A stale entry maps
    the code to a previous session's sqlite row id, misattributing
    analytics and breaking repeat runs. Only keys whose payload URL
    contains `example.com` (i.e. provably test-created) are removed;
    anything else on the shared server is left untouched. Slice 3
    replaces this with full FakeRedis isolation.
    """
    import json

    import backend.fastapi_app.cache as cache_module

    client = cache_module.redis_client
    if client is None:
        return
    try:
        redirect_keys = client.keys("davelink:redirect:*") or []
        stats_keys = client.keys("davelink:stats:*") or []
    except Exception:
        return
    for key in redirect_keys:
        try:
            payload = json.loads(client.get(key) or b"{}")
        except Exception:
            continue
        if "example.com" in payload.get("url_original", ""):
            try:
                client.delete(key)
            except Exception:
                pass
    for key in stats_keys:
        try:
            payload = json.loads(client.get(key) or b"{}")
        except Exception:
            continue
        if "example.com" in payload.get("original_url", ""):
            try:
                client.delete(key)
            except Exception:
                pass


@pytest.fixture
def fake_redis(monkeypatch):
    """FakeRedis client patched over the cache module's redis_client.

    Slice 2+ uses this for Redis-free cache/limiter tests. Patches
    `backend.fastapi_app.cache.redis_client` so `cache_get`/`cache_set`
    operate against in-memory fakeredis (bytes mode, matching real
    redis client decode behavior in `cache_get`).
    """
    import fakeredis

    import backend.fastapi_app.cache as cache_module

    fake = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(cache_module, "redis_client", fake)
    # Slice 3: cache mirrors every write to the in-memory fallback store,
    # so reset it too — otherwise keys leak across tests using fake_redis.
    cache_module._memory_store.clear()
    yield fake
    fake.flushall()
    cache_module._memory_store.clear()
