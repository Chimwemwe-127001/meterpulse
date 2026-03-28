"""
Reading Model
Represents a single consumption data point for a meter.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import Float, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base

if TYPE_CHECKING:
    from app.models.meter import Meter
    from app.models.user import User


class Reading(Base):
    """
    A single meter reading submission.
    
    The consumption field stores the delta from the previous reading.
    """
    __tablename__ = "readings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    meter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    consumption: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    meter: Mapped["Meter"] = relationship("Meter", back_populates="readings")
    submitter: Mapped["User"] = relationship("User", back_populates="readings")

    def __repr__(self) -> str:
        return f"<Reading {self.meter_id} value={self.value}>"
