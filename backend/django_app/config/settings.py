"""
Django settings for LinkSnap / Acortador project.

Reads DATABASE_URL, SECRET_KEY, and DEBUG from .env (at project root).
Uses the same PostgreSQL database as FastAPI.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from project root
dotenv_path = BASE_DIR.parent.parent / ".env"


def _safe_load_dotenv(path: Path) -> None:
    """Load dotenv files only when the runtime can read them."""
    try:
        if path.exists():
            load_dotenv(path)
    except (PermissionError, OSError):
        # Sandboxed runs may expose the path but deny reads.
        pass


_safe_load_dotenv(dotenv_path)


def _db_config_from_url(url: str) -> dict:
    """Parse a PostgreSQL URL into Django DATABASES dict."""
    url = url.removeprefix("postgresql://")
    user_pass, rest = url.split("@", 1) if "@" in url else ("", url)
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


# ── Security ───────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "django-insecure-change-me-to-a-real-secret-key",
)
DEBUG = os.getenv("DEBUG", "true").strip().lower() in ("true", "1", "yes")
ALLOWED_HOSTS = ["*"]

# ── Installed apps ─────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "links",
]

# ── Middleware ──────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ── Database ───────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://acortador:acortador_pass@localhost:5432/acortador",
)
DATABASES = {
    "default": _db_config_from_url(DATABASE_URL),
}

# ── Password validation ────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Internationalization ───────────────────────────────────────────────────
LANGUAGE_CODE = "es-es"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True

# ── Static files ───────────────────────────────────────────────────────────
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ── Default primary key field type ─────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
