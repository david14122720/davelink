"""
LinkSnap / Acortador — QR Code Route
GET /api/qr/{code} - Generate QR code for a link
"""

import base64
import io

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from shared.database import get_db
from shared.models import Link

router = APIRouter()


class QRResponse(BaseModel):
    qr_code: str  # Base64 encoded PNG
    code: str


@router.get("/api/qr/{code}", response_model=QRResponse)
async def get_qr_code(code: str, db: Session = Depends(get_db)):
    """
    Generate a QR code for a short URL.
    
    - Returns the QR code as a base64-encoded PNG image
    """
    # Find the link
    link = db.query(Link).filter(Link.codigo == code).first()
    
    if not link:
        raise HTTPException(
            status_code=404,
            detail="Enlace no encontrado"
        )
    
    # Generate QR code
    try:
        import qrcode
        from qrcode.image.styledpil import StyledPilImage
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(link.url_original)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="#6366f1", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return QRResponse(
            qr_code=img_base64,
            code=code,
        )
        
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Generación de QR no disponible. Instala qrcode[pil]."
        )
