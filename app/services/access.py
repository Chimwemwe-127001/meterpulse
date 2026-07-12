"""
Access Control Service
Object-level authorization helpers (OWASP API1:2023 - BOLA).

Authentication proves who the caller is; these helpers prove the caller
may touch the specific object. Unauthorized access returns 404, not 403,
so the API does not confirm that someone else's resource exists.
"""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.meter import Meter
from app.models.user import User


def is_admin(user: User) -> bool:
    return user.role == "admin"


def get_accessible_meter_or_404(
    meter_id: UUID,
    db: Session,
    user: User,
    for_update: bool = False,
) -> Meter:
    """
    Fetch a meter the user owns (or any meter, for admins), else 404.

    Args:
        for_update: Acquire a row lock (SELECT ... FOR UPDATE) so
            concurrent writes against the same meter serialize.
    """
    query = db.query(Meter).filter(Meter.id == meter_id)
    if for_update:
        query = query.with_for_update()
    meter = query.first()

    if meter is None or (meter.owner_id != user.id and not is_admin(user)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meter not found",
        )
    return meter
