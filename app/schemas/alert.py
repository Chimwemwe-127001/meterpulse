"""
Alert Schemas
Pydantic models for alert request/response validation.
"""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class AlertBase(BaseModel):
    """Base alert fields."""
    alert_type: str
    severity: str
    message: str


class AlertResponse(AlertBase):
    """Schema for alert response."""
    id: UUID
    meter_id: UUID
    reading_id: UUID
    resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AlertListResponse(BaseModel):
    """Schema for paginated alert list."""
    items: list[AlertResponse]
    total: int
    page: int
    per_page: int
    pages: int


class AlertGenerated(BaseModel):
    """Schema for alerts generated during reading submission."""
    alert_type: str
    severity: str
    message: str


class ReadingWithAlerts(BaseModel):
    """Schema for reading response with generated alerts."""
    id: UUID
    meter_id: UUID
    value: float
    consumption: float | None
    recorded_at: datetime
    submitted_by: UUID
    created_at: datetime
    alerts_generated: list[AlertGenerated]

    class Config:
        from_attributes = True


class AlertResolve(BaseModel):
    """Schema for resolving an alert."""
    resolved: bool = Field(default=True)
