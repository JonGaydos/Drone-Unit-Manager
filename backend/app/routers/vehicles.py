from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.vehicle import Vehicle
from app.models.user import User
from app.routers.auth import get_current_user, require_admin, require_supervisor
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
    return [VehicleOut.model_validate(v) for v in q.order_by(Vehicle.nickname, Vehicle.serial_number).all()]


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
def create_vehicle(data: VehicleCreate, db: Session = Depends(get_db), admin: User = Depends(require_supervisor)):
    from app.services.audit import log_action
    if db.query(Vehicle).filter(Vehicle.serial_number == data.serial_number).first():
        raise HTTPException(status_code=400, detail="Vehicle with this serial number already exists")
    vehicle = Vehicle(**data.model_dump())
    db.add(vehicle)
    db.flush()
    log_action(db, admin.id, admin.display_name, "create", "vehicle", vehicle.id, f"{vehicle.manufacturer} {vehicle.model}")
    db.commit()
    db.refresh(vehicle)
    return VehicleOut.model_validate(vehicle)


@router.patch("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(vehicle_id: int, data: VehicleUpdate, db: Session = Depends(get_db), admin: User = Depends(require_supervisor)):
    from app.services.audit import log_action, compute_changes
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    update_data = data.model_dump(exclude_unset=True)
    changes = compute_changes(vehicle, update_data, ["nickname", "status", "manufacturer", "model", "serial_number"])
    for key, value in update_data.items():
        setattr(vehicle, key, value)
    if changes:
        log_action(db, admin.id, admin.display_name, "update", "vehicle", vehicle.id, vehicle.nickname or f"{vehicle.manufacturer} {vehicle.model}", changes=changes)
    db.commit()
    db.refresh(vehicle)
    return VehicleOut.model_validate(vehicle)


@router.delete("/{vehicle_id}")
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db), admin: User = Depends(require_supervisor)):
    from app.services.audit import log_action
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    vehicle.status = "retired"
    log_action(db, admin.id, admin.display_name, "retire", "vehicle", vehicle.id, vehicle.nickname or f"{vehicle.manufacturer} {vehicle.model}")
    db.commit()
    return {"ok": True, "message": "Vehicle retired"}


@router.post("/{vehicle_id}/photo")
async def upload_vehicle_photo(vehicle_id: int, file: UploadFile, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(404, "Vehicle not found")
    upload_dir = Path(settings.UPLOAD_DIR) / "photos" / "vehicles" / str(vehicle_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    for old in upload_dir.glob("profile.*"):
        old.unlink()
    ext = Path(file.filename).suffix or ".jpg"
    filepath = upload_dir / f"profile{ext}"
    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)
    vehicle.photo_url = f"/api/vehicles/{vehicle_id}/photo/view"
    db.commit()
    return {"ok": True, "photo_url": vehicle.photo_url}


@router.get("/{vehicle_id}/photo/view")
def view_vehicle_photo(vehicle_id: int, db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(404)
    photo_dir = Path(settings.UPLOAD_DIR) / "photos" / "vehicles" / str(vehicle_id)
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        p = photo_dir / f"profile{ext}"
        if p.exists():
            return FileResponse(p)
    raise HTTPException(404, "No photo found")
