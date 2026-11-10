"""Pilot CRUD endpoints with flight statistics and profile photo management."""

from datetime import date
from pathlib import Path
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func

from app.config import settings
from app.constants import PILOT_NOT_FOUND, ACCESS_DENIED, FILE_TYPE_NOT_ALLOWED, FILE_TOO_LARGE
from app.deps import AdminForm, DBSession, CurrentUser
from app.models.user import User
from app.routers.auth import require_permission
from app.models.pilot import Pilot
from app.models.flight import Flight
from app.models.currency_rule import CurrencyRule
from app.models.certification import PilotCertification, CertificationType
from app.routers.currency import _pilot_currency
from app.schemas.pilot import PilotCreate, PilotUpdate, PilotOut, PilotStats
from app.responses import responses
from app.services import permissions as permissions_service
from app.services.pilot_contacts import CONTACT_FIELDS, hides_contacts, pilot_out

router = APIRouter(prefix="/api/pilots", tags=["pilots"])

EDIT_KEY = "pilots.edit"
MANAGE_KEY = "pilots.manage"

ViewUser = Annotated[User, Depends(require_permission("pilots.view"))]
EditUser = Annotated[User, Depends(require_permission(EDIT_KEY))]
ManageUser = Annotated[User, Depends(require_permission(MANAGE_KEY))]
# Figures drawn from another feature follow that feature's view permission.
FlightsViewUser = Annotated[User, Depends(require_permission("flights.view"))]
CertificationsViewUser = Annotated[User, Depends(require_permission("certifications.view"))]


@router.get("/options", responses=responses(401))
def pilot_options(db: DBSession, user: CurrentUser):
    """Pilots for a picker: id, name, badge number and status, with no contact details.

    Open to any signed-in user so forms can offer a pilot without the pilots
    list. Inactive pilots are included with their status.
    """
    pilots = db.query(Pilot).order_by(Pilot.first_name, Pilot.last_name).all()
    return [
        {"id": p.id, "full_name": p.full_name, "badge_number": p.badge_number, "status": p.status}
        for p in pilots
    ]


@router.get("", response_model=list[PilotOut])
def list_pilots(
    db: DBSession,
    user: ViewUser,
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
    return [pilot_out(db, p, user) for p in q.order_by(Pilot.first_name, Pilot.last_name).all()]


@router.get("/{pilot_id}", response_model=PilotOut, responses=responses(401, 404))
def get_pilot(pilot_id: int, db: DBSession, user: ViewUser):
    """Retrieve a single pilot by ID."""
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail=PILOT_NOT_FOUND)
    return pilot_out(db, pilot, user)


@router.get("/{pilot_id}/stats", response_model=PilotStats, responses=responses(401, 404))
def get_pilot_stats(pilot_id: int, db: DBSession, user: ViewUser, _flights: FlightsViewUser):
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
def get_pilot_needs_attention(pilot_id: int, db: DBSession, user: ViewUser, _certifications: CertificationsViewUser):
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
    ).filter(
        PilotCertification.pilot_id == pilot_id,
        # Archived (renewed) and never-issued records, as on the compliance dashboard.
        PilotCertification.status.notin_(["not_issued", "renewed"]),
    ).all()
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


def _check_badge_free(db, badge: str | None, pilot_id: int | None = None) -> None:
    """Refuse a badge number another pilot already has (trimmed, any case)."""
    if not badge or not badge.strip():
        return
    q = db.query(Pilot).filter(func.lower(func.trim(Pilot.badge_number)) == badge.strip().lower())
    if pilot_id is not None:
        q = q.filter(Pilot.id != pilot_id)
    holder = q.first()
    if holder:
        raise HTTPException(status_code=400, detail=f"Badge number {badge.strip()} is already used by {holder.full_name}")


