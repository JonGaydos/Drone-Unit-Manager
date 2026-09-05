"""Vehicle (drone) CRUD endpoints with flight statistics and profile photo management."""

from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.constants import VEHICLE_NOT_FOUND, ACCESS_DENIED, FILE_TYPE_NOT_ALLOWED, FILE_TOO_LARGE
from app.deps import DBSession, CurrentUser, AdminUser, SupervisorUser, PilotUser
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleUpdate, VehicleOut, VehicleLocationUpdate
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


@router.get("/locations", responses=responses(401))
def vehicle_locations(db: DBSession, user: CurrentUser):
    """Current location per active drone: the more recent of an active checkout
    (with a pilot) or a manually-set location. Readable by any user."""
    from app.models.equipment_checkout import EquipmentCheckout
    from app.models.pilot import Pilot
    vehicles = db.query(Vehicle).filter(Vehicle.status != "retired").all()
    vids = [v.id for v in vehicles]
    active = {}
    if vids:
        rows = db.query(EquipmentCheckout).filter(
            EquipmentCheckout.entity_type == "vehicle",
            EquipmentCheckout.entity_id.in_(vids),
            EquipmentCheckout.checked_in_at.is_(None),
        ).all()
        for c in rows:
            cur = active.get(c.entity_id)
            if cur is None or c.checked_out_at > cur.checked_out_at:
                active[c.entity_id] = c
    pilot_ids = {c.checked_out_by_id for c in active.values()}
    pilot_ids |= {v.manual_location_pilot_id for v in vehicles if v.manual_location_pilot_id}
    names = {}
    if pilot_ids:
        names = {p.id: p.full_name for p in db.query(Pilot).filter(Pilot.id.in_(pilot_ids)).all()}
    result = []
    for v in vehicles:
        label = v.nickname or f"{v.manufacturer} {v.model}"
        co = active.get(v.id)
        co_time = co.checked_out_at if co else None
        man_time = v.location_set_at
        location_text, source = "Unknown", "unknown"
        manual_newer = man_time is not None and (co_time is None or man_time >= co_time)
        if manual_newer:
            source = "manual"
            if v.manual_location_pilot_id:
                location_text = f"with {names.get(v.manual_location_pilot_id, 'a pilot')}"
            elif v.manual_location_place:
                location_text = v.manual_location_place
        elif co is not None:
            source = "checkout"
            location_text = f"with {names.get(co.checked_out_by_id, 'a pilot')}"
        result.append({"vehicle_id": v.id, "label": label, "location_text": location_text, "source": source})
    return result


@router.get("/{vehicle_id}", response_model=VehicleOut, responses=responses(401, 404))
def get_vehicle(vehicle_id: int, db: DBSession, user: CurrentUser):
    """Retrieve a single vehicle by ID."""
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail=VEHICLE_NOT_FOUND)
    return VehicleOut.model_validate(vehicle)


