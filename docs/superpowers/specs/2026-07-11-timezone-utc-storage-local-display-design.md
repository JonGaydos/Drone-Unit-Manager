# Timezone: UTC storage, admin-configured local display

Date: 2026-07-11
Status: Draft (pending user review)

## Problem

Skydio-synced flights display their takeoff/landing times 5 hours ahead in
Central time. The times shown are UTC, not local.

Root cause: `flights.takeoff_time` and `flights.landing_time` are naive
`DateTime` columns (no offset), and the codebase holds two contradictory
conventions for what that naive value means.

| Path | Convention |
|------|------------|
| Skydio sync (`skydio.py` `_map_raw_flight`; `sync_manager.py` `_enrich_flight_timestamps`) | Parses Skydio's `...Z` timestamp as UTC, stores UTC wall-clock (the `+00:00` offset is dropped on write to the naive column) |
| Manual entry (`datetime-local` input, `FlightDetailPage`) | Stores local wall-clock |
| CSV export (`export.py`, ~L87-107) | Comment: "stored (local) datetime"; converts local to UTC using `TZ` env (default `America/Chicago`) |
| Frontend display (`utils.js` `formatDateTime`; `FlightDetailPage` `new Date(iso).toLocaleTimeString()`) | JS parses an offset-less ISO string as browser-local |

Everything except the Skydio importer treats the column as local. So a
14:30 UTC takeoff is stored as `14:30` and rendered as `14:30` local, i.e.
5 hours ahead of the true 09:30 CDT. Manually-entered flights render
correctly; only Skydio-synced flights are wrong. That asymmetry confirms the
diagnosis.

The app's own backlog already flags this ("Timezone consistency sweep",
"timezone off-by-one").

## Goal

- Store all datetimes as UTC (canonical, unambiguous).
- Display every timestamp in a single, admin-configured timezone, so an
  agency in any zone sees correct local times without code changes.

## Design

### Model

- **Database = UTC.** Keep naive `DateTime` columns, UTC-by-convention (no
  column type change; matches SQLite). Skydio rows are already UTC and become
  correct under this model.
- **API = UTC with offset.** Serialize datetimes as ISO 8601 with a trailing
  `Z` (e.g. `2026-07-11T14:30:00Z`) so clients cannot mis-parse them as local.
- **Display = admin timezone.** The frontend converts UTC to the configured
  IANA zone for every rendered timestamp. DST is handled by the browser's
  `Intl` engine.

Timezone is a single program-wide setting, not per-user. An agency operates
in one zone, and the request is for an admin-controlled program setting.

### Setting: `display_timezone`

- New program setting keyed `display_timezone`, default `America/Chicago`.
- Set in two places, both writing the same program setting:
  1. First-launch **setup page** (`SetupPage` / the setup flow), as an
     IANA-zone dropdown, so the agency's zone is captured at install.
  2. Admin **Settings page**, editable later, reusing the existing
     admin-gated `set_setting` / bulk-save path.
- Loaded into the frontend during app bootstrap (via `/api/settings`),
  exposed through a small settings context and a module-level setter
  (`setDisplayTimezone(tz)`) that the formatting helpers read. Bootstrap
  completes before flight views render; falls back to browser-local until
  loaded.

### Backend changes

1. **Serialize with `Z`.** Add a Pydantic serializer (on `FlightOut`, and
   any other schema that surfaces datetimes to the UI) that stamps naive
   datetimes as UTC and emits a `Z`-suffixed ISO string.
2. **Manual entry round-trip.** The `datetime-local` input is a wall-clock
   value in the admin zone. On save, convert admin-zone to UTC before storing;
   on edit-form populate, convert UTC to admin-zone. Manual and Skydio flights
   then share one convention.
3. **Export.** `export.py` currently assumes "stored = local" and shifts the
   UTC columns by the offset, so today's export is also wrong. Flip it to
   "stored = UTC": the "Local Takeoff Time" column converts UTC to the admin
   zone; the `Takeoff` / `Land` UTC columns become a passthrough. Drive the
   zone from the `display_timezone` setting (falling back to the existing `TZ`
   env default) so export and UI agree.
4. **Shared helper.** A single backend utility resolves the configured zone
   and does UTC-to-local / local-to-UTC conversions, used by the export and
   manual-entry paths. Keeps the convention in one place.

### Frontend changes

1. Make `formatDateTime` / `formatDate` timezone-aware via
   `Intl.DateTimeFormat(..., { timeZone })`, reading the module-level zone.
2. Sweep direct `new Date(...).toLocaleTimeString()` / `.toLocaleString()`
   calls (FlightDetailPage L475/L479, and any others found) to route through
   the helpers, so nothing bypasses the configured zone.
3. Add the timezone dropdown to the Settings page.

### Existing data

Verified against the live DB (1356 flights) on 2026-07-11:

- 51 `skydio_api` rows: stored UTC. Confirmed by exact match to the Skydio
  API (`DBB45… -> 16:11:12.804494` stored == `16:11:12.804494+00:00` API).
- 1305 `excel_import` rows: also stored UTC. Confirmed by cross-checking four
  external IDs against the Skydio API; stored times match the API's UTC
  takeoff to the minute (seconds were dropped on import). They came from the
  Skydio export's UTC `Takeoff` column (`excel_import._parse_dt`, preferring
  `Takeoff` over `Local Takeoff Time`).
- There are zero hand-typed (`data_source="manual"`) flights.

**Result: all stored data is already UTC. No data migration is required.**
`created_at` / `updated_at` and other tables already use `utcnow` (UTC).

### Telemetry note

Telemetry points use `timestamp_ms` (epoch millis, unambiguous UTC) and the
chart X-axis uses `elapsed_s` (seconds from takeoff). The plotted data is
already correct and out of scope. Only wall-clock fields (takeoff/landing
time) change.

## Testing

- Backend: Skydio import stores correct UTC; serializer emits `Z`;
  manual-entry round-trip (local to UTC to local) is stable; export columns
  correct for at least two configured zones.
- Frontend: `formatDateTime` renders a known UTC instant correctly in
  `America/Chicago` and one other zone, proving multi-agency behavior.

## Verification (completed 2026-07-11)

- Skydio API: raw timestamps are UTC as `+00:00` (e.g.
  `2026-07-09T16:11:12.804494+00:00`); the code's `.replace("Z", ...)` is a
  no-op but `fromisoformat` parses the offset correctly.
- DUM live DB: all 1356 flights stored UTC (see Existing data). No migration.
- Post-implementation, re-check one real flight's stored vs displayed time in
  `America/Chicago` and one other zone.

## Out of scope

- Per-user timezone preferences.
- Changing telemetry storage or chart axes.
- Reworking non-flight datetime displays beyond routing them through the
  tz-aware helpers where they surface flight-relevant times.
