"""
LinkSnap / Acortador — Stats Route
GET /api/stats/{code} - Get analytics for a link
"""

import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.fastapi_app.cache import cache_get, cache_set
from backend.fastapi_app.rate_limit import limiter
from backend.shared.database import get_db
from backend.shared.models import Link, Analytics

router = APIRouter()


class AnalyticsResponse(BaseModel):
    ip_address: Optional[str]
    user_agent: Optional[str]
    referer: Optional[str]
    fecha_click: datetime


class StatsResponse(BaseModel):
    code: str
    original_url: str
    created_at: datetime
    total_clicks: int
    is_active: bool
    recent_clicks: List[AnalyticsResponse]


@router.get("/api/stats/{code}", response_model=StatsResponse)
@limiter.limit("10/second")
def get_stats(request: Request, response: Response, code: str, db: Session = Depends(get_db)):
    """
    Get analytics and statistics for a short URL.

    - Returns link details
    - Returns total click count
    - Returns recent click analytics (last 10)

    The `response` param gives slowapi a Response to inject the
    X-RateLimit-* headers into (endpoints returning a model have no
    Response of their own for header injection).
    """
    # Try cache first (TTL 30s — short enough for freshness)
    cached = cache_get(f"davelink:stats:{code}")
    if cached:
        try:
            data = json.loads(cached)
            return StatsResponse(**data)
        except (json.JSONDecodeError, TypeError) as exc:
            print(f"Stats cache parse error for '{code}': {exc}")
            # Fall through to DB

    # Find the link
    link = db.query(Link).filter(Link.codigo == code).first()
    
    if not link:
        raise HTTPException(
            status_code=404,
            detail="Enlace no encontrado"
        )
    
    # Get recent analytics (last 10 clicks)
    recent_analytics = (
        db.query(Analytics)
        .filter(Analytics.link_id == link.id)
        .order_by(Analytics.fecha_click.desc())
        .limit(10)
        .all()
    )

    # Get total clicks by counting analytics entries (more reliable and allows redirect optimization)
    total_clicks = db.query(Analytics).filter(Analytics.link_id == link.id).count()

    def mask_ip(ip: str) -> str:
        if not ip:
            return ""
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.*.*"
        return ip

    response = StatsResponse(
        code=link.codigo,
        original_url=link.url_original,
        created_at=link.fecha_creacion,
        total_clicks=total_clicks,
        is_active=link.activo,
        recent_clicks=[
            AnalyticsResponse(
                ip_address=mask_ip(a.ip_address),
                user_agent=a.user_agent,
                referer=a.referer,
                fecha_click=a.fecha_click,
            )
            for a in recent_analytics
        ],
    )

    # Cache the serialized response
    try:
        cache_set(
            f"davelink:stats:{code}",
            json.dumps(response.model_dump(mode="json")),
            ttl=30,
        )
    except Exception as exc:
        print(f"Stats cache set error for '{code}': {exc}")

    return response
