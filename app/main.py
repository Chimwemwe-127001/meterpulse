"""
MeterPulse API - Main Application
Utility Meter Reading, Anomaly Detection & Alert Management System
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine, Base
from app.routers import auth_router, meters_router, readings_router, alerts_router, meter_alerts_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Creates database tables on startup (development only).
    """
    # Startup: Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown: cleanup if needed


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
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
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
async def health_check():
    """Detailed health check."""
    return {
        "status": "healthy",
        "database": "connected",
        "version": settings.app_version,
    }
