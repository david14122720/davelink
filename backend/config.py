"""
LinkSnap / Acortador — Shared Configuration

Loads environment variables and provides a single source of truth
for DATABASE_URL, SECRET_KEY, BASE_URL, and other settings.
Used by both Django (settings.py) and FastAPI (direct import).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (docker-compose.yml level) or backend/
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # Fallback: try backend/.env
    load_dotenv(Path(__file__).resolve().parent / ".env")


def get_bool(key: str, default: str = "false") -> bool:
    return os.getenv(key, default).strip().lower() in ("true", "1", "yes")


# ── Database ───────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://acortador:acortador_pass@localhost:5432/acortador",
)

# ── Django ─────────────────────────────────────────────────────────────────
SECRET_KEY: str = os.getenv(
    "SECRET_KEY",
    "django-insecure-change-me-to-a-real-secret-key",
)
DEBUG: bool = get_bool("DEBUG", "true")

# ── App ────────────────────────────────────────────────────────────────────
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8001")
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

# ── Derived ────────────────────────────────────────────────────────────────
# For Django's DATABASES setting, we need a dict, not a string.
# This helper is used by django_app/config/settings.py
def django_db_config() -> dict:
    """Convert DATABASE_URL to Django DATABASES dict."""
    # postgresql://user:pass@host:port/dbname
    url = DATABASE_URL
    # Remove 'postgresql://' prefix
    without_protocol = url.split("://", 1)[1] if "://" in url else url
    user_pass, rest = without_protocol.split("@", 1) if "@" in without_protocol else ("", without_protocol)
    user, password = user_pass.split(":", 1) if ":" in user_pass else (user_pass, "")
    host_port, database = rest.split("/", 1) if "/" in rest else (rest, "")
    host, port = host_port.split(":", 1) if ":" in host_port else (host_port, "5432")

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database or "acortador",
        "USER": user or "acortador",
        "PASSWORD": password or "acortador_pass",
        "HOST": host or "localhost",
        "PORT": port or "5432",
    }
