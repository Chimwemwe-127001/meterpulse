"""
Reading Schemas
Pydantic models for reading request/response validation.
"""
from datetime import datetime, date
from uuid import UUID
from pydantic import BaseModel, Field


class ReadingCreate(BaseModel):
    """Schema for reading submission."""
    value: float = Field(..., ge=0, description="Cumulative meter reading value")
    recorded_at: datetime = Field(..., description="Time the reading was physically taken")


class ReadingResponse(BaseModel):
    """Schema for reading response."""
    id: UUID
    meter_id: UUID
    value: float
    consumption: float | None
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
    """Daily consumption summary."""
    date: date
    total_consumption: float
    reading_count: int
    min_value: float
    max_value: float


class ReadingSummaryResponse(BaseModel):
    """Schema for reading summary response."""
    meter_id: UUID
    meter_code: str
    period_start: datetime
    period_end: datetime
    total_consumption: float
    reading_count: int
    average_consumption: float
    daily_breakdown: list[DailySummary]
