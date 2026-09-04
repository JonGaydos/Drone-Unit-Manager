# Scheduled telemetry auto-sync — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-configurable background job that periodically fetches telemetry for up to 10 flights missing it, mirroring the existing Auto-Sync Interval control, and never contacts Skydio when nothing is missing.

**Architecture:** Relocate the existing telemetry-batch logic from the `sync.py` router into `sync_manager.py` so it is a shared service. Add a second APScheduler job driven by a new `telemetry_sync_interval` setting, with a pre-flight guard that returns before building Skydio credentials when no flight is missing telemetry. Add a matching dropdown to Settings -> Integrations.

**Tech Stack:** FastAPI, SQLAlchemy (SQLite), APScheduler, Pydantic v2, React 17, Vite, Vitest, MSW, pytest.

## Global Constraints

- One new setting: `telemetry_sync_interval` — minutes as a string, `""` = disabled. Default disabled. Admin-writable (`ALLOWED_SETTING_KEYS`) and public-readable (`PUBLIC_KEYS`).
- Batch size is fixed at 10, newest-first (`Flight.date.desc().nulls_last()`).
- The scheduled job must return WITHOUT building credentials or making any Skydio HTTP call when there are zero flights with `telemetry_synced = false` and `external_id` not null.
- Interval dropdown options: Disabled `""` / 30m `30` / 1h `60` / 2h `120` / 6h `360`.
- No new dependencies. No emojis, no em dashes; match existing code style.
- Telemetry storage, the chart, and the manual telemetry button are unchanged in behavior.
- Test-gotcha (scheduler): `app/services/scheduler.py` does `from app.database import SessionLocal`, binding the name in its own module. Conftest patches `app.database.SessionLocal`, which does NOT affect the scheduler's copy. Any test that calls a scheduler function which opens `SessionLocal()` MUST `monkeypatch.setattr("app.services.scheduler.SessionLocal", <TestingSessionLocal>)` first.
- Sonar-gotcha (S2068 hard-coded credentials): do NOT introduce string literals bound to credential-named identifiers (`*token*`, `*password*`, `*secret*`) or credential-named dict keys with inline values. For test credentials, seed settings positionally via a helper exactly like `backend/tests/test_sync.py` (`_seed_setting(db, "skydio_api_token", "test-token")`), and reuse `from tests.conftest import ADMIN_PASSWORD` for any password. These forms are already Sonar-clean in this repo.
- Backend tests: `backend/.venv/Scripts/python.exe -m pytest <path> -v` (from repo root).
- Frontend tests: `cd frontend && npm run test:run -- <path>`.

---

### Task 1: Relocate the telemetry-batch logic into `sync_manager`

**Files:**
- Modify: `backend/app/services/sync_manager.py` (add relocated functions + `SyncManager.batch_sync_telemetry`)
- Modify: `backend/app/routers/sync.py` (remove the three functions; call the relocated one)
- Test: `backend/tests/test_telemetry_batch.py` (create)

**Interfaces:**
- Produces: `SyncManager.batch_sync_telemetry(db, limit=10) -> int` in `sync_manager.py`, plus module-level `_parse_timestamp_ms(ts)` and `_store_telemetry_points(flight, telemetry_data, session_factory, point_model)`.
- The router endpoints `POST /api/sync/now` and `POST /api/sync/telemetry` call `SyncManager.batch_sync_telemetry(db, limit=10)` with identical behavior to before.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_telemetry_batch.py`:

```python
"""SyncManager.batch_sync_telemetry: fetch + store telemetry for unsynced flights."""
import httpx

from app.models.flight import Flight
from app.models.setting import Setting
from app.models.telemetry import TelemetryPoint
from app.services.sync_manager import SyncManager


def _seed_creds(db):
    db.add(Setting(key="skydio_api_token", value="test-token"))
    db.add(Setting(key="skydio_token_id", value="test-token-id"))
    db.commit()


