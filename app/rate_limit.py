"""
Rate Limiting
Shared slowapi limiter instance (NIST SP 800-63B §5.2.2 throttling).

Defined in its own module so both main.py (handler registration) and
routers (decorators) can import it without circular imports.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.rate_limit_enabled,
)
