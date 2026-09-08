"""
LinkSnap / Acortador — Analytics Service (Slice 2 perf core)

Deferred analytics writes for the redirect critical path. The redirect
handler returns the 302 first and schedules ``record_analytics`` as a
FastAPI ``BackgroundTask``.

Why its own session factory: FastAPI ``yield`` dependencies (``get_db``)
are torn down BEFORE background tasks run, so the background write MUST
NOT reuse the request session. It opens a short-lived session from
``session_factory`` (default: the shared ``SessionLocal``) instead.

Failure policy: a failing INSERT is logged and swallowed — the 302 has
already been delivered and must never become a 500.
"""

import logging
from typing import Callable

from sqlalchemy.orm import Session

from backend.shared.database import SessionLocal
from backend.shared.models import Analytics

logger = logging.getLogger(__name__)


def record_analytics(
    link_id: int,
    ip_address: str = "",
    user_agent: str = "",
    referer: str = "",
    session_factory: Callable[[], Session] = SessionLocal,
) -> None:
    """
    Insert exactly one analytics row for a redirect click.

    Args:
        link_id: PK of the resolved link.
        ip_address: Client IP (already extracted from the request).
        user_agent: Raw User-Agent header (may be empty).
        referer: Raw Referer header (may be empty).
        session_factory: Zero-arg session factory. Defaults to the shared
            ``SessionLocal``; tests pass their own factory to stay off the
            production database.

    Never raises: any failure is logged and the click is dropped (accepted
    per design — a lost click beats a broken redirect).
    """
    try:
        db = session_factory()
        try:
            db.add(
                Analytics(
                    link_id=link_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    referer=referer,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception:
        logger.exception("analytics insert failed for link_id=%s", link_id)
