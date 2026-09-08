"""
LinkSnap / Acortador — QR Code Route (Slice 4: full customization backend)

JSON (legacy base64, kept for the current frontend until Slice 5):
  GET  /api/qr/{code}      - QR for a link with default styling
  POST /api/qr/generate    - Customized QR (colors, dot style, size, EC, logo)

Binary (Slice 5 frontend switches its panels to these):
  GET  /api/qr/{code}.png  - PNG bytes (styled drawers allowed)
  GET  /api/qr/{code}.svg  - SVG bytes (square modules only)

No-DB (standalone panel — encodes an arbitrary URL, never writes DB):
  POST /api/qr/raw         - {url, config} -> base64 image + metadata

HARD INVARIANTS (apply throughout):
  - QR content ALWAYS encodes the ORIGINAL long URL (never the short URL).
  - Logo presets are built-in ONLY (``LOGO_PRESETS``); no uploads accepted.
  - SVG output is square-modules-only (``SvgPathImage``); styled module
    drawers are PNG-only. A logo request with ``format="svg"`` renders a
    plain square SVG (logo is a Pillow overlay and is skipped, documented).
"""

import base64
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from PIL import Image, ImageColor, ImageDraw
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.fastapi_app.cache import cache_get, cache_set
from backend.fastapi_app.qr_drawers import get_module_drawer
from backend.fastapi_app.rate_limit import limiter
from backend.shared.database import get_db
from backend.shared.models import Link
from qrcode.image.styles.colormasks import SolidFillColorMask

router = APIRouter()

# ── Constants ───────────────────────────────────────────────────────────────

#: Minimum WCAG-style contrast ratio between fill and background colors.
CONTRAST_MIN_RATIO = 3.0

#: Warning flag emitted when a logo forces EC below H (spec: qr-customization).
CAPACITY_WARNING_LOGO = "logo_not_supported_for_long_urls"

#: Cache TTL for QR payloads (1h, same as pre-Slice-4 behavior).
QR_CACHE_TTL = 3600

#: Browser cache header for binary QR responses (spec: qr-delivery-formats).
QR_CACHE_CONTROL = "public, max-age=3600"

#: Built-in logo presets ONLY — preset name -> PNG file under ``assets/``.
#: No user uploads are accepted in this change (spec: qr-customization).
LOGO_PRESETS: dict[str, str] = {
    "davelink": "davelink_logo.png",
    "link": "logo_link.png",
    "star": "logo_star.png",
    "heart": "logo_heart.png",
}
LogoPreset = Literal["davelink", "link", "star", "heart"]

#: EC candidates from strongest to weakest (adaptive EC walks this order).
EC_HIGH_TO_LOW = ("H", "Q", "M", "L")

#: Logo overlay width as a fraction of the QR image width (keeps QR scannable).
LOGO_SCALE = 0.20

ASSETS_DIR = Path(__file__).parent.parent / "assets"

# ── Schemas ─────────────────────────────────────────────────────────────────


class QRResponse(BaseModel):
    """Response model for QR code generation (legacy JSON base64)."""

    qr_code: str
    """Base64-encoded image bytes (PNG, or SVG when ``format="svg"``)."""
    code: str
    """The short URL code this QR represents."""
    capacity_warning: Optional[str] = None
    """Set when adaptive EC degraded below H (logo + long URL)."""
    error_correction: str = "L"
    """Effective EC level used (may differ from requested after adaption)."""
    format: str = "png"
    """Image format of the decoded ``qr_code`` bytes."""


