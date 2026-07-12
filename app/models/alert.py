"""
Alert Model
Represents auto-generated alerts for anomalous meter readings.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, Index, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.meter import Meter
    from app.models.reading import Reading
    from app.models.user import User


class Alert(Base):
    """
    An auto-generated record flagging an anomalous reading.

    Alert Types:
        - SPIKE: Consumption rate far above the meter's robust baseline
        - ZERO_READING: Consumption == 0 when previous > 0
        - NEGATIVE_DELTA: New value < previous value (tampering)

    Severity Levels:
        - LOW: Minor anomaly
        - MEDIUM: Notable anomaly requiring attention
        - HIGH: Critical anomaly requiring immediate action

    Resolution is audited (resolved_by / resolved_at) so tampering alerts
    cannot be silently buried without a trace.
    """
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_meter_id_created_at", "meter_id", "created_at"),
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
    reading_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("readings.id", ondelete="CASCADE"),
        nullable=False,
    )
    alert_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    resolved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    meter: Mapped["Meter"] = relationship("Meter", back_populates="alerts")
    reading: Mapped["Reading"] = relationship("Reading", back_populates="alerts")
    resolver: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return f"<Alert {self.alert_type} for meter {self.meter_id}>"