@router.post("/{target_id}/merge", responses=responses(400, 401, 404))
def merge_vehicles(target_id: int, merge_from_id: int, db: DBSession, admin: SupervisorUser):
    """Merge a duplicate vehicle (source) into a keeper (target).

    Reassigns every reference (flights, flight plans, incidents, mission and
    training logs, documents, registrations, components, checklist completions,
    equipment quals, and polymorphic equipment-checkout / maintenance / alert
    rows) from the source to the target, then deletes the source. Useful after a
    bad Skydio re-sync creates a duplicate airframe. Supervisor or admin only.
    """
    from app.services.audit import log_action
    from app.models.flight import Flight
    from app.models.flight_approval import FlightPlan
    from app.models.incident import Incident
    from app.models.mission_log import MissionLog
    from app.models.training_log import TrainingLog
    from app.models.document import Document
    from app.models.vehicle_registration import VehicleRegistration
    from app.models.component import Component
    from app.models.checklist import ChecklistCompletion
    from app.models.certification import PilotEquipmentQual
    from app.models.equipment_checkout import EquipmentCheckout
    from app.models.maintenance import MaintenanceRecord
    from app.models.maintenance_schedule import MaintenanceSchedule
    from app.models.alert import Alert

    if merge_from_id == target_id:
        raise HTTPException(400, "Cannot merge a vehicle into itself")
    target = db.query(Vehicle).filter(Vehicle.id == target_id).first()
    source = db.query(Vehicle).filter(Vehicle.id == merge_from_id).first()
    if not target or not source:
        raise HTTPException(404, VEHICLE_NOT_FOUND)

    def reassign(model, col):
        """Repoint a direct vehicle_id foreign key from source to target."""
        column = getattr(model, col)
        moved = db.query(model).filter(column == merge_from_id).update(
            {column: target_id}, synchronize_session=False
        )
        return moved

    def reassign_poly(model):
        """Repoint a polymorphic (entity_type='vehicle', entity_id) reference."""
        moved = db.query(model).filter(
            model.entity_type == "vehicle", model.entity_id == merge_from_id
        ).update({model.entity_id: target_id}, synchronize_session=False)
        return moved

    moved = (
        reassign(Flight, "vehicle_id")
        + reassign(FlightPlan, "vehicle_id")
        + reassign(Incident, "vehicle_id")
        + reassign(MissionLog, "vehicle_id")
        + reassign(TrainingLog, "vehicle_id")
        + reassign(Document, "vehicle_id")
        + reassign(VehicleRegistration, "vehicle_id")
        + reassign(Component, "vehicle_id")
        + reassign(ChecklistCompletion, "vehicle_id")
        + reassign(PilotEquipmentQual, "vehicle_id")
        + reassign_poly(EquipmentCheckout)
        + reassign_poly(MaintenanceRecord)
        + reassign_poly(MaintenanceSchedule)
        + reassign_poly(Document)
        + reassign_poly(Alert)
    )

    # The keeper adopts the source's provider identity when it lacks one, so
    # the next API sync matches it instead of recreating the duplicate.
    if not target.provider_serial and source.provider_serial:
        target.provider_serial = source.provider_serial
    if not target.api_provider and source.api_provider:
        target.api_provider = source.api_provider

    src_name = f"{source.manufacturer} {source.model}" + (f" ({source.nickname})" if source.nickname else "")
    tgt_name = f"{target.manufacturer} {target.model}" + (f" ({target.nickname})" if target.nickname else "")
    db.delete(source)
    log_action(db, admin.id, admin.display_name, "merge", "vehicle", target.id, tgt_name, details=f"{src_name} -> {tgt_name}")
    db.commit()
    db.refresh(target)
    return {"ok": True, "references_moved": moved, "message": f"Merged '{src_name}' into '{tgt_name}'"}


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
    from app.services.equipment_lifecycle import set_fields_with_lifecycle
    vehicle = Vehicle()
    set_fields_with_lifecycle(vehicle, data.model_dump())
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
    from app.services.equipment_lifecycle import set_fields_with_lifecycle
    update_data = data.model_dump(exclude_unset=True)
    changes = compute_changes(vehicle, update_data, ["nickname", "status", "manufacturer", "model", "serial_number"])
    set_fields_with_lifecycle(vehicle, update_data)
    if changes:
        log_action(db, admin.id, admin.display_name, "update", "vehicle", vehicle.id, vehicle.nickname or f"{vehicle.manufacturer} {vehicle.model}", changes=changes)
    db.commit()
    db.refresh(vehicle)
    return VehicleOut.model_validate(vehicle)


@router.patch("/{vehicle_id}/location", responses=responses(400, 401, 404))
def set_vehicle_location(vehicle_id: int, data: VehicleLocationUpdate, db: DBSession, user: PilotUser):
    """Manually set a drone's location to a pilot OR a named place. Pilots and above."""
    from datetime import datetime, timezone
    from app.services.audit import log_action
    from app.models.pilot import Pilot
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail=VEHICLE_NOT_FOUND)
    if (data.pilot_id is None) == (data.place is None):
        raise HTTPException(status_code=400, detail="Provide exactly one of pilot_id or place")
    if data.pilot_id is not None:
        pilot = db.query(Pilot).filter(Pilot.id == data.pilot_id).first()
        if not pilot:
            raise HTTPException(status_code=404, detail="Pilot not found")
        vehicle.manual_location_pilot_id = data.pilot_id
        vehicle.manual_location_place = None
        loc_label = f"with {pilot.full_name}"
    else:
        vehicle.manual_location_pilot_id = None
        vehicle.manual_location_place = data.place
        loc_label = data.place
    vehicle.location_set_at = datetime.now(timezone.utc).replace(tzinfo=None)
    vehicle.location_set_by_id = user.id
    log_action(db, user.id, user.display_name, "update", "vehicle", vehicle.id,
               vehicle.nickname or f"{vehicle.manufacturer} {vehicle.model}",
               details=f"Set location: {loc_label}")
    db.commit()
    return {"ok": True}


@router.delete("/{vehicle_id}", responses=responses(401, 404))
def delete_vehicle(vehicle_id: int, db: DBSession, admin: SupervisorUser):
    """Soft-delete a vehicle by setting status to retired. Supervisor or admin only."""
    from app.services.audit import log_action
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail=VEHICLE_NOT_FOUND)
    from datetime import date
    vehicle.status = "retired"
    if vehicle.decommissioned_date is None:
        vehicle.decommissioned_date = date.today()
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
    from app.services.file_validation import is_image
    if not is_image(content[:512]):
        raise HTTPException(400, "File content is not a recognized image")
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
