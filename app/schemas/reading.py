"""
Reading Schemas
Pydantic models for reading request/response validation.
"""
from datetime import datetime, date, timezone
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class ReadingCreate(BaseModel):
    """Schema for reading submission."""
    value: Decimal = Field(
        ...,
        ge=0,
        max_digits=12,
        decimal_places=3,
        description="Cumulative meter reading value",
    )
    recorded_at: datetime = Field(..., description="Time the reading was physically taken")

    @field_validator("recorded_at")
    @classmethod
    def ensure_timezone(cls, v: datetime) -> datetime:
        # Naive timestamps are ambiguous; interpret them as UTC so all
        # stored/compared datetimes are timezone-aware.
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class ReadingResponse(BaseModel):
    """Schema for reading response."""
    id: UUID
    meter_id: UUID
    value: Decimal
    consumption: Decimal | None
    recorded_at: datetime
    submitted_by: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class ReadingListResponse(BaseModel):
    """Schema for paginated reading list."""
    items: list[ReadingResponse]
    total: int
    page: int
    per_page: int
    pages: int


class DailySummary(BaseModel):
    """Daily consumption summary (days bucketed by UTC date)."""
    date: date
    total_consumption: Decimal
    reading_count: int
    min_value: Decimal
    max_value: Decimal


class ReadingSummaryResponse(BaseModel):
    """Schema for reading summary response."""
    meter_id: UUID
    meter_code: str
    period_start: datetime
    period_end: datetime
    total_consumption: Decimal
    reading_count: int
    average_consumption: Decimal
    daily_breakdown: list[DailySummary]
