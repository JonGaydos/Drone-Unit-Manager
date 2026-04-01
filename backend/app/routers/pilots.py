"""Pilot CRUD endpoints with flight statistics and profile photo management."""

from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func

from app.config import settings
from app.constants import PILOT_NOT_FOUND, ACCESS_DENIED, FILE_TYPE_NOT_ALLOWED, FILE_TOO_LARGE
from app.deps import DBSession, CurrentUser, AdminUser, PilotUser, SupervisorUser
from app.models.pilot import Pilot
from app.models.flight import Flight
from app.schemas.pilot import PilotCreate, PilotUpdate, PilotOut, PilotStats
from app.responses import responses

router = APIRouter(prefix="/api/pilots", tags=["pilots"])


@router.get("", response_model=list[PilotOut])
def list_pilots(
    db: DBSession,
    user: CurrentUser,
    status: str | None = None):
    """List all pilots with optional status filtering.

    Args:
        status: Filter by pilot status (active, inactive).

    Returns:
        List of pilot records sorted by name.
    """
    q = db.query(Pilot)
    if status:
        q = q.filter(Pilot.status == status)
    return [PilotOut.model_validate(p) for p in q.order_by(Pilot.first_name, Pilot.last_name).all()]


@router.get("/{pilot_id}", response_model=PilotOut, responses=responses(401, 404))
def get_pilot(pilot_id: int, db: DBSession, user: CurrentUser):
    """Retrieve a single pilot by ID."""
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail=PILOT_NOT_FOUND)
    return PilotOut.model_validate(pilot)


@router.get("/{pilot_id}/stats", response_model=PilotStats, responses=responses(401, 404))
def get_pilot_stats(pilot_id: int, db: DBSession, user: CurrentUser):
    """Get aggregated flight statistics for a pilot (total flights, hours, avg duration)."""
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail=PILOT_NOT_FOUND)
    stats = db.query(
        func.count(Flight.id).label("total_flights"),
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("total_seconds"),
        func.coalesce(func.avg(Flight.duration_seconds), 0).label("avg_seconds"),
    ).filter(Flight.pilot_id == pilot_id).first()
    return PilotStats(
        total_flights=stats.total_flights,
        total_flight_hours=stats.total_seconds / 3600,
        avg_flight_duration_seconds=float(stats.avg_seconds),
    )


@router.post("", response_model=PilotOut, responses=responses(401))
def create_pilot(data: PilotCreate, db: DBSession, admin: SupervisorUser):
    """Create a new pilot record. Supervisor or admin only."""
    from app.services.audit import log_action
    pilot = Pilot(**data.model_dump())
    db.add(pilot)
    db.flush()
    log_action(db, admin.id, admin.display_name, "create", "pilot", pilot.id, f"{pilot.first_name} {pilot.last_name}")
    db.commit()
    db.refresh(pilot)
    return PilotOut.model_validate(pilot)


@router.patch("/{pilot_id}", response_model=PilotOut, responses=responses(401, 403, 404))
def update_pilot(pilot_id: int, data: PilotUpdate, db: DBSession, user: PilotUser):
    """Update a pilot's profile. Pilots can only edit their own; supervisors/admins can edit any."""
    from app.services.audit import log_action, compute_changes
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail=PILOT_NOT_FOUND)
    # Pilots can only edit their own profile; supervisors/admins can edit any
    if user.role == "pilot" and user.pilot_id != pilot_id:
        raise HTTPException(status_code=403, detail="You can only edit your own profile")
    update_data = data.model_dump(exclude_unset=True)
    changes = compute_changes(pilot, update_data, ["first_name", "last_name", "email", "status", "badge_number"])
    for key, value in update_data.items():
        setattr(pilot, key, value)
    if changes:
        log_action(db, user.id, user.display_name, "update", "pilot", pilot.id, f"{pilot.first_name} {pilot.last_name}", changes=changes)
    db.commit()
    db.refresh(pilot)
    return PilotOut.model_validate(pilot)


@router.delete("/{pilot_id}", responses=responses(401, 404))
def delete_pilot(pilot_id: int, db: DBSession, admin: SupervisorUser):
    """Soft-delete a pilot by setting status to inactive. Supervisor or admin only."""
    from app.services.audit import log_action
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail=PILOT_NOT_FOUND)
    pilot.status = "inactive"
    log_action(db, admin.id, admin.display_name, "deactivate", "pilot", pilot.id, f"{pilot.first_name} {pilot.last_name}")
    db.commit()
    return {"ok": True, "message": "Pilot deactivated"}


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


@router.post("/{pilot_id}/photo", responses=responses(400, 401, 404, 413))
async def upload_pilot_photo(pilot_id: int, file: UploadFile, db: DBSession, user: AdminUser):
    """Upload or replace a pilot's profile photo. Admin only."""
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(404, PILOT_NOT_FOUND)
    ext = Path(file.filename).suffix.lower() or ".jpg"
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(400, FILE_TYPE_NOT_ALLOWED.format(ext))
    upload_dir = Path(settings.UPLOAD_DIR) / "photos" / "pilots" / str(pilot_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    for old in upload_dir.glob("profile.*"):
        old.unlink()
    filepath = upload_dir / f"profile{ext}"
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, FILE_TOO_LARGE.format(settings.MAX_UPLOAD_SIZE // (1024 * 1024)))
    await anyio.Path(filepath).write_bytes(content)
    pilot.photo_url = f"/api/pilots/{pilot_id}/photo/view"
    db.commit()
    return {"ok": True, "photo_url": pilot.photo_url}


@router.get("/{pilot_id}/photo/view", responses=responses(401, 403, 404))
def view_pilot_photo(pilot_id: int, db: DBSession, _user: CurrentUser):
    """Serve a pilot's profile photo with path-traversal prevention."""
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(404)
    photo_dir = Path(settings.UPLOAD_DIR) / "photos" / "pilots" / str(pilot_id)
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
