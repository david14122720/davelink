"""Verify-remediation gap tests (change: perf-hardening-and-full-qr-customization).

Closes the 5 WARNINGs from openspec/changes/.../verify-report.md with
runtime proofs. Each test name maps to its WARNING in the docstring.
"""

import base64
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.shared.models import Link

LONG_URL = "https://example.com/verify-gaps-original-long-url?x=1"


def _make_link(db_session, code, url=LONG_URL):
    link = Link(codigo=code, url_original=url)
    db_session.add(link)
    db_session.commit()
    return link


def _capture_add_data(monkeypatch):
    """Wrap qrcode.QRCode.add_data, recording every payload fed to it."""
    import qrcode

    captured = []
    original = qrcode.QRCode.add_data

    def wrapper(self, data, *args, **kwargs):
        captured.append(data)
        return original(self, data, *args, **kwargs)

    monkeypatch.setattr(qrcode.QRCode, "add_data", wrapper)
    return captured


def _assert_original_only(captured):
    """Every payload fed to the QR engine must be the ORIGINAL long URL."""
    assert captured, "expected at least one QR payload to be captured"
    for payload in captured:
        assert payload == LONG_URL, f"QR encoded unexpected payload: {payload!r}"


# ── WARNING 2: QR encodes ORIGINAL long URL (runtime payload proof) ──────────


def test_qr_png_encodes_original_url(client, db_session, monkeypatch,
                                     fake_redis, isolated_memory_limiter):
    """GET /api/qr/{code}.png feeds the ORIGINAL long URL to the QR engine."""
    _make_link(db_session, "gapqrpng")
    captured = _capture_add_data(monkeypatch)
    response = client.get("/api/qr/gapqrpng.png")
    assert response.status_code == 200, response.text
    _assert_original_only(captured)


def test_qr_svg_encodes_original_url(client, db_session, monkeypatch,
                                     fake_redis, isolated_memory_limiter):
    """GET /api/qr/{code}.svg feeds the ORIGINAL long URL to the QR engine."""
    _make_link(db_session, "gapqrsvg")
    captured = _capture_add_data(monkeypatch)
    response = client.get("/api/qr/gapqrsvg.svg")
    assert response.status_code == 200, response.text
    _assert_original_only(captured)


def test_qr_legacy_json_encodes_original_url(client, db_session, monkeypatch,
                                             fake_redis, isolated_memory_limiter):
    """Legacy GET /api/qr/{code} feeds the ORIGINAL long URL (never short)."""
    _make_link(db_session, "gapqrjson")
    captured = _capture_add_data(monkeypatch)
    response = client.get("/api/qr/gapqrjson")
    assert response.status_code == 200, response.text
    assert base64.b64decode(response.json()["qr_code"])[:8] == b"\x89PNG\r\n\x1a\n"
    _assert_original_only(captured)


def test_qr_legacy_generate_encodes_original_url(client, db_session, monkeypatch,
                                                 fake_redis, isolated_memory_limiter):
    """Legacy POST /api/qr/generate feeds the ORIGINAL long URL (never short)."""
    _make_link(db_session, "gapqrgen")
    captured = _capture_add_data(monkeypatch)
    response = client.post(
        "/api/qr/generate", json={"code": "gapqrgen", "config": {}})
    assert response.status_code == 200, response.text
    _assert_original_only(captured)


def test_qr_raw_encodes_original_url(client, monkeypatch,
                                     fake_redis, isolated_memory_limiter):
    """POST /api/qr/raw feeds the submitted URL itself (no DB, no short URL)."""
    captured = _capture_add_data(monkeypatch)
    response = client.post(
        "/api/qr/raw", json={"url": LONG_URL, "config": {}})
    assert response.status_code == 200, response.text
    _assert_original_only(captured)


# ── WARNING 3: SVG gzip-compressible, PNG untouched ───────────────────────────


