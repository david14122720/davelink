"""
LinkSnap / Acortador — Shorten Route
POST /api/shorten - Create short URL
"""

import hashlib
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, HttpUrl
from sqlalchemy import func
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


def find_existing_link(db: Session, url: str):
    """Dedup lookup for an original URL (Slice 3 data layer).

    The md5(url_original) expression index (migration 0003) makes this an
    index scan on Postgres: compare func.md5(url_original) against the
    Python-computed digest, plus an equality guard (collision-proof, and
    Postgres still uses the index for the md5 clause). SQLite has no
    md5() function at all, so the test/dev dialect uses plain equality —
    same result, sequential scan, acceptable outside prod.
    """
    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else ""
    if dialect == "sqlite":
        return db.query(Link).filter(Link.url_original == url).first()
    url_md5 = hashlib.md5(url.encode("utf-8")).hexdigest()
    return (
        db.query(Link)
        .filter(func.md5(Link.url_original) == url_md5)
        .filter(Link.url_original == url)
        .first()
    )


class ShortenRequest(BaseModel):
    url: HttpUrl


class ShortenResponse(BaseModel):
    short_url: str
    code: str
    original_url: str


@router.post("/api/shorten", response_model=ShortenResponse)
@limiter.limit("10/second")
def shorten_url(
    request: Request,
    response: Response,
    shorten_req: ShortenRequest,
    db: Session = Depends(get_db),
):
    """
    Create a short URL from a long URL.

    - Generates a unique 6-character code
    - Stores the link in the database
    - Returns the shortened URL

    The `response` param gives slowapi a Response to inject the
    X-RateLimit-* headers into.
    """
    # Dedup: does this URL already have a code? (commit 454785c behavior:
    # return the existing code, never insert a second row for one URL.)
    url_str = str(shorten_req.url)
    existing = find_existing_link(db, url_str)
    if existing:
        scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.hostname
        return ShortenResponse(
            short_url=f"{scheme}://{host}/{existing.codigo}",
            code=existing.codigo,
            original_url=str(shorten_req.url),
        )

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
    
    # Build short URL from request host (works with any domain)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.hostname
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    short_url = f"{scheme}://{host}/{code}"
    
    return ShortenResponse(
        short_url=short_url,
        code=code,
        original_url=str(shorten_req.url),
    )
