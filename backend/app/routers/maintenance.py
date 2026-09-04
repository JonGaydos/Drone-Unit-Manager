from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import date
from typing import Optional

from app.constants import RECORD_NOT_FOUND
from app.deps import CurrentUser, DBSession, PilotUser
from app.models.attachment import Attachment
from app.models.battery import Battery
from app.models.controller import Controller
from app.models.dock import Dock
from app.models.maintenance import MaintenanceRecord
from app.models.other_equipment import OtherEquipment
from app.models.sensor import SensorPackage
from app.models.vehicle import Vehicle
from app.responses import responses


# entity_type -> model. None means the type is allowed but has no table to
# verify against (existence check is skipped).
ENTITY_MODELS = {
    "vehicle": Vehicle,
    "battery": Battery,
    "controller": Controller,
    "dock": Dock,
    "sensor": SensorPackage,
    "attachment": Attachment,
    "organization": None,
    "other": OtherEquipment,
}

# "other" predates the other_equipment table, so legacy records have no
# entity_id; it stays optional for that type.
OPTIONAL_ENTITY_ID = {"other"}


def _validate_entity(db, entity_type: str, entity_id: int | None) -> None:
    """Reject unknown entity_type (400) and a missing entity_id row (404).

    "organization" has no table; the existence check is skipped and no
    entity_id is required. "other" accepts a null entity_id for legacy
    records but verifies the row when one is supplied."""
    if entity_type not in ENTITY_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity_type '{entity_type}'. Allowed: {', '.join(sorted(ENTITY_MODELS))}",
        )
    model = ENTITY_MODELS[entity_type]
    if model is not None:
        if entity_id is None:
            if entity_type not in OPTIONAL_ENTITY_ID:
                raise HTTPException(status_code=400, detail=f"entity_id is required for entity_type '{entity_type}'")
        elif not db.query(model).filter(model.id == entity_id).first():
            raise HTTPException(status_code=404, detail=f"{entity_type} #{entity_id} not found")


class MaintenanceCreate(BaseModel):
    entity_type: str
    entity_id: Optional[int] = None
    maintenance_type: str = "scheduled"
    description: str
    performed_by: Optional[str] = None
    performed_date: Optional[date] = None
    next_due_date: Optional[date] = None
    next_due_hours: Optional[float] = None
    cost: Optional[float] = None
    notes: Optional[str] = None


class MaintenanceUpdate(BaseModel):
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    maintenance_type: Optional[str] = None
    description: Optional[str] = None
    performed_by: Optional[str] = None
    performed_date: Optional[date] = None
    next_due_date: Optional[date] = None
    next_due_hours: Optional[float] = None
    cost: Optional[float] = None
    notes: Optional[str] = None


class MaintenanceOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    maintenance_type: str
    description: str
    performed_by: Optional[str] = None
    performed_date: Optional[date] = None
    next_due_date: Optional[date] = None
    next_due_hours: Optional[float] = None
    cost: Optional[float] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


@router.get("", response_model=list[MaintenanceOut])
def list_maintenance(
    db: DBSession,
    user: CurrentUser,
    entity_type: str | None = None,
    entity_id: int | None = None,
    upcoming: bool = False):
    q = db.query(MaintenanceRecord)
    if entity_type:
        q = q.filter(MaintenanceRecord.entity_type == entity_type)
    if entity_id:
        q = q.filter(MaintenanceRecord.entity_id == entity_id)
    if upcoming:
        q = q.filter(MaintenanceRecord.next_due_date.isnot(None)).order_by(MaintenanceRecord.next_due_date)
    else:
        q = q.order_by(MaintenanceRecord.performed_date.desc())
    return [MaintenanceOut.model_validate(m) for m in q.limit(200).all()]


@router.get("/{record_id}", response_model=MaintenanceOut, responses=responses(401, 404))
def get_maintenance(record_id: int, db: DBSession, user: CurrentUser):
    record = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=RECORD_NOT_FOUND)
    return MaintenanceOut.model_validate(record)


@router.post("", response_model=MaintenanceOut, responses=responses(401))
def create_maintenance(data: MaintenanceCreate, db: DBSession, admin: PilotUser):
    from app.services.audit import log_action
    _validate_entity(db, data.entity_type, data.entity_id)
    # entity_id is NOT NULL in the table; table-less types ("other",
    # "organization") use the same sentinel 0 as schedule completion.
    payload = data.model_dump()
    if payload["entity_id"] is None:
        payload["entity_id"] = 0
    record = MaintenanceRecord(**payload)
    db.add(record)
    db.flush()
    log_action(db, admin.id, admin.display_name, "create", "maintenance", record.id, record.description[:100] if record.description else None)
    db.commit()
    db.refresh(record)
    return MaintenanceOut.model_validate(record)


@router.patch("/{record_id}", response_model=MaintenanceOut, responses=responses(401, 404))
def update_maintenance(record_id: int, data: MaintenanceUpdate, db: DBSession, admin: PilotUser):
    from app.services.audit import log_action
    record = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=RECORD_NOT_FOUND)
    update_data = data.model_dump(exclude_unset=True)
    if "entity_type" in update_data or "entity_id" in update_data:
        new_type = update_data.get("entity_type", record.entity_type)
        id_optional = ENTITY_MODELS.get(new_type) is None or new_type in OPTIONAL_ENTITY_ID
        # Changing to a different table-backed type requires a fresh entity_id;
        # the old id must not be reinterpreted against the new type's table.
        if new_type != record.entity_type and "entity_id" not in update_data:
            if id_optional:
                update_data["entity_id"] = 0
            else:
                raise HTTPException(status_code=400, detail=f"entity_id is required when changing entity_type to '{new_type}'")
        new_id = update_data.get("entity_id", record.entity_id)
        # The stored sentinel 0 ("no entity") is None for validation.
        _validate_entity(db, new_type, new_id or None)
        if id_optional and not new_id:
            update_data["entity_id"] = 0
    for key, value in update_data.items():
        setattr(record, key, value)
    log_action(db, admin.id, admin.display_name, "update", "maintenance", record.id, record.description[:100] if record.description else None)
    db.commit()
    db.refresh(record)
    return MaintenanceOut.model_validate(record)


@router.delete("/{record_id}", responses=responses(401, 404))
def delete_maintenance(record_id: int, db: DBSession, admin: PilotUser):
    from app.services.audit import log_action
    record = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=RECORD_NOT_FOUND)
    log_action(db, admin.id, admin.display_name, "delete", "maintenance", record.id, record.description[:100] if record.description else None)
    db.delete(record)
    db.commit()
    return {"ok": True}
