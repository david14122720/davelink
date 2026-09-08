"""
LinkSnap / Acortador — Rate Limiter Configuration (Slice 2 perf core)

Provides a shared Limiter instance used by both the FastAPI app
(setup) and route decorators. Using a single shared instance
ensures that rate limit counters are consistent across all routes.

Storage: Dragonfly (Redis-compatible) via ``storage_uri=DRAGONFLY_URL``
so all workers share counters. When ``DRAGONFLY_URL`` is empty/unset,
or Dragonfly is unreachable at init, the limiter automatically falls
back to per-process in-memory storage (``memory://``) instead of
crashing at import.

Mid-flight storage errors are intentionally fail-closed (500), per
design — only the init-time fallback degrades to memory.

Rate-limit response headers (``X-RateLimit-Limit/Remaining/Reset``)
are enabled so clients can back off (see rate-limiting spec).
"""

import logging
import os

import redis
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

MEMORY_URI = "memory://"


def _dragonfly_reachable(url: str) -> bool:
    """Ping Dragonfly with a short timeout; never raise."""
    try:
        probe = redis.Redis.from_url(
            url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        probe.ping()
        return True
    except Exception as exc:
        logger.warning(
            "Rate-limit storage unreachable (%s); using in-memory fallback", exc
        )
        return False


def resolve_limiter_storage_uri(raw_url: str | None = None) -> str:
    """
    Pick the limiter storage URI.

    - Empty/unset URL → ``memory://`` (per-process counters).
    - Reachable Dragonfly URL → the URL itself (shared counters).
    - Unreachable URL → ``memory://`` with a warning.

    ``raw_url=None`` (default) reads ``DRAGONFLY_URL`` from the
    environment at call time so tests can ``monkeypatch.setenv`` it.
    """
    url = (raw_url if raw_url is not None else os.getenv("DRAGONFLY_URL", "") or "").strip()
    if not url:
        return MEMORY_URI
    return url if _dragonfly_reachable(url) else MEMORY_URI


def build_limiter(storage_uri: str | None = None) -> Limiter:
    """
    Build a Limiter with shared storage + init-time memory fallback.

    ``storage_uri=None`` resolves from ``DRAGONFLY_URL``; pass an explicit
    URI (or ``""``) to force shared storage or the memory fallback —
    the limiter fallback tests use this seam.
    """
    original_isfile = os.path.isfile
    try:
        # Keep slowapi from touching an unreadable sandbox .env file.
        os.path.isfile = lambda path: False if path == ".env" else original_isfile(path)
        return Limiter(
            key_func=get_remote_address,
            headers_enabled=True,
            storage_uri=resolve_limiter_storage_uri(storage_uri),
        )
    finally:
        os.path.isfile = original_isfile


limiter = build_limiter()