def _telemetry_handler(request):
    if "/telemetry" in str(request.url):
        return httpx.Response(200, json={"data": {"flight_telemetry": [
            {"timestamp_ms": 1000, "gps_latitude": 30.72, "gps_longitude": -86.10,
             "height_above_takeoff": 50.0, "battery_percentage": 90},
            {"timestamp_ms": 2000, "gps_latitude": 30.73, "gps_longitude": -86.11,
             "height_above_takeoff": 55.0, "battery_percentage": 88},
        ]}})
    return httpx.Response(200, json={})


def test_batch_sync_fetches_and_marks_flight(db, telemetry_db, mock_httpx):
    _seed_creds(db)
    f = Flight(external_id="FLIGHT-1", api_provider="skydio", telemetry_synced=False)
    db.add(f)
    db.commit()
    db.refresh(f)

    mock_httpx(_telemetry_handler)
    synced = SyncManager.batch_sync_telemetry(db, limit=10)

    assert synced == 1
    db.expire_all()
    updated = db.query(Flight).filter(Flight.id == f.id).first()
    assert updated.telemetry_synced is True
    assert updated.has_telemetry is True
    points = telemetry_db.query(TelemetryPoint).filter(TelemetryPoint.flight_id == f.id).count()
    assert points == 2


def test_batch_sync_returns_zero_without_credentials(db, mock_httpx):
    f = Flight(external_id="FLIGHT-2", api_provider="skydio", telemetry_synced=False)
    db.add(f)
    db.commit()
    # No token seeded -> batch must no-op.
    assert SyncManager.batch_sync_telemetry(db, limit=10) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_telemetry_batch.py -v`
Expected: FAIL — `SyncManager` has no attribute `batch_sync_telemetry`.

- [ ] **Step 3: Add the relocated functions to `sync_manager.py`**

In `backend/app/services/sync_manager.py`, confirm the top imports include `from app.constants import API_TOKEN_NOT_CONFIGURED` and add `UTC_OFFSET` to that constants import. Add these module-level functions ABOVE the `class SyncManager` definition:

```python
def _parse_timestamp_ms(ts) -> int:
    """Parse a timestamp value (ISO string or epoch ms) to integer milliseconds."""
    if isinstance(ts, str):
        try:
            parsed = datetime.fromisoformat(ts.replace("Z", UTC_OFFSET))
            return int(parsed.timestamp() * 1000)
        except (ValueError, AttributeError):
            return 0
    elif isinstance(ts, (int, float)):
        return int(ts)
    return 0


def _store_telemetry_points(flight, telemetry_data: list, session_factory, point_model):
    """Store telemetry points in the telemetry DB and update flight max metrics."""
    tdb = session_factory()
    try:
        tdb.query(point_model).filter(point_model.flight_id == flight.id).delete()
        max_alt = 0
        max_speed = 0
        for point in telemetry_data:
            alt = point.get("altitude_m")
            speed = point.get("speed_mps")
            tp = point_model(
                flight_id=flight.id,
                timestamp_ms=_parse_timestamp_ms(point.get("timestamp_ms")),
                lat=point.get("lat"),
                lon=point.get("lon"),
                altitude_m=float(alt) if alt is not None else None,
                speed_mps=float(speed) if speed is not None else None,
                battery_pct=point.get("battery_pct"),
                heading_deg=point.get("heading_deg"),
            )
            tdb.add(tp)
            if alt is not None and float(alt) > max_alt:
                max_alt = float(alt)
            if speed is not None and float(speed) > max_speed:
                max_speed = float(speed)
        tdb.commit()
        if max_alt > 0:
            flight.max_altitude_m = max_alt
        if max_speed > 0:
            flight.max_speed_mps = max_speed
    finally:
        tdb.close()
