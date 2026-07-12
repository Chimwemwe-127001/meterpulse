"""
Meters Router
Endpoints for meter device management (CRUD).

Every object access is authorized at the object level: non-admin users
only ever see or modify meters they own (OWASP API1:2023 - BOLA).
"""
from typing import Annotated, Literal
from uuid import UUID
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.meter import Meter
from app.models.user import User
from app.schemas.meter import (
    MeterCreate,
    MeterUpdate,
    MeterResponse,
    MeterListResponse,
)
from app.services.access import get_accessible_meter_or_404, is_admin
from app.services.auth import get_current_user, get_current_admin_user

router = APIRouter(prefix="/meters", tags=["Meters"])


@router.post("", response_model=MeterResponse, status_code=status.HTTP_201_CREATED)
def create_meter(
    meter_data: MeterCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Meter:
    """
    Register a new meter device.

    - **meter_code**: Unique identifier (e.g., ZW-001)
    - **location**: Physical address or description
    - **utility_type**: electricity, water, or gas
    - **unit**: Measurement unit (kWh, m3, litres)
    """
    new_meter = Meter(
        meter_code=meter_data.meter_code,
        location=meter_data.location,
        utility_type=meter_data.utility_type,
        unit=meter_data.unit,
        status=meter_data.status,
        owner_id=current_user.id,
    )
    db.add(new_meter)
    try:
        db.commit()
    except IntegrityError:
        # Rely on the unique constraint rather than check-then-insert,
        # which races under concurrency (TOCTOU, CWE-367).
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Meter code '{meter_data.meter_code}' already exists",
        )
    db.refresh(new_meter)

    return new_meter


@router.get("", response_model=MeterListResponse)
def list_meters(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Literal["active", "inactive", "flagged"] | None = Query(None, description="Filter by status"),
    utility_type: Literal["electricity", "water", "gas"] | None = Query(None, description="Filter by utility type"),
) -> dict:
    """
    List meters (own meters; admins see all) with optional filters.

    - **page**: Page number (default: 1)
    - **per_page**: Items per page (default: 20, max: 100)
    - **status**: Filter by active, inactive, or flagged
    - **utility_type**: Filter by electricity, water, or gas
    """
    query = db.query(Meter)

    # Object-level scoping: operators only see their own meters
    if not is_admin(current_user):
        query = query.filter(Meter.owner_id == current_user.id)

    # Apply filters
    if status:
        query = query.filter(Meter.status == status)
    if utility_type:
        query = query.filter(Meter.utility_type == utility_type)

    # Get total count
    total = query.count()
    pages = ceil(total / per_page) if total > 0 else 1

    # Paginate
    meters = query.order_by(Meter.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return {
        "items": meters,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/{meter_id}", response_model=MeterResponse)
def get_meter(
    meter_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Meter:
    """
    Get full details for a specific meter (owner or admin only).
    """
    return get_accessible_meter_or_404(meter_id, db, current_user)


@router.put("/{meter_id}", response_model=MeterResponse)
def update_meter(
    meter_id: UUID,
    meter_data: MeterUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Meter:
    """
    Update meter metadata (location, status, etc.). Owner or admin only.
    """
    meter = get_accessible_meter_or_404(meter_id, db, current_user)

    # Update only provided fields
    update_data = meter_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(meter, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Meter code '{meter_data.meter_code}' already exists",
        )
    db.refresh(meter)

    return meter


@router.delete("/{meter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meter(
    meter_id: UUID,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """
    Delete a meter and all associated readings.

    **Requires admin role.**
    """
    meter = db.query(Meter).filter(Meter.id == meter_id).first()
    if not meter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meter not found",
        )

    db.delete(meter)
    db.commit()
