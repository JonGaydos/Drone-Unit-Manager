from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.constants import DOCUMENT_NOT_FOUND
from app.deps import DBSession
from app.models.document import Document
from app.models.user import User
from app.routers.auth import require_permission
from app.models.vehicle import Vehicle
from app.models.vehicle_registration import VehicleRegistration
from app.responses import responses

router = APIRouter(tags=["vehicle-registrations"])

ViewUser = Annotated[User, Depends(require_permission("registrations.view"))]
ManageUser = Annotated[User, Depends(require_permission("registrations.manage"))]


class RegistrationCreate(BaseModel):
    registration_number: Optional[str] = None
    registration_date: Optional[date] = None
    expiry_date: Optional[date] = None
    document_id: Optional[int] = None
    notes: Optional[str] = None


class RegistrationOut(BaseModel):
    id: int
    vehicle_id: int
    registration_number: Optional[str] = None
    registration_date: Optional[date] = None
    expiry_date: Optional[date] = None
    document_id: Optional[int] = None
    is_current: bool
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


def keep_one_current(db, vehicle_id: int) -> None:
    """Leave the vehicle with exactly one current registration when it has any.

    With none current, the latest registration (by registration date, then id)
    becomes current; with several, only the latest of them stays current.
    """
    regs = db.query(VehicleRegistration).filter(VehicleRegistration.vehicle_id == vehicle_id).all()
    current = [r for r in regs if r.is_current]
    if not regs or len(current) == 1:
        return
    keep = max(current or regs, key=lambda r: (r.registration_date or date.min, r.id))
    for reg in regs:
        reg.is_current = reg is keep


def _three_years_after(d: date) -> date:
    """The same calendar date three years on; Feb 29 falls back to Feb 28."""
    try:
        return d.replace(year=d.year + 3)
    except ValueError:
        return d.replace(year=d.year + 3, day=28)


@router.post("/api/vehicles/{vehicle_id}/registrations", response_model=RegistrationOut, responses=responses(404))
def create_registration(
    vehicle_id: int,
    data: RegistrationCreate,
    db: DBSession,
    user: ManageUser,
):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(404, "Vehicle not found")
    if data.document_id is not None and not db.query(Document).filter(
        Document.id == data.document_id, Document.deleted_at.is_(None)
    ).first():
        raise HTTPException(404, DOCUMENT_NOT_FOUND)

    # Auto-calculate expiry if not provided: registration_date + 3 years (FAA Part 107)
    expiry = data.expiry_date
    if not expiry and data.registration_date:
        expiry = _three_years_after(data.registration_date)

    for current in db.query(VehicleRegistration).filter(
        VehicleRegistration.vehicle_id == vehicle_id,
        VehicleRegistration.is_current.is_(True),
    ).all():
        current.is_current = False

    reg = VehicleRegistration(
        vehicle_id=vehicle_id,
        registration_number=data.registration_number,
        registration_date=data.registration_date,
        expiry_date=expiry,
        document_id=data.document_id,
        is_current=True,
        notes=data.notes,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)
    return RegistrationOut.model_validate(reg)


@router.get("/api/vehicles/{vehicle_id}/registrations", response_model=list[RegistrationOut])
def list_registrations(
    vehicle_id: int,
    db: DBSession,
    user: ViewUser,
):
    regs = (
        db.query(VehicleRegistration)
        .filter(VehicleRegistration.vehicle_id == vehicle_id)
        .order_by(VehicleRegistration.registration_date.desc())
        .all()
    )
    return [RegistrationOut.model_validate(r) for r in regs]


@router.get("/api/vehicle-registrations/current", response_model=list[RegistrationOut])
def list_current_registrations(
    db: DBSession,
    user: ViewUser,
):
    """Return the current registration for every vehicle in a single query.

    Lets the fleet view resolve all current registrations at once instead of
    issuing one request per vehicle (avoids an N+1 on the Fleet page).
    """
    regs = (
        db.query(VehicleRegistration)
        .filter(VehicleRegistration.is_current.is_(True))
        .all()
    )
    return [RegistrationOut.model_validate(r) for r in regs]


@router.delete("/api/vehicle-registrations/{reg_id}", responses=responses(404))
def delete_registration(
    reg_id: int,
    db: DBSession,
    user: ManageUser,
):
    reg = db.query(VehicleRegistration).filter(VehicleRegistration.id == reg_id).first()
    if not reg:
        raise HTTPException(404, "Registration not found")
    db.delete(reg)
    db.flush()
    keep_one_current(db, reg.vehicle_id)
    db.commit()
    return {"ok": True}
