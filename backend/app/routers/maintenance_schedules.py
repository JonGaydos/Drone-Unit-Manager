import calendar
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.constants import SCHEDULE_NOT_FOUND
from app.deps import CurrentUser, DBSession, PilotUser
from app.models.attachment import Attachment
from app.models.battery import Battery
from app.models.controller import Controller
from app.models.dock import Dock
from app.models.maintenance_schedule import MaintenanceSchedule
from app.models.maintenance import MaintenanceRecord
from app.models.other_equipment import OtherEquipment
from app.models.pilot import Pilot
from app.models.sensor import SensorPackage
from app.models.vehicle import Vehicle
from app.responses import responses
from app.services.audit import compute_changes, log_action

router = APIRouter(prefix="/api/maintenance/schedules", tags=["maintenance-schedules"])


# entity_type -> model. "organization" is allowed but has no table, so its
# value is None and the existence check is skipped for it.
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


def _validate_entity(db, entity_type: str, entity_id: int | None) -> None:
    """Reject unknown entity_type (400) and a missing entity_id row (404).

    "organization" has no table and is skipped. The existence check also only
    runs when an entity_id is supplied (the field is optional for schedules)."""
    if entity_type not in ENTITY_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity_type '{entity_type}'. Allowed: {', '.join(sorted(ENTITY_MODELS))}",
        )
    model = ENTITY_MODELS[entity_type]
    if model is not None and entity_id is not None:
        if not db.query(model).filter(model.id == entity_id).first():
            raise HTTPException(status_code=404, detail=f"{entity_type} #{entity_id} not found")



Frequency = Literal["monthly", "quarterly", "yearly", "two_years", "three_years", "one_time"]


class ScheduleCreate(BaseModel):
    name: str
    entity_type: str
    entity_id: Optional[int] = None
    frequency: Frequency
    description: Optional[str] = None
    assigned_to_id: Optional[int] = None
    next_due: Optional[date] = None  # required for one_time; optional override otherwise

class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    frequency: Optional[Frequency] = None
    description: Optional[str] = None
    assigned_to_id: Optional[int] = None
    is_active: Optional[bool] = None
    next_due: Optional[date] = None


# Calendar months, not a day count: 365 days drifts a yearly task a day
# earlier after every leap year, and 30 days runs a monthly one a week early
# by summer.
FREQUENCY_MONTHS = {
    "monthly": 1,
    "quarterly": 3,
    "yearly": 12,
    "two_years": 24,
    "three_years": 36,
}

# One-time tasks have no recurrence interval: the due date is user-supplied
# and completing the task deactivates it instead of rescheduling.
ONE_TIME = "one_time"


def _add_months(base: date, months: int) -> date:
    """``base`` plus whole months, kept inside the target month (January 31
    plus one month is the last day of February)."""
    month_index = base.month - 1 + months
    year, month = base.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(base.day, calendar.monthrange(year, month)[1]))


def _calc_next_due(frequency: str, from_date: date | None = None) -> date:
    base = from_date or date.today()
    return _add_months(base, FREQUENCY_MONTHS.get(frequency, 1))



@router.get("")
def list_schedules(
    db: DBSession,
    user: CurrentUser,
    all: bool = False):
    q = db.query(MaintenanceSchedule)
    if not all:
        q = q.filter(MaintenanceSchedule.is_active.is_(True))
    schedules = q.order_by(MaintenanceSchedule.next_due.asc().nullslast()).all()
    results = []
    for s in schedules:
        pilot = None
        if s.assigned_to_id:
            pilot = db.query(Pilot).filter(Pilot.id == s.assigned_to_id).first()
        results.append({
            "id": s.id,
            "name": s.name,
            "entity_type": s.entity_type,
            "entity_id": s.entity_id,
            "frequency": s.frequency,
            "description": s.description,
            "assigned_to_id": s.assigned_to_id,
            "assigned_to_name": pilot.full_name if pilot else None,
            "last_completed": s.last_completed.isoformat() if s.last_completed else None,
            "next_due": s.next_due.isoformat() if s.next_due else None,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })
    return results


