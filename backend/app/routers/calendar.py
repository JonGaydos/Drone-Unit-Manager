"""Unit calendar: aggregates dated records + manual events/leave for a date range."""

from datetime import date

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func

from app.deps import DBSession
from app.models.user import User
from app.routers.auth import require_permission
from app.services import permissions as permissions_service
from app.responses import responses
from app.models.calendar_event import CalendarEvent
from app.models.training_log import TrainingLog
from app.models.mission_log import MissionLog
from app.models.maintenance_schedule import MaintenanceSchedule
from app.models.certification import PilotCertification, CertificationType
from app.models.pilot import Pilot
from app.models.flight import Flight
from app.schemas.calendar import CalendarEventCreate, CalendarEventUpdate, CalendarEventOut, END_BEFORE_START

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

CALENDAR_EDIT = "calendar.edit"

ViewUser = Annotated[User, Depends(require_permission("calendar.view"))]
CreateUser = Annotated[User, Depends(require_permission("calendar.create"))]
EditUser = Annotated[User, Depends(require_permission(CALENDAR_EDIT))]


def _iso(d):
    return d.isoformat() if d else None


def _log_events(db, start, end) -> list[dict]:
    """Training days and missions in the range."""
    events = []
    for t in db.query(TrainingLog).filter(TrainingLog.date >= start, TrainingLog.date <= end).all():
        events.append({"id": f"training-{t.id}", "title": t.title, "start": _iso(t.date),
                       "end": None, "all_day": True, "category": "training_day",
                       "source": "training_log", "link": "/training", "editable": False})
    for m in db.query(MissionLog).filter(MissionLog.date >= start, MissionLog.date <= end).all():
        events.append({"id": f"mission-{m.id}", "title": m.title, "start": _iso(m.date),
                       "end": None, "all_day": True, "category": "mission",
                       "source": "mission_log", "link": "/missions", "editable": False})
    return events


def _maintenance_events(db, start, end) -> list[dict]:
    """Maintenance schedules falling due in the range."""
    schedules = db.query(MaintenanceSchedule).filter(
        MaintenanceSchedule.next_due.isnot(None),
        MaintenanceSchedule.next_due >= start, MaintenanceSchedule.next_due <= end).all()
    return [{"id": f"maint-{s.id}", "title": f"Due: {s.name}", "start": _iso(s.next_due),
             "end": None, "all_day": True, "category": "maintenance_due",
             "source": "maintenance_schedule", "link": "/maintenance", "editable": False}
            for s in schedules]


def _cert_events(db, start, end) -> list[dict]:
    """Certifications expiring in the range: live records of active pilots,
    the same set the compliance dashboard counts."""
    cert_rows = db.query(PilotCertification, CertificationType, Pilot).join(
        CertificationType, PilotCertification.certification_type_id == CertificationType.id).join(
        Pilot, PilotCertification.pilot_id == Pilot.id).filter(
        Pilot.status == "active",
        PilotCertification.status.notin_(["not_issued", "renewed"]),
        PilotCertification.expiration_date.isnot(None),
        PilotCertification.expiration_date >= start, PilotCertification.expiration_date <= end).all()
    return [{"id": f"cert-{pc.id}", "title": f"{pilot.first_name} {pilot.last_name} - {ct.name} expires",
             "start": _iso(pc.expiration_date), "end": None, "all_day": True,
             "category": "cert_expiration", "source": "cert", "link": "/certifications", "editable": False}
            for pc, ct, pilot in cert_rows]


@router.get("", responses=responses(401))
def get_calendar(db: DBSession, user: ViewUser, start: date, end: date):
    """Aggregate calendar items in [start, end]. Returns {events: [...], flight_counts: {date: n}}.

    Items drawn from another feature appear only with that feature's view permission.
    """
    events = []

    if permissions_service.can(db, user, "logs.view"):
        events += _log_events(db, start, end)
    if permissions_service.can(db, user, "maintenance.view"):
        events += _maintenance_events(db, start, end)
    if permissions_service.can(db, user, "certifications.view"):
        events += _cert_events(db, start, end)
    # Manual events + leave (overlap the range)
    manual = db.query(CalendarEvent).filter(
        CalendarEvent.start_date <= end,
        func.coalesce(CalendarEvent.end_date, CalendarEvent.start_date) >= start).all()
    edit_level = permissions_service.level(db, user, CALENDAR_EDIT)
    for e in manual:
        editable = edit_level == permissions_service.ALL or (
            edit_level == permissions_service.OWN and e.created_by_id == user.id)
        events.append({"id": f"event-{e.id}", "event_id": e.id, "title": e.title,
                       "start": _iso(e.start_date), "end": _iso(e.end_date), "all_day": e.all_day,
                       "category": e.category, "source": "calendar_event", "link": None,
                       "notes": e.notes, "editable": editable})
    # Per-day flight counts, only for users who may view flights
    flight_counts = {}
    if permissions_service.can(db, user, "flights.view"):
        rows = db.query(Flight.date, func.count(Flight.id)).filter(
            Flight.date.isnot(None), Flight.date >= start, Flight.date <= end).group_by(Flight.date).all()
        flight_counts = {_iso(d): n for d, n in rows}

    return {"events": events, "flight_counts": flight_counts}


@router.post("/events", response_model=CalendarEventOut, responses=responses(401, 403))
def create_event(data: CalendarEventCreate, db: DBSession, user: CreateUser):
    """Create a manual event or leave entry. Needs the calendar.create permission."""
    from app.services.audit import log_action
    ev = CalendarEvent(**data.model_dump(), created_by_id=user.id)
    db.add(ev)
    db.flush()
    log_action(db, user.id, user.display_name, "create", "calendar_event", ev.id, ev.title)
    db.commit()
    db.refresh(ev)
    return CalendarEventOut.model_validate(ev)


@router.patch("/events/{event_id}", response_model=CalendarEventOut, responses=responses(401, 403, 404, 422))
def update_event(event_id: int, data: CalendarEventUpdate, db: DBSession, user: EditUser):
    """Update a manual event. Needs calendar.edit, at Own for the creator's events."""
    from app.services.audit import log_action
    ev = db.query(CalendarEvent).filter(CalendarEvent.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    permissions_service.require_record_access(db, user, CALENDAR_EDIT, ev.created_by_id == user.id)
    update_data = data.model_dump(exclude_unset=True)
    end = update_data.get("end_date", ev.end_date)
    if end and end < update_data.get("start_date", ev.start_date):
        raise HTTPException(status_code=422, detail=END_BEFORE_START)
    for key, value in update_data.items():
        setattr(ev, key, value)
    log_action(db, user.id, user.display_name, "update", "calendar_event", ev.id, ev.title)
    db.commit()
    db.refresh(ev)
    return CalendarEventOut.model_validate(ev)


@router.delete("/events/{event_id}", responses=responses(401, 403, 404))
def delete_event(event_id: int, db: DBSession, user: EditUser):
    """Delete a manual event. Needs calendar.edit, at Own for the creator's events."""
    from app.services.audit import log_action
    ev = db.query(CalendarEvent).filter(CalendarEvent.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    permissions_service.require_record_access(db, user, CALENDAR_EDIT, ev.created_by_id == user.id)
    log_action(db, user.id, user.display_name, "delete", "calendar_event", ev.id, ev.title)
    db.delete(ev)
    db.commit()
    return {"ok": True}