```

Add this static method inside `class SyncManager` (near `sync_all`):

```python
    @staticmethod
    def batch_sync_telemetry(db: Session, limit: int = 10) -> int:
        """Fetch telemetry for up to `limit` flights without it. Returns count synced."""
        from app.models.telemetry import TelemetryPoint
        from app.database import TelemetrySessionLocal

        creds = _build_creds(db, "skydio")
        if not creds.api_token:
            return 0

        provider = get_provider("skydio")
        flights = db.query(Flight).filter(
            Flight.telemetry_synced.is_(False),
            Flight.external_id.isnot(None),
        ).order_by(Flight.date.desc().nulls_last()).limit(limit).all()

        synced = 0
        for flight in flights:
            try:
                telemetry_data = provider.get_flight_telemetry(creds, flight.external_id)
                if telemetry_data and len(telemetry_data) > 0:
                    _store_telemetry_points(flight, telemetry_data, TelemetrySessionLocal, TelemetryPoint)
                flight.telemetry_synced = True
                flight.has_telemetry = True
                synced += 1
            except Exception as exc:
                logger.warning("Telemetry sync failed for flight %s: %s", flight.external_id, exc)

        db.commit()
        return synced
```

(`_build_creds`, `get_provider`, `Flight`, `Session`, `logger`, and `datetime` are already imported in `sync_manager.py`. Verify `datetime` is imported as `from datetime import datetime, ...` — it is used elsewhere in the file.)

- [ ] **Step 4: Remove the old functions from `sync.py` and call the relocated one**

In `backend/app/routers/sync.py`:
- Delete the three functions `_parse_timestamp_ms` (lines ~57-68), `_store_telemetry_points` (~71-104), and `_batch_sync_telemetry` (~107-138).
- In `sync_now`, change `telemetry_result = _batch_sync_telemetry(db, limit=10)` to `telemetry_result = SyncManager.batch_sync_telemetry(db, limit=10)`.
- In `sync_telemetry_batch`, change `synced = _batch_sync_telemetry(db, limit=10)` to `synced = SyncManager.batch_sync_telemetry(db, limit=10)`.
- Do NOT remove `from app.constants import UTC_OFFSET` — it is still used elsewhere in `sync.py` (lines ~225, ~232). Remove any import that genuinely becomes unused after the deletions (check `Session` — keep it if still referenced by remaining functions; the linter/tests will confirm).

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_telemetry_batch.py backend/tests/test_sync.py -v`
Expected: PASS (new batch tests + existing sync endpoint tests).

- [ ] **Step 6: Run the full backend suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/sync_manager.py backend/app/routers/sync.py backend/tests/test_telemetry_batch.py
git commit -m "refactor(sync): move telemetry batch into sync_manager as a shared service"
```

---

### Task 2: Scheduled telemetry job + reschedule

**Files:**
- Modify: `backend/app/services/scheduler.py`
- Test: `backend/tests/test_telemetry_scheduler.py` (create)

**Interfaces:**
- Consumes: `SyncManager.batch_sync_telemetry` (Task 1).
- Produces: `TELEMETRY_SYNC_JOB_ID`, `_get_telemetry_sync_interval_minutes() -> int | None`, `_run_scheduled_telemetry_sync()`, `reschedule_telemetry_sync(interval_minutes: int | None)`; the telemetry job is registered in `start_scheduler` when the setting is configured.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_telemetry_scheduler.py`:

