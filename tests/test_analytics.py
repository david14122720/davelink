"""
Slice 2: analytics async-write (BackgroundTasks + own session factory).

Covers the analytics-async-write spec:
- redirect returns 302 before the analytics commit lands client-side;
- exactly one analytics row per redirect, with correct metadata;
- a failing analytics write is logged and never breaks the redirect.
"""

import logging

import pytest

import conftest
from backend.fastapi_app.services.analytics import record_analytics


def _make_link(db_session, code, url="https://example.com/analytics"):
    from backend.shared.models import Link

    link = Link(codigo=code, url_original=url)
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)
    return link


def test_record_analytics_inserts_exactly_one_row(db_session):
    """Single call → exactly one row with link_id/ip/ua/referer."""
    from backend.shared.models import Analytics

    link = _make_link(db_session, "anlyone")

    record_analytics(
        link.id,
        "192.168.1.10",
        "test-agent/1.0",
        "https://referer.example",
        session_factory=conftest.TestingSessionLocal,
    )

    rows = db_session.query(Analytics).filter(Analytics.link_id == link.id).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.ip_address == "192.168.1.10"
    assert row.user_agent == "test-agent/1.0"
    assert row.referer == "https://referer.example"


def test_record_analytics_failure_is_logged_not_raised(db_session, caplog):
    """Exploding session factory → no raise, error logged."""
    def exploding_factory():
        raise RuntimeError("DB timeout")

    with caplog.at_level(logging.ERROR, logger="backend.fastapi_app.services.analytics"):
        record_analytics(12345, "1.2.3.4", "ua", "ref", session_factory=exploding_factory)

    assert any("analytics insert failed" in r.message for r in caplog.records)


def test_redirect_returns_302_with_single_analytics_row(client, db_session):
    """Normal path: 302 + Location, exactly one analytics row post-response."""
    from backend.shared.models import Analytics

    link = _make_link(db_session, "anlyredir", "https://example.com/analytics-redirect")

    response = client.get(f"/{link.codigo}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/analytics-redirect"
    rows = db_session.query(Analytics).filter(Analytics.link_id == link.id).all()
    assert len(rows) == 1


def test_redirect_ok_when_analytics_write_fails(client, db_session, monkeypatch):
    """Failing background write → redirect still 302 to the original URL."""
    import backend.fastapi_app.routes.redirect as redirect_module

    link = _make_link(db_session, "anlyfail", "https://example.com/analytics-fail")

    class ExplodingFactory:
        def __call__(self, *args, **kwargs):
            raise RuntimeError("DB down")

    monkeypatch.setattr(redirect_module, "SessionLocal", ExplodingFactory())

    response = client.get(f"/{link.codigo}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/analytics-fail"
