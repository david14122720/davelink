"""
LinkSnap / Acortador — Redis Cache Module

Provides a DragonflyDB (Redis-compatible) caching layer with graceful
degradation. If DRAGONFLY_URL is empty, all operations are no-ops.
"""

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


def cache_get(key: str) -> str | None:
    """
    Retrieve a value from cache.

    Returns None on cache miss, connection error, or when cache is disabled.
    """
    if redis_client is None:
        return None

    try:
        value = redis_client.get(key)
        return value.decode() if value else None
    except RedisError as exc:
        print(f"Cache GET error for key '{key}': {exc}")
        return None


def cache_set(key: str, value: str, ttl: int) -> None:
    """
    Store a value in cache with a TTL (seconds).

    Logs a warning on failure. No-op when cache is disabled.
    """
    if redis_client is None:
        return

    try:
        redis_client.setex(key, ttl, value)
    except RedisError as exc:
        print(f"Cache SET error for key '{key}': {exc}")


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