```python
"""Scheduled telemetry job: runs batch when flights are missing telemetry,
skips (no Skydio call) when none are, and reschedule adds/removes the job."""
import pytest
from apscheduler.schedulers.background import BackgroundScheduler

import app.services.scheduler as sched
from app.models.flight import Flight
from app.models.setting import Setting
from app.services.sync_manager import SyncManager


@pytest.fixture
def scheduler_db(_engines, monkeypatch):
    """Point the scheduler module's SessionLocal at the temp engine."""
    TestingSessionLocal, _ = _engines
    monkeypatch.setattr(sched, "SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def _seed_token(db):
    db.add(Setting(key="skydio_api_token", value="test-token"))
    db.commit()


def test_scheduled_telemetry_runs_batch_when_missing(db, scheduler_db, monkeypatch):
    _seed_token(db)
    db.add(Flight(external_id="F1", api_provider="skydio", telemetry_synced=False))
    db.commit()

    calls = []
    monkeypatch.setattr(SyncManager, "batch_sync_telemetry",
                        staticmethod(lambda session, limit=10: calls.append(limit) or 1))

    sched._run_scheduled_telemetry_sync()

    assert calls == [10]


def test_scheduled_telemetry_skips_when_none_missing(db, scheduler_db, monkeypatch):
    _seed_token(db)
    # No unsynced flights present.
    calls = []
    monkeypatch.setattr(SyncManager, "batch_sync_telemetry",
                        staticmethod(lambda session, limit=10: calls.append(limit) or 0))

    sched._run_scheduled_telemetry_sync()

    assert calls == []  # guard returned before touching the batch / Skydio


def test_scheduled_telemetry_skips_without_token(db, scheduler_db, monkeypatch):
    db.add(Flight(external_id="F2", api_provider="skydio", telemetry_synced=False))
    db.commit()
    calls = []
    monkeypatch.setattr(SyncManager, "batch_sync_telemetry",
                        staticmethod(lambda session, limit=10: calls.append(limit) or 0))

    sched._run_scheduled_telemetry_sync()

    assert calls == []  # no token -> no work


def test_reschedule_telemetry_adds_and_removes_job(monkeypatch):
    s = BackgroundScheduler()
    s.start()
    monkeypatch.setattr(sched, "_scheduler", s)
    try:
        sched.reschedule_telemetry_sync(30)
        assert s.get_job(sched.TELEMETRY_SYNC_JOB_ID) is not None
        sched.reschedule_telemetry_sync(None)
        assert s.get_job(sched.TELEMETRY_SYNC_JOB_ID) is None
    finally:
        s.shutdown(wait=False)


def test_get_telemetry_interval_reads_setting(db, scheduler_db):
    db.add(Setting(key="telemetry_sync_interval", value="60"))
    db.commit()
    assert sched._get_telemetry_sync_interval_minutes() == 60


def test_get_telemetry_interval_none_when_empty(db, scheduler_db):
    db.add(Setting(key="telemetry_sync_interval", value=""))
    db.commit()
    assert sched._get_telemetry_sync_interval_minutes() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_telemetry_scheduler.py -v`
Expected: FAIL — scheduler has no `_run_scheduled_telemetry_sync` / `reschedule_telemetry_sync` / `_get_telemetry_sync_interval_minutes` / `TELEMETRY_SYNC_JOB_ID`.

- [ ] **Step 3: Add the job id and interval reader**

In `backend/app/services/scheduler.py`, add next to the existing job ids (after `BACKUP_JOB_ID = "daily_backup"`):

```python
TELEMETRY_SYNC_JOB_ID = "skydio_telemetry_sync"
```

Add this function next to `_get_sync_interval_minutes` (mirrors it):

```python
def _get_telemetry_sync_interval_minutes() -> int | None:
    """Read the telemetry sync interval from the database settings."""
    db = SessionLocal()
    try:
        setting = db.query(Setting).filter(Setting.key == "telemetry_sync_interval").first()
        if setting and setting.value:
            try:
                minutes = int(setting.value)
                if minutes > 0:
                    return minutes
            except ValueError:
                logger.warning("Invalid telemetry_sync_interval setting: %s", setting.value)
        return None
    except Exception:
        return None
    finally:
        db.close()
```

- [ ] **Step 4: Add the scheduled job runner**

Add next to `_run_scheduled_sync`:

