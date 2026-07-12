"""
MeterPulse API - Main Application
Utility Meter Reading, Anomaly Detection & Alert Management System

Database schema is managed exclusively by Alembic (`alembic upgrade head`);
tables are not auto-created at startup, so migration history stays the
single source of truth.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.config import get_settings
from app.database import engine
from app.rate_limit import limiter
from app.routers import auth_router, meters_router, readings_router, alerts_router, meter_alerts_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="""
## MeterPulse API

A RESTful API backend for utility meter management, featuring:

- 🔐 **Authentication**: JWT-based user authentication
- 📊 **Meter Management**: Full CRUD for utility meters
- 📈 **Readings**: Submit and track meter consumption
- ⚠️ **Anomaly Detection**: Automatic spike, zero, and tampering alerts
- 🔔 **Alerts**: View and resolve system-generated alerts

### Authentication

1. Register an account via `POST /auth/register`
2. Login via `POST /auth/login` to get a JWT token
3. Include the token in requests: `Authorization: Bearer <token>`
""",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Rate limiting (login/register throttling per NIST SP 800-63B §5.2.2)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: explicit origin allowlist from settings. Bearer tokens travel in
# the Authorization header, which is not a CORS "credential", so
# allow_credentials stays False (avoids wildcard+credentials, CWE-942).
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include routers
app.include_router(auth_router)
app.include_router(meters_router)
app.include_router(readings_router)
app.include_router(alerts_router)
app.include_router(meter_alerts_router)


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/health", tags=["Health"])
def health_check():
    """Detailed health check. Actually probes the database."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "connected"
    except Exception:
        database = "unreachable"

    return {
        "status": "healthy" if database == "connected" else "degraded",
        "database": database,
        "version": settings.app_version,
    }
