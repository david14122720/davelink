"""
Tests for GET /api/stats/{code} endpoint.
"""

import pytest


def test_stats_zero_clicks(client, db_session):
    """Verify stats for a link with 0 clicks"""
    from backend.shared.models import Link

    code = "statzero"
    link = Link(codigo=code, url_original="https://example.com/stats-zero")
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)

    response = client.get(f"/api/stats/{code}")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == code
    assert data["original_url"] == "https://example.com/stats-zero"
    assert data["total_clicks"] == 0
    assert data["is_active"] is True
    assert data["recent_clicks"] == []


def test_stats_with_clicks(client, db_session):
    """Verify stats with N clicks recorded"""
    from backend.shared.models import Link, Analytics

    code = "statclicks"
    link = Link(codigo=code, url_original="https://example.com/stats-clicks")
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)

    # Record 3 analytics entries manually
    for i in range(3):
        entry = Analytics(
            link_id=link.id,
            ip_address=f"192.168.1.{i + 1}",
            user_agent="test-agent",
            referer="https://referer.com",
        )
        db_session.add(entry)
    db_session.commit()

    response = client.get(f"/api/stats/{code}")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == code
    assert data["total_clicks"] == 3
    assert len(data["recent_clicks"]) == 3


def test_stats_nonexistent_code(client):
    """Verify 404 for non-existent code"""
    response = client.get("/api/stats/nonexistent")
    assert response.status_code == 404
    assert response.json()["detail"] == "Enlace no encontrado"


def test_stats_inactive_link(client, db_session):
    """Verify stats for inactive link (should still return stats)"""
    from backend.shared.models import Link

    code = "statinactive"
    link = Link(codigo=code, url_original="https://example.com/stats-inactive", activo=False)
    db_session.add(link)
    db_session.commit()

    response = client.get(f"/api/stats/{code}")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == code
    assert data["is_active"] is False
    assert data["total_clicks"] == 0


def test_stats_after_redirect(client, db_session):
    """Verify stats reflect clicks after visiting redirect"""
    from backend.shared.models import Link, Analytics

    code = "statvia"
    link = Link(codigo=code, url_original="https://example.com/stats-via-redirect")
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)

    # Visit redirect
    response = client.get(f"/{code}", follow_redirects=False)
    assert response.status_code == 302

    # Now check stats
    response = client.get(f"/api/stats/{code}")
    assert response.status_code == 200
    data = response.json()
    assert data["total_clicks"] >= 1
