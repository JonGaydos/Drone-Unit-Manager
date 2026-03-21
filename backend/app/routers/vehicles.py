from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.vehicle import Vehicle
from app.models.user import User
from app.routers.auth import get_current_user, require_admin
from app.schemas.vehicle import VehicleCreate, VehicleUpdate, VehicleOut

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


@router.get("", response_model=list[VehicleOut])
def list_vehicles(
    status: str | None = None,
    manufacturer: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Vehicle)
    if status:
        q = q.filter(Vehicle.status == status)
    if manufacturer:
        q = q.filter(Vehicle.manufacturer == manufacturer)
    return [VehicleOut.model_validate(v) for v in q.order_by(Vehicle.manufacturer, Vehicle.model).all()]


@router.get("/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(vehicle_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return VehicleOut.model_validate(vehicle)


@router.get("/{vehicle_id}/stats")
def get_vehicle_stats(vehicle_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from sqlalchemy import func
    from app.models.flight import Flight

    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    stats = db.query(
        func.count(Flight.id).label("total_flights"),
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("total_seconds"),
        func.max(Flight.date).label("last_flight"),
    ).filter(Flight.vehicle_id == vehicle_id).first()
    return {
        "total_flights": stats.total_flights,
        "total_flight_hours": stats.total_seconds / 3600,
        "last_flight_date": str(stats.last_flight) if stats.last_flight else None,
    }


@router.post("", response_model=VehicleOut)
def create_vehicle(data: VehicleCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.query(Vehicle).filter(Vehicle.serial_number == data.serial_number).first():
        raise HTTPException(status_code=400, detail="Vehicle with this serial number already exists")
    vehicle = Vehicle(**data.model_dump())
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return VehicleOut.model_validate(vehicle)


@router.patch("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(vehicle_id: int, data: VehicleUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(vehicle, key, value)
    db.commit()
    db.refresh(vehicle)
    return VehicleOut.model_validate(vehicle)


@router.delete("/{vehicle_id}")
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    db.delete(vehicle)
    db.commit()
    return {"ok": True}
