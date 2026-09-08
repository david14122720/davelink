"""Slice 3 (task 3.1): cache_delete + invalidate_link_cache + memory fallback."""

import time

import pytest

import backend.fastapi_app.cache as cache_module
from backend.fastapi_app.cache import (
    cache_delete,
    cache_get,
    cache_set,
    invalidate_link_cache,
)


@pytest.fixture(autouse=True)
def _clean_memory_store():
    cache_module._memory_store.clear()
    yield
    cache_module._memory_store.clear()


def test_cache_set_get_roundtrip_fake_redis(fake_redis):
    cache_set("davelink:redirect:abc123", '{"id": 1}', ttl=3600)
    assert cache_get("davelink:redirect:abc123") == '{"id": 1}'
    # Mirrored to the in-memory store as well (coherence across stores)
    assert cache_module._memory_store["davelink:redirect:abc123"][0] == '{"id": 1}'


def test_cache_delete_removes_from_both_stores(fake_redis):
    cache_set("davelink:stats:abc123", "{}", ttl=30)
    cache_delete("davelink:stats:abc123")
    assert cache_get("davelink:stats:abc123") is None
    assert fake_redis.get("davelink:stats:abc123") is None
    assert "davelink:stats:abc123" not in cache_module._memory_store


def test_invalidate_link_cache_purges_redirect_stats_and_all_qr(fake_redis):
    code, other = "inv001", "inv999"
    cache_set(f"davelink:redirect:{code}", "{}", ttl=3600)
    cache_set(f"davelink:stats:{code}", "{}", ttl=30)
    cache_set(f"davelink:qr:{code}:a1b2c3d4", "qr1", ttl=3600)
    cache_set(f"davelink:qr:{code}:e5f6a7b8", "qr2", ttl=3600)
    # Unrelated code's keys must survive
    cache_set(f"davelink:redirect:{other}", "{}", ttl=3600)
    cache_set(f"davelink:qr:{other}:a1b2c3d4", "qr-other", ttl=3600)

    invalidate_link_cache(code)

    assert cache_get(f"davelink:redirect:{code}") is None
    assert cache_get(f"davelink:stats:{code}") is None
    assert cache_get(f"davelink:qr:{code}:a1b2c3d4") is None
    assert cache_get(f"davelink:qr:{code}:e5f6a7b8") is None
    assert fake_redis.keys(f"davelink:qr:{code}:*") == []
    assert cache_get(f"davelink:redirect:{other}") == "{}"
    assert cache_get(f"davelink:qr:{other}:a1b2c3d4") == "qr-other"


def test_invalidate_unknown_code_is_noop(fake_redis):
    # Deleting missing keys must not raise (DEL is cheap unconditionally)
    invalidate_link_cache("no-such-code")


def test_memory_fallback_without_redis(monkeypatch):
    """DRAGONFLY_URL empty → redis_client None → memory-only path."""
    monkeypatch.setattr(cache_module, "redis_client", None)
    cache_set("davelink:redirect:mem01", '{"id": 7}', ttl=3600)
    assert cache_get("davelink:redirect:mem01") == '{"id": 7}'

    cache_set("davelink:stats:mem01", "{}", ttl=30)
    cache_set("davelink:qr:mem01:deadbeef", "qr", ttl=3600)
    invalidate_link_cache("mem01")
    assert cache_get("davelink:redirect:mem01") is None
    assert cache_get("davelink:stats:mem01") is None
    assert cache_get("davelink:qr:mem01:deadbeef") is None


def test_memory_store_honors_ttl(monkeypatch):
    monkeypatch.setattr(cache_module, "redis_client", None)
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    cache_set("davelink:redirect:ttl01", "v", ttl=60)
    assert cache_get("davelink:redirect:ttl01") == "v"
    now[0] += 61.0
    assert cache_get("davelink:redirect:ttl01") is None
