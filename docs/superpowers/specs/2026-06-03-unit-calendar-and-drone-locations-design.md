# Unit Calendar + Drone Location Tracking — Design

Date: 2026-06-03
Project: Drone Unit Manager (FastAPI + React + SQLite)
Status: proposed (awaiting review)

## Context

The drone unit wants two unit-wide visibility features:

1. A **calendar** showing what the unit is doing as a whole — training days,
   mission logs, maintenance due, events, and personal leave — pulled from
   existing data where possible. A generic, reputable calendar (Outlook-style),
   not a hand-built one.
2. A dashboard **"Locations" tile** showing the last-known location of each
   drone, where a location is either a pilot (the drone is with them) or a
   named place (North / Central / South, agency-defined).

These are two independent features sharing one spec. They can be built and
shipped separately.

## Non-goals

- No GPS/telemetry-derived drone location (the unit wants custody/where-is-it,
  not coordinates).
- No leave approval workflow (leave here is a shared visibility entry only;
  real leave is managed by each pilot's home unit).
- No custom calendar widget (use a library).
- Individual flights are NOT plotted on the calendar (too noisy at 2000+); a
  per-day flight count is shown instead.

---

## Feature 1 — Unit Calendar

### Library

FullCalendar (React): `@fullcalendar/react` + `@fullcalendar/daygrid`,
`@fullcalendar/timegrid`, `@fullcalendar/list`, `@fullcalendar/interaction`.
All MIT-licensed (FullCalendar's paid plugins are resource/timeline views we do
not need). Gives Month / Week / List views and event click handling out of the
box.

### Page and navigation

- New route `/calendar` and a sidebar entry ("Calendar").
- Month / Week / List view toggle (FullCalendar header toolbar).
- A category legend with toggles to show/hide each source.

### Event sources (unit-level, color-coded categories)

| Category | Source | Click action |
|---|---|---|
| Training day | `training_logs` (date) | open training log |
| Mission | `mission_logs` (date) | open mission log |
| Maintenance due | `maintenance_schedules.next_due` | open maintenance |
| Cert expiration | `pilot_certifications.expiration_date` | open certifications |
| Event | new `calendar_events` (category=event) | open event editor |
| Leave | new `calendar_events` (category=leave) | open leave editor |
| Flights (count) | `flights` aggregated per day | open Flights filtered to that day |

Flights appear only as an all-day count badge per day (e.g. "4 flights"), never
as individual entries. Cert-expiration category is included; trivial to drop if
unwanted.

### Backend

- **New model `CalendarEvent`** (`backend/app/models/calendar_event.py`):
  `id`, `title` (str), `category` (str: "event" | "leave"), `start_date`
  (date), `end_date` (date, nullable for single-day), `all_day` (bool, default
  true), `pilot_id` (FK pilots, nullable — used for leave), `notes` (text,
  nullable), `created_by_id` (FK users), `created_at`, `updated_at`. New table
  is created by `create_all`; no destructive migration. Use Python-side
  `default=datetime.utcnow` for timestamps (NOT `server_default`, per the
  2026-06-03 login-500 lesson) to be safe even though it is a new table.
- **New router `routers/calendar.py`:**
  - `GET /api/calendar?start=YYYY-MM-DD&end=YYYY-MM-DD` — aggregation: returns a
    flat list of `{id, title, start, end, all_day, category, source, link}`
    across all categories within the range, plus a `flight_counts`
    `{date: count}` map. Auth: any `CurrentUser`. One bounded query per source
    over the visible range (no N+1).
  - `POST /api/calendar/events` — create an event or leave entry. Any
    `CurrentUser`. `created_by_id = user.id`.
  - `PATCH /api/calendar/events/{id}` and `DELETE /api/calendar/events/{id}` —
    allowed if `user.id == created_by_id` OR user is supervisor+. Audit-logged.
- Pydantic schemas for `CalendarEvent` create/update/out.

### Frontend

- `pages/CalendarPage.jsx` — FullCalendar with `dateset`/`datesSet` driving a
  fetch of `GET /api/calendar` for the visible range; maps results to
  FullCalendar events with per-category colors; category toggle state filters
  client-side. Daily flight counts render as background/all-day badges.
- Event/leave create + edit modal (reuse `components/ui/Modal`): title, category
  (event/leave), date range, all-day, optional pilot (for leave, defaults to the
  current user's linked pilot), notes. Delete with confirm (reuse `useConfirm`).
- Clicking an auto-pulled item navigates to its source page; clicking an
  event/leave opens the editor (edit disabled if not owner/supervisor).

### Permissions

- View: all authenticated users.
- Create events and leave: any authenticated user (no approval).
- Edit/delete: the creator, or supervisor+.

---

## Feature 2 — Drone Location Tracking

### Named places (agency-defined)

- Stored as a Setting `drone_location_places` (JSON list), **default
  `["North", "Central", "South"]`**, admin-editable in the Settings page (a
  small add/remove list, reusing the existing settings write path).

### Vehicle location data

Add nullable columns to `vehicles` (additive migration via the existing
`_apply_column_migrations` pattern; all nullable, no `server_default`):
- `manual_location_place` (str, nullable) — a named place, OR
- `manual_location_pilot_id` (FK pilots, nullable) — a pilot,
  (exactly one of the two is set when a manual location exists)
- `location_set_at` (datetime, nullable)
- `location_set_by_id` (FK users, nullable)

### Current-location rule ("whichever is newer")

For each vehicle, the displayed current location is the more recent of:
- **Active checkout:** the latest `equipment_checkout` with
  `entity_type="vehicle"`, `entity_id=vehicle.id`, not yet checked in →
  "with <pilot>" as of its `checked_out_at`.
- **Manual set:** the `manual_location_*` as of `location_set_at`.

Compare the two timestamps; show the newer. If neither exists, show "Unknown".
A checked-in (returned) checkout does not assert a location, so only an active
checkout competes with the manual set. Using the dropdown writes a manual set
with a fresh timestamp, so it immediately wins until a newer checkout occurs.

### Backend

- `GET /api/vehicles/locations` — returns
  `[{vehicle_id, label, location_text, source: "checkout"|"manual"|"unknown"}]`
  for active vehicles, computing the rule above. One batched query for active
  checkouts; no N+1.
- `PATCH /api/vehicles/{id}/location` — body `{place}` or `{pilot_id}`; sets the
  manual location, `location_set_at=now`, `location_set_by_id=user.id`. Auth:
  any `CurrentUser` (anyone can change it). Audit-logged.
- Settings: the places list managed through existing settings endpoints; add
  `drone_location_places` to the admin-editable key set.

### Frontend

- **Dashboard "Locations" tile** (in `pages/DashboardPage.jsx`): one row per
  active drone — label (manufacturer/model/nickname) + current location text —
  each with an inline `Select` dropdown whose options are active pilots + the
  named places. Changing it calls `PATCH /api/vehicles/{id}/location` and
  optimistically updates the row. Anyone can change it.
- **Settings:** a small "Drone Locations" section to add/remove named places
  (admin only), defaulting to North/Central/South.

---

## Data flow summary

- Calendar: `CalendarPage` → `GET /api/calendar?start&end` (aggregates 5 read
  sources + manual events + flight counts) → FullCalendar render; create/edit
  via `/api/calendar/events`.
- Locations: `DashboardPage` Locations tile → `GET /api/vehicles/locations`
  (newer-of checkout vs manual) → inline dropdown → `PATCH
  /api/vehicles/{id}/location`.

## Migrations / data safety

- New table `calendar_events` via `create_all` (no risk).
- New nullable `vehicles` columns via `_apply_column_migrations` (idempotent,
  nullable, no `server_default` — avoids the 2026-06-03 existing-DB INSERT bug).
- New Setting key with a default; no schema change.

## Verification

- Backend: `py_compile` + `import app.main`; seeded in-memory SQLite smoke
  tests for (a) the calendar aggregation over a date range across each source +
  flight counts, (b) the location rule (manual-newer vs checkout-newer vs
  none), (c) manual-location PATCH, (d) `calendar_events` CRUD + permission
  (owner vs non-owner vs supervisor). Confirm the new vehicle columns migrate
  idempotently on an existing-schema DB.
- Frontend: `npm run build` + `eslint`.
- Live: add an event and a leave entry; verify month/week/list; toggle
  categories; verify a training day and a maintenance-due appear and link out;
  set a drone's location via the tile and confirm it shows; check out a drone to
  a pilot and confirm the tile flips to "with <pilot>" (newer wins).

## Open / deferred

- Cert-expiration calendar category included; drop if noisy.
- Calendar export/iCal feed: out of scope for v1.
- Location history/audit trail beyond the single current value: out of scope
  (the change is audit-logged, but no per-vehicle location timeline UI).

## Files (anticipated)

Backend: `models/calendar_event.py` (new), `routers/calendar.py` (new),
`schemas/calendar.py` (new), `services/migrations.py` (vehicle columns),
`models/vehicle.py` (columns), `routers/vehicles.py` (location endpoints),
`routers/settings.py` (places key), `main.py` (register calendar router).
Frontend: `pages/CalendarPage.jsx` (new), calendar event modal, `App.jsx`
(route), `components/layout/Sidebar.jsx` (nav), `pages/DashboardPage.jsx`
(Locations tile), `pages/SettingsPage.jsx` (places management),
`package.json` (FullCalendar deps).