class QRConfig(BaseModel):
    """Configuration for customizing QR code appearance."""

    fill_color: str = Field(
        default="#6366f1",
        description="Color del patrón del QR en formato hex (ej: #ff0000)",
    )
    back_color: str = Field(
        default="white",
        description="Color de fondo del QR (nombre o hex, ej: white, #ffffff)",
    )
    dot_style: str = Field(
        default="square",
        description=(
            "Estilo visual de los puntos del QR. "
            "Opciones: 'square' (cuadrados), 'circle' (círculos), "
            "'rounded' (esquinas redondeadas), 'gapped' (cuadrados con separación). "
            "Solo 'square' aplica a SVG; otros estilos son PNG-only."
        ),
    )
    size: int = Field(
        default=400,
        ge=64,
        le=2048,
        description="Dimensiones en píxeles de la imagen final (cuadrada)",
    )
    box_size: Optional[int] = Field(
        default=None,
        ge=1,
        le=50,
        description="Escala de cada módulo; None usa el valor por defecto (10)",
    )
    border: int = Field(
        default=4,
        ge=0,
        le=16,
        description="Zona de silencio en módulos alrededor del QR",
    )
    error_correction: Literal["L", "M", "Q", "H"] = Field(
        default="L",
        description="Nivel de corrección de errores solicitado (puede degradarse con logo)",
    )
    logo: Optional[LogoPreset] = Field(
        default=None,
        description="Preset de logo integrado (built-in); None = sin logo. Sin uploads.",
    )
    format: Literal["png", "svg"] = Field(
        default="png",
        description="Formato de imagen de salida",
    )


class CustomQRRequest(BaseModel):
    """Request body for customized QR code generation."""

    code: str = Field(description="Código del link acortado")
    config: QRConfig = Field(
        default_factory=QRConfig,
        description="Opciones de personalización del QR",
    )


class RawQRRequest(BaseModel):
    """Request body for no-DB QR generation (standalone panel)."""

    url: str = Field(
        min_length=1,
        max_length=8192,
        description="URL arbitraria a codificar (no se escribe en la DB)",
    )
    config: QRConfig = Field(
        default_factory=QRConfig,
        description="Opciones de personalización del QR",
    )


class RawQRResponse(BaseModel):
    """Response for no-DB QR generation (no ``code`` — nothing was stored)."""

    qr_code: str
    """Base64-encoded image bytes (PNG, or SVG when ``format="svg"``)."""
    format: str
    """Image format of the decoded ``qr_code`` bytes."""
    capacity_warning: Optional[str] = None
    """Set when adaptive EC degraded below H (logo + long URL)."""
    error_correction: str = "L"
    """Effective EC level used (may differ from requested after adaption)."""


# ── Cache Helpers ────────────────────────────────────────────────────────────


def _qr_config_hash(config: QRConfig) -> str:
    """
    Generate a short, deterministic hash from a QRConfig.

    Serializes the config to sorted JSON, then SHA-256 truncated to 8 hex chars.
    Used as part of the cache key to distinguish QR images by style.
    New config fields flow in automatically via ``model_dump()``.
    """
    config_dict = config.model_dump()
    config_json = json.dumps(config_dict, sort_keys=True)
    return hashlib.sha256(config_json.encode()).hexdigest()[:8]


def _parse_color(color_value: str):
    """Convert a CSS color string into an RGB/RGBA tuple for qrcode."""
    normalized = color_value.strip()
    return ImageColor.getrgb(normalized)


# ── Contrast Validation (pure, table-testable) ───────────────────────────────


