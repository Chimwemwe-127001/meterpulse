"""
Meter Model
Represents utility metering devices (electricity, water, gas).
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.reading import Reading


class Meter(Base):
    """
    A registered utility metering device tracked by the system.
    
    Utility Types: electricity, water, gas
    Status: active, inactive, flagged
    """
    __tablename__ = "meters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    meter_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    location: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    utility_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    unit: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="meters")
    readings: Mapped[list["Reading"]] = relationship(
        "Reading", 
        back_populates="meter",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Meter {self.meter_code}>"
