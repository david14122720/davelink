"""
LinkSnap / Acortador — Redirect Route
GET /{code} - Redirect to original URL
"""

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.fastapi_app.cache import cache_get, cache_set
from backend.shared.database import get_db
from backend.shared.models import Link, Analytics

router = APIRouter()


@router.get("/{code}")
async def redirect_to_url(
    code: str,
    request: Request,
    db: Session = Depends(get_db)
):
    start_time = time.perf_counter()

    # Try cache first
    cached = cache_get(f"davelink:redirect:{code}")
    if cached:
        try:
            data = json.loads(cached)
            link_id = data["id"]
            url_original = data["url_original"]
        except (json.JSONDecodeError, KeyError) as exc:
            print(f"Redirect cache parse error for '{code}': {exc}")
            cached = None

    if not cached:
        # OPTIMIZATION: Fetch only required columns to reduce memory and DB load
        # Instead of loading the full object, we only get what we need for the redirect
        link_data = db.query(Link.id, Link.url_original, Link.activo).filter(Link.codigo == code).first()

        if not link_data:
            raise HTTPException(
                status_code=404,
                detail="Enlace no encontrado"
            )

        if not link_data.activo:
            raise HTTPException(
                status_code=410,
                detail="Este enlace ha sido desactivado"
            )

        link_id = link_data.id
        url_original = link_data.url_original

        # Cache only on successful redirect (active, found link)
        cache_set(
            f"davelink:redirect:{code}",
            json.dumps({
                "id": link_id,
                "url_original": url_original,
                "activo": True,
            }),
            ttl=3600,
        )

    # Extract headers once
    headers = request.headers

    # Record analytics
    # OPTIMIZATION: Removed the synchronous update to Link.clicks (the row lock)
    # We now only perform a single INSERT. Total clicks are calculated on-demand in /stats
    analytics = Analytics(
        link_id=link_id,
        ip_address=(request.client.host if request.client else "") or "",
        user_agent=headers.get("user-agent") or "",
        referer=headers.get("referer") or "",
    )
    db.add(analytics)
    db.commit()

    end_time = time.perf_counter()
    duration = (end_time - start_time) * 1000
    print(f"PERF LOG: Redirect for {code} took {duration:.2f}ms")

    # Return redirect
    return RedirectResponse(url=url_original, status_code=302)
