"""
LinkSnap / Acortador — Redirect Route
GET /{code} - Redirect to original URL
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from shared.database import get_db
from shared.models import Link, Analytics

router = APIRouter()


@router.get("/{code}")
async def redirect_to_url(
    code: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Redirect to the original URL using the short code.
    
    - Looks up the link by code
    - Records analytics (IP, user agent, referer)
    - Increments click counter
    - Returns 302 redirect to original URL
    """
    # Find the link
    link = db.query(Link).filter(Link.codigo == code).first()
    
    if not link:
        raise HTTPException(
            status_code=404,
            detail="Enlace no encontrado"
        )
    
    if not link.activo:
        raise HTTPException(
            status_code=410,
            detail="Este enlace ha sido desactivado"
        )
    
    # Record analytics (use empty string instead of None — DB columns are NOT NULL)
    analytics = Analytics(
        link_id=link.id,
        ip_address=(request.client.host if request.client else "") or "",
        user_agent=request.headers.get("user-agent") or "",
        referer=request.headers.get("referer") or "",
    )
    db.add(analytics)
    
    # Increment click counter
    link.clicks = (link.clicks or 0) + 1
    db.commit()
    
    # Return redirect
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=link.url_original, status_code=302)
