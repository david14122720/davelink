"""
LinkSnap / Acortador — Shorten Route
POST /api/shorten - Create short URL
"""

import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from backend.fastapi_app.rate_limit import limiter
from backend.shared.database import get_db
from backend.shared.models import Link

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
@limiter.limit("10/second")
async def shorten_url(
    request: Request,
    shorten_req: ShortenRequest,
    db: Session = Depends(get_db),
):
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
        url_original=str(shorten_req.url),
    )
    db.add(new_link)
    db.commit()
    db.refresh(new_link)
    
    # Build short URL
    from backend.app_config import BASE_URL
    short_url = f"{BASE_URL}/{code}"
    
    return ShortenResponse(
        short_url=short_url,
        code=code,
        original_url=str(shorten_req.url),
    )
