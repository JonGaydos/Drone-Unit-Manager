"""Pilot CRUD endpoints with flight statistics and profile photo management."""

from datetime import date
from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func

from app.config import settings
from app.constants import PILOT_NOT_FOUND, ACCESS_DENIED, FILE_TYPE_NOT_ALLOWED, FILE_TOO_LARGE
from app.deps import DBSession, CurrentUser, AdminUser, PilotUser, SupervisorUser
from app.models.pilot import Pilot
from app.models.flight import Flight
from app.models.currency_rule import CurrencyRule
from app.models.certification import PilotCertification, CertificationType
from app.routers.currency import _pilot_currency
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


@router.get("/{pilot_id}/needs-attention", responses=responses(401, 404))
def get_pilot_needs_attention(pilot_id: int, db: DBSession, user: CurrentUser):
    """Aggregate a pilot's lapsed currency and expired/expiring certifications.

    Single source of truth for the Pilot Detail "Needs Attention" card.
    """
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail=PILOT_NOT_FOUND)

    items = []

    # Currency: any active rule the pilot is not current on.
    rules = db.query(CurrencyRule).filter(CurrencyRule.is_active.is_(True)).all()
    rule_results = _pilot_currency(pilot, rules, db)
    for r in rule_results:
        if not r["is_current"]:
            items.append({
                "level": "red",
                "category": "currency",
                "text": f"Currency lapsed: {r['rule_name']}",
            })

    # Certifications: expired or expiring within 30 days.
    certs = db.query(
        PilotCertification.expiration_date, CertificationType.name
    ).join(
        CertificationType,
        PilotCertification.certification_type_id == CertificationType.id,
    ).filter(PilotCertification.pilot_id == pilot_id).all()
    today = date.today()
    for expiration_date, name in certs:
        if expiration_date is None:
            continue
        days = (expiration_date - today).days
        if days < 0:
            items.append({
                "level": "red",
                "category": "certification",
                "text": f"Certification expired: {name} ({expiration_date})",
            })
        elif days <= 30:
            items.append({
                "level": "amber",
                "category": "certification",
                "text": f"Certification expiring in {days}d: {name} ({expiration_date})",
            })

    return {"count": len(items), "items": items}


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


class PilotMergeRequest(BaseModel):
    source_id: int


@router.post("/{target_id}/merge", responses=responses(400, 401, 404))
def merge_pilots(target_id: int, data: PilotMergeRequest, db: DBSession, admin: SupervisorUser):
    """Merge a duplicate pilot (source) into a keeper (target).

    Reassigns every reference (flights, mission/training rosters, certifications,
    equipment quals, checklists, documents, photos, incidents, equipment
    checkouts, controller assignment, maintenance schedule, linked user) from the
    source to the target, copies the source email onto the target when it has
    none (so future email-matched imports find the keeper), then deletes the
    source. Supervisor or admin only.
    """
    from app.services.audit import log_action
    source_id = data.source_id
    if source_id == target_id:
        raise HTTPException(400, "Cannot merge a pilot into itself")
    target = db.query(Pilot).filter(Pilot.id == target_id).first()
    source = db.query(Pilot).filter(Pilot.id == source_id).first()
    if not target or not source:
        raise HTTPException(404, PILOT_NOT_FOUND)

    from app.models.mission_log_pilot import MissionLogPilot
    from app.models.training_log_pilot import TrainingLogPilot
    from app.models.certification import PilotCertification, PilotEquipmentQual
    from app.models.checklist import ChecklistCompletion
    from app.models.controller import Controller
    from app.models.document import Document
    from app.models.equipment_checkout import EquipmentCheckout
    from app.models.flight_approval import FlightPlan
    from app.models.incident import Incident
    from app.models.maintenance_schedule import MaintenanceSchedule
    from app.models.photo import PhotoPilot
    from app.models.user import User

    def reassign(model, col, conflict_cols=None):
        """Move rows from source to target. With conflict_cols, drop a source row
        if the target already has a matching row (avoids logical duplicates on
        roster/cert tables)."""
        moved = 0
        for row in db.query(model).filter(getattr(model, col) == source_id).all():
            if conflict_cols and db.query(model).filter(
                getattr(model, col) == target_id,
                *[getattr(model, c) == getattr(row, c) for c in conflict_cols],
            ).first():
                db.delete(row)
                continue
            setattr(row, col, target_id)
            moved += 1
        db.flush()
        return moved

    moved = (
        reassign(Flight, "pilot_id")
        + reassign(MissionLogPilot, "pilot_id", ["mission_log_id"])
        + reassign(TrainingLogPilot, "pilot_id", ["training_log_id"])
        + reassign(PilotCertification, "pilot_id", ["certification_type_id"])
        + reassign(PilotEquipmentQual, "pilot_id")
        + reassign(ChecklistCompletion, "pilot_id")
        + reassign(Controller, "assigned_pilot_id")
        + reassign(Document, "pilot_id")
        + reassign(EquipmentCheckout, "checked_out_by_id")
        + reassign(EquipmentCheckout, "checked_in_by_id")
        + reassign(FlightPlan, "pilot_id")
        + reassign(Incident, "pilot_id")
        + reassign(MaintenanceSchedule, "assigned_to_id")
        + reassign(PhotoPilot, "pilot_id", ["photo_id"])
        + reassign(User, "pilot_id")
    )

    if not target.email and source.email:
        target.email = source.email

    src_name = f"{source.first_name} {source.last_name}".strip()
    tgt_name = f"{target.first_name} {target.last_name}".strip()
    db.delete(source)
    log_action(db, admin.id, admin.display_name, "merge", "pilot", target.id, tgt_name, details=f"{src_name} -> {tgt_name}")
    db.commit()
    db.refresh(target)
    return {"ok": True, "references_moved": moved, "target": PilotOut.model_validate(target)}


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
    from app.services.file_validation import is_image
    if not is_image(content[:512]):
        raise HTTPException(400, "File content is not a recognized image")
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
