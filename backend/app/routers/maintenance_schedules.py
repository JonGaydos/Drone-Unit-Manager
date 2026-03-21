"""Maintenance schedule endpoints."""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.maintenance_schedule import MaintenanceSchedule
from app.models.maintenance import MaintenanceRecord
from app.models.pilot import Pilot
from app.models.user import User
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/maintenance/schedules", tags=["maintenance-schedules"])


# ── Pydantic Schemas ─────────────────────────────────────────────────────────

class ScheduleCreate(BaseModel):
    name: str
    entity_type: str
    entity_id: Optional[int] = None
    frequency: str  # monthly, quarterly, yearly
    description: Optional[str] = None
    assigned_to_id: Optional[int] = None

class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    frequency: Optional[str] = None
    description: Optional[str] = None
    assigned_to_id: Optional[int] = None
    is_active: Optional[bool] = None
    next_due: Optional[date] = None


FREQUENCY_DAYS = {
    "monthly": 30,
    "quarterly": 90,
    "yearly": 365,
}


def _calc_next_due(frequency: str, from_date: date | None = None) -> date:
    base = from_date or date.today()
    days = FREQUENCY_DAYS.get(frequency, 30)
    return base + timedelta(days=days)


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("")
def list_schedules(
    all: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(MaintenanceSchedule)
    if not all:
        q = q.filter(MaintenanceSchedule.is_active == True)
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


@router.get("/{schedule_id}")
def get_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    if not s:
        raise HTTPException(404, "Schedule not found")
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


@router.post("")
def create_schedule(
    data: ScheduleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    schedule = MaintenanceSchedule(
        name=data.name,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        frequency=data.frequency,
        description=data.description,
        assigned_to_id=data.assigned_to_id,
        next_due=_calc_next_due(data.frequency),
        is_active=True,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return {"id": schedule.id, "message": "Schedule created"}


@router.patch("/{schedule_id}")
def update_schedule(
    schedule_id: int,
    data: ScheduleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    schedule = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(schedule, key, value)
    db.commit()
    return {"message": "Schedule updated"}


@router.delete("/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    schedule = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    db.delete(schedule)
    db.commit()
    return {"message": "Schedule deleted"}


@router.post("/{schedule_id}/complete")
def complete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    schedule = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    today = date.today()
    schedule.last_completed = today
    schedule.next_due = _calc_next_due(schedule.frequency, today)

    # Auto-create a maintenance record
    record = MaintenanceRecord(
        entity_type=schedule.entity_type,
        entity_id=schedule.entity_id or 0,
        maintenance_type="scheduled",
        description=schedule.name,
        performed_date=today,
        next_due_date=schedule.next_due,
        performed_by=user.display_name if user.display_name else user.username,
    )
    db.add(record)
    db.commit()
    return {
        "message": "Schedule marked complete",
        "last_completed": today.isoformat(),
        "next_due": schedule.next_due.isoformat(),
    }
