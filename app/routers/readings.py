"""
Readings Router
Endpoints for meter reading submission and retrieval.
"""
from uuid import UUID
from datetime import datetime, timedelta, date, timezone
from decimal import Decimal
from typing import Annotated
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.reading import Reading
from app.models.user import User
from app.schemas.reading import (
    ReadingCreate,
    ReadingListResponse,
    ReadingSummaryResponse,
    DailySummary,
)
from app.schemas.alert import ReadingWithAlerts, AlertGenerated
from app.services.access import get_accessible_meter_or_404
from app.services.auth import get_current_user
from app.services.anomaly import detect_anomalies, as_utc

router = APIRouter(prefix="/meters/{meter_id}/readings", tags=["Readings"])


@router.post("", response_model=ReadingWithAlerts, status_code=status.HTTP_201_CREATED)
def submit_reading(
    meter_id: UUID,
    reading_data: ReadingCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Submit a new meter reading.

    Automatically calculates consumption (delta from previous reading).
    Runs anomaly detection and creates alerts if anomalies found.
    The reading and its alerts are persisted in a single transaction.

    - **value**: Cumulative meter reading value
    - **recorded_at**: Time the reading was physically taken (must be
      after the meter's latest reading)
    """
    # Row-lock the meter so concurrent submissions for the same meter
    # serialize; otherwise two requests read the same "previous" reading
    # and one consumption delta is silently wrong.
    meter = get_accessible_meter_or_404(meter_id, db, current_user, for_update=True)

    if meter.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Meter is {meter.status}; readings are only accepted for active meters",
        )

    # Get most recent reading to calculate consumption delta
    previous_reading = (
        db.query(Reading)
        .filter(Reading.meter_id == meter_id)
        .order_by(Reading.recorded_at.desc())
        .first()
    )

    # Consumption deltas are only meaningful against the chronologically
    # preceding reading; a backfilled timestamp would corrupt this delta
    # and its successor's, producing false NEGATIVE_DELTA alerts.
    if previous_reading and reading_data.recorded_at <= as_utc(previous_reading.recorded_at):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "recorded_at must be after the meter's latest reading "
                f"({as_utc(previous_reading.recorded_at).isoformat()})"
            ),
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
    db.flush()

    # Anomaly detection adds alerts to the same session/transaction
    alerts = detect_anomalies(
        meter_id=meter_id,
        new_reading=new_reading,
        db=db,
    )

    # Single commit: reading + alerts persist atomically (unit of work)
    db.commit()
    db.refresh(new_reading)

    alerts_generated = [
        AlertGenerated(
            alert_type=alert.alert_type,
            severity=alert.severity,
            message=alert.message,
        )
        for alert in alerts
    ]

    return ReadingWithAlerts(
        id=new_reading.id,
        meter_id=new_reading.meter_id,
        value=new_reading.value,
        consumption=new_reading.consumption,
        recorded_at=new_reading.recorded_at,
        submitted_by=new_reading.submitted_by,
        created_at=new_reading.created_at,
        alerts_generated=alerts_generated,
    )


@router.get("", response_model=ReadingListResponse)
def list_readings(
    meter_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    start_date: datetime | None = Query(None, description="Filter from date"),
    end_date: datetime | None = Query(None, description="Filter to date"),
) -> dict:
    """
    Retrieve paginated reading history for a meter (owner or admin only).

    - **page**: Page number (default: 1)
    - **per_page**: Items per page (default: 20, max: 100)
    - **start_date**: Filter readings from this date
    - **end_date**: Filter readings to this date
    """
    get_accessible_meter_or_404(meter_id, db, current_user)

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
def get_reading_summary(
    meter_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    days: int = Query(7, ge=1, le=90, description="Number of days to summarize"),
) -> dict:
    """
    Return daily/weekly consumption aggregates (owner or admin only).

    Days are bucketed by UTC date.

    - **days**: Number of days to include (default: 7, max: 90)
    """
    meter = get_accessible_meter_or_404(meter_id, db, current_user)

    # Calculate date range (timezone-aware; utcnow() is naive/deprecated)
    end_date = datetime.now(timezone.utc)
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
    total_consumption = sum(consumptions) if consumptions else Decimal("0")
    reading_count = len(readings)
    avg_consumption = total_consumption / len(consumptions) if consumptions else Decimal("0")

    # Build daily breakdown
    daily_data: dict[date, list[Reading]] = {}
    for reading in readings:
        day = as_utc(reading.recorded_at).date()
        if day not in daily_data:
            daily_data[day] = []
        daily_data[day].append(reading)

    daily_breakdown = []
    for day, day_readings in sorted(daily_data.items()):
        day_consumptions = [r.consumption for r in day_readings if r.consumption is not None]
        daily_breakdown.append(DailySummary(
            date=day,
            total_consumption=sum(day_consumptions) if day_consumptions else Decimal("0"),
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
