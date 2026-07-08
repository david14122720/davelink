"""
LinkSnap / Acortador — Shorten Route
POST /api/shorten - Create short URL
"""

import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from shared.database import get_db
from shared.models import Link

router = APIRouter()

# Base62 characters
BASE62 = string.ascii_letters + string.digits


def generate_code(length: int = 6) -> str:
    """Generate a random 6-character base62 code"""
    return "".join(secrets.choice(BASE62) for _ in range(length))


class ShortenRequest(BaseModel):
    url: HttpUrl


class ShortenResponse(BaseModel):
    short_url: str
    code: str
    original_url: str


@router.post("/api/shorten", response_model=ShortenResponse)
async def shorten_url(request: ShortenRequest, db: Session = Depends(get_db)):
    """
    Create a short URL from a long URL.
    
    - Generates a unique 6-character code
    - Stores the link in the database
    - Returns the shortened URL
    """
    # Generate unique code (retry on collision)
    max_retries = 10
    for _ in range(max_retries):
        code = generate_code()
        existing = db.query(Link).filter(Link.codigo == code).first()
        if not existing:
            break
    else:
        raise HTTPException(
            status_code=500,
            detail="No se pudo generar un código único. Intenta de nuevo."
        )
    
    # Create new link
    new_link = Link(
        codigo=code,
        url_original=str(request.url),
    )
    db.add(new_link)
    db.commit()
    db.refresh(new_link)
    
    # Build short URL (in production, use your domain)
    base_url = "http://localhost:8000"
    short_url = f"{base_url}/{code}"
    
    return ShortenResponse(
        short_url=short_url,
        code=code,
        original_url=str(request.url),
    )