@router.get("/{schedule_id}", responses=responses(404))
def get_schedule(
    schedule_id: int,
    db: DBSession,
    user: CurrentUser,
):
    s = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    if not s:
        raise HTTPException(404, SCHEDULE_NOT_FOUND)
    pilot = None
    if s.assigned_to_id:
        pilot = db.query(Pilot).filter(Pilot.id == s.assigned_to_id).first()
    return {
        "id": s.id,
        "name": s.name,
        "entity_type": s.entity_type,
        "entity_id": s.entity_id,
        "frequency": s.frequency,
        "description": s.description,
        "assigned_to_id": s.assigned_to_id,
        "assigned_to_name": pilot.full_name if pilot else None,
        "last_completed": s.last_completed.isoformat() if s.last_completed else None,
        "next_due": s.next_due.isoformat() if s.next_due else None,
        "is_active": s.is_active,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.post("", responses=responses(400, 404))
def create_schedule(
    data: ScheduleCreate,
    db: DBSession,
    user: PilotUser,
):
    _validate_entity(db, data.entity_type, data.entity_id)
    if data.frequency == ONE_TIME and data.next_due is None:
        raise HTTPException(400, "next_due (due date) is required for one-time tasks")
    schedule = MaintenanceSchedule(
        name=data.name,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        frequency=data.frequency,
        description=data.description,
        assigned_to_id=data.assigned_to_id,
        next_due=data.next_due or _calc_next_due(data.frequency),
        is_active=True,
    )
    db.add(schedule)
    db.flush()
    log_action(db, user.id, user.display_name, "create", "maintenance_schedule", schedule.id, schedule.name,
               details=f"{schedule.entity_type} #{schedule.entity_id}, {schedule.frequency}")
    db.commit()
    db.refresh(schedule)
    return {"ok": True, "id": schedule.id}


@router.patch("/{schedule_id}", responses=responses(400, 404))
def update_schedule(
    schedule_id: int,
    data: ScheduleUpdate,
    db: DBSession,
    user: PilotUser,
):
    schedule = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(404, SCHEDULE_NOT_FOUND)
    update_data = data.model_dump(exclude_unset=True)
    if "entity_type" in update_data or "entity_id" in update_data:
        _validate_entity(
            db,
            update_data.get("entity_type", schedule.entity_type),
            update_data.get("entity_id", schedule.entity_id),
        )
    if (
        update_data.get("frequency", schedule.frequency) == ONE_TIME
        and update_data.get("next_due", schedule.next_due) is None
    ):
        raise HTTPException(400, "next_due (due date) is required for one-time tasks")
    changes = compute_changes(schedule, update_data, list(update_data))
    for key, value in update_data.items():
        setattr(schedule, key, value)
    if changes:
        log_action(db, user.id, user.display_name, "update", "maintenance_schedule", schedule.id, schedule.name,
                   changes=changes)
    db.commit()
    return {"ok": True}


@router.delete("/{schedule_id}", responses=responses(404))
def delete_schedule(
    schedule_id: int,
    db: DBSession,
    user: PilotUser,
):
    schedule = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(404, SCHEDULE_NOT_FOUND)
    log_action(db, user.id, user.display_name, "delete", "maintenance_schedule", schedule.id, schedule.name)
    db.delete(schedule)
    db.commit()
    return {"ok": True}


@router.post("/{schedule_id}/complete", responses=responses(404))
def complete_schedule(
    schedule_id: int,
    db: DBSession,
    user: PilotUser,
):
    schedule = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(404, SCHEDULE_NOT_FOUND)

    today = date.today()
    schedule.last_completed = today
    if schedule.frequency == ONE_TIME:
        # A one-time task is done for good: deactivate it (dropping it out of
        # alerts/compliance) and keep next_due as-is for history.
        schedule.is_active = False
    else:
        schedule.next_due = _calc_next_due(schedule.frequency, today)

    # Auto-create a maintenance record. One-time tasks get no next_due_date so
    # the record doesn't linger in the Upcoming list.
    record = MaintenanceRecord(
        entity_type=schedule.entity_type,
        entity_id=schedule.entity_id or 0,
        maintenance_type="scheduled",
        description=schedule.name,
        performed_date=today,
        next_due_date=None if schedule.frequency == ONE_TIME else schedule.next_due,
        performed_by=user.display_name if user.display_name else user.username,
    )
    db.add(record)
    log_action(db, user.id, user.display_name, "complete", "maintenance_schedule", schedule.id, schedule.name)
    db.commit()
    return {
        "ok": True,
        "last_completed": today.isoformat(),
        "next_due": schedule.next_due.isoformat() if schedule.next_due else None,
        "is_active": schedule.is_active,
    }
