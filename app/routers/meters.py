"""
Meters Router
Endpoints for meter device management (CRUD).
"""
from uuid import UUID
from typing import Annotated
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.meter import Meter
from app.models.user import User
from app.schemas.meter import (
    MeterCreate,
    MeterUpdate,
    MeterResponse,
    MeterListResponse,
)
from app.services.auth import get_current_user, get_current_admin_user

router = APIRouter(prefix="/meters", tags=["Meters"])


@router.post("", response_model=MeterResponse, status_code=status.HTTP_201_CREATED)
async def create_meter(
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
    # Check if meter_code already exists
    existing = db.query(Meter).filter(Meter.meter_code == meter_data.meter_code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Meter code '{meter_data.meter_code}' already exists",
        )
    
    new_meter = Meter(
        meter_code=meter_data.meter_code,
        location=meter_data.location,
        utility_type=meter_data.utility_type,
        unit=meter_data.unit,
        status=meter_data.status,
        owner_id=current_user.id,
    )
    db.add(new_meter)
    db.commit()
    db.refresh(new_meter)
    
    return new_meter


@router.get("", response_model=MeterListResponse)
async def list_meters(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(None, description="Filter by status"),
    utility_type: str | None = Query(None, description="Filter by utility type"),
) -> dict:
    """
    List all meters with optional filters.
    
    - **page**: Page number (default: 1)
    - **per_page**: Items per page (default: 20, max: 100)
    - **status**: Filter by active, inactive, or flagged
    - **utility_type**: Filter by electricity, water, or gas
    """
    query = db.query(Meter)
    
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
async def get_meter(
    meter_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Meter:
    """
    Get full details for a specific meter.
    """
    meter = db.query(Meter).filter(Meter.id == meter_id).first()
    if not meter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meter not found",
        )
    return meter


@router.put("/{meter_id}", response_model=MeterResponse)
async def update_meter(
    meter_id: UUID,
    meter_data: MeterUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Meter:
    """
    Update meter metadata (location, status, etc.).
    """
    meter = db.query(Meter).filter(Meter.id == meter_id).first()
    if not meter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meter not found",
        )
    
    # Check meter_code uniqueness if being updated
    if meter_data.meter_code and meter_data.meter_code != meter.meter_code:
        existing = db.query(Meter).filter(Meter.meter_code == meter_data.meter_code).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Meter code '{meter_data.meter_code}' already exists",
            )
    
    # Update only provided fields
    update_data = meter_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(meter, field, value)
    
    db.commit()
    db.refresh(meter)
    
    return meter


@router.delete("/{meter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meter(
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