```python
def _run_scheduled_telemetry_sync():
    """Fetch telemetry for a batch of flights missing it (scheduled).

    Returns before building Skydio credentials when no flight is missing
    telemetry, so a caught-up fleet never triggers an API call.
    """
    db = SessionLocal()
    try:
        token_setting = db.query(Setting).filter(Setting.key == "skydio_api_token").first()
        if not token_setting or not token_setting.value:
            logger.debug("Scheduled telemetry sync skipped: no API token configured")
            return

        from app.models.flight import Flight
        missing = db.query(Flight).filter(
            Flight.telemetry_synced.is_(False),
            Flight.external_id.isnot(None),
        ).count()
        if missing == 0:
            logger.debug("Scheduled telemetry sync: no telemetry missing, skipping")
            return

        synced = SyncManager.batch_sync_telemetry(db, limit=10)
        logger.info("Scheduled telemetry sync: fetched telemetry for %d flights (%d were missing)",
                    synced, missing)
    except Exception:
        logger.exception("Scheduled telemetry sync failed")
    finally:
        db.close()
```

- [ ] **Step 5: Add the reschedule function**

Add next to `reschedule_sync`:

```python
def reschedule_telemetry_sync(interval_minutes: int | None):
    """Update the telemetry sync schedule (call after settings change)."""
    global _scheduler

    if _scheduler is None:
        return

    try:
        _scheduler.remove_job(TELEMETRY_SYNC_JOB_ID)
    except Exception:
        pass

    if interval_minutes and interval_minutes > 0:
        _scheduler.add_job(
            _run_scheduled_telemetry_sync,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=TELEMETRY_SYNC_JOB_ID,
            replace_existing=True,
            max_instances=1,
        )
        logger.info("Telemetry sync rescheduled to every %d minutes", interval_minutes)
    else:
        logger.info("Telemetry sync schedule removed (no interval)")
```

- [ ] **Step 6: Register the job at startup**

In `start_scheduler`, immediately after the `if interval_minutes:` / `else:` block that adds the main sync job (right before the `# Always run digest check every 30 minutes` comment), add:

```python
    telemetry_interval = _get_telemetry_sync_interval_minutes()
    if telemetry_interval:
        _scheduler.add_job(
            _run_scheduled_telemetry_sync,
            trigger=IntervalTrigger(minutes=telemetry_interval),
            id=TELEMETRY_SYNC_JOB_ID,
            replace_existing=True,
            max_instances=1,
        )
        logger.info("Telemetry sync scheduler started with %d minute interval", telemetry_interval)
    else:
        logger.info("Telemetry sync scheduler idle (no interval configured)")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_telemetry_scheduler.py -v`
Expected: PASS (all six).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/scheduler.py backend/tests/test_telemetry_scheduler.py
git commit -m "feat(scheduler): periodic telemetry sync job with skip-when-none guard"
```

---

### Task 3: Setting allowlist + bulk-save reschedule wiring

**Files:**
- Modify: `backend/app/routers/settings.py`
- Test: `backend/tests/test_telemetry_sync_setting.py` (create)

**Interfaces:**
- Consumes: `reschedule_telemetry_sync` (Task 2).
- Produces: `telemetry_sync_interval` is admin-writable and public-readable; `PUT /settings/bulk` with that key reschedules the telemetry job.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_telemetry_sync_setting.py`:

```python
"""telemetry_sync_interval: allowlist, public read, and bulk-save reschedule."""
from app.models.setting import Setting


def test_pilot_can_read_telemetry_interval(client, db, pilot_headers):
    db.add(Setting(key="telemetry_sync_interval", value="30"))
    db.commit()
    resp = client.get("/api/settings/telemetry_sync_interval", headers=pilot_headers)
    assert resp.status_code == 200
    assert resp.json()["value"] == "30"


def test_admin_can_write_telemetry_interval(client, db, admin_headers):
    resp = client.put("/api/settings",
                      json={"key": "telemetry_sync_interval", "value": "60"},
                      headers=admin_headers)
    assert resp.status_code == 200
    assert db.query(Setting).filter(Setting.key == "telemetry_sync_interval").first().value == "60"


def test_bulk_save_reschedules_telemetry(client, db, admin_headers, monkeypatch):
    calls = []
    import app.services.scheduler as sched
    monkeypatch.setattr(sched, "reschedule_telemetry_sync", lambda minutes: calls.append(minutes))

    resp = client.put("/api/settings/bulk",
                      json=[{"key": "telemetry_sync_interval", "value": "30"}],
                      headers=admin_headers)
    assert resp.status_code == 200
    assert calls == [30]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_telemetry_sync_setting.py -v`
