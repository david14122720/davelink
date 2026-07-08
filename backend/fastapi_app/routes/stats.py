"""
LinkSnap / Acortador — Stats Route
GET /api/stats/{code} - Get analytics for a link
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from shared.database import get_db
from shared.models import Link, Analytics

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
async def get_stats(code: str, db: Session = Depends(get_db)):
    """
    Get analytics and statistics for a short URL.
    
    - Returns link details
    - Returns total click count
    - Returns recent click analytics (last 10)
    """
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
    
    return StatsResponse(
        code=link.codigo,
        original_url=link.url_original,
        created_at=link.fecha_creacion,
        total_clicks=link.clicks or 0,
        is_active=link.activo,
        recent_clicks=[
            AnalyticsResponse(
                ip_address=a.ip_address,
                user_agent=a.user_agent,
                referer=a.referer,
                fecha_click=a.fecha_click,
            )
            for a in recent_analytics
        ],
    )
