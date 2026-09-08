"""
LinkSnap / Acortador — Redis Cache Module

Provides a DragonflyDB (Redis-compatible) caching layer with graceful
degradation. If DRAGONFLY_URL is empty, all Redis operations are no-ops
and a process-local in-memory store acts as fallback (Slice 3: the
cache-invalidation spec requires invalidation to keep working in
fallback mode, so every write/delete touches BOTH stores).
"""

import time

import redis
from redis.exceptions import RedisError

from backend.app_config import DRAGONFLY_URL

# Connection pool — max 10 connections, 2s socket timeouts
_connection_pool = (
    redis.ConnectionPool.from_url(
        DRAGONFLY_URL,
        max_connections=10,
        socket_timeout=2,
        socket_connect_timeout=2,
    )
    if DRAGONFLY_URL
    else None
)

# Redis client — None if no URL configured (graceful fallback)
redis_client: redis.Redis | None = (
    redis.Redis(connection_pool=_connection_pool) if _connection_pool else None
)

# ── In-memory fallback store ──────────────────────────────────────────────
# Process-local dict used when DRAGONFLY_URL is empty (or Redis is down):
# every cache_set/cache_delete mirrors here so reads and invalidation keep
# working without Dragonfly. Entries honor TTL via monotonic expiry.
# {key: (value, expires_at_monotonic | None)}
_memory_store: dict[str, tuple[str, float | None]] = {}


def _memory_get(key: str) -> str | None:
    """Read from the in-memory fallback store (None on miss/expiry)."""
    entry = _memory_store.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if expires_at is not None and time.monotonic() >= expires_at:
        _memory_store.pop(key, None)
        return None
    return value


def _memory_set(key: str, value: str, ttl: int) -> None:
    """Write to the in-memory fallback store with a TTL (seconds)."""
    expires_at = time.monotonic() + ttl if ttl > 0 else None
    _memory_store[key] = (value, expires_at)


def _memory_delete(key: str) -> None:
    """Remove one key from the in-memory fallback store."""
    _memory_store.pop(key, None)


def _memory_delete_prefix(prefix: str) -> int:
    """Remove all in-memory keys starting with prefix; return count."""
    doomed = [key for key in _memory_store if key.startswith(prefix)]
    for key in doomed:
        del _memory_store[key]
    return len(doomed)


def cache_get(key: str) -> str | None:
    """
    Retrieve a value from cache.

    Tries Dragonfly first (when configured), then the in-memory fallback.
    Returns None on cache miss, connection error, or when both are empty.
    """
    if redis_client is not None:
        try:
            value = redis_client.get(key)
            if value:
                return value.decode() if isinstance(value, bytes) else value
        except RedisError as exc:
            print(f"Cache GET error for key '{key}': {exc}")

    return _memory_get(key)


def cache_set(key: str, value: str, ttl: int) -> None:
    """
    Store a value in cache with a TTL (seconds).

    Mirrors to BOTH Dragonfly (when configured) and the in-memory fallback
    so invalidation stays coherent across stores. Failures are logged,
    never raised. Fully operable when DRAGONFLY_URL is empty.
    """
    if redis_client is not None:
        try:
            redis_client.setex(key, ttl, value)
        except RedisError as exc:
            print(f"Cache SET error for key '{key}': {exc}")

    _memory_set(key, value, ttl)


def cache_status() -> tuple[bool, str]:
    """
    Check if DragonflyDB is reachable.

    Returns (connected: bool, message: str) where message is a
    human-readable status string for logging and display.
    """
    if redis_client is None:
        return False, "DragonflyDB no configurado (DRAGONFLY_URL vacío)"

    try:
        redis_client.ping()
        return True, "DragonflyDB conectado"
    except RedisError as exc:
        return False, f"DragonflyDB no accesible: {exc}"


def cache_delete(key: str) -> None:
    """
    Delete one key from BOTH Dragonfly (when configured) and the
    in-memory fallback store. Errors are logged, never raised.
    """
    if redis_client is not None:
        try:
            redis_client.delete(key)
        except RedisError as exc:
            print(f"Cache DELETE error for key '{key}': {exc}")

    _memory_delete(key)


def _redis_delete_prefix(prefix: str) -> int:
    """Delete all Dragonfly keys starting with prefix via SCAN. No-op
    (return 0) when Redis is unconfigured; errors swallowed (TTL heals)."""
    if redis_client is None:
        return 0
    try:
        count = 0
        for key in redis_client.scan_iter(match=f"{prefix}*"):
            redis_client.delete(key)
            count += 1
        return count
    except RedisError as exc:
        print(f"Cache SCAN-DELETE error for prefix '{prefix}': {exc}")
        return 0


def invalidate_link_cache(codigo: str) -> None:
    """
    Invalidate every cached entry for a short code (Slice 3 data layer).

    Called from Django post_save/post_delete signals on Link — fires on
    ALL write paths (admin, shell, management commands). Deletes:
      - davelink:redirect:{code}  (302 target cache, TTL 3600)
      - davelink:stats:{code}     (stats JSON cache, TTL 30)
      - davelink:qr:{code}:*      (one key per QR config hash, TTL 3600)

    QR keys need scan/delete-by-prefix (fakeredis in tests, real Redis
    SCAN in prod — Dragonfly supports SCAN). Operates on both stores so
    the DRAGONFLY_URL-empty in-memory fallback invalidates correctly.
    Deleting a missing key is a cheap no-op, so invalidation is
    unconditional (no dirty-field checks — DEL is cheaper than diffing).
    """
    cache_delete(f"davelink:redirect:{codigo}")
    cache_delete(f"davelink:stats:{codigo}")
    prefix = f"davelink:qr:{codigo}:"
    _redis_delete_prefix(prefix)
    _memory_delete_prefix(prefix)
