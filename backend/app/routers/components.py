from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.constants import COMPONENT_NOT_FOUND
from app.deps import DBSession, CurrentUser, PilotUser, SupervisorUser
from app.models.component import Component
from app.services.audit import log_action
from app.responses import responses

router = APIRouter(prefix="/api/components", tags=["components"])



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
    db: DBSession,
    user: CurrentUser,
    vehicle_id: Optional[int] = None,
    component_type: Optional[str] = None,
    status: Optional[str] = None):
    q = db.query(Component)
    if vehicle_id is not None:
        q = q.filter(Component.vehicle_id == vehicle_id)
    if component_type:
        q = q.filter(Component.component_type == component_type)
    if status:
        q = q.filter(Component.status == status)
    return [_serialize(c) for c in q.order_by(Component.name).all()]


@router.get("/{component_id}", responses=responses(401, 404))
def get_component(component_id: int, db: DBSession, user: CurrentUser):
    c = db.query(Component).filter(Component.id == component_id).first()
    if not c:
        raise HTTPException(404, COMPONENT_NOT_FOUND)
    return _serialize(c)


@router.post("", status_code=201, responses=responses(401))
def create_component(data: ComponentCreate, db: DBSession, user: PilotUser):
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
    log_action(db, user.id, user.display_name, "create", "component", c.id, data.name)
    return _serialize(c)


@router.patch("/{component_id}", responses=responses(401, 404))
def update_component(component_id: int, data: ComponentUpdate, db: DBSession, user: PilotUser):
    c = db.query(Component).filter(Component.id == component_id).first()
    if not c:
        raise HTTPException(404, COMPONENT_NOT_FOUND)
    update_data = data.model_dump(exclude_unset=True)
    for field in ("install_date", "warranty_expiry"):
        if field in update_data and update_data[field]:
            update_data[field] = date.fromisoformat(update_data[field])
    for key, val in update_data.items():
        setattr(c, key, val)
    db.commit()
    db.refresh(c)
    log_action(db, user.id, user.display_name, "update", "component", c.id, c.name, changes=update_data)
    return _serialize(c)


@router.delete("/{component_id}", responses=responses(401, 404))
def delete_component(component_id: int, db: DBSession, user: SupervisorUser):
    c = db.query(Component).filter(Component.id == component_id).first()
    if not c:
        raise HTTPException(404, COMPONENT_NOT_FOUND)
    log_action(db, user.id, user.display_name, "delete", "component", c.id, c.name)
    db.delete(c)
    db.commit()
    return {"ok": True}
