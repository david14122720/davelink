"""Slice 3 (task 3.3): Django signal invalidation + admin bulk actions.

- post_save on Link (incl. activo=False) purges redirect/stats/QR keys
- post_delete purges too; direct ORM AND admin writes both trigger
- DRAGONFLY_URL-empty (redis_client None) falls back to memory invalidation
- admin mark_active/mark_inactive use per-object .save() so signals fire
  (design risk #5: QuerySet.update() would skip them silently)
"""

import os
import sys
from pathlib import Path

import pytest

# ── Django setup (same pattern as test_admin; guarded for double import ──
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
_backend_dir = Path(__file__).resolve().parent.parent / "backend"
_django_app_dir = _backend_dir / "django_app"
for _p in (str(_django_app_dir), str(_backend_dir)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import django  # noqa: E402
from django.apps import apps  # noqa: E402
from django.conf import settings  # noqa: E402

if not apps.ready:
    settings.DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
    }
    django.setup()

import backend.fastapi_app.cache as cache_module  # noqa: E402
from backend.fastapi_app.cache import cache_set  # noqa: E402
from django.contrib import admin as django_admin  # noqa: E402
from django.db.models.signals import post_delete, post_save  # noqa: E402
from links.admin import LinkAdmin  # noqa: E402
from links.models import Link  # noqa: E402

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_memory_store():
    cache_module._memory_store.clear()
    yield
    cache_module._memory_store.clear()


def _seed(code):
    """Seed redirect + stats + two QR-variant keys (both stores)."""
    cache_set(f"davelink:redirect:{code}", '{"id": 1}', ttl=3600)
    cache_set(f"davelink:stats:{code}", '{}', ttl=30)
    cache_set(f"davelink:qr:{code}:a1b2c3d4", "qr1", ttl=3600)
    cache_set(f"davelink:qr:{code}:e5f6a7b8", "qr2", ttl=3600)


def _assert_gone(fake, code):
    from backend.fastapi_app.cache import cache_get

    assert cache_get(f"davelink:redirect:{code}") is None
    assert cache_get(f"davelink:stats:{code}") is None
    assert cache_get(f"davelink:qr:{code}:a1b2c3d4") is None
    assert fake.keys(f"davelink:qr:{code}:*") == []


def test_signals_registered_via_apps_ready():
    """ready() in apps.py wired the receivers for every entrypoint."""
    assert post_save.has_listeners(Link)
    assert post_delete.has_listeners(Link)


def test_deactivate_invalidates_cache(fake_redis):
    """Spec scenario: admin sets activo=False → redirect key deleted."""
    link = Link.objects.create(codigo="sgn001", url_original="https://example.com/s1")
    _seed("sgn001")

    link.activo = False
    link.save()

    _assert_gone(fake_redis, "sgn001")
    assert Link.objects.get(codigo="sgn001").activo is False


def test_url_change_invalidates_qr_cache(fake_redis):
    """Spec scenario: url_original change → QR keys invalidated too."""
    link = Link.objects.create(codigo="sgn002", url_original="https://example.com/s2")
    _seed("sgn002")

    link.url_original = "https://example.com/s2-changed"
    link.save()

    _assert_gone(fake_redis, "sgn002")


def test_delete_invalidates_cache(fake_redis):
    link = Link.objects.create(codigo="sgn003", url_original="https://example.com/s3")
    _seed("sgn003")

    link.delete()

    _assert_gone(fake_redis, "sgn003")


def test_invalidation_noop_without_redis(monkeypatch):
    """DRAGONFLY_URL empty → memory fallback still invalidates."""
    from backend.fastapi_app.cache import cache_get

    monkeypatch.setattr(cache_module, "redis_client", None)
    link = Link.objects.create(codigo="sgn004", url_original="https://example.com/s4")
    _seed("sgn004")
    assert cache_get("davelink:redirect:sgn004") == '{"id": 1}'

    link.activo = False
    link.save()

    assert cache_get("davelink:redirect:sgn004") is None
    assert cache_get("davelink:stats:sgn004") is None
    assert cache_get("davelink:qr:sgn004:a1b2c3d4") is None


def _admin_for_model():
    model_admin = LinkAdmin(Link, django_admin.AdminSite())
    # Stub message_user (needs the messages framework + request otherwise)
    model_admin.message_user = lambda *a, **k: None
    return model_admin


def test_bulk_mark_inactive_fires_invalidation(fake_redis):
    """Design risk #5: bulk actions must save per-object so signals fire."""
    Link.objects.create(codigo="blk001", url_original="https://example.com/b1")
    Link.objects.create(codigo="blk002", url_original="https://example.com/b2")
    _seed("blk001")
    _seed("blk002")

    _admin_for_model().mark_inactive(
        request=None, queryset=Link.objects.filter(codigo__in=["blk001", "blk002"])
    )

    assert Link.objects.filter(activo=False).count() == 2
    _assert_gone(fake_redis, "blk001")
    _assert_gone(fake_redis, "blk002")


def test_bulk_mark_active_fires_invalidation(fake_redis):
    Link.objects.create(
        codigo="blk003", url_original="https://example.com/b3", activo=False
    )
    _seed("blk003")

    _admin_for_model().mark_active(
        request=None, queryset=Link.objects.filter(codigo="blk003")
    )

    assert Link.objects.get(codigo="blk003").activo is True
    _assert_gone(fake_redis, "blk003")
