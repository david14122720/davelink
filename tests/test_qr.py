"""Tests for QR code generation endpoints."""

import base64
from io import BytesIO

import pytest
from PIL import Image

from backend.shared.models import Link


def test_get_qr_code_success(client, db_session):
    """Verify GET /api/qr/{code} returns base64 image with defaults."""
    code = "qrgene"
    link = Link(codigo=code, url_original="https://example.com/qr")
    db_session.add(link)
    db_session.commit()

    response = client.get(f"/api/qr/{code}")
    assert response.status_code == 200
    data = response.json()
    assert "qr_code" in data
    assert data["code"] == code
    assert len(data["qr_code"]) > 100


def test_get_qr_code_not_found(client):
    """Verify 404 for non-existent QR code."""
    response = client.get("/api/qr/nonexistent")
    assert response.status_code == 404
    assert response.json()["detail"] == "Enlace no encontrado"


@pytest.mark.parametrize("dot_style", ["square", "circle", "rounded", "gapped"])
def test_generate_custom_qr_all_styles(client, db_session, dot_style):
    """Verify POST /api/qr/generate with each dot style returns a valid image."""
    code = f"style_{dot_style}"
    link = Link(codigo=code, url_original="https://example.com/style")
    db_session.add(link)
    db_session.commit()

    body = {
        "code": code,
        "config": {
            "fill_color": "#ff0000",
            "back_color": "#000000",
            "dot_style": dot_style,
        },
    }

    response = client.post("/api/qr/generate", json=body)
    assert response.status_code == 200, f"Failed for style={dot_style}: {response.text}"
    data = response.json()
    assert "qr_code" in data
    assert data["code"] == code
    assert len(data["qr_code"]) > 100


def test_generate_custom_qr_applies_colors(client, db_session):
    """Verify custom foreground and background colors are rendered in the PNG."""
    code = "colorcheck"
    link = Link(codigo=code, url_original="https://example.com/color")
    db_session.add(link)
    db_session.commit()

    body = {
        "code": code,
        "config": {
            "fill_color": "#ff0000",
            "back_color": "#00ff00",
            "dot_style": "square",
        },
    }

    response = client.post("/api/qr/generate", json=body)
    assert response.status_code == 200, response.text

    data = response.json()
    image = Image.open(BytesIO(base64.b64decode(data["qr_code"]))).convert("RGB")

    assert image.getpixel((0, 0)) == (0, 255, 0)
    assert any(
        r > 200 and g < 80 and b < 80
        for r, g, b in image.getdata()
    ), "Expected a red foreground pixel in the QR image"


def test_generate_custom_qr_default_config(client, db_session):
    """Verify POST /api/qr/generate works without explicit config."""
    code = "defaultcfg"
    link = Link(codigo=code, url_original="https://example.com/default")
    db_session.add(link)
    db_session.commit()

    body = {"code": code}

    response = client.post("/api/qr/generate", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == code
    assert len(data["qr_code"]) > 100


def test_generate_custom_qr_invalid_config(client, db_session):
    """Verify 422 for invalid config types."""
    code = "invalidconfig"
    link = Link(codigo=code, url_original="https://example.com/invalid")
    db_session.add(link)
    db_session.commit()

    body = {
        "code": code,
        "config": {
            "fill_color": 12345,  # Should be string
        },
    }

    response = client.post("/api/qr/generate", json=body)
    assert response.status_code == 422


def test_generate_custom_qr_invalid_code(client):
    """Verify 404 for non-existent code in custom endpoint."""
    body = {
        "code": "nobodyhome",
        "config": {"fill_color": "#ff0000", "back_color": "white", "dot_style": "square"},
    }
    response = client.post("/api/qr/generate", json=body)
    assert response.status_code == 404


def test_generate_custom_qr_unknown_style_fallback(client, db_session):
    """Verify unknown dot_style falls back to square without error."""
    code = "unknownstyle"
    link = Link(codigo=code, url_original="https://example.com/unknown")
    db_session.add(link)
    db_session.commit()

    body = {
        "code": code,
        "config": {
            "fill_color": "#6366f1",
            "back_color": "white",
            "dot_style": "triangular",  # Not a real style
        },
    }

    response = client.post("/api/qr/generate", json=body)
    assert response.status_code == 200, f"Should fallback gracefully: {response.text}"
    data = response.json()
    assert len(data["qr_code"]) > 100
