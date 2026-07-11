"""
LinkSnap / Acortador — Rate Limiter Configuration

Provides a shared Limiter instance used by both the FastAPI app
(setup) and route decorators. Using a single shared instance
ensures that rate limit counters are consistent across all routes.
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address


def _create_limiter() -> Limiter:
    """Create the shared limiter without touching an unreadable .env file."""
    original_isfile = os.path.isfile
    try:
        os.path.isfile = lambda path: False if path == ".env" else original_isfile(path)
        return Limiter(key_func=get_remote_address)
    finally:
        os.path.isfile = original_isfile


limiter = _create_limiter()
