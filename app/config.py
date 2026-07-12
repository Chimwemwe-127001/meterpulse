"""
MeterPulse Configuration
Environment variables and application settings.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://user:password@localhost:5432/meterpulse"

    # JWT Authentication.
    # No default on purpose: the app must fail fast at startup rather than
    # silently sign tokens with a publicly known key (CWE-798).
    # Generate one with: python -c "import secrets; print(secrets.token_hex(32))"
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # CORS: JSON list of allowed frontend origins,
    # e.g. CORS_ORIGINS='["http://localhost:3000"]'
    cors_origins: list[str] = []

    # Rate limiting (disable in tests)
    rate_limit_enabled: bool = True

    # Application
    debug: bool = False
    app_name: str = "MeterPulse API"
    app_version: str = "1.0.0"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
