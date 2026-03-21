from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.vehicle import Vehicle
from app.models.vehicle_registration import VehicleRegistration
from app.models.user import User
from app.routers.auth import get_current_user, require_admin

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
    registration_number: Optional[str]
    registration_date: Optional[date]
    expiry_date: Optional[date]
    document_id: Optional[int]
    is_current: bool
    notes: Optional[str]

    model_config = {"from_attributes": True}


@router.post("/api/vehicles/{vehicle_id}/registrations", response_model=RegistrationOut)
def create_registration(
    vehicle_id: int,
    data: RegistrationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(404, "Vehicle not found")

    # Auto-calculate expiry if not provided: registration_date + 730 days (2 years)
    expiry = data.expiry_date
    if not expiry and data.registration_date:
        expiry = data.registration_date + timedelta(days=730)

    # Set previous registrations to not current
    db.query(VehicleRegistration).filter(
        VehicleRegistration.vehicle_id == vehicle_id,
        VehicleRegistration.is_current == True,
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    regs = (
        db.query(VehicleRegistration)
        .filter(VehicleRegistration.vehicle_id == vehicle_id)
        .order_by(VehicleRegistration.registration_date.desc())
        .all()
    )
    return [RegistrationOut.model_validate(r) for r in regs]


@router.delete("/api/vehicle-registrations/{reg_id}")
def delete_registration(
    reg_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    reg = db.query(VehicleRegistration).filter(VehicleRegistration.id == reg_id).first()
    if not reg:
        raise HTTPException(404, "Registration not found")
    db.delete(reg)
    db.commit()
    return {"ok": True}
