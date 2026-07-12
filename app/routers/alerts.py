"""
Alerts Router
Endpoints for alert retrieval and management.

Alerts are scoped through meter ownership: operators only see alerts
for meters they own; admins see all (OWASP API1:2023 - BOLA).
"""
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.alert import Alert
from app.models.meter import Meter
from app.models.user import User
from app.schemas.alert import (
    AlertResponse,
    AlertListResponse,
    AlertResolve,
)
from app.services.access import get_accessible_meter_or_404, is_admin
from app.services.auth import get_current_user

router = APIRouter(prefix="/alerts", tags=["Alerts"])

Severity = Literal["LOW", "MEDIUM", "HIGH"]
AlertType = Literal["SPIKE", "ZERO_READING", "NEGATIVE_DELTA"]


def get_accessible_alert_or_404(alert_id: UUID, db: Session, user: User) -> Alert:
    """Fetch an alert whose meter the user owns (or any, for admins), else 404."""
    query = db.query(Alert).filter(Alert.id == alert_id)
    if not is_admin(user):
        query = query.join(Meter).filter(Meter.owner_id == user.id)
    alert = query.first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    return alert


@router.get("", response_model=AlertListResponse)
def list_all_alerts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    severity: Severity | None = Query(None, description="Filter by severity (LOW, MEDIUM, HIGH)"),
    alert_type: AlertType | None = Query(None, description="Filter by type (SPIKE, ZERO_READING, NEGATIVE_DELTA)"),
    resolved: bool | None = Query(None, description="Filter by resolved status"),
) -> dict:
    """
    List alerts across the caller's meters (all meters for admins).

    - **page**: Page number (default: 1)
    - **per_page**: Items per page (default: 20, max: 100)
    - **severity**: Filter by LOW, MEDIUM, or HIGH
    - **alert_type**: Filter by SPIKE, ZERO_READING, or NEGATIVE_DELTA
    - **resolved**: Filter by resolved status (true/false)
    """
    query = db.query(Alert)

    if not is_admin(current_user):
        query = query.join(Meter).filter(Meter.owner_id == current_user.id)

    # Apply filters
    if severity:
        query = query.filter(Alert.severity == severity)
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)
    if resolved is not None:
        query = query.filter(Alert.resolved == resolved)

    # Get total count
    total = query.count()
    pages = ceil(total / per_page) if total > 0 else 1

    # Paginate (newest first)
    alerts = (
        query
        .order_by(Alert.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "items": alerts,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(
    alert_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Alert:
    """
    Get details of a specific alert (meter owner or admin only).
    """
    return get_accessible_alert_or_404(alert_id, db, current_user)


@router.patch("/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(
    alert_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    resolve_data: AlertResolve | None = None,
) -> Alert:
    """
    Mark an alert as resolved/acknowledged (meter owner or admin only).

    Resolution is audited: who resolved it and when are recorded.
    Call without body to resolve, or pass {"resolved": false} to unresolve.
    """
    alert = get_accessible_alert_or_404(alert_id, db, current_user)

    # Default to True if no body provided
    resolved = resolve_data.resolved if resolve_data else True
    alert.resolved = resolved
    if resolved:
        alert.resolved_by = current_user.id
        alert.resolved_at = datetime.now(timezone.utc)
    else:
        alert.resolved_by = None
        alert.resolved_at = None
    db.commit()
    db.refresh(alert)

    return alert


# Meter-specific alerts endpoint
meter_alerts_router = APIRouter(prefix="/meters/{meter_id}/alerts", tags=["Alerts"])


@meter_alerts_router.get("", response_model=AlertListResponse)
def list_meter_alerts(
    meter_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    severity: Severity | None = Query(None, description="Filter by severity"),
    resolved: bool | None = Query(None, description="Filter by resolved status"),
) -> dict:
    """
    List all alerts for a specific meter (owner or admin only).
    """
    get_accessible_meter_or_404(meter_id, db, current_user)

    query = db.query(Alert).filter(Alert.meter_id == meter_id)

    # Apply filters
    if severity:
        query = query.filter(Alert.severity == severity)
    if resolved is not None:
        query = query.filter(Alert.resolved == resolved)

    # Get total count
    total = query.count()
    pages = ceil(total / per_page) if total > 0 else 1

    # Paginate
    alerts = (
        query
        .order_by(Alert.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "items": alerts,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }
