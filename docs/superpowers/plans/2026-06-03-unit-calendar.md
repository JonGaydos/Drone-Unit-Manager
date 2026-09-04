# Unit Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A unit-wide calendar (FullCalendar) that aggregates training days, missions, maintenance-due, cert expirations, and per-day flight counts, plus manually-entered events and leave.

**Architecture:** A new `CalendarEvent` table holds manual events/leave. A read-only aggregation endpoint `GET /api/calendar?start&end` merges that table with existing dated records (training/mission/maintenance/cert) and a per-day flight count, returning a flat event list the frontend renders with FullCalendar. Manual events/leave have full CRUD; anyone can create, owner-or-supervisor can edit/delete.

**Tech Stack:** FastAPI + SQLAlchemy (SQLite), React 19 + Vite, FullCalendar v6. No test framework — verification is `py_compile` + `import app.main` + seeded in-memory SQLite smoke scripts + `npm run build`/eslint.

**Branch:** `feat/unit-calendar` off `main`.

**Verification idiom:** backend python `D:/Claude Projects/Drone-Unit-Manager/backend/.venv/Scripts/python.exe`, run with `PYTHONPATH=.` from the `backend` dir. Smoke scripts go under `C:/Users/jgayd/.claude/plans/` (NOT the repo); run then delete. **Smoke scripts that call any create/update/delete endpoint MUST seed a real `User` row** (audit `log_action` inserts an `audit_logs` row with an FK to `users.id`, enforced under `PRAGMA foreign_keys=ON`).

**Key facts (verified against the codebase):**
- `TrainingLog.title`, `MissionLog.title` (field is `title`); `MaintenanceSchedule.name` + `next_due` (nullable); `PilotCertification.expiration_date` (nullable) with `.certification_type.name` and `.pilot`; `Flight.date` (nullable). Filter out null dates when aggregating.
- New table is created by `Base.metadata.create_all` at startup — no migration needed. The model MUST be imported in `backend/app/models/__init__.py` so SQLAlchemy registers it.
- `created_by_id` is NOT auto-set by the mirrored create pattern — set it explicitly.
- Shared UI: `Modal({open,onClose,title,children})`, `Input({label,...})`, `Button({variant,size,...})`, `useToast()` → `toast.error(...)`, `useConfirm()` → `[confirmProps, requestConfirm]` + `<ConfirmDialog {...confirmProps}/>`.

---

### Task 0: Branch

- [ ] **Step 1: Create the branch**
```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" checkout main
git -C "D:/Claude Projects/Drone-Unit-Manager" pull --ff-only
git -C "D:/Claude Projects/Drone-Unit-Manager" checkout -b feat/unit-calendar
```

---

### Task 1: CalendarEvent model

**Files:**
- Create: `backend/app/models/calendar_event.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the model**

`backend/app/models/calendar_event.py`:
```python
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Text, Date, DateTime, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(20))  # event, leave
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=True)
    pilot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pilots.id"), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```
(Timestamps use Python `default=datetime.utcnow` per the approved spec — bulletproof on insert regardless of table DDL. The table is created fresh by `create_all`, so this is safe.)

- [ ] **Step 2: Register the model**

In `backend/app/models/__init__.py`, add an import alongside the others (so `create_all` sees the table):
```python
from app.models.calendar_event import CalendarEvent  # noqa: F401
```
If that file has an `__all__`, add `"CalendarEvent"` to it.

- [ ] **Step 3: Compile + import + confirm the table registers**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && .venv/Scripts/python.exe -m py_compile app/models/calendar_event.py app/models/__init__.py && PYTHONPATH=. .venv/Scripts/python.exe -c "import app.main; from app.database import Base; assert 'calendar_events' in Base.metadata.tables; print('TABLE_OK')"
```
Expected: `TABLE_OK`

- [ ] **Step 4: Commit**
```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add backend/app/models/calendar_event.py backend/app/models/__init__.py
git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(calendar): add CalendarEvent model"
```

---

### Task 2: Calendar schemas

**Files:**
- Create: `backend/app/schemas/calendar.py`

- [ ] **Step 1: Create the schemas**

`backend/app/schemas/calendar.py`:
```python
from datetime import date as DateType, datetime
from pydantic import BaseModel, field_validator

ALLOWED_CATEGORIES = ("event", "leave")


