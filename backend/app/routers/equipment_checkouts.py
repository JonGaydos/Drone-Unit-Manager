from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.constants import CHECKOUT_NOT_FOUND
from app.deps import DBSession, CurrentUser, PilotUser, SupervisorUser
from app.models.attachment import Attachment
from app.models.battery import Battery
from app.models.controller import Controller
from app.models.dock import Dock
from app.models.equipment_checkout import EquipmentCheckout
from app.models.other_equipment import OtherEquipment
from app.models.sensor import SensorPackage
from app.models.vehicle import Vehicle
from app.responses import responses

router = APIRouter(prefix="/api/equipment-checkouts", tags=["equipment-checkouts"])


# entity_type -> model. Every allowed type has a table to verify against.
ENTITY_MODELS = {
    "vehicle": Vehicle,
    "battery": Battery,
    "controller": Controller,
    "dock": Dock,
    "sensor": SensorPackage,
    "attachment": Attachment,
    "other": OtherEquipment,
}


def _validate_entity(db, entity_type: str, entity_id: int) -> None:
    """Reject unknown entity_type (400) and a missing entity_id row (404)."""
    if entity_type not in ENTITY_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity_type '{entity_type}'. Allowed: {', '.join(sorted(ENTITY_MODELS))}",
        )
    model = ENTITY_MODELS[entity_type]
    if model is not None:
        if not db.query(model).filter(model.id == entity_id).first():
            raise HTTPException(status_code=404, detail=f"{entity_type} #{entity_id} not found")



class CheckoutCreate(BaseModel):
    entity_type: str  # vehicle, battery, controller
    entity_id: int
    entity_name: Optional[str] = None
    checked_out_by_id: int
    expected_return: Optional[datetime] = None
    condition_out: Optional[str] = None  # good, fair, needs_attention
    notes_out: Optional[str] = None


class CheckinData(BaseModel):
    checked_in_by_id: int
    condition_in: Optional[str] = None
    notes_in: Optional[str] = None


class CheckoutOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    entity_name: Optional[str] = None
    checked_out_by_id: int
    checked_out_at: datetime
    expected_return: Optional[datetime] = None
    checked_in_at: Optional[datetime] = None
    checked_in_by_id: Optional[int] = None
    condition_out: Optional[str] = None
    condition_in: Optional[str] = None
    notes_out: Optional[str] = None
    notes_in: Optional[str] = None
    created_at: datetime
    # Virtual fields populated in endpoints
    checked_out_by_name: Optional[str] = None
    checked_in_by_name: Optional[str] = None
    model_config = {"from_attributes": True}


@router.get("")
def list_checkouts(

    db: DBSession,

    user: CurrentUser,

    entity_type: Annotated[Optional[str], Query()] = None,

    entity_id: Annotated[Optional[int], Query()] = None,

    pilot_id: Annotated[Optional[int], Query()] = None,

    active_only: Annotated[bool, Query()] = False,
):
    q = db.query(EquipmentCheckout)
    if entity_type:
        q = q.filter(EquipmentCheckout.entity_type == entity_type)
    if entity_id is not None:
        q = q.filter(EquipmentCheckout.entity_id == entity_id)
    if pilot_id is not None:
        q = q.filter(EquipmentCheckout.checked_out_by_id == pilot_id)
    if active_only:
        q = q.filter(EquipmentCheckout.checked_in_at.is_(None))
    rows = q.order_by(EquipmentCheckout.checked_out_at.desc()).limit(200).all()
    return [_enrich(r, db) for r in rows]


@router.get("/active")
def list_active_checkouts(
    db: DBSession,
    user: CurrentUser,
):
    rows = (
        db.query(EquipmentCheckout)
        .filter(EquipmentCheckout.checked_in_at.is_(None))
        .order_by(EquipmentCheckout.checked_out_at.desc())
        .all()
    )
    return [_enrich(r, db) for r in rows]


