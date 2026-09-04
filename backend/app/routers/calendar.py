"""Unit calendar: aggregates dated records + manual events/leave for a date range."""

from datetime import date

from fastapi import APIRouter, HTTPException
from sqlalchemy import func

from app.deps import DBSession, CurrentUser, PilotUser
from app.responses import responses
from app.models.calendar_event import CalendarEvent
from app.models.training_log import TrainingLog
from app.models.mission_log import MissionLog
from app.models.maintenance_schedule import MaintenanceSchedule
from app.models.certification import PilotCertification, CertificationType
from app.models.pilot import Pilot
from app.models.flight import Flight
from app.schemas.calendar import CalendarEventCreate, CalendarEventUpdate, CalendarEventOut

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

SUPERVISOR_ROLES = {"admin", "supervisor"}


def _iso(d):
    return d.isoformat() if d else None


@router.get("", responses=responses(401))
def get_calendar(db: DBSession, user: CurrentUser, start: date, end: date):
    """Aggregate calendar items in [start, end]. Returns {events: [...], flight_counts: {date: n}}."""
    events = []

    # Training days
    for t in db.query(TrainingLog).filter(TrainingLog.date >= start, TrainingLog.date <= end).all():
        events.append({"id": f"training-{t.id}", "title": t.title, "start": _iso(t.date),
                       "end": None, "all_day": True, "category": "training_day",
                       "source": "training_log", "link": "/training", "editable": False})
    # Missions
    for m in db.query(MissionLog).filter(MissionLog.date >= start, MissionLog.date <= end).all():
        events.append({"id": f"mission-{m.id}", "title": m.title, "start": _iso(m.date),
                       "end": None, "all_day": True, "category": "mission",
                       "source": "mission_log", "link": "/missions", "editable": False})
    # Maintenance due
    for s in db.query(MaintenanceSchedule).filter(
            MaintenanceSchedule.next_due.isnot(None),
            MaintenanceSchedule.next_due >= start, MaintenanceSchedule.next_due <= end).all():
        events.append({"id": f"maint-{s.id}", "title": f"Due: {s.name}", "start": _iso(s.next_due),
                       "end": None, "all_day": True, "category": "maintenance_due",
                       "source": "maintenance_schedule", "link": "/maintenance", "editable": False})
    # Cert expirations
    cert_rows = db.query(PilotCertification, CertificationType, Pilot).join(
        CertificationType, PilotCertification.certification_type_id == CertificationType.id).join(
        Pilot, PilotCertification.pilot_id == Pilot.id).filter(
        PilotCertification.expiration_date.isnot(None),
        PilotCertification.expiration_date >= start, PilotCertification.expiration_date <= end).all()
    for pc, ct, pilot in cert_rows:
        events.append({"id": f"cert-{pc.id}", "title": f"{pilot.first_name} {pilot.last_name} - {ct.name} expires",
                       "start": _iso(pc.expiration_date), "end": None, "all_day": True,
                       "category": "cert_expiration", "source": "cert", "link": "/certifications", "editable": False})
    # Manual events + leave (overlap the range)
    manual = db.query(CalendarEvent).filter(
        CalendarEvent.start_date <= end,
        func.coalesce(CalendarEvent.end_date, CalendarEvent.start_date) >= start).all()
    for e in manual:
        editable = e.created_by_id == user.id or user.role in SUPERVISOR_ROLES
        events.append({"id": f"event-{e.id}", "event_id": e.id, "title": e.title,
                       "start": _iso(e.start_date), "end": _iso(e.end_date), "all_day": e.all_day,
                       "category": e.category, "source": "calendar_event", "link": None,
                       "notes": e.notes, "editable": editable})
    # Per-day flight counts
    rows = db.query(Flight.date, func.count(Flight.id)).filter(
        Flight.date.isnot(None), Flight.date >= start, Flight.date <= end).group_by(Flight.date).all()
    flight_counts = {_iso(d): n for d, n in rows}

    return {"events": events, "flight_counts": flight_counts}


@router.post("/events", response_model=CalendarEventOut, responses=responses(401, 403))
def create_event(data: CalendarEventCreate, db: DBSession, user: PilotUser):
    """Create a manual event or leave entry. Pilot role or higher (viewer is read-only)."""
    from app.services.audit import log_action
    ev = CalendarEvent(**data.model_dump(), created_by_id=user.id)
    db.add(ev)
    db.flush()
    log_action(db, user.id, user.display_name, "create", "calendar_event", ev.id, ev.title)
    db.commit()
    db.refresh(ev)
    return CalendarEventOut.model_validate(ev)


@router.patch("/events/{event_id}", response_model=CalendarEventOut, responses=responses(401, 403, 404))
def update_event(event_id: int, data: CalendarEventUpdate, db: DBSession, user: CurrentUser):
    """Update a manual event. Owner or supervisor+ only."""
    from app.services.audit import log_action
    ev = db.query(CalendarEvent).filter(CalendarEvent.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    if ev.created_by_id != user.id and user.role not in SUPERVISOR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed to edit this event")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(ev, key, value)
    log_action(db, user.id, user.display_name, "update", "calendar_event", ev.id, ev.title)
    db.commit()
    db.refresh(ev)
    return CalendarEventOut.model_validate(ev)


@router.delete("/events/{event_id}", responses=responses(401, 403, 404))
def delete_event(event_id: int, db: DBSession, user: CurrentUser):
    """Delete a manual event. Owner or supervisor+ only."""
    from app.services.audit import log_action
    ev = db.query(CalendarEvent).filter(CalendarEvent.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    if ev.created_by_id != user.id and user.role not in SUPERVISOR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed to delete this event")
    log_action(db, user.id, user.display_name, "delete", "calendar_event", ev.id, ev.title)
    db.delete(ev)
    db.commit()
    return {"ok": True}
