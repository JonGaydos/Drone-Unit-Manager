from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.component import Component
from app.models.user import User
from app.routers.auth import get_current_user, require_pilot, require_supervisor
from app.services.audit import log_action

router = APIRouter(prefix="/api/components", tags=["components"])


# --- Schemas ---

class ComponentCreate(BaseModel):
    name: str
    component_type: str
    serial_number: Optional[str] = None
    vehicle_id: Optional[int] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: str = "active"
    install_date: Optional[str] = None
    flight_hours: float = 0.0
    max_flight_hours: Optional[float] = None
    warranty_expiry: Optional[str] = None
    replacement_cost: Optional[float] = None
    notes: Optional[str] = None


class ComponentUpdate(BaseModel):
    name: Optional[str] = None
    component_type: Optional[str] = None
    serial_number: Optional[str] = None
    vehicle_id: Optional[int] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None
    install_date: Optional[str] = None
    flight_hours: Optional[float] = None
    max_flight_hours: Optional[float] = None
    warranty_expiry: Optional[str] = None
    replacement_cost: Optional[float] = None
    notes: Optional[str] = None


def _serialize(c: Component) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "component_type": c.component_type,
        "serial_number": c.serial_number,
        "vehicle_id": c.vehicle_id,
        "manufacturer": c.manufacturer,
        "model": c.model,
        "status": c.status,
        "install_date": str(c.install_date) if c.install_date else None,
        "flight_hours": c.flight_hours,
        "max_flight_hours": c.max_flight_hours,
        "warranty_expiry": str(c.warranty_expiry) if c.warranty_expiry else None,
        "replacement_cost": c.replacement_cost,
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.get("")
def list_components(
    vehicle_id: Optional[int] = None,
    component_type: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Component)
    if vehicle_id is not None:
        q = q.filter(Component.vehicle_id == vehicle_id)
    if component_type:
        q = q.filter(Component.component_type == component_type)
    if status:
        q = q.filter(Component.status == status)
    return [_serialize(c) for c in q.order_by(Component.name).all()]


@router.get("/{component_id}")
def get_component(component_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.query(Component).filter(Component.id == component_id).first()
    if not c:
        raise HTTPException(404, "Component not found")
    return _serialize(c)


@router.post("", status_code=201)
def create_component(data: ComponentCreate, db: Session = Depends(get_db), user: User = Depends(require_pilot)):
    c = Component(
        name=data.name,
        component_type=data.component_type,
        serial_number=data.serial_number,
        vehicle_id=data.vehicle_id,
        manufacturer=data.manufacturer,
        model=data.model,
        status=data.status,
        install_date=date.fromisoformat(data.install_date) if data.install_date else None,
        flight_hours=data.flight_hours,
        max_flight_hours=data.max_flight_hours,
        warranty_expiry=date.fromisoformat(data.warranty_expiry) if data.warranty_expiry else None,
        replacement_cost=data.replacement_cost,
        notes=data.notes,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    log_action(db, user.id, "component.create", "component", c.id, new_data={"name": c.name})
    return _serialize(c)


@router.patch("/{component_id}")
def update_component(component_id: int, data: ComponentUpdate, db: Session = Depends(get_db), user: User = Depends(require_pilot)):
    c = db.query(Component).filter(Component.id == component_id).first()
    if not c:
        raise HTTPException(404, "Component not found")
    update_data = data.model_dump(exclude_unset=True)
    for field in ("install_date", "warranty_expiry"):
        if field in update_data and update_data[field]:
            update_data[field] = date.fromisoformat(update_data[field])
    for key, val in update_data.items():
        setattr(c, key, val)
    db.commit()
    db.refresh(c)
    log_action(db, user.id, "component.update", "component", c.id, new_data=update_data)
    return _serialize(c)


@router.delete("/{component_id}")
def delete_component(component_id: int, db: Session = Depends(get_db), user: User = Depends(require_supervisor)):
    c = db.query(Component).filter(Component.id == component_id).first()
    if not c:
        raise HTTPException(404, "Component not found")
    log_action(db, user.id, "component.delete", "component", c.id, old_data={"name": c.name})
    db.delete(c)
    db.commit()
    return {"ok": True}