def _relative_luminance(rgb: tuple) -> float:
    """WCAG relative luminance of an (R, G, B) triple (0-255 each)."""
    r, g, b = rgb[0], rgb[1], rgb[2]

    def channel(value: int) -> float:
        scaled = value / 255.0
        if scaled <= 0.03928:
            return scaled / 12.92
        return ((scaled + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(color_a: str, color_b: str) -> float:
    """
    WCAG contrast ratio between two CSS colors (1.0 = identical, 21.0 = B/W).

    Pure function — raises ``ValueError`` for unparseable color strings.
    """
    lum_a = _relative_luminance(_parse_color(color_a))
    lum_b = _relative_luminance(_parse_color(color_b))
    lighter, darker = (lum_a, lum_b) if lum_a >= lum_b else (lum_b, lum_a)
    return (lighter + 0.05) / (darker + 0.05)


def require_sufficient_contrast(fill_color: str, back_color: str) -> float:
    """
    Enforce the QR contrast floor (``CONTRAST_MIN_RATIO``).

    Returns the ratio on success; raises ``HTTPException`` 422
    (``insufficient_contrast``) when too low, or 422 (``invalid_color``)
    when a color string cannot be parsed.
    """
    try:
        ratio = contrast_ratio(fill_color, back_color)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_color")
    if ratio < CONTRAST_MIN_RATIO:
        raise HTTPException(status_code=422, detail="insufficient_contrast")
    return ratio


# ── Adaptive EC + Capacity Guard ─────────────────────────────────────────────


def _ec_constant(ec_name: str) -> int:
    """Map an EC level name to its ``qrcode.constants`` value."""
    import qrcode

    return {
        "L": qrcode.constants.ERROR_CORRECT_L,
        "M": qrcode.constants.ERROR_CORRECT_M,
        "Q": qrcode.constants.ERROR_CORRECT_Q,
        "H": qrcode.constants.ERROR_CORRECT_H,
    }[ec_name]


def _payload_fits(url: str, ec_name: str) -> bool:
    """
    Probe whether ``url`` fits in a QR at the given EC level.

    qrcode 7.x signals overflow as ``DataOverflowError`` for moderate
    overflows but as ``ValueError`` (invalid version > 40) when ``fit=True``
    walks past the maximum version — both mean "does not fit".
    """
    import qrcode
    from qrcode.exceptions import DataOverflowError

    try:
        probe = qrcode.QRCode(
            version=None,
            error_correction=_ec_constant(ec_name),
            box_size=10,
            border=4,
        )
        probe.add_data(url)
        probe.make(fit=True)
        return True
    except (DataOverflowError, ValueError):
        return False


def resolve_error_correction(
    url: str, requested: str, logo: Optional[str]
) -> tuple[str, Optional[str]]:
    """
    Pick the effective EC level for a payload.

    - With a logo: walk H → Q → M → L and use the strongest level that
      fits the ORIGINAL long URL; emit ``CAPACITY_WARNING_LOGO`` when the
      pick degrades below H. Raises 422 (``data_too_long``) if even L
      cannot hold the payload.
    - Without a logo: honor the requested level; raise 422
      (``data_too_long``) on overflow.
    """
    if logo is not None:
        for candidate in EC_HIGH_TO_LOW:
            if _payload_fits(url, candidate):
                warning = (
                    None if candidate == "H" else CAPACITY_WARNING_LOGO
                )
                return candidate, warning
        raise HTTPException(status_code=422, detail="data_too_long")
    if not _payload_fits(url, requested):
        raise HTTPException(status_code=422, detail="data_too_long")
    return requested, None


def _build_qr(url: str, ec_name: str, box_size: int, border: int):
    """Build a fitted ``qrcode.QRCode`` for the payload at the given EC."""
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=_ec_constant(ec_name),
        box_size=box_size,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr


# ── Rendering ────────────────────────────────────────────────────────────────


def _paste_logo(img: Image.Image, preset: str) -> Image.Image:
    """
    Paste a built-in logo preset centered on the QR image.

    The logo is scaled to ``LOGO_SCALE`` of the QR width and backed by a
    white rounded rectangle so dark modules never touch the glyph. The
    caller should use EC H (or the adaptive pick) to keep the code
    scannable. Raises ``HTTPException`` 500 if the asset file is missing.
    """
    filename = LOGO_PRESETS.get(preset)
    if filename is None:  # pragma: no cover — pydantic Literal guards this
        raise HTTPException(status_code=422, detail="unknown_logo_preset")
    asset_path = ASSETS_DIR / filename
    if not asset_path.exists():
        raise HTTPException(status_code=500, detail="logo_asset_missing")

    target = img.convert("RGBA")
    logo = Image.open(asset_path).convert("RGBA")

    logo_width = max(1, int(target.width * LOGO_SCALE))
    ratio = logo_width / logo.width
    logo = logo.resize(
        (logo_width, max(1, int(logo.height * ratio))), Image.LANCZOS
    )

    # White rounded backing slightly larger than the logo.
    pad = max(4, logo_width // 8)
    backing = Image.new(
        "RGBA",
        (logo.width + pad * 2, logo.height + pad * 2),
        (255, 255, 255, 0),
    )
    mask_draw = ImageDraw.Draw(backing)
    mask_draw.rounded_rectangle(
        [0, 0, backing.width, backing.height],
        radius=pad,
        fill=(255, 255, 255, 255),
    )
    offset = ((target.width - backing.width) // 2, (target.height - backing.height) // 2)
    target.alpha_composite(backing, dest=offset)
    logo_offset = (offset[0] + pad, offset[1] + pad)
    target.alpha_composite(logo, dest=logo_offset)
    return target.convert("RGB")


def _render_png_bytes(qr, config: QRConfig) -> bytes:
    """Render a fitted QR as PNG bytes resized to ``config.size`` (LANCZOS)."""
    from qrcode.image.styledpil import StyledPilImage

    module_drawer = get_module_drawer(config.dot_style)
    color_mask = SolidFillColorMask(
        back_color=_parse_color(config.back_color),
        front_color=_parse_color(config.fill_color),
    )
    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=module_drawer,
        color_mask=color_mask,
    )
    # StyledPilImage is a PilImage wrapper — unwrap to a real PIL image.
    pil_img = img._img if hasattr(img, "_img") else img
    if pil_img.size != (config.size, config.size):
        pil_img = pil_img.resize((config.size, config.size), Image.LANCZOS)
    if config.logo is not None:
        pil_img = _paste_logo(pil_img, config.logo)
    buffer = io.BytesIO()
    pil_img.save(buffer, format="PNG")
    return buffer.getvalue()


def _render_svg_bytes(qr, config: QRConfig) -> bytes:
    """
    Render a fitted QR as SVG bytes (square modules ONLY).

    Styled module drawers are PNG-only, so ``dot_style`` is ignored here by
    design. A logo request is likewise skipped (Pillow overlay has no SVG
    equivalent). The ``width``/``height`` attributes are pinned to
    ``config.size`` so browsers honor the requested dimensions.
    """
    from qrcode.image.svg import SvgPathImage

    svg_img = qr.make_image(image_factory=SvgPathImage)
    buffer = io.BytesIO()
    svg_img.save(buffer)
    svg_text = buffer.getvalue().decode("utf-8")
    svg_text = re.sub(
        r'width="[^"]*"', f'width="{config.size}px"', svg_text, count=1
    )
    svg_text = re.sub(
        r'height="[^"]*"', f'height="{config.size}px"', svg_text, count=1
    )
    return svg_text.encode("utf-8")


class _QRPayload(BaseModel):
    """Internal validated render result (never returned directly)."""

    model_config = {"arbitrary_types_allowed": True}

    data: bytes
    mime: str
    error_correction: str
    capacity_warning: Optional[str] = None
    image_format: str = "png"


def generate_qr_payload(url: str, config: QRConfig) -> _QRPayload:
    """
    Validate + render a QR payload for an arbitrary URL string.

    Applies contrast validation (422 ``insufficient_contrast``), adaptive
    EC with capacity guard (422 ``data_too_long``), then renders PNG
    (styled) or SVG (square-only). Raises ``HTTPException`` on rejection;
    never returns ``None``.
    """
    require_sufficient_contrast(config.fill_color, config.back_color)
    effective_ec, warning = resolve_error_correction(
        url, config.error_correction, config.logo
    )
    qr = _build_qr(
        url,
        effective_ec,
        box_size=config.box_size or 10,
        border=config.border,
    )
    if config.format == "svg":
        data = _render_svg_bytes(qr, config)
        mime = "image/svg+xml"
    else:
        data = _render_png_bytes(qr, config)
        mime = "image/png"
    return _QRPayload(
        data=data,
        mime=mime,
        error_correction=effective_ec,
        capacity_warning=warning,
        image_format=config.format,
    )


def generate_qr_image(url: str, config: QRConfig) -> Optional[str]:
    """
    Generate a QR code image as a base64-encoded string (legacy helper).

    Kept for backwards compatibility — wraps :func:`generate_qr_payload`
    and returns ``None`` on ANY failure (including 422 rejections, which
    the HTTP endpoints surface directly instead). New code should call
    :func:`generate_qr_payload`.
    """
    try:
        payload = generate_qr_payload(url, config)
        return base64.b64encode(payload.data).decode()
    except Exception as exc:
        print(f"QR Gen Error: {exc}")
        return None


# ── Shared Endpoint Logic ────────────────────────────────────────────────────


def _cached_or_render(code: str, url: str, config: QRConfig) -> tuple[str, _QRPayload]:
    """
    Return ``(base64_body, payload)`` for a link QR, using the config-hash
    cache (``davelink:qr:{code}:{hash8}`` — the hash covers the FULL config
    including ``format``, so PNG/SVG variants never collide).

    The cache stores base64 bytes only; EC/warning metadata is recomputed
    cheaply from the payload on a hit so the cached value format is stable.
    """
    cache_key = f"davelink:qr:{code}:{_qr_config_hash(config)}"
    cached = cache_get(cache_key)
    if cached:
        payload = generate_qr_payload(url, config)
        return cached, payload
    payload = generate_qr_payload(url, config)
    body = base64.b64encode(payload.data).decode()
    cache_set(cache_key, body, ttl=QR_CACHE_TTL)
    return body, payload


def _binary_response(payload: _QRPayload) -> Response:
    """Wrap rendered bytes in a cacheable binary ``Response``."""
    return Response(
        content=payload.data,
        media_type=payload.mime,
        headers={"Cache-Control": QR_CACHE_CONTROL},
    )


def _config_from_query(
    fill_color: str,
    back_color: str,
    dot_style: str,
    size: int,
    box_size: Optional[int],
    border: int,
    error_correction: str,
    logo: Optional[str],
    image_format: str,
) -> QRConfig:
    """Build a validated ``QRConfig`` from binary-endpoint query params."""
    return QRConfig(
        fill_color=fill_color,
        back_color=back_color,
        dot_style=dot_style,
        size=size,
        box_size=box_size,
        border=border,
        error_correction=error_correction,  # type: ignore[arg-type]
        logo=logo,  # type: ignore[arg-type]
        format=image_format,  # type: ignore[arg-type]
    )


# ── Binary Endpoints (registered BEFORE the generic {code} route) ────────────


@router.get("/api/qr/{code}.png")
@limiter.limit("10/second")
def get_qr_png(
    request: Request,
    response: Response,
    code: str,
    fill_color: str = Query(default="#6366f1"),
    back_color: str = Query(default="white"),
    dot_style: str = Query(default="square"),
    size: int = Query(default=400, ge=64, le=2048),
    box_size: Optional[int] = Query(default=None, ge=1, le=50),
    border: int = Query(default=4, ge=0, le=16),
    error_correction: str = Query(default="L"),
    logo: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> Response:
    """
    Serve a link QR as ``image/png`` bytes (styled drawers allowed).

    Query params mirror ``QRConfig`` (``format`` is fixed to PNG here).
    Cacheable: ``Cache-Control: public, max-age=3600``. Config-hash cached.
    The `response` param gives slowapi a Response for X-RateLimit-* headers.
    """
    config = _config_from_query(
        fill_color, back_color, dot_style, size, box_size, border,
        error_correction, logo, "png",
    )
    link = db.query(Link).filter(Link.codigo == code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Enlace no encontrado")
    # ORIGINAL long URL is always the encoded payload — never the short URL.
    _body, payload = _cached_or_render(code, link.url_original, config)
    return _binary_response(payload)


@router.get("/api/qr/{code}.svg")
@limiter.limit("10/second")
def get_qr_svg(
    request: Request,
    response: Response,
    code: str,
    fill_color: str = Query(default="#6366f1"),
    back_color: str = Query(default="white"),
    size: int = Query(default=400, ge=64, le=2048),
    box_size: Optional[int] = Query(default=None, ge=1, le=50),
    border: int = Query(default=4, ge=0, le=16),
    error_correction: str = Query(default="L"),
    db: Session = Depends(get_db),
) -> Response:
    """
    Serve a link QR as ``image/svg+xml`` bytes (SQUARE modules only).

    Styled ``dot_style`` and ``logo`` are PNG-only and have no SVG
    equivalent, so this endpoint intentionally omits those query params.
    Gzip-compressible via the app GZip middleware. Config-hash cached.
    The `response` param gives slowapi a Response for X-RateLimit-* headers.
    """
    config = _config_from_query(
        fill_color, back_color, "square", size, box_size, border,
        error_correction, None, "svg",
    )
    link = db.query(Link).filter(Link.codigo == code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Enlace no encontrado")
    # ORIGINAL long URL is always the encoded payload — never the short URL.
    _body, payload = _cached_or_render(code, link.url_original, config)
    return _binary_response(payload)


# ── No-DB Raw Endpoint ───────────────────────────────────────────────────────


@router.post("/api/qr/raw", response_model=RawQRResponse)
@limiter.limit("10/second")
def generate_raw_qr(
    request: Request,
    response: Response,
    body: RawQRRequest,
) -> RawQRResponse:
    """
    Generate a QR for an ARBITRARY url WITHOUT touching the database.

    Powers the standalone panel (Slice 5): encodes the provided URL
    directly, creates no ``Link`` row, and respects the full ``QRConfig``
    (contrast 422, adaptive EC + capacity warning). No ``db`` dependency
    is injected on purpose — this endpoint cannot write even by accident.
    The `response` param gives slowapi a Response for X-RateLimit-* headers.
    """
    url = body.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="invalid_url")
    cache_key = (
        "davelink:qr:raw:"
        f"{hashlib.sha256(url.encode()).hexdigest()[:12]}:"
        f"{_qr_config_hash(body.config)}"
    )
    cached = cache_get(cache_key)
    if cached:
        payload = generate_qr_payload(url, body.config)
        return RawQRResponse(
            qr_code=cached,
            format=payload.image_format,
            capacity_warning=payload.capacity_warning,
            error_correction=payload.error_correction,
        )
    payload = generate_qr_payload(url, body.config)
    encoded = base64.b64encode(payload.data).decode()
    cache_set(cache_key, encoded, ttl=QR_CACHE_TTL)
    return RawQRResponse(
        qr_code=encoded,
        format=payload.image_format,
        capacity_warning=payload.capacity_warning,
        error_correction=payload.error_correction,
    )


# ── Legacy JSON Endpoints (base64; kept for the current frontend) ────────────


@router.get("/api/qr/{code}", response_model=QRResponse)
@limiter.limit("10/second")
def get_qr_code(
    request: Request,
    response: Response,
    code: str,
    db: Session = Depends(get_db),
) -> QRResponse:
    """
    Generate a QR code for a short URL using default styling.

    Legacy JSON base64 endpoint — kept working for the current frontend
    until Slice 5 switches its panels to the binary ``.png``/``.svg``
    routes. Returns a base64-encoded image with indigo pattern and white
    background. Results are cached for 1h keyed by code + default config hash.

    The `response` param gives slowapi a Response to inject the
    X-RateLimit-* headers into.
    """
    default_config = QRConfig()
    link = db.query(Link).filter(Link.codigo == code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Enlace no encontrado")
    # ORIGINAL long URL is always the encoded payload — never the short URL.
    body, payload = _cached_or_render(code, link.url_original, default_config)
    return QRResponse(
        qr_code=body,
        code=code,
        capacity_warning=payload.capacity_warning,
        error_correction=payload.error_correction,
        format=payload.image_format,
    )


@router.post("/api/qr/generate", response_model=QRResponse)
@limiter.limit("10/second")
def generate_custom_qr(
    request: Request,
    response: Response,
    body: CustomQRRequest,
    db: Session = Depends(get_db),
) -> QRResponse:
    """
    Generate a customized QR code with full control over styling.

    Legacy JSON base64 endpoint — kept working for the current frontend
    until Slice 5 switches its panels to the binary ``.png``/``.svg``
    routes. Accepts a ``QRConfig`` object in the request body to customize:
    - ``fill_color``: Hex color for the QR pattern (default: #6366f1)
    - ``back_color``: Background color (default: white)
    - ``dot_style``: Module shape — ``square``, ``circle``, ``rounded``, or ``gapped``
    - ``size``/``box_size``/``border``: dimensions and quiet zone
    - ``error_correction``: L/M/Q/H (may auto-degrade with ``logo``)
    - ``logo``: built-in preset name (no uploads); ``format``: png/svg

    Low-contrast palettes are rejected with 422 ``insufficient_contrast``;
    over-capacity payloads with 422 ``data_too_long``. Results are cached
    for 1h keyed by code + config hash.

    The `response` param gives slowapi a Response to inject the
    X-RateLimit-* headers into.
    """
    link = db.query(Link).filter(Link.codigo == body.code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Enlace no encontrado")
    # ORIGINAL long URL is always the encoded payload — never the short URL.
    encoded, payload = _cached_or_render(body.code, link.url_original, body.config)
    return QRResponse(
        qr_code=encoded,
        code=body.code,
        capacity_warning=payload.capacity_warning,
        error_correction=payload.error_correction,
        format=payload.image_format,
    )
