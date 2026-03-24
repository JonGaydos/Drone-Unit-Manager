from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.equipment_checkout import EquipmentCheckout
from app.models.user import User
from app.routers.auth import get_current_user, require_pilot, require_supervisor

router = APIRouter(prefix="/api/equipment-checkouts", tags=["equipment-checkouts"])


# ── Schemas ──────────────────────────────────────────────────────────────

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
    entity_name: Optional[str]
    checked_out_by_id: int
    checked_out_at: datetime
    expected_return: Optional[datetime]
    checked_in_at: Optional[datetime]
    checked_in_by_id: Optional[int]
    condition_out: Optional[str]
    condition_in: Optional[str]
    notes_out: Optional[str]
    notes_in: Optional[str]
    created_at: datetime
    # Virtual fields populated in endpoints
    checked_out_by_name: Optional[str] = None
    checked_in_by_name: Optional[str] = None
    model_config = {"from_attributes": True}


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("")
def list_checkouts(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[int] = Query(None),
    pilot_id: Optional[int] = Query(None),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        db.query(EquipmentCheckout)
        .filter(EquipmentCheckout.checked_in_at.is_(None))
        .order_by(EquipmentCheckout.checked_out_at.desc())
        .all()
    )
    return [_enrich(r, db) for r in rows]


@router.post("")
def create_checkout(
    data: CheckoutCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_pilot),
):
    # Prevent double-checkout
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

    checkout = EquipmentCheckout(**data.model_dump())
    db.add(checkout)
    db.commit()
    db.refresh(checkout)
    return _enrich(checkout, db)


@router.post("/{checkout_id}/checkin")
def checkin_equipment(
    checkout_id: int,
    data: CheckinData,
    db: Session = Depends(get_db),
    user: User = Depends(require_pilot),
):
    checkout = db.query(EquipmentCheckout).filter(EquipmentCheckout.id == checkout_id).first()
    if not checkout:
        raise HTTPException(status_code=404, detail="Checkout record not found")
    if checkout.checked_in_at is not None:
        raise HTTPException(status_code=400, detail="Already checked in")

    checkout.checked_in_at = datetime.utcnow()
    checkout.checked_in_by_id = data.checked_in_by_id
    checkout.condition_in = data.condition_in
    checkout.notes_in = data.notes_in
    db.commit()
    db.refresh(checkout)
    return _enrich(checkout, db)


@router.delete("/{checkout_id}")
def delete_checkout(
    checkout_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_supervisor),
):
    checkout = db.query(EquipmentCheckout).filter(EquipmentCheckout.id == checkout_id).first()
    if not checkout:
        raise HTTPException(status_code=404, detail="Checkout record not found")
    db.delete(checkout)
    db.commit()
    return {"ok": True}


# ── Helpers ──────────────────────────────────────────────────────────────

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
