"""Slice 4 QR delivery tests: binary PNG/SVG endpoints + no-DB raw endpoint."""

import base64
from io import BytesIO

from PIL import Image

from backend.shared.models import Link


def _make_link(db_session, code, url):
    link = Link(codigo=code, url_original=url)
    db_session.add(link)
    db_session.commit()
    return link


# ── Binary PNG ──────────────────────────────────────────────────────────────


def test_binary_png_magic_and_headers(client, db_session, isolated_memory_limiter):
    """GET .png returns real PNG bytes with Content-Type + Cache-Control."""
    _make_link(db_session, "binpng", "https://example.com/binpng")
    response = client.get("/api/qr/binpng.png")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "public, max-age=3600"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_binary_png_size_honored(client, db_session, isolated_memory_limiter):
    """?size= controls the PNG dimensions (dimension check)."""
    _make_link(db_session, "binpngsize", "https://example.com/binpngsize")
    response = client.get("/api/qr/binpngsize.png?size=256")
    assert response.status_code == 200, response.text
    image = Image.open(BytesIO(response.content))
    assert image.size == (256, 256)


def test_binary_png_preset_renders(client, db_session, isolated_memory_limiter):
    """Styled drawers + logo work on the PNG route."""
    _make_link(db_session, "binpnglogo", "https://example.com/binpnglogo")
    response = client.get("/api/qr/binpnglogo.png?logo=star&dot_style=circle&size=256")
    assert response.status_code == 200, response.text
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert Image.open(BytesIO(response.content)).size == (256, 256)


def test_binary_png_contrast_422(client, db_session, isolated_memory_limiter):
    """Low-contrast palettes reject on the binary route too."""
    _make_link(db_session, "binpnglow", "https://example.com/binpnglow")
    response = client.get("/api/qr/binpnglow.png?fill_color=%23000000&back_color=%23000001")
    assert response.status_code == 422
    assert response.json()["detail"] == "insufficient_contrast"


def test_binary_png_not_found(client, isolated_memory_limiter):
    """Missing code on the binary route is a 404."""
    response = client.get("/api/qr/doesnotexist.png")
    assert response.status_code == 404


# ── Binary SVG ──────────────────────────────────────────────────────────────


def test_binary_svg_content_and_headers(client, db_session, isolated_memory_limiter):
    """GET .svg returns an <svg> document with the pinned pixel size."""
    _make_link(db_session, "binsvg", "https://example.com/binsvg")
    response = client.get("/api/qr/binsvg.svg?size=256")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/svg+xml"
    assert response.headers["cache-control"] == "public, max-age=3600"
    text = response.text
    assert "<svg" in text
    assert 'width="256px"' in text
    assert 'height="256px"' in text


def test_binary_svg_square_modules_only(client, db_session, isolated_memory_limiter):
    """SVG output uses square path modules (no circle/ellipse primitives)."""
    _make_link(db_session, "binsvg sq".replace(" ", ""), "https://example.com/binsvgsq")
    response = client.get("/api/qr/binsvgsq.svg")
    assert response.status_code == 200, response.text
    text = response.text.lower()
    assert "<svg" in text
    assert "<circle" not in text and "<ellipse" not in text


def test_binary_svg_not_found(client, isolated_memory_limiter):
    """Missing code on the SVG route is a 404."""
    response = client.get("/api/qr/doesnotexist.svg")
    assert response.status_code == 404


# ── No-DB raw endpoint ──────────────────────────────────────────────────────


def test_raw_no_db_write(client, db_session, isolated_memory_limiter):
    """POST /api/qr/raw encodes the URL without creating a Link row."""
    before = db_session.query(Link).count()
    response = client.post(
        "/api/qr/raw",
        json={"url": "https://example.com/standalone", "config": {}},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["format"] == "png"
    assert len(data["qr_code"]) > 100
    assert base64.b64decode(data["qr_code"])[:8] == b"\x89PNG\r\n\x1a\n"
    assert db_session.query(Link).count() == before


def test_raw_respects_config(client, isolated_memory_limiter):
    """Raw endpoint honors fill color (red pixel present in output)."""
    response = client.post(
        "/api/qr/raw",
        json={
            "url": "https://example.com/red",
            "config": {"fill_color": "#ff0000", "back_color": "#ffffff"},
        },
    )
    assert response.status_code == 200, response.text
    image = Image.open(BytesIO(base64.b64decode(response.json()["qr_code"]))).convert("RGB")
    assert any(
        r > 200 and g < 80 and b < 80 for r, g, b in image.getdata()
    ), "Expected a red foreground pixel in the raw QR image"


def test_raw_svg_format(client, isolated_memory_limiter):
    """Raw endpoint with format=svg returns base64 SVG bytes."""
    response = client.post(
        "/api/qr/raw",
        json={"url": "https://example.com/rawsvg", "config": {"format": "svg"}},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["format"] == "svg"
    assert b"<svg" in base64.b64decode(data["qr_code"])


def test_raw_contrast_422(client, isolated_memory_limiter):
    """Raw endpoint rejects low contrast with 422 insufficient_contrast."""
    response = client.post(
        "/api/qr/raw",
        json={
            "url": "https://example.com/rawlow",
            "config": {"fill_color": "#000000", "back_color": "#000001"},
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "insufficient_contrast"


def test_raw_invalid_url_422(client, isolated_memory_limiter):
    """Raw endpoint rejects non-http(s) URLs with 422 invalid_url."""
    response = client.post("/api/qr/raw", json={"url": "not-a-url"})
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_url"


def test_raw_logo_long_url_warns(client, db_session, isolated_memory_limiter):
    """Raw + logo + 1500-char URL degrades EC with a warning, no DB write."""
    base = "https://example.com/"
    long_url = base + "a" * (1500 - len(base))
    before = db_session.query(Link).count()
    response = client.post(
        "/api/qr/raw",
        json={"url": long_url, "config": {"logo": "davelink"}},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["error_correction"] == "Q"
    assert data["capacity_warning"] == "logo_not_supported_for_long_urls"
    assert db_session.query(Link).count() == before


def test_raw_logo_short_url_clean(client, isolated_memory_limiter):
    """Raw + logo + short URL keeps H with no warning."""
    response = client.post(
        "/api/qr/raw",
        json={"url": "https://example.com/short", "config": {"logo": "heart"}},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["error_correction"] == "H"
    assert data["capacity_warning"] is None
