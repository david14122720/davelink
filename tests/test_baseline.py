"""
Slice 1 baseline smoke tests.

End-to-end smoke through the three endpoint families (shorten →
redirect → QR) plus the FakeRedis fixture wiring. Detailed edge cases
live in test_api.py / test_qr.py / test_stats.py; this file only proves
the environment can serve the core flows.
"""

from backend.fastapi_app import cache as cache_module


def test_baseline_shorten_then_redirect(client, db_session):
    """Shorten a URL, then follow the redirect (302 to original URL)."""
    long_url = "https://example.com/baseline-smoke"
    resp = client.post("/api/shorten", json={"url": long_url})
    assert resp.status_code == 200
    code = resp.json()["code"]
    assert code

    redir = client.get(f"/{code}", follow_redirects=False)
    assert redir.status_code == 302
    assert redir.headers["location"] == long_url


def test_baseline_qr_for_existing_code(client, db_session):
    """QR endpoint serves a QR payload for a code created via shorten."""
    resp = client.post("/api/shorten", json={"url": "https://example.com/baseline-qr"})
    assert resp.status_code == 200
    code = resp.json()["code"]

    qr = client.get(f"/api/qr/{code}")
    assert qr.status_code == 200
    assert qr.json()["qr_code"]


def test_baseline_fake_redis_fixture_wiring(client, fake_redis):
    """FakeRedis fixture patches cache.redis_client; set/get round-trips."""
    assert cache_module.redis_client is fake_redis
    cache_module.cache_set("baseline:key", "baseline:value", ttl=60)
    assert cache_module.cache_get("baseline:key") == "baseline:value"
