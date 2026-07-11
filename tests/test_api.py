import pytest
from httpx import Response

import string
import secrets


def test_code_generation_base62(client):
    """Verify generated codes use only base62 characters (a-z, A-Z, 0-9)"""
    base62 = string.ascii_letters + string.digits
    for _ in range(5):
        payload = {"url": f"https://example.com/test/{secrets.token_hex(4)}"}
        response = client.post("/api/shorten", json=payload)
        assert response.status_code == 200
        code = response.json()["code"]
        assert len(code) == 6
        assert all(c in base62 for c in code), f"Code '{code}' contains non-base62 chars"


def test_dedup_creates_different_codes(client):
    """Verify same URL shortened multiple times returns different codes"""
    url = "https://example.com/dedup-test"
    codes = set()
    for _ in range(3):
        response = client.post("/api/shorten", json={"url": url})
        assert response.status_code == 200
        codes.add(response.json()["code"])
    assert len(codes) == 3, "Each shorten call should generate a unique code"


def test_shorten_empty_body(client):
    """Verify empty body returns 422"""
    response = client.post("/api/shorten", json={})
    assert response.status_code == 422


def test_redirect_logs_click(client, db_session):
    """Verify visiting a redirect creates an analytics entry"""
    from backend.shared.models import Link, Analytics

    # Setup a link
    code = "clicklog"
    original_url = "https://example.com/click-test"
    link = Link(codigo=code, url_original=original_url)
    db_session.add(link)
    db_session.commit()

    # Visit redirect
    response = client.get(f"/{code}", follow_redirects=False)
    assert response.status_code == 302

    # Verify analytics entry was created
    analytics_entry = db_session.query(Analytics).filter(Analytics.link_id == link.id).first()
    assert analytics_entry is not None
    assert analytics_entry.link_id == link.id


def test_redirect_returns_302_with_location_header(client, db_session):
    """Verify redirect returns 302 with correct Location header"""
    from backend.shared.models import Link

    code = "redirloc"
    original_url = "https://example.com/location-test"
    link = Link(codigo=code, url_original=original_url)
    db_session.add(link)
    db_session.commit()

    response = client.get(f"/{code}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == original_url


def test_health_check(client):
    """Verify health check endpoint"""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "daveLinK"}

def test_shorten_url_success(client):
    """Verify creating a short URL"""
    payload = {"url": "https://www.google.com"}
    response = client.post("/api/shorten", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "short_url" in data
    assert "code" in data
    assert data["original_url"].rstrip("/") == "https://www.google.com"
    assert len(data["code"]) == 6

def test_shorten_url_invalid(client):
    """Verify invalid URL handling (Pydantic validation)"""
    # Testing a non-URL string
    payload = {"url": "not-a-url"}
    response = client.post("/api/shorten", json=payload)
    assert response.status_code == 422

def test_redirect_success(client, db_session):
    """Verify successful redirect to original URL"""
    from backend.shared.models import Link

    # Setup a link manually
    code = "test123"
    original_url = "https://anthropic.com"
    link = Link(codigo=code, url_original=original_url)
    db_session.add(link)
    db_session.commit()

    # Debug: Verify link exists in session
    exists = db_session.query(Link).filter(Link.codigo == code).first()
    print(f"DEBUG: Link exists in test session: {exists}")

    response = client.get(f"/{code}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == original_url

def test_redirect_not_found(client):
    """Verify 404 for non-existent codes"""
    response = client.get("/nonexistentcode")
    assert response.status_code == 404
    assert response.json()["detail"] == "Enlace no encontrado"

def test_redirect_inactive(client, db_session):
    """Verify 410 for inactive links"""
    from backend.shared.models import Link

    code = "inactive"
    link = Link(codigo=code, url_original="https://test.com", activo=False)
    db_session.add(link)
    db_session.commit()

    response = client.get(f"/{code}")
    assert response.status_code == 410
    assert response.json()["detail"] == "Este enlace ha sido desactivado"