Expected: FAIL — key not allowed/public; no reschedule call.

- [ ] **Step 3: Add the key to the allowlists**

In `backend/app/routers/settings.py`, add `"telemetry_sync_interval"` to `ALLOWED_SETTING_KEYS` (near `"sync_interval"`) and to `PUBLIC_KEYS`:

```python
# in ALLOWED_SETTING_KEYS { ... }
    "sync_interval", "telemetry_sync_interval", "sidebar_config", ...
```

```python
# in PUBLIC_KEYS { ... }
    "sidebar_config", "sidebar_show_groups", "telemetry_sync_interval",
```

- [ ] **Step 4: Reschedule the telemetry job on bulk save**

In `set_settings_bulk`, after the existing `sync_interval` reschedule block (the `if any(item.key == "sync_interval" ...)` block), add:

```python
    # Reschedule telemetry job if its interval changed
    if any(item.key == "telemetry_sync_interval" for item in data):
        from app.services.scheduler import reschedule_telemetry_sync
        telemetry_minutes = None
        for item in data:
            if item.key == "telemetry_sync_interval" and item.value:
                try:
                    telemetry_minutes = int(item.value)
                except ValueError:
                    pass
        reschedule_telemetry_sync(telemetry_minutes)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_telemetry_sync_setting.py -v`
Expected: PASS (all three).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/settings.py backend/tests/test_telemetry_sync_setting.py
git commit -m "feat(settings): allow telemetry_sync_interval and reschedule on save"
```

---

### Task 4: Settings -> Integrations telemetry dropdown

**Files:**
- Modify: `frontend/src/pages/IntegrationsPage.jsx`
- Test: `frontend/src/pages/IntegrationsPage.test.jsx`

**Interfaces:**
- Consumes: `telemetry_sync_interval` (Task 3) via `PUT /settings/bulk`.
- Produces: a "Telemetry Auto-Sync" dropdown + description in the Skydio provider card.

- [ ] **Step 1: Write the failing test**

In `frontend/src/pages/IntegrationsPage.test.jsx`, add a test inside the `describe('IntegrationsPage', ...)` block:

```js
  it('saves the telemetry auto-sync interval via PUT /settings/bulk', async () => {
    let body = null
    mockMount()
    server.use(
      http.put('/api/settings/bulk', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ok: true })
      }),
    )
    const { user } = renderWithProviders(<IntegrationsPage />, { role: 'admin' })
    await screen.findByText('Skydio')
    await user.click(screen.getByText('Skydio'))

    const select = await screen.findByLabelText('Telemetry Auto-Sync')
    await user.selectOptions(select, '30')

    await screen.findByText('Skydio')
    expect(Array.isArray(body)).toBe(true)
    expect(body).toEqual([{ key: 'telemetry_sync_interval', value: '30' }])
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:run -- src/pages/IntegrationsPage.test.jsx`
Expected: FAIL — no "Telemetry Auto-Sync" control.

- [ ] **Step 3: Add the state and load it**

In `frontend/src/pages/IntegrationsPage.jsx`, inside `ProviderCard`, add the state next to `syncInterval`:

```js
  const [syncInterval, setSyncInterval] = useState('')
  const [telemetrySyncInterval, setTelemetrySyncInterval] = useState('')
```

In the `useEffect` that loads settings, after `if (interval) setSyncInterval(interval.value || '')`, add:

```js
      const tInterval = settings.find(s => s.key === 'telemetry_sync_interval')
      if (tInterval) setTelemetrySyncInterval(tInterval.value || '')
