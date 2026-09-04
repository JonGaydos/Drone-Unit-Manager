# Timezone: UTC storage, admin-configured local display — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store all flight datetimes as UTC and display every timestamp in an admin-configured timezone, fixing the 5-hour-ahead display.

**Architecture:** Backend serializes flight datetimes as ISO-8601 with a trailing `Z` (unambiguous UTC) and normalizes any tz-aware input back to naive-UTC on write. The frontend converts UTC to a single program-wide `display_timezone` (IANA name) for display, set on the first-launch setup page and the admin Settings page, loaded at app bootstrap into a module-level value the formatting helpers read. The CSV export is flipped to treat stored times as UTC.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy (SQLite), React 17, Vite, Vitest, MSW, pytest.

## Global Constraints

- Storage is UTC. No column type changes; naive datetimes are UTC-by-convention.
- Flight datetimes serialize to JSON with a trailing `Z` (e.g. `2026-06-24T16:26:00Z`).
- Display timezone is a single program-wide setting `display_timezone`, an IANA name, default `America/Chicago`.
- No data migration: every existing flight (verified live) is already stored in UTC.
- No new dependencies. Timezone conversion uses the built-in `Intl` API.
- Telemetry (`timestamp_ms`, `elapsed_s`) is out of scope and unchanged.
- Style: no emojis, no em dashes; match existing code style.
- Backend tests run: `backend/.venv/Scripts/python.exe -m pytest <path> -v` (run from repo root, or `cd backend` and drop the prefix).
- Frontend tests run: `cd frontend && npm run test:run -- <path>`.

---

### Task 1: Backend — serialize flight datetimes as UTC `Z`, normalize input to naive-UTC

**Files:**
- Modify: `backend/app/schemas/flight.py`
- Test: `backend/tests/test_flight_timezone.py` (create)

**Interfaces:**
- Produces: `FlightOut` JSON where `takeoff_time`, `landing_time`, `created_at`, `updated_at` are `...Z` strings (or null). `FlightCreate` / `FlightUpdate` coerce any tz-aware `takeoff_time` / `landing_time` to naive-UTC before storage.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_flight_timezone.py`:

```python
"""Timezone serialization/normalization for flight datetimes."""
from datetime import datetime, timezone

from app.models.flight import Flight


