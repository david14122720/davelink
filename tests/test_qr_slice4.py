"""Slice 4 QR backend tests: contrast, adaptive EC, presets, size, cache keys."""

import base64
from io import BytesIO

import pytest
from PIL import Image

from backend.fastapi_app.routes.qr import (
    CAPACITY_WARNING_LOGO,
    contrast_ratio,
    resolve_error_correction,
)
from backend.shared.models import Link


def _make_link(db_session, code, url):
    link = Link(codigo=code, url_original=url)
    db_session.add(link)
    db_session.commit()
    return link


# ── Contrast: pure helper table ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "fill,back,expected_ok",
    [
        ("#000000", "#ffffff", True),  # spec: sufficient contrast accepted
        ("black", "white", True),  # named colors resolve too
        ("#6366f1", "white", True),  # default palette passes (4.47:1)
        ("#ff0000", "#000000", True),  # red on black (5.25:1)
        ("#000000", "#000001", False),  # spec: ~1.0 rejected
        ("#ffffff", "#ffffff", False),  # identical colors rejected
        ("#777777", "#888888", False),  # close grays rejected
    ],
)
def test_contrast_ratio_table(fill, back, expected_ok):
    """WCAG-ish ratio >= 3.0 passes; near-identical colors fail."""
    ratio = contrast_ratio(fill, back)
    assert (ratio >= 3.0) is expected_ok


def test_contrast_ratio_black_white_is_21():
    """Sanity anchor: black/white is exactly 21:1."""
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)


# ── Contrast: HTTP 422 shape ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "fill,back,ok",
    [
        ("#000000", "#ffffff", True),
        ("#6366f1", "white", True),
        ("#000000", "#000001", False),
    ],
)
def test_generate_contrast_http(client, db_session, isolated_memory_limiter, fill, back, ok):
    """Accepted palettes render; low contrast rejects with 422 insufficient_contrast."""
    code = f"contrast_{fill[-4:]}_{back[-4:]}".replace("#", "")
    _make_link(db_session, code, "https://example.com/contrast")
    body = {"code": code, "config": {"fill_color": fill, "back_color": back}}
    response = client.post("/api/qr/generate", json=body)
    if ok:
        assert response.status_code == 200, response.text
    else:
        assert response.status_code == 422
        assert response.json()["detail"] == "insufficient_contrast"


def test_generate_invalid_color_422(client, db_session, isolated_memory_limiter):
    """Unparseable color strings reject with 422 invalid_color."""
    _make_link(db_session, "badcolor", "https://example.com/badcolor")
    body = {"code": "badcolor", "config": {"fill_color": "not-a-color"}}
    response = client.post("/api/qr/generate", json=body)
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_color"


# ── Adaptive EC ─────────────────────────────────────────────────────────────


def _long_url(n):
    base = "https://example.com/"
    return base + "a" * (n - len(base))


def test_adaptive_ec_pure_long_url_degrades():
    """1500-char URL + logo degrades H -> Q with a warning (spec scenario)."""
    ec, warning = resolve_error_correction(_long_url(1500), "L", "davelink")
    assert ec == "Q"
    assert warning == CAPACITY_WARNING_LOGO


def test_adaptive_ec_pure_short_url_keeps_h():
    """200-char URL + logo keeps H with no warning (spec scenario)."""
    ec, warning = resolve_error_correction(_long_url(200), "L", "davelink")
    assert ec == "H"
    assert warning is None


def test_adaptive_ec_no_logo_honors_requested():
    """Without a logo the requested EC is honored (no adaptation)."""
    ec, warning = resolve_error_correction(_long_url(200), "M", None)
    assert (ec, warning) == ("M", None)


def test_adaptive_ec_overflow_without_logo_422():
    """A payload even L cannot hold rejects with 422 data_too_long."""
    with pytest.raises(Exception) as exc_info:
        resolve_error_correction(_long_url(4000), "L", None)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "data_too_long"


