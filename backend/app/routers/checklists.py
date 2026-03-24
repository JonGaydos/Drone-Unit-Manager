from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.checklist import ChecklistTemplate, ChecklistCompletion
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.user import User
from app.routers.auth import get_current_user, require_pilot, require_supervisor

router = APIRouter(prefix="/api/checklists", tags=["checklists"])


# --- Schemas ---

class ChecklistItemIn(BaseModel):
    label: str
    required: bool = True


class ChecklistTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    vehicle_model: Optional[str] = None
    items: list[ChecklistItemIn]


class ChecklistTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    vehicle_model: Optional[str] = None
    items: Optional[list[ChecklistItemIn]] = None
    is_active: Optional[bool] = None


class ChecklistResponseIn(BaseModel):
    label: str
    checked: bool = False
    notes: str = ""


class ChecklistCompleteIn(BaseModel):
    template_id: int
    flight_plan_id: Optional[int] = None
    flight_id: Optional[int] = None
    pilot_id: int
    vehicle_id: Optional[int] = None
    responses: list[ChecklistResponseIn]
    notes: Optional[str] = None


# --- Template Endpoints ---

@router.get("/templates")
def list_templates(
    active_only: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(ChecklistTemplate)
    if active_only:
        q = q.filter(ChecklistTemplate.is_active.is_(True))
    templates = q.order_by(ChecklistTemplate.name).all()
    return [_template_out(t) for t in templates]


@router.get("/templates/{template_id}")
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return _template_out(t)


@router.post("/templates")
def create_template(
    data: ChecklistTemplateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_supervisor),
):
    if not data.items:
        raise HTTPException(status_code=400, detail="At least one checklist item is required")
    template = ChecklistTemplate(
        name=data.name,
        description=data.description,
        vehicle_model=data.vehicle_model,
        items=[item.model_dump() for item in data.items],
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _template_out(template)


@router.patch("/templates/{template_id}")
def update_template(
    template_id: int,
    data: ChecklistTemplateUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_supervisor),
):
    t = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    updates = data.model_dump(exclude_unset=True)
    if "items" in updates and updates["items"] is not None:
        updates["items"] = [item if isinstance(item, dict) else item.model_dump() for item in data.items]
    for key, val in updates.items():
        setattr(t, key, val)
    db.commit()
    db.refresh(t)
    return _template_out(t)


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_supervisor),
):
    t = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(t)
    db.commit()
    return {"ok": True}


# --- Completion Endpoints ---

@router.post("/complete")
def complete_checklist(
    data: ChecklistCompleteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_pilot),
):
    template = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == data.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Validate pilot exists
    pilot = db.query(Pilot).filter(Pilot.id == data.pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail="Pilot not found")

    responses = [r.model_dump() for r in data.responses]
    all_passed = all(r["checked"] for r in responses if any(
        item.get("required", True) for item in (template.items or []) if item.get("label") == r["label"]
    ))

    completion = ChecklistCompletion(
        template_id=data.template_id,
        flight_plan_id=data.flight_plan_id,
        flight_id=data.flight_id,
        pilot_id=data.pilot_id,
        vehicle_id=data.vehicle_id,
        responses=responses,
        all_passed=all_passed,
        notes=data.notes,
    )
    db.add(completion)
    db.commit()
    db.refresh(completion)
    return _completion_out(completion, db)


@router.get("/completions")
def list_completions(
    pilot_id: Optional[int] = None,
    vehicle_id: Optional[int] = None,
    flight_plan_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(ChecklistCompletion)
    if pilot_id:
        q = q.filter(ChecklistCompletion.pilot_id == pilot_id)
    if vehicle_id:
        q = q.filter(ChecklistCompletion.vehicle_id == vehicle_id)
    if flight_plan_id:
        q = q.filter(ChecklistCompletion.flight_plan_id == flight_plan_id)
    if date_from:
        q = q.filter(func.date(ChecklistCompletion.completed_at) >= date_from)
    if date_to:
        q = q.filter(func.date(ChecklistCompletion.completed_at) <= date_to)
    completions = q.order_by(ChecklistCompletion.completed_at.desc()).all()
    return [_completion_out(c, db) for c in completions]


@router.get("/completions/{completion_id}")
def get_completion(
    completion_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    c = db.query(ChecklistCompletion).filter(ChecklistCompletion.id == completion_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Completion not found")
    return _completion_out(c, db)


# --- Helpers ---

def _template_out(t: ChecklistTemplate) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "vehicle_model": t.vehicle_model,
        "items": t.items or [],
        "is_active": t.is_active,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _completion_out(c: ChecklistCompletion, db: Session) -> dict:
    pilot = db.query(Pilot).filter(Pilot.id == c.pilot_id).first()
    template = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == c.template_id).first()
    vehicle = db.query(Vehicle).filter(Vehicle.id == c.vehicle_id).first() if c.vehicle_id else None
    return {
        "id": c.id,
        "template_id": c.template_id,
        "template_name": template.name if template else None,
        "flight_plan_id": c.flight_plan_id,
        "flight_id": c.flight_id,
        "pilot_id": c.pilot_id,
        "pilot_name": f"{pilot.first_name} {pilot.last_name}" if pilot else None,
        "vehicle_id": c.vehicle_id,
        "vehicle_name": f"{vehicle.manufacturer} {vehicle.model}" if vehicle else None,
        "responses": c.responses or [],
        "all_passed": c.all_passed,
        "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        "notes": c.notes,
    }