class CalendarEventCreate(BaseModel):
    title: str
    category: str = "event"
    start_date: DateType
    end_date: DateType | None = None
    all_day: bool = True
    pilot_id: int | None = None
    notes: str | None = None

    @field_validator("category")
    @classmethod
    def _check_category(cls, v):
        if v not in ALLOWED_CATEGORIES:
            raise ValueError("category must be 'event' or 'leave'")
        return v


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    start_date: DateType | None = None
    end_date: DateType | None = None
    all_day: bool | None = None
    pilot_id: int | None = None
    notes: str | None = None

    @field_validator("category")
    @classmethod
    def _check_category(cls, v):
        if v is not None and v not in ALLOWED_CATEGORIES:
            raise ValueError("category must be 'event' or 'leave'")
        return v


class CalendarEventOut(BaseModel):
    id: int
    title: str
    category: str
    start_date: DateType
    end_date: DateType | None = None
    all_day: bool = True
    pilot_id: int | None = None
    notes: str | None = None
    created_by_id: int | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Compile**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && .venv/Scripts/python.exe -m py_compile app/schemas/calendar.py && echo OK
```
Expected: `OK`

- [ ] **Step 3: Commit**
```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add backend/app/schemas/calendar.py
git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(calendar): add calendar event schemas"
```

---

### Task 3: Calendar router (aggregation + CRUD) + registration

**Files:**
- Create: `backend/app/routers/calendar.py`
- Modify: `backend/app/main.py` (import + include_router)

- [ ] **Step 1: Create the router**

`backend/app/routers/calendar.py`:
```python
"""Unit calendar: aggregates dated records + manual events/leave for a date range."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func

from app.deps import DBSession, CurrentUser
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
                       "editable": editable})
    # Per-day flight counts
    rows = db.query(Flight.date, func.count(Flight.id)).filter(
        Flight.date.isnot(None), Flight.date >= start, Flight.date <= end).group_by(Flight.date).all()
    flight_counts = {_iso(d): n for d, n in rows}

    return {"events": events, "flight_counts": flight_counts}


@router.post("/events", response_model=CalendarEventOut, responses=responses(401))
def create_event(data: CalendarEventCreate, db: DBSession, user: CurrentUser):
    """Create a manual event or leave entry. Any authenticated user."""
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
```

- [ ] **Step 2: Register the router in `main.py`**

Add `calendar` to the first `from app.routers import (...)` block (e.g. append to a line: `..., components, geofences, adsb, notifications, calendar,`). Then add `app.include_router(calendar.router)` in the include block.

- [ ] **Step 3: Compile + import**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && .venv/Scripts/python.exe -m py_compile app/routers/calendar.py app/main.py && PYTHONPATH=. .venv/Scripts/python.exe -c "import app.main; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**
```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add backend/app/routers/calendar.py backend/app/main.py
git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(calendar): aggregation endpoint + event CRUD"
```

---

### Task 4: Backend smoke test

**Files:** Temp `C:/Users/jgayd/.claude/plans/smoke_calendar.py` (run, then delete).

- [ ] **Step 1: Write the smoke script**
```python
import app.main
from datetime import date, timedelta
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models.user import User
from app.models.training_log import TrainingLog
from app.models.calendar_event import CalendarEvent
from app.routers.calendar import get_calendar, create_event, update_event, delete_event
from app.schemas.calendar import CalendarEventCreate, CalendarEventUpdate
import fastapi

eng = create_engine("sqlite:///:memory:")
@event.listens_for(eng, "connect")
def _fk(dbapi, rec):
    cur = dbapi.cursor(); cur.execute("PRAGMA foreign_keys=ON"); cur.close()
Base.metadata.create_all(eng)
S = sessionmaker(bind=eng); db = S()

# audit log_action FK requires a real users row
db.add(User(id=1, username="t", password_hash="x", display_name="Owner", role="pilot")); 
db.add(User(id=2, username="s", password_hash="x", display_name="Sup", role="supervisor"))
db.add(TrainingLog(date=date(2026, 6, 10), title="Range Day")); db.commit()

class U: id = 1; display_name = "Owner"; role = "pilot"
class Sup: id = 2; display_name = "Sup"; role = "supervisor"

start, end = date(2026, 6, 1), date(2026, 6, 30)
# create an event (any user)
ev = create_event(CalendarEventCreate(title="Unit BBQ", category="event", start_date=date(2026, 6, 15)), db, U())
# aggregation includes training + the event
res = get_calendar(db, U(), start, end)
cats = {e["category"] for e in res["events"]}
assert "training_day" in cats and "event" in cats, cats
ev_item = next(e for e in res["events"] if e["category"] == "event")
assert ev_item["editable"] is True  # owner
# a different non-supervisor cannot edit
class Other: id = 9; display_name = "Other"; role = "pilot"
try:
    update_event(ev.id, CalendarEventUpdate(title="Hijack"), db, Other()); raise SystemExit("no 403")
except fastapi.HTTPException as e:
    assert e.status_code == 403, e.status_code
# supervisor can edit + delete
update_event(ev.id, CalendarEventUpdate(title="Unit BBQ (moved)"), db, Sup())
delete_event(ev.id, db, Sup())
res2 = get_calendar(db, U(), start, end)
assert not any(e["category"] == "event" for e in res2["events"])
# bad category rejected
try:
    create_event(CalendarEventCreate(title="x", category="bogus", start_date=date(2026,6,1)), db, U()); raise SystemExit("no validation")
except Exception:
    pass
print("CALENDAR_SMOKE_OK")
```

- [ ] **Step 2: Run it**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && PYTHONPATH=. .venv/Scripts/python.exe "C:/Users/jgayd/.claude/plans/smoke_calendar.py" && rm -f "C:/Users/jgayd/.claude/plans/smoke_calendar.py"
```
Expected: `CALENDAR_SMOKE_OK`

(No commit — throwaway.)

---

### Task 5: Install FullCalendar

**Files:** `frontend/package.json` + `frontend/package-lock.json` (npm).

- [ ] **Step 1: Install (React 19-compatible v6)**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm install @fullcalendar/react@^6.1.15 @fullcalendar/daygrid@^6.1.15 @fullcalendar/timegrid@^6.1.15 @fullcalendar/list@^6.1.15 @fullcalendar/interaction@^6.1.15
```
If npm reports a React 19 peer-dependency conflict, retry with `--legacy-peer-deps` and note it. FullCalendar v6 bundles its own CSS via JS (no separate CSS import needed).

- [ ] **Step 2: Confirm it builds**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build 2>&1 | tail -2
```
Expected: a clean vite build (no new page yet, just verifying the dep installs cleanly).

- [ ] **Step 3: Commit**
```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add frontend/package.json frontend/package-lock.json
git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "build(calendar): add FullCalendar v6 deps"
```

---

### Task 6: CalendarPage

**Files:** Create `frontend/src/pages/CalendarPage.jsx`

- [ ] **Step 1: Create the page**

`frontend/src/pages/CalendarPage.jsx`:
```jsx
import { useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import listPlugin from '@fullcalendar/list'
import interactionPlugin from '@fullcalendar/interaction'
import { api } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useConfirm } from '@/hooks/useConfirm'

const COLORS = {
  training_day: '#0ea5e9', mission: '#8b5cf6', maintenance_due: '#f59e0b',
  cert_expiration: '#ef4444', event: '#10b981', leave: '#6b7280', flights: '#3b82f6',
}
const LABELS = {
  training_day: 'Training', mission: 'Missions', maintenance_due: 'Maintenance due',
  cert_expiration: 'Cert expirations', event: 'Events', leave: 'Leave', flights: 'Flights',
}
const ALL_CATS = Object.keys(LABELS)
const blankForm = () => ({ title: '', category: 'event', start_date: '', end_date: '', notes: '' })

export default function CalendarPage() {
  const navigate = useNavigate()
  const { user, isSupervisor } = useAuth()
  const toast = useToast()
  const [confirmProps, requestConfirm] = useConfirm()
  const calRef = useRef(null)
  const rangeRef = useRef({ start: null, end: null })
  const [events, setEvents] = useState([])
  const [flightCounts, setFlightCounts] = useState({})
  const [enabled, setEnabled] = useState(() => Object.fromEntries(ALL_CATS.map(c => [c, true])))
  const [modalOpen, setModalOpen] = useState(false)
  const [form, setForm] = useState(blankForm())
  const [editId, setEditId] = useState(null)

  const fetchRange = useCallback(async (start, end) => {
    rangeRef.current = { start, end }
    try {
      const res = await api.get(`/calendar?start=${start}&end=${end}`)
      setEvents(res.events || [])
      setFlightCounts(res.flight_counts || {})
    } catch (err) { toast.error(err.message) }
  }, [toast])

  const handleDatesSet = (arg) => {
    fetchRange(arg.startStr.slice(0, 10), arg.endStr.slice(0, 10))
  }

  const fcEvents = []
  for (const e of events) {
    if (!enabled[e.category]) continue
    fcEvents.push({
      id: e.id, title: e.title, start: e.start, end: e.end || undefined, allDay: e.all_day,
      color: COLORS[e.category] || '#64748b',
      extendedProps: { category: e.category, link: e.link, editable: e.editable, raw: e },
    })
  }
  if (enabled.flights) {
    for (const [d, n] of Object.entries(flightCounts)) {
      fcEvents.push({ id: `flights-${d}`, title: `${n} flight${n === 1 ? '' : 's'}`, start: d, allDay: true,
        color: COLORS.flights, extendedProps: { category: 'flights', link: '/flights' } })
    }
  }

  const handleEventClick = (info) => {
    const xp = info.event.extendedProps
    if (xp.category === 'event' || xp.category === 'leave') {
      const raw = xp.raw
      setEditId(raw.event_id)
      setForm({
        title: raw.title, category: raw.category, start_date: raw.start || '',
        end_date: raw.end || '', notes: raw.raw_notes || '',
      })
      setModalOpen(true)
    } else if (xp.link) {
      navigate(xp.link)
    }
  }

  const openCreate = () => { setEditId(null); setForm(blankForm()); setModalOpen(true) }

  const canEditCurrent = editId == null || (() => {
    const e = events.find(x => x.event_id === editId)
    return e ? e.editable : true
  })()

  const handleSave = async (e) => {
    e.preventDefault()
    const body = { title: form.title, category: form.category, start_date: form.start_date,
                   end_date: form.end_date || null, notes: form.notes || null }
    try {
      if (editId) await api.patch(`/calendar/events/${editId}`, body)
      else await api.post('/calendar/events', body)
      setModalOpen(false)
      const { start, end } = rangeRef.current
      if (start) fetchRange(start, end)
    } catch (err) { toast.error(err.message) }
  }

  const handleDelete = () => {
    if (!editId) return
    requestConfirm({
      title: 'Delete entry', message: 'Delete this calendar entry?',
      onConfirm: async () => {
        try {
          await api.delete(`/calendar/events/${editId}`)
          setModalOpen(false)
          const { start, end } = rangeRef.current
          if (start) fetchRange(start, end)
        } catch (err) { toast.error(err.message) }
      },
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold text-foreground">Calendar</h1>
        <Button onClick={openCreate}>Add event / leave</Button>
      </div>

      <div className="flex flex-wrap gap-3">
        {ALL_CATS.map(c => (
          <label key={c} className="flex items-center gap-1.5 text-xs text-foreground cursor-pointer">
            <input type="checkbox" checked={enabled[c]} onChange={() => setEnabled(s => ({ ...s, [c]: !s[c] }))} />
            <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: COLORS[c] }} />
            {LABELS[c]}
          </label>
        ))}
      </div>

      <div className="bg-card border border-border rounded-xl p-3">
        <FullCalendar
          ref={calRef}
          plugins={[dayGridPlugin, timeGridPlugin, listPlugin, interactionPlugin]}
          initialView="dayGridMonth"
          headerToolbar={{ left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,listMonth' }}
          height="auto"
          events={fcEvents}
          datesSet={handleDatesSet}
          eventClick={handleEventClick}
        />
      </div>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editId ? 'Edit entry' : 'Add event / leave'}>
        <form onSubmit={handleSave} className="space-y-3">
          <Input label="Title" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} required />
          <div>
            <label className="text-sm font-medium text-foreground">Category</label>
            <select className="flex h-10 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground"
              value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}>
              <option value="event">Event</option>
              <option value="leave">Leave</option>
            </select>
          </div>
          <Input label="Start date" type="date" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} required />
          <Input label="End date (optional)" type="date" value={form.end_date} onChange={e => setForm({ ...form, end_date: e.target.value })} />
          <Input label="Notes (optional)" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
          <div className="flex justify-between gap-2 pt-2">
            {editId && canEditCurrent
              ? <Button type="button" variant="destructive" onClick={handleDelete}>Delete</Button>
              : <span />}
            <div className="flex gap-2">
              <Button type="button" variant="secondary" onClick={() => setModalOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={editId && !canEditCurrent}>Save</Button>
            </div>
          </div>
        </form>
      </Modal>
      <ConfirmDialog {...confirmProps} />
    </div>
  )
}
```
Notes: the aggregation does not return event `notes`; editing keeps the existing notes unless changed. If `isSupervisor`/`user` are needed for finer gating they are available from `useAuth()`; the server enforces edit/delete permission regardless, and the frontend disables Save when `editId && !canEditCurrent`.

- [ ] **Step 2: Build + lint**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build && npx eslint src/pages/CalendarPage.jsx
```
Expected: build succeeds; no NEW eslint errors. (Remove the unused `user`/`isSupervisor`/`calRef` if eslint flags them — keep the file clean.)

- [ ] **Step 3: Commit**
```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add frontend/src/pages/CalendarPage.jsx
git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(calendar): CalendarPage with FullCalendar + event modal"
```

---

### Task 7: Route + sidebar entry

**Files:** Modify `frontend/src/App.jsx`, `frontend/src/components/layout/Sidebar.jsx`

- [ ] **Step 1: Add the lazy import + route in App.jsx**

Add near the other lazy imports:
```jsx
const CalendarPage = lazy(() => import('@/pages/CalendarPage'))
```
Add among the protected routes:
```jsx
          <Route path="/calendar" element={<CalendarPage />} />
```

- [ ] **Step 2: Add the sidebar entry**

In `Sidebar.jsx`, import the `Calendar` icon from `lucide-react` (add to the existing `lucide-react` import), and add to `navItems`:
```jsx
  { to: '/calendar', icon: Calendar, label: 'Calendar', group: 'Flight Ops' },
```

- [ ] **Step 3: Build + lint**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build && npx eslint src/App.jsx src/components/layout/Sidebar.jsx
```
Expected: build succeeds; no NEW eslint errors.

- [ ] **Step 4: Commit**
```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add frontend/src/App.jsx frontend/src/components/layout/Sidebar.jsx
git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(calendar): route + sidebar entry"
```

---

### Task 8: Final verification + live retest checklist

- [ ] **Step 1: Whole-app check**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && PYTHONPATH=. .venv/Scripts/python.exe -c "import app.main; print('BACKEND_OK')"
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build
```
Expected: `BACKEND_OK` + clean build.

- [ ] **Step 2: Live retest (after deploy):**
  - Sidebar shows "Calendar"; the page renders Month/Week/List.
  - Existing training days, missions, maintenance-due, cert expirations appear on their dates; a day with flights shows an "N flights" badge.
  - Category toggles hide/show each color.
  - Clicking a training/mission/maintenance/cert item navigates to its page; clicking a flight badge goes to Flights.
  - "Add event / leave" creates an entry that appears immediately; editing it works; a non-owner non-supervisor cannot edit/delete it (Save disabled / server 403); a supervisor can.
  - Navigate months → events refetch for the visible range.

- [ ] **Step 3: Finish the branch** — `superpowers:finishing-a-development-branch` (merge to main / push only when Jonathan asks).

---

## Self-review (against the spec, Feature 1)

- FullCalendar (MIT, month/week/list) → Task 5/6. ✓
- Sidebar "Calendar" page → Task 7. ✓
- Sources: training, missions, maintenance-due, cert expirations, manual events/leave, per-day flight count → Task 3 aggregation + Task 6 render. ✓
- Category color toggles → Task 6. ✓
- Click auto-item → source page; click event/leave → edit modal → Task 6. ✓
- CalendarEvent model + CRUD; anyone creates; owner/supervisor edit/delete → Tasks 1-3, smoke Task 4. ✓
- New table via create_all (model imported in __init__) → Task 1. ✓
- No placeholders; exact code + commands throughout. ✓
- Pitfalls baked in: title vs name fields, null-date filtering, explicit created_by_id, seeded User in smoke test, React-19 FullCalendar version. ✓