@router.post("", responses=responses(409))
def create_checkout(
    data: CheckoutCreate,
    db: DBSession,
    user: PilotUser,
):
    """Create a checkout. The 'checked_out_by_id' (pilot who has the equipment)
    can be set to any pilot — the frontend defaults to the logged-in user but
    allows override (e.g. supervisor recording a checkout on behalf of someone
    else). Audit log captures who actually entered the record."""
    from app.services.audit import log_action
    from app.models.pilot import Pilot

    _validate_entity(db, data.entity_type, data.entity_id)

    # Prevent double-checkout (best-effort; a unique partial index would
    # close the race definitively but requires a migration).
    existing = (
        db.query(EquipmentCheckout)
        .filter(
            EquipmentCheckout.entity_type == data.entity_type,
            EquipmentCheckout.entity_id == data.entity_id,
            EquipmentCheckout.checked_in_at.is_(None),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="This equipment is already checked out")

    pilot = db.query(Pilot).filter(Pilot.id == data.checked_out_by_id).first()
    if not pilot:
        raise HTTPException(status_code=400, detail="checked_out_by_id does not match a known pilot")

    checkout = EquipmentCheckout(**data.model_dump())
    db.add(checkout)
    db.flush()
    on_behalf = " (on behalf of)" if user.pilot_id != pilot.id else ""
    log_action(
        db, user.id, user.display_name, "checkout", "equipment", checkout.id,
        f"{data.entity_type} #{data.entity_id}",
        details=f"checked out {data.entity_type} #{data.entity_id} to {pilot.full_name}{on_behalf}",
    )
    db.commit()
    db.refresh(checkout)
    return _enrich(checkout, db)


@router.post("/{checkout_id}/checkin", responses=responses(400, 404))
def checkin_equipment(
    checkout_id: int,
    data: CheckinData,
    db: DBSession,
    user: PilotUser,
):
    """Mark a checkout returned. Logs who entered the check-in (the JWT
    user) and which pilot returned the item (data.checked_in_by_id)."""
    from app.services.audit import log_action
    from app.models.pilot import Pilot

    checkout = db.query(EquipmentCheckout).filter(EquipmentCheckout.id == checkout_id).first()
    if not checkout:
        raise HTTPException(status_code=404, detail=CHECKOUT_NOT_FOUND)
    if checkout.checked_in_at is not None:
        raise HTTPException(status_code=400, detail="Already checked in")

    in_pilot = db.query(Pilot).filter(Pilot.id == data.checked_in_by_id).first()
    if not in_pilot:
        raise HTTPException(status_code=400, detail="checked_in_by_id does not match a known pilot")

    checkout.checked_in_at = datetime.now(timezone.utc)
    checkout.checked_in_by_id = data.checked_in_by_id
    checkout.condition_in = data.condition_in
    checkout.notes_in = data.notes_in
    on_behalf = " (on behalf of)" if user.pilot_id != in_pilot.id else ""
    log_action(
        db, user.id, user.display_name, "checkin", "equipment", checkout.id,
        f"{checkout.entity_type} #{checkout.entity_id}",
        details=f"checked in {checkout.entity_type} #{checkout.entity_id} by {in_pilot.full_name}{on_behalf}",
    )
    db.commit()
    db.refresh(checkout)
    return _enrich(checkout, db)


@router.delete("/{checkout_id}", responses=responses(404))
def delete_checkout(
    checkout_id: int,
    db: DBSession,
    user: SupervisorUser,
):
    from app.services.audit import log_action
    checkout = db.query(EquipmentCheckout).filter(EquipmentCheckout.id == checkout_id).first()
    if not checkout:
        raise HTTPException(status_code=404, detail=CHECKOUT_NOT_FOUND)
    log_action(
        db, user.id, user.display_name, "delete", "equipment", checkout.id,
        f"{checkout.entity_type} #{checkout.entity_id}",
        details=f"deleted checkout record for {checkout.entity_type} #{checkout.entity_id}",
    )
    db.delete(checkout)
    db.commit()
    return {"ok": True}


def _enrich(checkout: EquipmentCheckout, db: Session) -> dict:
    """Add pilot names to the checkout record."""
    from app.models.pilot import Pilot
    out_pilot = db.query(Pilot).filter(Pilot.id == checkout.checked_out_by_id).first()
    in_pilot = None
    if checkout.checked_in_by_id:
        in_pilot = db.query(Pilot).filter(Pilot.id == checkout.checked_in_by_id).first()

    return {
        "id": checkout.id,
        "entity_type": checkout.entity_type,
        "entity_id": checkout.entity_id,
        "entity_name": checkout.entity_name,
        "checked_out_by_id": checkout.checked_out_by_id,
        "checked_out_by_name": out_pilot.full_name if out_pilot else None,
        "checked_out_at": checkout.checked_out_at.isoformat() if checkout.checked_out_at else None,
        "expected_return": checkout.expected_return.isoformat() if checkout.expected_return else None,
        "checked_in_at": checkout.checked_in_at.isoformat() if checkout.checked_in_at else None,
        "checked_in_by_id": checkout.checked_in_by_id,
        "checked_in_by_name": in_pilot.full_name if in_pilot else None,
        "condition_out": checkout.condition_out,
        "condition_in": checkout.condition_in,
        "notes_out": checkout.notes_out,
        "notes_in": checkout.notes_in,
        "created_at": checkout.created_at.isoformat() if checkout.created_at else None,
    }
