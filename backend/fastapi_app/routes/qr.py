"""
LinkSnap / Acortador — QR Code Route
GET /api/qr/{code} - Generate QR code for a link
POST /api/qr/generate - Generate custom QR with styling options
"""

import base64
import hashlib
import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from PIL import ImageColor
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.fastapi_app.cache import cache_get, cache_set
from backend.fastapi_app.qr_drawers import get_module_drawer
from backend.fastapi_app.rate_limit import limiter
from backend.shared.database import get_db
from backend.shared.models import Link
from qrcode.image.styles.colormasks import SolidFillColorMask

router = APIRouter()

# ── Schemas ─────────────────────────────────────────────────────────────────


class QRResponse(BaseModel):
    """Response model for QR code generation."""

    qr_code: str
    """Base64-encoded PNG image of the QR code."""
    code: str
    """The short URL code this QR represents."""


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
            "'rounded' (esquinas redondeadas), 'gapped' (cuadrados con separación)"
        ),
    )


class CustomQRRequest(BaseModel):
    """Request body for customized QR code generation."""

    code: str = Field(description="Código del link acortado")
    config: QRConfig = Field(
        default_factory=QRConfig,
        description="Opciones de personalización del QR",
    )


# ── Cache Helpers ────────────────────────────────────────────────────────────


def _qr_config_hash(config: QRConfig) -> str:
    """
    Generate a short, deterministic hash from a QRConfig.

    Serializes the config to sorted JSON, then SHA-256 truncated to 8 hex chars.
    Used as part of the cache key to distinguish QR images by style.
    """
    config_dict = config.model_dump()
    config_json = json.dumps(config_dict, sort_keys=True)
    return hashlib.sha256(config_json.encode()).hexdigest()[:8]


def _parse_color(color_value: str):
    """Convert a CSS color string into an RGB/RGBA tuple for qrcode."""
    normalized = color_value.strip()
    return ImageColor.getrgb(normalized)


# ── QR Generation Engine ────────────────────────────────────────────────────


def generate_qr_image(url: str, config: QRConfig) -> Optional[str]:
    """
    Generate a QR code image as a base64-encoded PNG string.

    Accepts a ``QRConfig`` object for full control over colors and dot style.
    Returns ``None`` if generation fails (e.g. missing dependencies).

    Args:
        url: The URL to encode in the QR code.
        config: Configuration object controlling colors and dot style.

    Returns:
        Base64-encoded PNG string, or ``None`` on failure.
    """
    try:
        import qrcode
        from qrcode.image.styledpil import StyledPilImage

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)

        # Resolve module drawer from dot_style config
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

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return base64.b64encode(buffer.getvalue()).decode()

    except Exception as exc:
        print(f"QR Gen Error: {exc}")
        return None


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/api/qr/{code}", response_model=QRResponse)
@limiter.limit("10/second")
async def get_qr_code(
    request: Request,
    code: str,
    db: Session = Depends(get_db),
) -> QRResponse:
    """
    Generate a QR code for a short URL using default styling.

    Returns a base64-encoded PNG image with indigo pattern and white background.
    Results are cached for 1h keyed by code + default config hash.
    """
    default_config = QRConfig()
    cache_key = f"davelink:qr:{code}:{_qr_config_hash(default_config)}"

    # Try cache first
    cached = cache_get(cache_key)
    if cached:
        return QRResponse(qr_code=cached, code=code)

    # Cache miss: query DB and generate
    link = db.query(Link).filter(Link.codigo == code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Enlace no encontrado")

    qr_base64 = generate_qr_image(link.url_original, default_config)
    if not qr_base64:
        raise HTTPException(status_code=500, detail="Error generando QR")

    # Cache only on successful generation
    cache_set(cache_key, qr_base64, ttl=3600)

    return QRResponse(qr_code=qr_base64, code=code)


@router.post("/api/qr/generate", response_model=QRResponse)
@limiter.limit("10/second")
async def generate_custom_qr(
    request: Request,
    body: CustomQRRequest,
    db: Session = Depends(get_db),
) -> QRResponse:
    """
    Generate a customized QR code with full control over styling.

    Accepts a ``QRConfig`` object in the request body to customize:
    - ``fill_color``: Hex color for the QR pattern (default: #6366f1)
    - ``back_color``: Background color (default: white)
    - ``dot_style``: Module shape — ``square``, ``circle``, ``rounded``, or ``gapped``

    Results are cached for 1h keyed by code + config hash.
    """
    cache_key = f"davelink:qr:{body.code}:{_qr_config_hash(body.config)}"

    # Try cache first
    cached = cache_get(cache_key)
    if cached:
        return QRResponse(qr_code=cached, code=body.code)

    # Cache miss: query DB and generate
    link = db.query(Link).filter(Link.codigo == body.code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Enlace no encontrado")

    qr_base64 = generate_qr_image(link.url_original, body.config)
    if not qr_base64:
        raise HTTPException(status_code=500, detail="Error generando QR")

    # Cache only on successful generation
    cache_set(cache_key, qr_base64, ttl=3600)

    return QRResponse(qr_code=qr_base64, code=body.code)
