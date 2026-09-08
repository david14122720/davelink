"""
Slice 2: redirect critical path — threadpool handlers, pool sizing.

- Sync-`def` handlers run DB/cache/Pillow I/O in the Starlette threadpool
  instead of blocking the event loop (redirect-performance spec). slowapi
  wraps sync handlers in a plain `def` wrapper, so asserting "not a
  coroutine function" fails pre-change and passes post-change.
- DB pool right-sized per worker (4 persistent + 6 overflow).
- Burst smoke: N rapid sequential redirects all 302 with one analytics
  row each (true 40-way timing concurrency is prod-PG-only; the tasks
  table marks this slice's runtime harness N/A).
"""

import inspect

from sqlalchemy.pool import QueuePool

from backend.shared.database import engine


def _all_sync_endpoints():
    """(route-id, endpoint) for every Slice 2 sync-I/O handler.

    Router routes are read off the APIRouter objects directly: this
    FastAPI version defers `include_router` until startup
    (`_IncludedRouter` placeholders in `app.routes`), so `app.routes`
    is empty for API paths on a bare import.
    """
    from backend.fastapi_app import main as main_module
    from backend.fastapi_app.routes import qr, redirect, shorten, stats

    found = []
    for router in (redirect.router, stats.router, shorten.router, qr.router):
        for route in router.routes:
            methods = sorted(getattr(route, "methods", set()) or [])
            found.append((f"{'/'.join(methods)} {route.path}", route.endpoint))
    found.append(("GET /api/cache/status", main_module.cache_status_endpoint))
    return found


def test_sync_io_handlers_run_in_threadpool():
    """DB/cache/Pillow handlers must be sync `def`, not `async def`.

    Slice 4 adds 3 QR endpoints (.png/.svg binary + /raw no-DB), all sync
    `def` per the Slice 4 sync-style rule — the expected count grows 6 → 9.
    """
    endpoints = _all_sync_endpoints()
    assert len(endpoints) == 9, f"expected 6 Slice 2 + 3 Slice 4 endpoints, got: {[k for k, _ in endpoints]}"
    for route_id, endpoint in endpoints:
        assert not inspect.iscoroutinefunction(endpoint), (
            f"{route_id} is still `async def` — sync I/O would block the event loop"
        )


def test_db_pool_right_sized():
    """Shared engine pool: 4 persistent + 6 overflow per worker."""
    assert isinstance(engine.pool, QueuePool)
    assert engine.pool.size() == 4
    assert engine.pool._max_overflow == 6


def test_redirect_burst_all_302_with_analytics(client, db_session, fake_redis):
    """20 rapid redirects → all 302, each with exactly one analytics row."""
    from backend.shared.models import Analytics, Link

    code = "burstsmoke"
    url = "https://example.com/burst-smoke"
    link = Link(codigo=code, url_original=url)
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)

    for _ in range(20):
        response = client.get(f"/{code}", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == url

    count = db_session.query(Analytics).filter(Analytics.link_id == link.id).count()
    assert count == 20
