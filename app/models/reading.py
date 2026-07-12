"""
Reading Model
Represents a single consumption data point for a meter.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from sqlalchemy import Numeric, DateTime, ForeignKey, Index, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.meter import Meter
    from app.models.user import User
    from app.models.alert import Alert


class Reading(Base):
    """
    A single meter reading submission.

    The consumption field stores the delta from the previous reading.
    Values use Numeric, not Float: register values feed billing, and
    binary floats cannot represent decimal fractions exactly.
    """
    __tablename__ = "readings"
    __table_args__ = (
        # Every submission, listing, and detection pass queries
        # "WHERE meter_id = ? ORDER BY recorded_at DESC".
        Index("ix_readings_meter_id_recorded_at", "meter_id", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    meter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("meters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    value: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        nullable=False,
    )
    consumption: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3),
        nullable=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
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
    alerts: Mapped[list["Alert"]] = relationship(
        "Alert",
        back_populates="reading",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Reading {self.meter_id} value={self.value}>"