def test_svg_is_gzipped_and_valid(client, db_session,
                                  fake_redis, isolated_memory_limiter):
    """GET .svg with gzip → Content-Encoding: gzip + valid <svg after decode."""
    _make_link(db_session, "gapgapsvg")
    response = client.get(
        "/api/qr/gapgapsvg.svg", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200, response.text
    assert response.headers.get("content-encoding") == "gzip"
    assert len(response.content) > 500  # over the GZip minimum_size
    assert b"<svg" in response.content  # httpx auto-decompresses -> still valid


def test_png_still_not_gzipped(client, db_session,
                               fake_redis, isolated_memory_limiter):
    """GET .png with gzip → NO Content-Encoding (no double-compression)."""
    _make_link(db_session, "gapgappng")
    response = client.get(
        "/api/qr/gapgappng.png", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200, response.text
    assert response.headers.get("content-encoding") is None
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


# ── WARNING 4: shared limiter storage across workers ─────────────────────────


def test_limiter_storage_shared_across_instances():
    """Two limits-library storages on the same Dragonfly share counters.

    Honest runtime proof for the rate-limiting "shared across workers"
    scenario: storage A and storage B are independent client instances
    against the same server (the closest in-test equivalent of two
    workers / a restart — instance B is a brand-new connection, so this
    also covers "persists across restart" at the storage level).

    Limits of this proof (documented, not hidden): it exercises the
    limits storage layer directly, not two live uvicorn workers; a true
    multi-process restart test is out of scope for this suite.
    """
    import os

    import redis
    from limits import parse
    from limits.storage import RedisStorage
    from limits.strategies import FixedWindowRateLimiter

    url = (os.getenv("DRAGONFLY_URL", "") or "").strip()
    if not url:
        pytest.skip("DRAGONFLY_URL empty — no shared server to prove against")
    try:
        redis.Redis.from_url(
            url, socket_connect_timeout=2, socket_timeout=2).ping()
    except Exception as exc:
        pytest.skip(f"shared Dragonfly unreachable: {exc}")

    key = f"verify-gaps-shared-{uuid.uuid4().hex[:12]}"
    item = parse("3/minute")
    storage_a, storage_b = RedisStorage(url), RedisStorage(url)
    try:
        hits_a = [FixedWindowRateLimiter(storage_a).hit(item, key)
                  for _ in range(3)]
        assert hits_a == [True, True, True]
        # Fourth hit through the OTHER instance must see A's counters.
        assert FixedWindowRateLimiter(storage_b).hit(item, key) is False
        stats = FixedWindowRateLimiter(storage_a).get_window_stats(item, key)
        assert stats.remaining == 0
    finally:
        for storage in (storage_a, storage_b):
            try:
                for k in storage.storage.keys(f"LIMITS*{key}*"):
                    storage.storage.delete(k)
            except Exception:
                pass


# ── WARNING 5: concurrent redirects ───────────────────────────────────────────


def test_concurrent_redirect_burst_all_302(db_session, monkeypatch,
                                           fake_redis):
    """10 parallel TestClients × 20 requests → all 302, no corruption.

    Real runtime concurrency proof (extends the sequential burst smoke):
    one TestClient per thread via ThreadPoolExecutor, cache warmed first
    so the burst exercises the cached hot path. "No corruption" = every
    response is 302 with the exact original Location and zero 5xx.
    """
    from fastapi.testclient import TestClient

    from backend.fastapi_app.main import app
    from backend.shared.database import get_db
    from conftest import TestingSessionLocal
    import backend.fastapi_app.routes.redirect as redirect_module

    code = f"concbrst{uuid.uuid4().hex[:8]}"
    db_session.add(Link(codigo=code, url_original=LONG_URL))
    db_session.commit()

    monkeypatch.setattr(redirect_module, "SessionLocal", TestingSessionLocal)

    def override_get_db():
        thread_session = TestingSessionLocal()
        try:
            yield thread_session
        finally:
            thread_session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as warm:
            first = warm.get(f"/{code}", follow_redirects=False)
            assert first.status_code == 302

        def hit(_i):
            with TestClient(app, raise_server_exceptions=False) as thread_client:
                resp = thread_client.get(f"/{code}", follow_redirects=False)
                return resp.status_code, resp.headers.get("location")

        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(hit, range(20)))
    finally:
        app.dependency_overrides.clear()

    assert len(results) == 20
    for status, location in results:
        assert status == 302, f"concurrent redirect failed: {status}"
        assert location == LONG_URL, f"corrupted Location: {location!r}"
    assert not any(s >= 500 for s, _ in results)
