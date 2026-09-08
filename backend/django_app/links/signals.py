"""
LinkSnap / Acortador — Link cache-invalidation signals (Slice 3 data layer).

Registers post_save / post_delete receivers on Link that purge every
cached entry for the short code (redirect + stats + all QR config-hash
variants) via ``backend.fastapi_app.cache.invalidate_link_cache``.

Fires on ALL write paths (admin, shell, management commands) — unlike
ModelAdmin hooks. Note ``QuerySet.update()`` BYPASSES signals, which is
why the admin bulk actions use per-object ``.save()`` (see admin.py).

Wired via ``LinksConfig.ready()`` so it loads both under standalone
Django (manage.py / runserver) and under the FastAPI ASGI mount
(``get_wsgi_application()`` in ``fastapi_app/main.py``).

The cache import is lazy and failure-tolerant: if the FastAPI package
is not importable from the Django process (path layout), invalidation
is skipped with a warning instead of breaking writes. TTLs heal.
"""

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _invalidate_link(codigo: str) -> None:
    """Purge redirect/stats/QR cache keys for a short code, swallowing
    failures (a stale entry heals via TTL; a write must never 500)."""
    try:
        from backend.fastapi_app.cache import invalidate_link_cache
    except ImportError as exc:
        logger.warning("Link cache invalidation skipped (cache module "
                       "unreachable): %s", exc)
        return
    try:
        invalidate_link_cache(codigo)
    except Exception as exc:  # noqa: BLE001 — signal must never break saves
        logger.warning("Link cache invalidation failed for '%s': %s",
                       codigo, exc)


@receiver(post_save, sender="links.Link")
def link_saved_invalidate_cache(sender, instance, **kwargs):
    """Purge cache on every Link save (create, deactivate, URL change)."""
    _invalidate_link(instance.codigo)


@receiver(post_delete, sender="links.Link")
def link_deleted_invalidate_cache(sender, instance, **kwargs):
    """Purge cache when a Link row is deleted."""
    _invalidate_link(instance.codigo)