def test_adaptive_ec_http_long_url_logo(
    client, db_session, isolated_memory_limiter
):
    """Long URL + logo over HTTP: degraded EC + warning in the response."""
    code = "adaptive_long"
    _make_link(db_session, code, _long_url(1500))
    body = {"code": code, "config": {"logo": "davelink"}}
    response = client.post("/api/qr/generate", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["error_correction"] == "Q"
    assert data["capacity_warning"] == CAPACITY_WARNING_LOGO


def test_adaptive_ec_http_short_url_logo(
    client, db_session, isolated_memory_limiter
):
    """Short URL + logo over HTTP: H with no warning."""
    code = "adaptive_short"
    _make_link(db_session, code, _long_url(200))
    body = {"code": code, "config": {"logo": "davelink"}}
    response = client.post("/api/qr/generate", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["error_correction"] == "H"
    assert data["capacity_warning"] is None


def test_generate_overflow_http_422(client, db_session, isolated_memory_limiter):
    """Over-capacity payload without logo rejects with 422 data_too_long."""
    code = "toolong"
    _make_link(db_session, code, _long_url(4000))
    response = client.post("/api/qr/generate", json={"code": code})
    assert response.status_code == 422
    assert response.json()["detail"] == "data_too_long"


# ── Logo presets ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("preset", ["davelink", "link", "star", "heart"])
def test_logo_presets_render(client, db_session, isolated_memory_limiter, preset):
    """Every built-in preset renders without crashing."""
    code = f"logo_{preset}"
    _make_link(db_session, code, "https://example.com/logo")
    body = {"code": code, "config": {"logo": preset}}
    response = client.post("/api/qr/generate", json=body)
    assert response.status_code == 200, f"preset={preset}: {response.text}"
    data = response.json()
    assert len(data["qr_code"]) > 100
    assert data["error_correction"] == "H"
    assert data["capacity_warning"] is None


def test_logo_png_dimensions_match_size(
    client, db_session, isolated_memory_limiter
):
    """Rendered PNG honors the requested size (dimension check)."""
    code = "logosize"
    _make_link(db_session, code, "https://example.com/logosize")
    body = {"code": code, "config": {"logo": "star", "size": 256}}
    response = client.post("/api/qr/generate", json=body)
    assert response.status_code == 200, response.text
    image = Image.open(BytesIO(base64.b64decode(response.json()["qr_code"])))
    assert image.size == (256, 256)


# ── Size / border ───────────────────────────────────────────────────────────


def test_size_honored(client, db_session, isolated_memory_limiter):
    """Custom size produces an image with exactly those dimensions."""
    code = "sizecheck"
    _make_link(db_session, code, "https://example.com/size")
    body = {"code": code, "config": {"size": 300}}
    response = client.post("/api/qr/generate", json=body)
    assert response.status_code == 200, response.text
    image = Image.open(BytesIO(base64.b64decode(response.json()["qr_code"])))
    assert image.size == (300, 300)


def test_size_bounds_rejected(client, db_session, isolated_memory_limiter):
    """Sizes outside 64-2048 are rejected by validation (422)."""
    _make_link(db_session, "badsize", "https://example.com/badsize")
    for size in (32, 4096):
        body = {"code": "badsize", "config": {"size": size}}
        response = client.post("/api/qr/generate", json=body)
        assert response.status_code == 422, f"size={size}"


# ── Cache keys ──────────────────────────────────────────────────────────────


def test_cache_key_differs_per_config(client, db_session, fake_redis):
    """Distinct configs produce distinct cache keys (no cross-style hits)."""
    import backend.fastapi_app.cache as cache_module

    code = "cachekey"
    _make_link(db_session, code, "https://example.com/cachekey")
    red = {"code": code, "config": {"fill_color": "#ff0000"}}
    blue = {"code": code, "config": {"fill_color": "#0000ff"}}
    assert client.post("/api/qr/generate", json=red).status_code == 200
    assert client.post("/api/qr/generate", json=blue).status_code == 200
    keys = [k for k in cache_module._memory_store if k.startswith(f"davelink:qr:{code}:")]
    assert len(keys) == 2, f"expected 2 distinct keys, got {keys}"


def test_cache_key_differs_per_new_field(client, db_session, fake_redis):
    """New Slice 4 fields (logo/size/EC) flow into the config hash."""
    import backend.fastapi_app.cache as cache_module

    code = "cachekey2"
    _make_link(db_session, code, "https://example.com/cachekey2")
    plain = {"code": code, "config": {}}
    with_logo = {"code": code, "config": {"logo": "heart"}}
    assert client.post("/api/qr/generate", json=plain).status_code == 200
    assert client.post("/api/qr/generate", json=with_logo).status_code == 200
    keys = [k for k in cache_module._memory_store if k.startswith(f"davelink:qr:{code}:")]
    assert len(keys) == 2, f"expected 2 distinct keys, got {keys}"


def test_identical_config_hits_cache(client, db_session, fake_redis):
    """Identical requests return the cached image (single cache key)."""
    import backend.fastapi_app.cache as cache_module

    code = "cachehit"
    _make_link(db_session, code, "https://example.com/cachehit")
    body = {"code": code, "config": {"fill_color": "#ff0000"}}
    first = client.post("/api/qr/generate", json=body)
    second = client.post("/api/qr/generate", json=body)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["qr_code"] == second.json()["qr_code"]
    keys = [k for k in cache_module._memory_store if k.startswith(f"davelink:qr:{code}:")]
    assert len(keys) == 1
