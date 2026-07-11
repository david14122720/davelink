"""
Tests for Django Admin interface.

Requires pytest-django. Uses Django test client and test database.
"""

import os
import sys
from pathlib import Path

import pytest

# ── Django setup (must happen before any Django imports) ──
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Ensure django_app is on sys.path so config.settings can be found
backend_dir = Path(__file__).resolve().parent.parent / "backend"
django_app_dir = backend_dir / "django_app"
if str(django_app_dir) not in sys.path:
    sys.path.insert(0, str(django_app_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import django
from django.conf import settings

# Use SQLite for admin tests to avoid needing PostgreSQL
settings.DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

django.setup()

from django.contrib.auth.models import User
from django.test import Client
from links.models import Link, Analytics

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client():
    """Create an authenticated admin client."""
    user = User.objects.create_superuser(
        username="admin", email="admin@test.com", password="admin123"
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def sample_links():
    """Create sample links for testing."""
    link1 = Link.objects.create(
        codigo="abc123", url_original="https://example.com/one", activo=True
    )
    link2 = Link.objects.create(
        codigo="def456", url_original="https://example.com/two", activo=True
    )
    link3 = Link.objects.create(
        codigo="ghi789", url_original="https://example.com/three", activo=False
    )
    # Add analytics entry for link1
    Analytics.objects.create(
        link=link1,
        ip_address="192.168.1.1",
        user_agent="test-bot/1.0",
        referer="https://google.com",
    )
    return link1, link2, link3


class TestLinkAdmin:
    """Tests for Link admin functionality."""

    def test_admin_list_view(self, admin_client, sample_links):
        """Verify admin list view renders correctly"""
        response = admin_client.get("/admin/links/link/")
        assert response.status_code == 200
        assert b"abc123" in response.content
        assert b"def456" in response.content
        assert b"ghi789" in response.content

    def test_admin_search_by_codigo(self, admin_client, sample_links):
        """Verify search by short code"""
        response = admin_client.get("/admin/links/link/?q=abc123")
        assert response.status_code == 200
        assert b"abc123" in response.content
        assert b"def456" not in response.content

    def test_admin_search_by_url(self, admin_client, sample_links):
        """Verify search by original URL"""
        response = admin_client.get("/admin/links/link/?q=example.com/one")
        assert response.status_code == 200
        assert b"abc123" in response.content
        assert b"def456" not in response.content

    def test_admin_filter_active(self, admin_client, sample_links):
        """Verify filter by active status"""
        # Filter for inactive links (activo=False)
        response = admin_client.get("/admin/links/link/?activo__exact=0")
        assert response.status_code == 200
        assert b"ghi789" in response.content
        assert b"abc123" not in response.content

    def test_admin_filter_inactive(self, admin_client, sample_links):
        """Verify filter by inactive status"""
        response = admin_client.get("/admin/links/link/?activo__exact=1")
        assert response.status_code == 200
        assert b"abc123" in response.content
        assert b"ghi789" not in response.content

    def test_admin_toggle_active_action(self, admin_client, sample_links):
        """Verify bulk mark_active/mark_inactive actions"""
        link1, link2, link3 = sample_links

        # Mark all as inactive (admin actions redirect after POST)
        response = admin_client.post(
            "/admin/links/link/",
            {
                "action": "mark_inactive",
                "index": 0,
                "_selected_action": [link1.pk, link2.pk, link3.pk],
            },
            follow=True,
        )
        assert response.status_code == 200

        # Verify all are now inactive
        assert Link.objects.filter(activo=False).count() == 3

        # Mark all as active
        response = admin_client.post(
            "/admin/links/link/",
            {
                "action": "mark_active",
                "index": 0,
                "_selected_action": [link1.pk, link2.pk, link3.pk],
            },
            follow=True,
        )
        assert response.status_code == 200

        # Verify all are now active
        assert Link.objects.filter(activo=True).count() == 3

    def test_admin_click_log_visible(self, admin_client, sample_links):
        """Verify click analytics are visible in link detail view"""
        link1, _, _ = sample_links

        response = admin_client.get(f"/admin/links/link/{link1.pk}/change/")
        assert response.status_code == 200
        assert b"192.168.1.1" in response.content
        assert b"test-bot/1.0" in response.content
        assert b"https://google.com" in response.content

    def test_admin_link_change_view(self, admin_client, sample_links):
        """Verify link change form renders with correct fields"""
        link1, _, _ = sample_links

        response = admin_client.get(f"/admin/links/link/{link1.pk}/change/")
        assert response.status_code == 200
        assert b"abc123" in response.content
        assert b"https://example.com/one" in response.content

    def test_admin_index_page(self, admin_client):
        """Verify admin index page renders"""
        response = admin_client.get("/admin/")
        assert response.status_code == 200
        assert b"Links" in response.content