@router.post("", response_model=PilotOut, responses=responses(400, 401))
def create_pilot(data: PilotCreate, db: DBSession, admin: ManageUser):
    """Create a new pilot record. Needs the pilots.manage permission."""
    from app.services.audit import log_action
    _check_badge_free(db, data.badge_number)
    pilot = Pilot(**data.model_dump())
    db.add(pilot)
    db.flush()
    log_action(db, admin.id, admin.display_name, "create", "pilot", pilot.id, f"{pilot.first_name} {pilot.last_name}")
    db.commit()
    db.refresh(pilot)
    return pilot_out(db, pilot, admin)


# Profile fields a pilot may not change on their own record: reactivating
# yourself, dropping out of unit totals, or pointing your photo at an outside
# URL are supervisor decisions.
SUPERVISOR_ONLY_PILOT_FIELDS = ("status", "counts_toward_totals", "photo_url")


@router.patch("/{pilot_id}", response_model=PilotOut, responses=responses(400, 401, 403, 404))
def update_pilot(pilot_id: int, data: PilotUpdate, db: DBSession, user: EditUser):
    """Update a pilot's profile.

    The pilots.edit level decides whether the user may edit this pilot: Own
    covers the pilot linked to their account, All covers any pilot.
    """
    from app.services.audit import log_action, compute_changes
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail=PILOT_NOT_FOUND)
    owned = user.pilot_id is not None and user.pilot_id == pilot_id
    permissions_service.require_record_access(db, user, EDIT_KEY, owned)
    update_data = data.model_dump(exclude_unset=True)
    # This user sees these fields masked, so a value sent back means nothing.
    if hides_contacts(db, user):
        for field in CONTACT_FIELDS:
            update_data.pop(field, None)
    # Rejected only on an actual change, so a form echoing current values works.
    if not permissions_service.can(db, user, MANAGE_KEY) and any(
        f in update_data and update_data[f] != getattr(pilot, f) for f in SUPERVISOR_ONLY_PILOT_FIELDS
    ):
        raise HTTPException(status_code=403, detail="Status, unit totals and photo URL need the pilots.manage permission")
    if "badge_number" in update_data:
        _check_badge_free(db, update_data["badge_number"], pilot_id)
    changes = compute_changes(pilot, update_data, list(update_data.keys()))
    for key, value in update_data.items():
        setattr(pilot, key, value)
    if changes:
        log_action(db, user.id, user.display_name, "update", "pilot", pilot.id, f"{pilot.first_name} {pilot.last_name}", changes=changes)
    db.commit()
    db.refresh(pilot)
    return pilot_out(db, pilot, user)


@router.delete("/{pilot_id}", responses=responses(401, 404))
def delete_pilot(pilot_id: int, db: DBSession, admin: ManageUser):
    """Soft-delete a pilot by setting status to inactive. Needs the pilots.manage permission."""
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


def _expires_later(a: PilotCertification, b: PilotCertification) -> bool:
    """Whether a expires strictly after b; a missing date counts as earliest."""
    return (a.expiration_date or date.min) > (b.expiration_date or date.min)


def _merge_certifications(db, source_id: int, target_id: int) -> int:
    """Move the source pilot's certifications to the target.

    Where both pilots hold the same certification type, the one that expires
    later is kept, whichever pilot it came from, and the other's documents and
    renewal links move onto it before it is deleted. Returns the number of
    source certifications that ended up on the target.
    """
    from app.models.document import Document
    from app.services.audit_capture import update_recorded
    moved = 0
    for cert in db.query(PilotCertification).filter(PilotCertification.pilot_id == source_id).all():
        twin = db.query(PilotCertification).filter(
            PilotCertification.pilot_id == target_id,
            PilotCertification.certification_type_id == cert.certification_type_id,
        ).first()
        if twin is None:
            cert.pilot_id = target_id
            moved += 1
            continue
        keep, drop = (cert, twin) if _expires_later(cert, twin) else (twin, cert)
        keep.pilot_id = target_id
        if keep.renewed_from_id == drop.id:
            keep.renewed_from_id = None
        update_recorded(db, db.query(Document).filter(Document.certification_id == drop.id),
                        {Document.certification_id: (drop.id, keep.id)})
        update_recorded(db, db.query(PilotCertification).filter(PilotCertification.renewed_from_id == drop.id),
                        {PilotCertification.renewed_from_id: (drop.id, keep.id)})
        db.delete(drop)
        if keep is cert:
            moved += 1
    db.flush()
    return moved


