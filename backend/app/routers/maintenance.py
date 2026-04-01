from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import date
from typing import Optional

from app.constants import RECORD_NOT_FOUND
from app.deps import CurrentUser, DBSession, PilotUser
from app.models.maintenance import MaintenanceRecord
from app.responses import responses


class MaintenanceCreate(BaseModel):
    entity_type: str
    entity_id: int
    maintenance_type: str = "scheduled"
    description: str
    performed_by: Optional[str] = None
    performed_date: Optional[date] = None
    next_due_date: Optional[date] = None
    next_due_hours: Optional[float] = None
    cost: Optional[float] = None
    notes: Optional[str] = None


class MaintenanceUpdate(BaseModel):
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
    record = MaintenanceRecord(**data.model_dump())
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
    for key, value in data.model_dump(exclude_unset=True).items():
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
