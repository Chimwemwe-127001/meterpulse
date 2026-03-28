"""
Alert Model
Represents auto-generated alerts for anomalous meter readings.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base

if TYPE_CHECKING:
    from app.models.meter import Meter
    from app.models.reading import Reading


class Alert(Base):
    """
    An auto-generated record flagging an anomalous reading.
    
    Alert Types:
        - SPIKE: Consumption > 1.5x rolling average
        - ZERO_READING: Consumption == 0 when previous > 0
        - NEGATIVE_DELTA: New value < previous value (tampering)
    
    Severity Levels:
        - LOW: Minor anomaly
        - MEDIUM: Notable anomaly requiring attention
        - HIGH: Critical anomaly requiring immediate action
    """
    __tablename__ = "alerts"

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
    reading_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    meter: Mapped["Meter"] = relationship("Meter", back_populates="alerts")
    reading: Mapped["Reading"] = relationship("Reading", back_populates="alerts")

    def __repr__(self) -> str:
        return f"<Alert {self.alert_type} for meter {self.meter_id}>"
