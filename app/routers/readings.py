"""
Readings Router
Endpoints for meter reading submission and retrieval.
"""
from uuid import UUID
from datetime import datetime, timedelta, date
from typing import Annotated
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date

from app.database import get_db
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.user import User
from app.schemas.reading import (
    ReadingCreate,
    ReadingResponse,
    ReadingListResponse,
    ReadingSummaryResponse,
    DailySummary,
)
from app.services.auth import get_current_user

router = APIRouter(prefix="/meters/{meter_id}/readings", tags=["Readings"])


def get_meter_or_404(meter_id: UUID, db: Session) -> Meter:
    """Helper to get meter or raise 404."""
    meter = db.query(Meter).filter(Meter.id == meter_id).first()
    if not meter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meter not found",
        )
    return meter


@router.post("", response_model=ReadingResponse, status_code=status.HTTP_201_CREATED)
async def submit_reading(
    meter_id: UUID,
    reading_data: ReadingCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Reading:
    """
    Submit a new meter reading.
    
    Automatically calculates consumption (delta from previous reading).
    
    - **value**: Cumulative meter reading value
    - **recorded_at**: Time the reading was physically taken
    """
    meter = get_meter_or_404(meter_id, db)
    
    # Get the previous reading to calculate consumption
    previous_reading = (
        db.query(Reading)
        .filter(Reading.meter_id == meter_id)
        .order_by(Reading.recorded_at.desc())
        .first()
    )
    
    # Calculate consumption (delta)
    consumption = None
    if previous_reading:
        consumption = reading_data.value - previous_reading.value
    
    new_reading = Reading(
        meter_id=meter_id,
        value=reading_data.value,
        consumption=consumption,
        recorded_at=reading_data.recorded_at,
        submitted_by=current_user.id,
    )
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)
    
    return new_reading


@router.get("", response_model=ReadingListResponse)
async def list_readings(
    meter_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    start_date: datetime | None = Query(None, description="Filter from date"),
    end_date: datetime | None = Query(None, description="Filter to date"),
) -> dict:
    """
    Retrieve paginated reading history for a meter.
    
    - **page**: Page number (default: 1)
    - **per_page**: Items per page (default: 20, max: 100)
    - **start_date**: Filter readings from this date
    - **end_date**: Filter readings to this date
    """
    meter = get_meter_or_404(meter_id, db)
    
    query = db.query(Reading).filter(Reading.meter_id == meter_id)
    
    # Apply date filters
    if start_date:
        query = query.filter(Reading.recorded_at >= start_date)
    if end_date:
        query = query.filter(Reading.recorded_at <= end_date)
    
    # Get total count
    total = query.count()
    pages = ceil(total / per_page) if total > 0 else 1
    
    # Paginate (newest first)
    readings = (
        query
        .order_by(Reading.recorded_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    
    return {
        "items": readings,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/summary", response_model=ReadingSummaryResponse)
async def get_reading_summary(
    meter_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    days: int = Query(7, ge=1, le=90, description="Number of days to summarize"),
) -> dict:
    """
    Return daily/weekly consumption aggregates.
    
    - **days**: Number of days to include (default: 7, max: 90)
    """
    meter = get_meter_or_404(meter_id, db)
    
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Get readings in the period
    readings = (
        db.query(Reading)
        .filter(
            Reading.meter_id == meter_id,
            Reading.recorded_at >= start_date,
            Reading.recorded_at <= end_date,
        )
        .order_by(Reading.recorded_at)
        .all()
    )
    
    # Calculate totals
    consumptions = [r.consumption for r in readings if r.consumption is not None]
    total_consumption = sum(consumptions) if consumptions else 0
    reading_count = len(readings)
    avg_consumption = total_consumption / len(consumptions) if consumptions else 0
    
    # Build daily breakdown
    daily_data: dict[date, list[Reading]] = {}
    for reading in readings:
        day = reading.recorded_at.date()
        if day not in daily_data:
            daily_data[day] = []
        daily_data[day].append(reading)
    
    daily_breakdown = []
    for day, day_readings in sorted(daily_data.items()):
        day_consumptions = [r.consumption for r in day_readings if r.consumption is not None]
        daily_breakdown.append(DailySummary(
            date=day,
            total_consumption=sum(day_consumptions) if day_consumptions else 0,
            reading_count=len(day_readings),
            min_value=min(r.value for r in day_readings),
            max_value=max(r.value for r in day_readings),
        ))
    
    return {
        "meter_id": meter.id,
        "meter_code": meter.meter_code,
        "period_start": start_date,
        "period_end": end_date,
        "total_consumption": total_consumption,
        "reading_count": reading_count,
        "average_consumption": avg_consumption,
        "daily_breakdown": daily_breakdown,
    }
