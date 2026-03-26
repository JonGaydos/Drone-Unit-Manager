from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.pilot import Pilot
from app.models.flight import Flight
from app.models.user import User
from app.routers.auth import get_current_user, require_admin, require_pilot, require_supervisor
from app.schemas.pilot import PilotCreate, PilotUpdate, PilotOut, PilotStats

router = APIRouter(prefix="/api/pilots", tags=["pilots"])


@router.get("", response_model=list[PilotOut])
def list_pilots(
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Pilot)
    if status:
        q = q.filter(Pilot.status == status)
    return [PilotOut.model_validate(p) for p in q.order_by(Pilot.first_name, Pilot.last_name).all()]


@router.get("/{pilot_id}", response_model=PilotOut)
def get_pilot(pilot_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail="Pilot not found")
    return PilotOut.model_validate(pilot)


@router.get("/{pilot_id}/stats", response_model=PilotStats)
def get_pilot_stats(pilot_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail="Pilot not found")
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


@router.post("", response_model=PilotOut)
def create_pilot(data: PilotCreate, db: Session = Depends(get_db), admin: User = Depends(require_supervisor)):
    from app.services.audit import log_action
    pilot = Pilot(**data.model_dump())
    db.add(pilot)
    db.flush()
    log_action(db, admin.id, admin.display_name, "create", "pilot", pilot.id, f"{pilot.first_name} {pilot.last_name}")
    db.commit()
    db.refresh(pilot)
    return PilotOut.model_validate(pilot)


@router.patch("/{pilot_id}", response_model=PilotOut)
def update_pilot(pilot_id: int, data: PilotUpdate, db: Session = Depends(get_db), user: User = Depends(require_pilot)):
    from app.services.audit import log_action, compute_changes
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail="Pilot not found")
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


@router.delete("/{pilot_id}")
def delete_pilot(pilot_id: int, db: Session = Depends(get_db), admin: User = Depends(require_supervisor)):
    from app.services.audit import log_action
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail="Pilot not found")
    pilot.status = "inactive"
    log_action(db, admin.id, admin.display_name, "deactivate", "pilot", pilot.id, f"{pilot.first_name} {pilot.last_name}")
    db.commit()
    return {"ok": True, "message": "Pilot deactivated"}


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


@router.post("/{pilot_id}/photo")
async def upload_pilot_photo(pilot_id: int, file: UploadFile, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(404, "Pilot not found")
    ext = Path(file.filename).suffix.lower() or ".jpg"
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' not allowed.")
    upload_dir = Path(settings.UPLOAD_DIR) / "photos" / "pilots" / str(pilot_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    for old in upload_dir.glob("profile.*"):
        old.unlink()
    filepath = upload_dir / f"profile{ext}"
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB")
    with open(filepath, "wb") as f:
        f.write(content)
    pilot.photo_url = f"/api/pilots/{pilot_id}/photo/view"
    db.commit()
    return {"ok": True, "photo_url": pilot.photo_url}


@router.get("/{pilot_id}/photo/view")
def view_pilot_photo(pilot_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(404)
    photo_dir = Path(settings.UPLOAD_DIR) / "photos" / "pilots" / str(pilot_id)
    # Path traversal prevention
    resolved_dir = photo_dir.resolve()
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    if not str(resolved_dir).startswith(str(upload_root)):
        raise HTTPException(403, "Access denied")
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        p = photo_dir / f"profile{ext}"
        if p.exists():
            return FileResponse(p)
    raise HTTPException(404, "No photo found")
