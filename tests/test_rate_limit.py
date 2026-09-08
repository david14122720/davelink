"""
Tests for rate limiting behavior.

The app uses slowapi with a 10/second limit on /api/* endpoints.
The redirect endpoint (GET /{code}) is NOT rate-limited.

Note: Since other tests may have consumed some of the rate limit budget,
these tests send requests until a 429 is received rather than expecting
an exact count.
"""

import pytest


def test_shorten_rate_limit_eventually_returns_429(client, isolated_memory_limiter):
    """Verify that sending enough rapid requests to shorten eventually triggers 429"""
    url_template = "https://example.com/ratelimit-{}"

    last_status = None
    codes_created = 0

    for i in range(25):
        response = client.post(
            "/api/shorten",
            json={"url": url_template.format(i)},
        )
        last_status = response.status_code
        if response.status_code == 200:
            codes_created += 1
        elif response.status_code == 429:
            break

    assert last_status == 429, (
        f"Rate limit was never triggered after 25 requests. "
        f"Created {codes_created} codes, last status: {last_status}"
    )


def test_rate_limit_response_has_retry_after_and_detail(client, isolated_memory_limiter):
    """Verify 429 response includes Retry-After header and detail field"""
    url_template = "https://example.com/retryafter-{}"

    response_429 = None
    for i in range(25):
        resp = client.post(
            "/api/shorten",
            json={"url": url_template.format(i)},
        )
        if resp.status_code == 429:
            response_429 = resp
            break

    assert response_429 is not None, "Rate limit was never triggered"
    assert response_429.status_code == 429

    data = response_429.json()
    assert "detail" in data, "429 response should have detail field"

    # Check Retry-After header
    retry_after = response_429.headers.get("retry-after")
    assert retry_after is not None, "429 response should have Retry-After header"
    retry_value = float(retry_after)
    assert retry_value >= 0, f"Retry-After should be >= 0, got {retry_value}"


def test_redirect_not_rate_limited(client, db_session):
    """Verify redirect endpoint bypasses rate limiting (no decorator)"""
    from backend.shared.models import Link

    code = "nolimit"
    link = Link(codigo=code, url_original="https://example.com/no-rate-limit")
    db_session.add(link)
    db_session.commit()

    # Send 20 rapid redirect requests — none should be 429
    for _ in range(20):
        response = client.get(f"/{code}", follow_redirects=False)
        assert response.status_code == 302, (
            f"Redirect should not be rate limited, got {response.status_code}"
        )


def test_stats_rate_limited(client, db_session, fake_redis, isolated_memory_limiter):
    """Verify stats endpoint is rate limited.

    Deterministic by construction: in-memory limiter storage (fresh per
    test) + fakeredis cache + sqlite mean all 20 sequential requests land
    inside one fixed 10/second window, so #11+ must 429. No live-Dragonfly
    dependence, no cross-test budget leakage.
    """
    from backend.shared.models import Link

    code = "statslimit"
    link = Link(codigo=code, url_original="https://example.com/stats-limit")
    db_session.add(link)
    db_session.commit()

    last_status = None
    for i in range(20):
        response = client.get(f"/api/stats/{code}")
        last_status = response.status_code
        if last_status == 429:
            break

    assert last_status == 429, (
        "Stats endpoint was never rate limited after 20 requests"
    )


def test_rate_limit_headers_present(client, db_session, fake_redis, isolated_memory_limiter):
    """Verify served responses carry X-RateLimit-Limit/Remaining/Reset."""
    from backend.shared.models import Link

    code = "hdrlimit"
    link = Link(codigo=code, url_original="https://example.com/headers-limit")
    db_session.add(link)
    db_session.commit()

    response = client.get(f"/api/stats/{code}")
    assert response.status_code == 200
    assert response.headers.get("x-ratelimit-limit") == "10"
    assert response.headers.get("x-ratelimit-remaining") is not None
    assert response.headers.get("x-ratelimit-reset") is not None


def test_limiter_falls_back_to_memory_when_url_empty():
    """Empty DRAGONFLY_URL → per-process in-memory limiting still 429s."""
    import backend.fastapi_app.rate_limit as rate_limit_module
    from fastapi import FastAPI, Request, Response
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from limits.storage import MemoryStorage
    from slowapi.errors import RateLimitExceeded

    fallback = rate_limit_module.build_limiter(storage_uri="")
    assert isinstance(fallback._storage, MemoryStorage)

    tiny = FastAPI()
    tiny.state.limiter = fallback

    async def _too_many(request, exc):
        return JSONResponse(status_code=429, content={"detail": "slow down"})

    tiny.add_exception_handler(RateLimitExceeded, _too_many)

    @tiny.get("/ping")
    @fallback.limit("5/second")
    def ping(request: Request, response: Response):
        return {"ok": True}

    with TestClient(tiny) as tiny_client:
        first = tiny_client.get("/ping")
        assert first.status_code == 200
        assert first.headers.get("x-ratelimit-limit") == "5"

        statuses = [tiny_client.get("/ping").status_code for _ in range(7)]

    assert 429 in statuses, f"memory fallback never limited: {statuses}"


def test_resolve_storage_uri_empty_and_unreachable(monkeypatch):
    """Resolver: empty URL → memory; unreachable host → memory (no raise)."""
    import backend.fastapi_app.rate_limit as rate_limit_module

    assert rate_limit_module.resolve_limiter_storage_uri("") == "memory://"
    assert rate_limit_module.resolve_limiter_storage_uri("   ") == "memory://"

    monkeypatch.setattr(rate_limit_module, "_dragonfly_reachable", lambda url: False)
    assert (
        rate_limit_module.resolve_limiter_storage_uri("redis://example.invalid:6379/0")
        == "memory://"
    )


def test_dragonfly_probe_returns_false_for_closed_port():
    """_dragonfly_reachable against a closed loopback port → False, fast."""
    import time

    import backend.fastapi_app.rate_limit as rate_limit_module

    start = time.perf_counter()
    assert rate_limit_module._dragonfly_reachable("redis://127.0.0.1:6390/0") is False
    assert time.perf_counter() - start < 5

