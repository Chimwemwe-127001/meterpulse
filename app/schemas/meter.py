"""
Meter Schemas
Pydantic models for meter request/response validation.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

UtilityType = Literal["electricity", "water", "gas"]
MeterStatus = Literal["active", "inactive", "flagged"]


class MeterBase(BaseModel):
    """Shared meter fields."""
    meter_code: str = Field(..., min_length=2, max_length=50, examples=["ZW-001"])
    location: str = Field(..., min_length=5, examples=["Cairo Road, Lusaka"])
    utility_type: UtilityType
    unit: str = Field(..., max_length=10, examples=["kWh", "m3", "litres"])


class MeterCreate(MeterBase):
    """Schema for meter registration."""
    status: MeterStatus = "active"


class MeterUpdate(BaseModel):
    """Schema for meter updates (all fields optional)."""
    meter_code: str | None = Field(None, min_length=2, max_length=50)
    location: str | None = Field(None, min_length=5)
    utility_type: UtilityType | None = None
    unit: str | None = Field(None, max_length=10)
    status: MeterStatus | None = None


class MeterResponse(MeterBase):
    """Schema for meter response."""
    id: UUID
    status: str
    owner_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MeterListResponse(BaseModel):
    """Schema for paginated meter list."""
    items: list[MeterResponse]
    total: int
    page: int
    per_page: int
    pages: int