```

- [ ] **Step 4: Add the dropdown and description**

Immediately after the existing "Auto-Sync Interval" block (the `<div className="flex items-center gap-3 pt-2 border-t border-border">...</div>` that ends just before the `{/* Sync status block */}` comment), add:

```jsx
          {/* Telemetry Auto-Sync Interval */}
          <div className="pt-2 border-t border-border">
            <div className="flex items-center gap-3">
              <label htmlFor="telemetry-sync-interval" className="text-xs text-muted-foreground whitespace-nowrap">Telemetry Auto-Sync</label>
              <select
                id="telemetry-sync-interval"
                value={telemetrySyncInterval}
                onChange={async (e) => {
                  const val = e.target.value
                  setTelemetrySyncInterval(val)
                  try {
                    await api.put('/settings/bulk', [{ key: 'telemetry_sync_interval', value: val }])
                    toast.success(val ? `Telemetry auto-sync set to every ${val} minutes` : 'Telemetry auto-sync disabled')
                  } catch (err) { toast.error(err.message) }
                }}
                className="px-2 py-1 bg-secondary border border-border rounded-lg text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">Disabled</option>
                <option value="30">Every 30 minutes</option>
                <option value="60">Every hour</option>
                <option value="120">Every 2 hours</option>
                <option value="360">Every 6 hours</option>
              </select>
            </div>
            <p className="text-[10px] text-muted-foreground mt-1">Fetches telemetry for up to 10 flights that are missing it each run, newest first. Only contacts Skydio when flights are actually missing telemetry, and stops once every flight has telemetry.</p>
          </div>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm run test:run -- src/pages/IntegrationsPage.test.jsx`
Expected: PASS (new test + existing IntegrationsPage tests).

- [ ] **Step 6: Run the full frontend suite**

Run: `cd frontend && npm run test:run`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/IntegrationsPage.jsx frontend/src/pages/IntegrationsPage.test.jsx
git commit -m "feat(integrations): telemetry auto-sync interval dropdown"
```

---

### Task 5: Full verification sweep

**Files:** none (verification only)

- [ ] **Step 1: Full backend suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -q`
Expected: PASS.

- [ ] **Step 2: Full frontend suite**

Run: `cd frontend && npm run test:run`
Expected: PASS.

- [ ] **Step 3: Import smoke check (scheduler wiring loads)**

Run: `backend/.venv/Scripts/python.exe -c "import app.services.scheduler as s; assert hasattr(s, 'reschedule_telemetry_sync') and hasattr(s, '_run_scheduled_telemetry_sync') and s.TELEMETRY_SYNC_JOB_ID == 'skydio_telemetry_sync'; from app.services.sync_manager import SyncManager; assert hasattr(SyncManager, 'batch_sync_telemetry'); print('scheduler + sync_manager wiring OK')"`
Expected: prints `scheduler + sync_manager wiring OK`.

- [ ] **Step 4: Commit any sweep fixups**

```bash
git add -A
git commit -m "test: telemetry sync sweep fixups"
```

---

## Self-Review

**Spec coverage:**
- One setting `telemetry_sync_interval`, admin-writable + public -> Task 3.
- Scheduled job, batch of 10 newest-first -> Task 2 (+ relocated batch in Task 1).
- Skip-before-Skydio guard when nothing missing -> Task 2 (`test_scheduled_telemetry_skips_when_none_missing`).
- Reschedule on save + startup registration -> Tasks 2, 3.
- Shared batch used by scheduler and router -> Task 1 relocation.
- Frontend dropdown + description -> Task 4.
- Interval options Disabled/30/60/120/360 -> Task 4.

**Placeholder scan:** none; every step carries concrete code and commands.

**Type consistency:** `SyncManager.batch_sync_telemetry(db, limit)` defined in Task 1 is called by the scheduler (Task 2) and router (Task 1) with the same signature. `reschedule_telemetry_sync(minutes)` defined in Task 2 is called by settings bulk-save (Task 3) and tested with `30`/`None`. `TELEMETRY_SYNC_JOB_ID` and `_get_telemetry_sync_interval_minutes` are consistent across Task 2 definition and its tests. Setting key `telemetry_sync_interval` is identical across backend (Tasks 2, 3) and frontend (Task 4).