def _make_flight(db, **kw):
    f = Flight(date=datetime(2026, 6, 24).date(), **kw)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def test_flightout_serializes_naive_takeoff_as_utc_z(client, db, admin_headers):
    f = _make_flight(db, takeoff_time=datetime(2026, 6, 24, 16, 26, 0))
    resp = client.get(f"/api/flights/{f.id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["takeoff_time"] == "2026-06-24T16:26:00Z"


def test_patch_tz_aware_takeoff_is_stored_naive_utc(client, db, admin_headers):
    f = _make_flight(db, takeoff_time=datetime(2026, 6, 24, 16, 26, 0))
    # Client sends a Central-offset wall time; it must land in the DB as 16:26 UTC.
    resp = client.patch(
        f"/api/flights/{f.id}",
        json={"takeoff_time": "2026-06-24T11:26:00-05:00"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["takeoff_time"] == "2026-06-24T16:26:00Z"
    db.expire_all()
    stored = db.query(Flight).filter(Flight.id == f.id).first().takeoff_time
    assert stored.tzinfo is None
    assert stored == datetime(2026, 6, 24, 16, 26, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_flight_timezone.py -v`
Expected: FAIL — `test_flightout_serializes_naive_takeoff_as_utc_z` gets `2026-06-24T16:26:00` (no `Z`).

- [ ] **Step 3: Add the serializer and validator**

In `backend/app/schemas/flight.py`, update the imports at the top:

```python
from datetime import datetime, timezone
from datetime import date as DateType
from typing import Optional

from pydantic import BaseModel, Field, field_validator, field_serializer
```

Add this module-level helper after the imports (above `ALLOWED_REVIEW_STATUS`):

```python
def _naive_utc(value: datetime | None) -> datetime | None:
    """Coerce a tz-aware datetime to naive UTC so it stores UTC-by-convention."""
    if value is not None and value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
```

In `FlightCreate`, add after its fields (inside the class body):

```python
    _tz_takeoff = field_validator("takeoff_time")(_naive_utc)
    _tz_landing = field_validator("landing_time")(_naive_utc)
```

In `FlightUpdate`, add the same two lines alongside the existing `_validate_review_status`:

```python
    _tz_takeoff = field_validator("takeoff_time")(_naive_utc)
    _tz_landing = field_validator("landing_time")(_naive_utc)
```

In `FlightOut`, add a serializer inside the class body (after `model_config`):

```python
    @field_serializer("takeoff_time", "landing_time", "created_at", "updated_at", when_used="json")
    def _serialize_utc_z(self, value: datetime | None):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_flight_timezone.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run the existing flight tests to check for regressions**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_flights.py -v`
Expected: PASS (adjust any test that hard-coded a no-`Z` datetime string to expect the `...Z` form).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/flight.py backend/tests/test_flight_timezone.py
git commit -m "feat(flights): serialize datetimes as UTC Z, normalize input to naive UTC"
```

---

### Task 2: Backend — add `display_timezone` setting and capture it during setup

**Files:**
- Modify: `backend/app/routers/settings.py`
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/routers/auth.py`
- Test: `backend/tests/test_timezone_setting.py` (create)

**Interfaces:**
- Consumes: `SetupRequest` (from `app/schemas/user.py`).
- Produces: setting key `display_timezone` is writable by admin (`ALLOWED_SETTING_KEYS`) and readable by any authenticated user (`PUBLIC_KEYS`). `POST /api/auth/setup` accepts `timezone` and persists it as `display_timezone`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_timezone_setting.py`:

```python
"""display_timezone setting: setup capture, public read, admin write."""
from app.models.setting import Setting


def test_setup_persists_display_timezone(client, db):
    resp = client.post("/api/auth/setup", json={
        "username": "admin",
        "password": "AdminPassw0rd!",
        "display_name": "Admin",
        "org_name": "Test Org",
        "timezone": "America/New_York",
    })
    assert resp.status_code == 200
    row = db.query(Setting).filter(Setting.key == "display_timezone").first()
    assert row is not None and row.value == "America/New_York"


def test_pilot_can_read_display_timezone(client, db, pilot_headers):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()
    resp = client.get("/api/settings/display_timezone", headers=pilot_headers)
    assert resp.status_code == 200
    assert resp.json()["value"] == "America/Chicago"


def test_admin_can_write_display_timezone(client, db, admin_headers):
    resp = client.put("/api/settings",
                      json={"key": "display_timezone", "value": "America/Denver"},
                      headers=admin_headers)
    assert resp.status_code == 200
    assert db.query(Setting).filter(Setting.key == "display_timezone").first().value == "America/Denver"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_timezone_setting.py -v`
Expected: FAIL — setup rejects `timezone` / key not allowed / not readable.

- [ ] **Step 3: Allow and expose the setting key**

In `backend/app/routers/settings.py`, add `"display_timezone"` to `ALLOWED_SETTING_KEYS` (append inside the set literal, near `org_name`) and to `PUBLIC_KEYS` (append inside that set literal):

```python
# in ALLOWED_SETTING_KEYS { ... }
    "org_name", "org_logo", "display_timezone",
```

```python
# in PUBLIC_KEYS { ... }
    "org_name", "org_logo", "display_timezone",
```

- [ ] **Step 4: Add `timezone` to the setup schema**

In `backend/app/schemas/user.py`, add a field to `SetupRequest`:

```python
class SetupRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=8, max_length=255)
    display_name: str = Field(default="", max_length=255)
    org_name: str = Field(default="", max_length=255)
    email: str = Field(default="", max_length=255)
    timezone: str = Field(default="America/Chicago", max_length=64)

    _validate_email = field_validator("email")(_validate_optional_email)
```

- [ ] **Step 5: Persist the timezone in `initial_setup`**

In `backend/app/routers/auth.py`, inside `initial_setup`, after the org-name block (`if org_name: db.add(Setting(key="org_name", value=org_name))`), add:

```python
    # Persist the agency display timezone chosen during setup.
    tz = (data.timezone or "America/Chicago").strip()
    db.add(Setting(key="display_timezone", value=tz))
```

- [ ] **Step 6: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_timezone_setting.py -v`
Expected: PASS (all three).

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/settings.py backend/app/schemas/user.py backend/app/routers/auth.py backend/tests/test_timezone_setting.py
git commit -m "feat(settings): add display_timezone setting, captured at setup"
```

---

### Task 3: Backend — flip CSV export to stored-UTC + configured local zone

**Files:**
- Modify: `backend/app/routers/export.py:91-107`
- Test: `backend/tests/test_export_timezone.py` (create)

**Interfaces:**
- Consumes: `display_timezone` setting (Task 2).
- Produces: the flights CSV `Takeoff` / `Land` columns are the stored UTC value formatted as-is; `Local Takeoff Time` is that UTC value converted to the configured zone.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_export_timezone.py`:

```python
"""CSV export renders UTC columns as-is and Local column in the configured zone."""
import csv
import io
from datetime import datetime

from app.models.flight import Flight
from app.models.setting import Setting


def test_export_utc_and_local_columns(client, db, admin_headers):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.add(Flight(external_id="F1", date=datetime(2026, 6, 24).date(),
                  takeoff_time=datetime(2026, 6, 24, 16, 26, 0),
                  landing_time=datetime(2026, 6, 24, 16, 31, 0)))
    db.commit()
    resp = client.get("/api/export/flights/csv", headers=admin_headers)
    assert resp.status_code == 200
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    row = next(r for r in rows if r["Flight ID"] == "F1")
    assert row["Takeoff"] == "2026-06-24 16:26"          # UTC, as stored
    assert row["Local Takeoff Time"] == "2026-06-24 11:26"  # CDT (UTC-5)
    assert row["Land"] == "2026-06-24 16:31"
```

(If the `Flight ID` header constant differs, read it from `SKYDIO_FLIGHT_ID_COL` in `export.py`; the value is `"Flight ID"`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_export_timezone.py -v`
Expected: FAIL — `Takeoff` currently shows a shifted value and `Local Takeoff Time` shows the UTC value.

- [ ] **Step 3: Rewrite the zone helpers in the export**

In `backend/app/routers/export.py`, replace the timezone setup block (currently lines ~91-107, from `import os` through the `_fmt_utc` definition) with:

```python
    from datetime import timezone
    from zoneinfo import ZoneInfo
    from app.models.setting import Setting

    tz_row = db.query(Setting).filter(Setting.key == "display_timezone").first()
    tz_name = (tz_row.value if tz_row and tz_row.value else None) or os.environ.get("TZ", "America/Chicago")
    try:
        local_tz = ZoneInfo(tz_name)
    except Exception:
        local_tz = ZoneInfo("America/Chicago")

    def _fmt_utc(dt):
        # Stored value is already UTC; render as-is.
        return dt.strftime("%Y-%m-%d %H:%M") if dt else ""

    def _fmt_local(dt):
        # Convert stored UTC to the configured local zone.
        if not dt:
            return ""
        return dt.replace(tzinfo=timezone.utc).astimezone(local_tz).strftime("%Y-%m-%d %H:%M")
```

Add `import os` at the top of the function if it is no longer present after the edit (it was previously the first line of the removed block). Keep the existing docstring; update its last sentence to read: "Takeoff and Land are the stored UTC values; Local Takeoff Time is converted to the configured display timezone."

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_export_timezone.py -v`
Expected: PASS.

- [ ] **Step 5: Run the existing export tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -k export -v`
Expected: PASS (update any export test that asserted the old shifted values).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/export.py backend/tests/test_export_timezone.py
git commit -m "fix(export): treat stored flight times as UTC, localize via display_timezone"
```

---

### Task 4: Frontend — timezone-aware formatting helpers

**Files:**
- Modify: `frontend/src/lib/utils.js`
- Test: `frontend/src/lib/utils.test.js`

**Interfaces:**
- Produces: `setDisplayTimezone(tz)`, `getDisplayTimezone()`, `formatTime(iso)`, `utcIsoToZonedInput(iso, tz?)`, `zonedInputToUtcIso(wall, tz?)`, and the `TIMEZONES` array. `formatDateTime` now renders in the configured zone. `formatDate` is unchanged (date-only values must not shift zones).

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/lib/utils.test.js` (add the new names to the existing import at the top: `setDisplayTimezone`, `getDisplayTimezone`, `formatTime`, `utcIsoToZonedInput`, `zonedInputToUtcIso`, `TIMEZONES`):

```js
describe('timezone-aware formatting (America/Chicago)', () => {
  afterEach(() => setDisplayTimezone(null))

  it('formatDateTime converts a UTC Z instant to the configured zone', () => {
    setDisplayTimezone('America/Chicago')
    // 16:26 UTC on 2026-06-24 is 11:26 CDT (UTC-5).
    expect(formatDateTime('2026-06-24T16:26:00Z')).toBe('Jun 24, 2026, 11:26 AM')
  })

  it('formatTime converts a UTC Z instant to the configured zone', () => {
    setDisplayTimezone('America/Chicago')
    expect(formatTime('2026-06-24T16:26:00Z')).toBe('11:26 AM')
    expect(formatTime(null)).toBe('—')
  })

  it('utcIsoToZonedInput yields a datetime-local wall value in the zone', () => {
    expect(utcIsoToZonedInput('2026-06-24T16:26:00Z', 'America/Chicago')).toBe('2026-06-24T11:26')
  })

  it('zonedInputToUtcIso round-trips a zoned wall value back to UTC Z', () => {
    expect(zonedInputToUtcIso('2026-06-24T11:26', 'America/Chicago')).toBe('2026-06-24T16:26:00Z')
  })

  it('exposes America/Chicago in the TIMEZONES list', () => {
    expect(TIMEZONES).toContain('America/Chicago')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test:run -- src/lib/utils.test.js`
Expected: FAIL — the new functions are not exported.

- [ ] **Step 3: Implement the helpers**

In `frontend/src/lib/utils.js`, add near the top (after the imports):

```js
// Program-wide display timezone (IANA name). null = use the browser's local zone.
let _displayTimezone = null

/** Set the program-wide display timezone (IANA name), e.g. 'America/Chicago'. */
export function setDisplayTimezone(tz) { _displayTimezone = tz || null }

/** Get the configured display timezone, or undefined to fall back to browser-local. */
export function getDisplayTimezone() { return _displayTimezone || undefined }

/** Curated IANA timezones offered in the setup and settings dropdowns. */
export const TIMEZONES = [
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Phoenix',
  'America/Los_Angeles', 'America/Anchorage', 'Pacific/Honolulu',
  'UTC', 'Europe/London', 'Europe/Paris', 'Australia/Sydney',
]
```

Change `formatDateTime` to pass the configured zone (add the one `timeZone` option; leave everything else):

```js
export function formatDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: getDisplayTimezone() })
}
```

Add `formatTime` and the two round-trip helpers at the end of the file:

```js
/**
 * Format an ISO datetime to a localized time-of-day in the configured zone.
 * @param {string} iso - ISO 8601 datetime string (UTC `Z` for flight times).
 * @returns {string} e.g. "11:26 AM", or em-dash if invalid/empty.
 */
export function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: getDisplayTimezone() })
}

/**
 * Convert a UTC ISO instant to a 'YYYY-MM-DDTHH:mm' wall value in `tz`,
 * suitable for a datetime-local input.
 * @param {string} iso - UTC ISO 8601 string.
 * @param {string} [tz] - IANA zone; defaults to the configured display zone.
 * @returns {string} datetime-local value, or '' if invalid/empty.
 */
export function utcIsoToZonedInput(iso, tz = getDisplayTimezone()) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(d)
  const g = t => parts.find(p => p.type === t).value
  let hh = g('hour'); if (hh === '24') hh = '00'
  return `${g('year')}-${g('month')}-${g('day')}T${hh}:${g('minute')}`
}

/**
 * Convert a 'YYYY-MM-DDTHH:mm' wall value (interpreted in `tz`) to a UTC ISO
 * instant ending in 'Z'.
 * @param {string} wall - datetime-local value.
 * @param {string} [tz] - IANA zone; defaults to the configured display zone.
 * @returns {string|null} UTC ISO string, or null if empty.
 */
export function zonedInputToUtcIso(wall, tz = getDisplayTimezone()) {
  if (!wall) return null
  if (!tz) {
    const d = new Date(wall)
    return Number.isNaN(d.getTime()) ? null : d.toISOString().replace('.000Z', 'Z')
  }
  const [datePart, timePart] = wall.split('T')
  const [y, mo, d] = datePart.split('-').map(Number)
  const [h, mi] = timePart.split(':').map(Number)
  const asUTC = Date.UTC(y, mo - 1, d, h, mi)
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(new Date(asUTC))
  const gp = t => Number(parts.find(p => p.type === t).value)
  let hh = gp('hour'); if (hh === 24) hh = 0
  const shown = Date.UTC(gp('year'), gp('month') - 1, gp('day'), hh, gp('minute'), gp('second'))
  const offset = shown - asUTC
  return new Date(asUTC - offset).toISOString().replace('.000Z', 'Z')
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm run test:run -- src/lib/utils.test.js`
Expected: PASS (new block and all pre-existing utils tests, including the no-`Z` `formatDateTime` local test which still renders 3:45 PM because the module zone resets to null).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/utils.js frontend/src/lib/utils.test.js
git commit -m "feat(utils): timezone-aware formatDateTime/formatTime + UTC<->zoned helpers"
```

---

### Task 5: Frontend — load `display_timezone` at app bootstrap

**Files:**
- Modify: `frontend/src/App.jsx`
- Test: `frontend/src/test/timezone-bootstrap.test.jsx` (create)

**Interfaces:**
- Consumes: `setDisplayTimezone` / `getDisplayTimezone` (Task 4), `GET /api/settings/display_timezone` (Task 2).
- Produces: after an authenticated bootstrap, the module display zone equals the fetched value; protected routes do not render until it resolves.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/timezone-bootstrap.test.jsx`:

```jsx
import { describe, it, expect, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { AuthProvider } from '@/contexts/AuthContext'
import { ThemeProvider } from '@/contexts/ThemeContext'
import { ToastProvider } from '@/contexts/ToastContext'
import { getDisplayTimezone, setDisplayTimezone } from '@/lib/utils'
import App from '@/App'

afterEach(() => setDisplayTimezone(null))

describe('timezone bootstrap', () => {
  it('sets the display timezone from the settings endpoint after login', async () => {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'admin', role: 'admin' }))
    server.use(
      http.get('/api/auth/setup-required', () => HttpResponse.json({ setup_required: false })),
      http.get('/api/auth/me', () => HttpResponse.json({ id: 1, username: 'admin', role: 'admin' })),
      http.get('/api/settings/display_timezone', () => HttpResponse.json({ key: 'display_timezone', value: 'America/Denver' })),
    )
    render(<App />)
    await waitFor(() => expect(getDisplayTimezone()).toBe('America/Denver'))
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:run -- src/test/timezone-bootstrap.test.jsx`
Expected: FAIL — timezone stays undefined (no bootstrap fetch yet).

- [ ] **Step 3: Wire the bootstrap fetch into `AppRoutes`**

In `frontend/src/App.jsx`, add `setDisplayTimezone` to the utils import:

```js
import { api } from '@/api/client'
import { setDisplayTimezone } from '@/lib/utils'
```

In `AppRoutes`, add a `tzReady` gate. Replace the existing setup-required block:

```js
function AppRoutes() {
  const { user, loading } = useAuth()
  const [setupRequired, setSetupRequired] = useState(null)
  const [tzReady, setTzReady] = useState(false)

  useEffect(() => {
    api.get('/auth/setup-required').then(d => setSetupRequired(d.setup_required)).catch(() => setSetupRequired(false))
  }, [])

  useEffect(() => {
    if (loading) return
    if (!user) { setTzReady(true); return }
    api.get('/settings/display_timezone')
      .then(d => setDisplayTimezone(d.value || 'America/Chicago'))
      .catch(() => setDisplayTimezone('America/Chicago'))
      .finally(() => setTzReady(true))
  }, [user, loading])

  if (loading || setupRequired === null || !tzReady) return <div className="min-h-screen bg-background flex items-center justify-center"><Spinner /></div>
  if (setupRequired) return <Suspense fallback={<Spinner />}><SetupPage /></Suspense>
```

(Leave the rest of `AppRoutes` unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:run -- src/test/timezone-bootstrap.test.jsx`
Expected: PASS. If the auth endpoint path differs (`/auth/me` vs another), read `frontend/src/contexts/AuthContext.jsx` and match the handler URL; the assertion on `getDisplayTimezone()` is what matters.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/test/timezone-bootstrap.test.jsx
git commit -m "feat(app): load display_timezone at bootstrap before protected routes render"
```

---

### Task 6: Frontend — FlightDetailPage display and edit round-trip

**Files:**
- Modify: `frontend/src/pages/FlightDetailPage.jsx` (imports; lines 251-252, 305-320, 475/479)
- Test: `frontend/src/pages/FlightDetailPage.test.jsx`

**Interfaces:**
- Consumes: `formatTime`, `utcIsoToZonedInput`, `zonedInputToUtcIso`, `setDisplayTimezone` (Task 4).
- Produces: takeoff/landing render in the configured zone; the edit form pre-fills the zoned wall value and saves UTC.

- [ ] **Step 1: Write the failing test**

In `frontend/src/pages/FlightDetailPage.test.jsx`, add `setDisplayTimezone` support and a new test. Add imports at the top:

```js
import { beforeEach, afterEach } from 'vitest'
import { setDisplayTimezone } from '@/lib/utils'
```

Add inside `describe('FlightDetailPage', () => {`:

```js
  beforeEach(() => setDisplayTimezone('America/Chicago'))
  afterEach(() => setDisplayTimezone(null))

  it('renders takeoff time in the configured zone and saves UTC', async () => {
    let patchBody = null
    mockMount({ flight: () => HttpResponse.json({ ...FLIGHT, takeoff_time: '2026-05-01T18:30:00Z' }) })
    server.use(http.patch('/api/flights/:id', async ({ request }) => {
      patchBody = await request.json()
      return HttpResponse.json({ ...FLIGHT, review_status: 'reviewed' })
    }))
    const { user } = render('admin')

    // 18:30 UTC on 2026-05-01 is 1:30 PM CDT.
    expect(await screen.findByText('1:30 PM')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.click(await screen.findByRole('button', { name: 'Save' }))
    // The edit form pre-filled 13:30 (zoned) and must post 18:30Z back.
    expect(patchBody.takeoff_time).toBe('2026-05-01T18:30:00Z')
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:run -- src/pages/FlightDetailPage.test.jsx`
Expected: FAIL — display uses raw `toLocaleTimeString` (wrong text) and save posts the zoned string, not UTC.

- [ ] **Step 3: Update imports in FlightDetailPage**

In `frontend/src/pages/FlightDetailPage.jsx`, add the helpers to the existing `@/lib/utils` import (it already imports `formatDuration`, `metersToFeet`, `mpsToMph`, `normalizeDateValue`):

```js
import { formatDuration, formatHours, metersToFeet, mpsToMph, normalizeDateValue, formatTime, utcIsoToZonedInput, zonedInputToUtcIso } from '@/lib/utils'
```

(Keep whatever names are already imported; add `formatTime`, `utcIsoToZonedInput`, `zonedInputToUtcIso`. Drop `formatHours` from this line if it was not already imported.)

- [ ] **Step 4: Pre-fill the edit form with zoned wall values**

Replace lines 251-252 in `initEditForm`:

```js
      takeoff_time: f.takeoff_time ? utcIsoToZonedInput(f.takeoff_time) : '',
      landing_time: f.landing_time ? utcIsoToZonedInput(f.landing_time) : '',
```

- [ ] **Step 5: Convert edit-form values back to UTC on save**

In `handleSave`, after the existing empty-string cleanup (`Object.keys(data).forEach(...)`) and before `const updated = await api.patch(...)`, add:

```js
      if (data.takeoff_time) data.takeoff_time = zonedInputToUtcIso(data.takeoff_time)
      if (data.landing_time) data.landing_time = zonedInputToUtcIso(data.landing_time)
```

- [ ] **Step 6: Render display times through `formatTime`**

Replace line 475:

```jsx
              <p className="text-foreground">{formatTime(flight.takeoff_time)}</p>
```

Replace line 479:

```jsx
              <p className="text-foreground">{formatTime(flight.landing_time)}</p>
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd frontend && npm run test:run -- src/pages/FlightDetailPage.test.jsx`
Expected: PASS (new test plus the existing ones; the existing save test still posts `purpose: 'Patrol'` with no takeoff_time).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/FlightDetailPage.jsx frontend/src/pages/FlightDetailPage.test.jsx
git commit -m "feat(flight-detail): show/edit flight times in the configured timezone"
```

---

### Task 7: Frontend — Settings page timezone dropdown

**Files:**
- Modify: `frontend/src/pages/SettingsPage.jsx` (import; Organization card ~line 723)
- Test: `frontend/src/pages/SettingsPage.test.jsx`

**Interfaces:**
- Consumes: `TIMEZONES` (Task 4); `display_timezone` in `ALLOWED_SETTING_KEYS` (Task 2).
- Produces: an admin dropdown whose value is included in the existing `PUT /api/settings/bulk` save.

- [ ] **Step 1: Write the failing test**

In `frontend/src/pages/SettingsPage.test.jsx`, add a test that loads settings (with `display_timezone`), changes it, saves, and asserts the bulk payload. Match the file's existing MSW/render setup; the assertion:

```js
  it('saves the selected display timezone in the bulk payload', async () => {
    let bulkBody = null
    server.use(
      http.get('/api/settings', () => HttpResponse.json([{ key: 'display_timezone', value: 'America/Chicago' }])),
      http.put('/api/settings/bulk', async ({ request }) => { bulkBody = await request.json(); return HttpResponse.json({ ok: true }) }),
    )
    const { user } = renderWithProviders(<SettingsPage />, { role: 'admin' })

    const select = await screen.findByLabelText('Time Zone')
    await user.selectOptions(select, 'America/Denver')
    await user.click(screen.getByRole('button', { name: 'Save Settings' }))

    await waitFor(() => expect(bulkBody).not.toBeNull())
    expect(bulkBody).toEqual(expect.arrayContaining([{ key: 'display_timezone', value: 'America/Denver' }]))
  })
```

(Import `screen`, `waitFor` from `@testing-library/react`, `http`/`HttpResponse` from `msw`, `server` from `@/test/server`, and `renderWithProviders` from `@/test/render` if not already imported.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:run -- src/pages/SettingsPage.test.jsx`
Expected: FAIL — no "Time Zone" control exists.

- [ ] **Step 3: Add `TIMEZONES` to the imports**

In `frontend/src/pages/SettingsPage.jsx`, add `TIMEZONES` to the `@/lib/utils` import (or add a new import line if utils is not yet imported there):

```js
import { TIMEZONES } from '@/lib/utils'
```

- [ ] **Step 4: Add the dropdown to the Organization card**

In the Organization card, immediately after `{field('Organization Name', 'org_name', 'text', 'Displayed on reports and exports')}` (around line 723), add:

```jsx
          <div>
            <label htmlFor="setting-display_timezone" className="block text-sm font-medium text-foreground mb-1">Time Zone</label>
            <p className="text-xs text-muted-foreground mb-1.5">All flight times display in this zone. Stored data stays in UTC.</p>
            <select
              id="setting-display_timezone"
              ref={el => { inputRefs.current['display_timezone'] = el }}
              key={`display_timezone-${settings.display_timezone === undefined ? 'loading' : 'loaded'}`}
              defaultValue={settings.display_timezone || 'America/Chicago'}
              className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              disabled={!isAdmin}
              onInput={() => setHasUnsavedChanges(true)}
            >
              {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
            </select>
          </div>
```

The existing `handleSave` gathers `inputRefs` via `gatherInputs()` and PUTs `/settings/bulk`, so no save-handler change is needed.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm run test:run -- src/pages/SettingsPage.test.jsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/SettingsPage.jsx frontend/src/pages/SettingsPage.test.jsx
git commit -m "feat(settings): admin Time Zone dropdown for display_timezone"
```

---

### Task 8: Frontend — Setup page timezone dropdown

**Files:**
- Modify: `frontend/src/pages/SetupPage.jsx` (form state; Step 1 Organization block)
- Test: `frontend/src/pages/SetupPage.test.jsx`

**Interfaces:**
- Consumes: `TIMEZONES` (Task 4); `POST /api/auth/setup` accepts `timezone` (Task 2).
- Produces: the setup POST body includes `timezone`, defaulting to `America/Chicago`.

- [ ] **Step 1: Write the failing test**

In `frontend/src/pages/SetupPage.test.jsx`, add a test asserting the setup POST includes `timezone`. Match the file's existing render/MSW setup; core assertion:

```js
  it('includes the selected timezone in the setup payload', async () => {
    let setupBody = null
    server.use(http.post('/api/auth/setup', async ({ request }) => {
      setupBody = await request.json()
      return HttpResponse.json({ token: 't', user: { id: 1, username: 'admin', role: 'admin' } })
    }))
    const { user } = renderWithProviders(<SetupPage />)

    await user.type(screen.getByLabelText('Your Name'), 'Admin User')
    await user.selectOptions(await screen.findByLabelText('Time Zone'), 'America/New_York')
    await user.click(screen.getByRole('button', { name: /Continue/ }))
    await user.type(screen.getByLabelText('Username'), 'admin')
    await user.type(screen.getByLabelText('Password'), 'AdminPassw0rd!!')
    await user.type(screen.getByLabelText('Confirm Password'), 'AdminPassw0rd!!')
    await user.click(screen.getByRole('button', { name: /Create Account/ }))

    await waitFor(() => expect(setupBody).not.toBeNull())
    expect(setupBody.timezone).toBe('America/New_York')
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:run -- src/pages/SetupPage.test.jsx`
Expected: FAIL — no "Time Zone" control, `timezone` absent from the body.

- [ ] **Step 3: Add timezone to the setup form state and import**

In `frontend/src/pages/SetupPage.jsx`, import `TIMEZONES`:

```js
import { TIMEZONES } from '@/lib/utils'
```

Add `timezone` to the initial `form` state:

```js
  const [form, setForm] = useState({
    display_name: '',
    org_name: '',
    email: '',
    username: '',
    password: '',
    password_confirm: '',
    timezone: 'America/Chicago',
  })
```

`handleSubmit` already sends `form` to `/auth/setup`, so `timezone` is included automatically.

- [ ] **Step 4: Add the dropdown to Step 1 (Organization)**

In the `step === 1` block, after the Organization Name field `<div>` (before the "Your Name" field), add:

```jsx
              <div>
                <label htmlFor="timezone" className="block text-sm font-medium mb-1">Time Zone</label>
                <select id="timezone"
                  value={form.timezone}
                  onChange={e => setForm({...form, timezone: e.target.value})}
                  className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-foreground"
                >
                  {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
                </select>
                <p className="text-xs text-muted-foreground mt-1">All flight times display in this zone. Stored data stays in UTC.</p>
              </div>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm run test:run -- src/pages/SetupPage.test.jsx`
Expected: PASS. If the existing setup test's field labels differ, align the new test's `getByLabelText` calls with the labels already used in the file.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/SetupPage.jsx frontend/src/pages/SetupPage.test.jsx
git commit -m "feat(setup): Time Zone dropdown captured during first-launch setup"
```

---

### Task 9: Full verification sweep

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -q`
Expected: PASS.

- [ ] **Step 2: Run the full frontend unit suite**

Run: `cd frontend && npm run test:run`
Expected: PASS.

- [ ] **Step 3: Manual end-to-end check (documented, not automated)**

Log into the running app, open a Skydio flight whose true takeoff was late morning Central, and confirm the takeoff time now reads local (roughly 5 hours earlier than before). Change the Settings Time Zone to another zone and confirm the same flight re-renders in that zone after reload. Export the flights CSV and confirm `Takeoff` is UTC and `Local Takeoff Time` matches the configured zone.

- [ ] **Step 4: Commit any test fixups made during the sweep**

```bash
git add -A
git commit -m "test: timezone sweep fixups"
```

---

## Self-Review

**Spec coverage:**
- Store UTC / serialize with `Z` -> Task 1.
- `display_timezone` setting, default America/Chicago, admin Settings + first-launch setup -> Tasks 2, 7, 8.
- Frontend UTC->zone display + bootstrap load -> Tasks 4, 5, 6.
- Manual-entry edit round-trip (local<->UTC) -> Tasks 1 (backend normalize) + 6 (frontend convert).
- Export flip to stored-UTC -> Task 3.
- No data migration -> confirmed in spec; no task, by design.
- Telemetry unchanged -> untouched.

**Placeholder scan:** none; every code step has concrete code. Component-test steps (Tasks 7, 8) include the core assertions and instruct matching the file's existing MSW/render harness for setup boilerplate.

**Type consistency:** `setDisplayTimezone` / `getDisplayTimezone` / `formatTime` / `utcIsoToZonedInput` / `zonedInputToUtcIso` / `TIMEZONES` are defined in Task 4 and consumed by the same names in Tasks 5, 6, 7, 8. Setting key `display_timezone` is consistent across backend (Tasks 2, 3) and frontend (Tasks 5, 7, 8). The `...Z` serialization (Task 1) is what the frontend `new Date(...)` parsing (Tasks 4, 6) relies on.
