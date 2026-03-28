"""
MeterPulse Database Configuration
SQLAlchemy engine, session, and base model setup.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import get_settings

settings = get_settings()

# Create engine
engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


def get_db():
    """
    Dependency that provides a database session.
    Yields session and ensures cleanup after request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
