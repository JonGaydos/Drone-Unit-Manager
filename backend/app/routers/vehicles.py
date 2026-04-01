"""Vehicle (drone) CRUD endpoints with flight statistics and profile photo management."""

from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.constants import VEHICLE_NOT_FOUND, ACCESS_DENIED, FILE_TYPE_NOT_ALLOWED, FILE_TOO_LARGE
from app.deps import DBSession, CurrentUser, AdminUser, SupervisorUser
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleUpdate, VehicleOut
from app.responses import responses

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


@router.get("", response_model=list[VehicleOut])
def list_vehicles(
    db: DBSession,
    user: CurrentUser,
    status: str | None = None,
    manufacturer: str | None = None):
    """List all vehicles with optional filtering by status and manufacturer.

    Args:
        status: Filter by vehicle status (active, grounded, retired).
        manufacturer: Filter by manufacturer name.

    Returns:
        List of vehicle records sorted by nickname/serial number.
    """
    q = db.query(Vehicle)
    if status:
        q = q.filter(Vehicle.status == status)
    if manufacturer:
        q = q.filter(Vehicle.manufacturer == manufacturer)
    return [VehicleOut.model_validate(v) for v in q.order_by(Vehicle.nickname, Vehicle.serial_number).all()]


@router.get("/{vehicle_id}", response_model=VehicleOut, responses=responses(401, 404))
def get_vehicle(vehicle_id: int, db: DBSession, user: CurrentUser):
    """Retrieve a single vehicle by ID."""
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail=VEHICLE_NOT_FOUND)
    return VehicleOut.model_validate(vehicle)


@router.get("/{vehicle_id}/stats", responses=responses(401, 404))
def get_vehicle_stats(vehicle_id: int, db: DBSession, user: CurrentUser):
    """Get aggregated flight statistics for a vehicle (total flights, hours, last flight date)."""
    from sqlalchemy import func
    from app.models.flight import Flight

    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail=VEHICLE_NOT_FOUND)
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


@router.post("", response_model=VehicleOut, responses=responses(400, 401))
def create_vehicle(data: VehicleCreate, db: DBSession, admin: SupervisorUser):
    """Create a new vehicle record. Enforces unique serial numbers. Supervisor or admin only."""
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


@router.patch("/{vehicle_id}", response_model=VehicleOut, responses=responses(401, 404))
def update_vehicle(vehicle_id: int, data: VehicleUpdate, db: DBSession, admin: SupervisorUser):
    """Update a vehicle's details with audit-logged change tracking. Supervisor or admin only."""
    from app.services.audit import log_action, compute_changes
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail=VEHICLE_NOT_FOUND)
    update_data = data.model_dump(exclude_unset=True)
    changes = compute_changes(vehicle, update_data, ["nickname", "status", "manufacturer", "model", "serial_number"])
    for key, value in update_data.items():
        setattr(vehicle, key, value)
    if changes:
        log_action(db, admin.id, admin.display_name, "update", "vehicle", vehicle.id, vehicle.nickname or f"{vehicle.manufacturer} {vehicle.model}", changes=changes)
    db.commit()
    db.refresh(vehicle)
    return VehicleOut.model_validate(vehicle)


@router.delete("/{vehicle_id}", responses=responses(401, 404))
def delete_vehicle(vehicle_id: int, db: DBSession, admin: SupervisorUser):
    """Soft-delete a vehicle by setting status to retired. Supervisor or admin only."""
    from app.services.audit import log_action
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail=VEHICLE_NOT_FOUND)
    vehicle.status = "retired"
    log_action(db, admin.id, admin.display_name, "retire", "vehicle", vehicle.id, vehicle.nickname or f"{vehicle.manufacturer} {vehicle.model}")
    db.commit()
    return {"ok": True, "message": "Vehicle retired"}


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


@router.post("/{vehicle_id}/photo", responses=responses(400, 401, 404, 413))
async def upload_vehicle_photo(vehicle_id: int, file: UploadFile, db: DBSession, user: AdminUser):
    """Upload or replace a vehicle's profile photo. Admin only."""
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(404, VEHICLE_NOT_FOUND)
    ext = Path(file.filename).suffix.lower() or ".jpg"
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(400, FILE_TYPE_NOT_ALLOWED.format(ext))
    upload_dir = Path(settings.UPLOAD_DIR) / "photos" / "vehicles" / str(vehicle_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    for old in upload_dir.glob("profile.*"):
        old.unlink()
    filepath = upload_dir / f"profile{ext}"
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, FILE_TOO_LARGE.format(settings.MAX_UPLOAD_SIZE // (1024 * 1024)))
    await anyio.Path(filepath).write_bytes(content)
    vehicle.photo_url = f"/api/vehicles/{vehicle_id}/photo/view"
    db.commit()
    return {"ok": True, "photo_url": vehicle.photo_url}


@router.get("/{vehicle_id}/photo/view", responses=responses(401, 403, 404))
def view_vehicle_photo(vehicle_id: int, db: DBSession, _user: CurrentUser):
    """Serve a vehicle's profile photo with path-traversal prevention."""
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(404)
    photo_dir = Path(settings.UPLOAD_DIR) / "photos" / "vehicles" / str(vehicle_id)
    # Path traversal prevention
    resolved_dir = photo_dir.resolve()
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    if not str(resolved_dir).startswith(str(upload_root)):
        raise HTTPException(403, ACCESS_DENIED)
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        p = photo_dir / f"profile{ext}"
        if p.exists():
            return FileResponse(p)
    raise HTTPException(404, "No photo found")
