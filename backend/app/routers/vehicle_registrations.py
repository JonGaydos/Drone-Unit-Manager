from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.deps import DBSession, CurrentUser, AdminUser
from app.models.vehicle import Vehicle
from app.models.vehicle_registration import VehicleRegistration
from app.responses import responses

router = APIRouter(tags=["vehicle-registrations"])


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


@router.post("/api/vehicles/{vehicle_id}/registrations", response_model=RegistrationOut, responses=responses(404))
def create_registration(
    vehicle_id: int,
    data: RegistrationCreate,
    db: DBSession,
    user: AdminUser,
):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(404, "Vehicle not found")

    # Auto-calculate expiry if not provided: registration_date + 3 years (FAA Part 107)
    expiry = data.expiry_date
    if not expiry and data.registration_date:
        expiry = data.registration_date + timedelta(days=1095)

    db.query(VehicleRegistration).filter(
        VehicleRegistration.vehicle_id == vehicle_id,
        VehicleRegistration.is_current.is_(True),
    ).update({"is_current": False})

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
    user: CurrentUser,
):
    regs = (
        db.query(VehicleRegistration)
        .filter(VehicleRegistration.vehicle_id == vehicle_id)
        .order_by(VehicleRegistration.registration_date.desc())
        .all()
    )
    return [RegistrationOut.model_validate(r) for r in regs]


@router.delete("/api/vehicle-registrations/{reg_id}", responses=responses(404))
def delete_registration(
    reg_id: int,
    db: DBSession,
    user: AdminUser,
):
    reg = db.query(VehicleRegistration).filter(VehicleRegistration.id == reg_id).first()
    if not reg:
        raise HTTPException(404, "Registration not found")
    db.delete(reg)
    db.commit()
    return {"ok": True}