@router.post("/{target_id}/merge", responses=responses(400, 401, 404))
def merge_pilots(target_id: int, data: PilotMergeRequest, db: DBSession, admin: ManageUser):
    """Merge a duplicate pilot (source) into a keeper (target).

    Reassigns every reference (flights, mission/training rosters, certifications,
    equipment quals, checklists, documents, photos, incidents, equipment
    checkouts, controller assignment, maintenance schedule, linked user, calendar
    events, vehicle location) from the source to the target, copies the source
    email onto the target when it has none (so future email-matched imports find
    the keeper), then deletes the source. Needs the pilots.manage permission.
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
    from app.models.certification import PilotEquipmentQual
    from app.models.calendar_event import CalendarEvent
    from app.models.checklist import ChecklistCompletion
    from app.models.controller import Controller
    from app.models.document import Document
    from app.models.equipment_checkout import EquipmentCheckout
    from app.models.flight_approval import FlightPlan
    from app.models.incident import Incident
    from app.models.maintenance_schedule import MaintenanceSchedule
    from app.models.photo import PhotoPilot
    from app.models.user import User
    from app.models.vehicle import Vehicle

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
        + _merge_certifications(db, source_id, target_id)
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
        + reassign(CalendarEvent, "pilot_id")
        + reassign(Vehicle, "manual_location_pilot_id")
    )

    if not target.email and source.email:
        target.email = source.email

    src_name = f"{source.first_name} {source.last_name}".strip()
    tgt_name = f"{target.first_name} {target.last_name}".strip()
    db.delete(source)
    log_action(db, admin.id, admin.display_name, "merge", "pilot", target.id, tgt_name, details=f"{src_name} -> {tgt_name}")
    db.commit()
    db.refresh(target)
    return {"ok": True, "references_moved": moved, "target": pilot_out(db, target, admin)}


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


@router.post("/{pilot_id}/photo", responses=responses(400, 401, 404, 413))
async def upload_pilot_photo(pilot_id: int, upload: AdminForm, db: DBSession):
    """Upload or replace a pilot's profile photo. Admin only."""
    file = upload.file
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(404, PILOT_NOT_FOUND)
    ext = Path(file.filename).suffix.lower() or ".jpg"
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(400, FILE_TYPE_NOT_ALLOWED.format(ext))
    upload_dir = Path(settings.UPLOAD_DIR) / "photos" / "pilots" / str(pilot_id)
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, FILE_TOO_LARGE.format(settings.MAX_UPLOAD_SIZE // (1024 * 1024)))
    from app.services.file_validation import is_image
    if not is_image(content[:512]):
        raise HTTPException(400, "File content is not a recognized image")
    # Only a valid upload replaces the photo: write it, then drop the old one.
    upload_dir.mkdir(parents=True, exist_ok=True)
    filepath = upload_dir / f"profile{ext}"
    await anyio.Path(filepath).write_bytes(content)
    for old in upload_dir.glob("profile.*"):
        if old.name != filepath.name:
            old.unlink()
    pilot.photo_url = f"/api/pilots/{pilot_id}/photo/view"
    db.commit()
    return {"ok": True, "photo_url": pilot.photo_url}


@router.get("/{pilot_id}/photo/view", responses=responses(401, 403, 404))
def view_pilot_photo(pilot_id: int, db: DBSession, _user: ViewUser):
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
    # Every type the upload accepts, served as the type its extension names.
    from app.services.file_validation import mime_for_filename
    for ext in sorted(ALLOWED_IMAGE_EXTENSIONS):
        p = photo_dir / f"profile{ext}"
        if p.exists():
            return FileResponse(p, media_type=mime_for_filename(p.name))
    raise HTTPException(404, "No photo found")
