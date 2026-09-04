# Per-sync status + Auto-Sync Interval descriptor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Auto-Sync Interval control a description and give each automatic sync (metadata, telemetry) its own status block, including a live "flights still missing telemetry" backfill count.

**Architecture:** Record a telemetry-run timestamp/result inside the shared `batch_sync_telemetry`, expose telemetry status + a live remaining-missing count from `GET /api/sync/status`, and split the single frontend status block into two presentational blocks placed under their respective interval dropdowns.

**Tech Stack:** FastAPI, SQLAlchemy (SQLite), Pydantic v2, React 17, Vite, Vitest, MSW, pytest.

## Global Constraints

- New settings written by the backend: `last_telemetry_sync_timestamp` (UTC ISO), `last_telemetry_sync_result` (JSON `{"synced": N}`). These are internal status rows, not user-editable settings (do NOT add them to the settings allowlists).
- `GET /api/sync/status` gains: `last_telemetry_sync`, `telemetry_sync_interval`, `last_telemetry_sync_result`, `telemetry_remaining` (live count of flights with `telemetry_synced = false` AND `external_id` not null). Existing metadata fields unchanged.
- The scheduled metadata auto-sync is metadata-only (no telemetry); the Auto-Sync Interval description must say so and point to Telemetry Auto-Sync.
- No new dependencies. No emojis, no em dashes; match existing code style.
- Sonar S2068: seed test credentials positionally (`_seed_setting(db, "skydio_api_token", "test-token")`); no credential-named literals/keys.
- Backend tests: `backend/.venv/Scripts/python.exe -m pytest <path> -v` (from repo root). Frontend: `cd frontend && npm run test:run -- <path>`.

---

### Task 1: Backend — record telemetry status and expose it in `/sync/status`

**Files:**
- Modify: `backend/app/services/sync_manager.py` (`batch_sync_telemetry`)
- Modify: `backend/app/routers/sync.py` (`SyncStatusResponse`, `sync_status`)
- Test: `backend/tests/test_per_sync_status.py` (create)

**Interfaces:**
- Produces: after a telemetry batch, settings `last_telemetry_sync_timestamp` and `last_telemetry_sync_result` exist. `GET /api/sync/status` returns `last_telemetry_sync`, `telemetry_sync_interval`, `last_telemetry_sync_result`, `telemetry_remaining`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_per_sync_status.py`:

```python
"""Per-sync status: batch records telemetry run; /sync/status exposes it."""
import httpx

from app.models.flight import Flight
from app.models.setting import Setting
from app.services.sync_manager import SyncManager


def _seed_setting(db, key, value):
    db.add(Setting(key=key, value=value))
    db.commit()


def _telemetry_handler(request):
    if "/telemetry" in str(request.url):
        return httpx.Response(200, json={"data": {"flight_telemetry": [
            {"timestamp_ms": 1000, "gps_latitude": 30.72, "gps_longitude": -86.10,
             "height_above_takeoff": 50.0, "battery_percentage": 90},
        ]}})
    return httpx.Response(200, json={})


def test_batch_records_last_telemetry_status(db, telemetry_db, mock_httpx):
    _seed_setting(db, "skydio_api_token", "test-token")
    _seed_setting(db, "skydio_token_id", "test-token-id")
    db.add(Flight(external_id="F1", api_provider="skydio", telemetry_synced=False))
    db.commit()

    mock_httpx(_telemetry_handler)
    SyncManager.batch_sync_telemetry(db, limit=10)

    db.expire_all()
    ts = db.query(Setting).filter(Setting.key == "last_telemetry_sync_timestamp").first()
    res = db.query(Setting).filter(Setting.key == "last_telemetry_sync_result").first()
    assert ts is not None and ts.value
    assert res is not None and '"synced": 1' in res.value


def test_status_returns_telemetry_fields_and_remaining(client, db, admin_headers):
    import json
    _seed_setting(db, "last_telemetry_sync_timestamp", "2026-07-11T20:00:00+00:00")
    _seed_setting(db, "telemetry_sync_interval", "30")
    _seed_setting(db, "last_telemetry_sync_result", json.dumps({"synced": 5}))
    # Two unsynced with external_id (counted) + one synced (excluded) + one without id (excluded).
    db.add(Flight(external_id="A", api_provider="skydio", telemetry_synced=False))
    db.add(Flight(external_id="B", api_provider="skydio", telemetry_synced=False))
    db.add(Flight(external_id="C", api_provider="skydio", telemetry_synced=True))
    db.add(Flight(external_id=None, api_provider="skydio", telemetry_synced=False))
    db.commit()

    resp = client.get("/api/sync/status", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_telemetry_sync"] == "2026-07-11T20:00:00+00:00"
    assert body["telemetry_sync_interval"] == "30"
    assert body["last_telemetry_sync_result"] == {"synced": 5}
    assert body["telemetry_remaining"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_per_sync_status.py -v`
Expected: FAIL — settings not written; status has no telemetry fields.

- [ ] **Step 3: Record telemetry status in `batch_sync_telemetry`**

In `backend/app/services/sync_manager.py`, in `SyncManager.batch_sync_telemetry`, locate the end of the method:

```python
        db.commit()
        return synced
```

Replace it with:

```python
        _set_setting(db, "last_telemetry_sync_timestamp", datetime.now(timezone.utc).isoformat())
        _set_setting(db, "last_telemetry_sync_result", json.dumps({"synced": synced}))
        db.commit()
        return synced
```

(`_set_setting`, `datetime`, `timezone`, and `json` are already imported in `sync_manager.py`.)

- [ ] **Step 4: Extend the status response and handler**

In `backend/app/routers/sync.py`, add fields to `SyncStatusResponse`:

```python
class SyncStatusResponse(BaseModel):
    last_sync: str | None = None
    sync_interval: str | None = None
    provider: str | None = None
    last_sync_result: dict | None = None
    last_telemetry_sync: str | None = None
    telemetry_sync_interval: str | None = None
    last_telemetry_sync_result: dict | None = None
    telemetry_remaining: int = 0
```

Replace the body of `sync_status` with (keeps the existing metadata logic, adds telemetry):

```python
def sync_status(
    db: DBSession,
    admin: AdminUser,
):
    from sqlalchemy import func
    from app.models.flight import Flight

    last_sync_setting = db.query(Setting).filter(Setting.key == "last_sync_timestamp").first()
    interval_setting = db.query(Setting).filter(Setting.key == "sync_interval").first()
    provider_setting = db.query(Setting).filter(Setting.key == "last_sync_provider").first()
    result_setting = db.query(Setting).filter(Setting.key == "last_sync_result").first()

    def _parse_result(setting):
        if setting and setting.value:
            try:
                parsed = json.loads(setting.value)
                if isinstance(parsed, dict):
                    return parsed
            except (ValueError, TypeError):
                return None
        return None

    tele_ts = db.query(Setting).filter(Setting.key == "last_telemetry_sync_timestamp").first()
    tele_interval = db.query(Setting).filter(Setting.key == "telemetry_sync_interval").first()
    tele_result = db.query(Setting).filter(Setting.key == "last_telemetry_sync_result").first()

    telemetry_remaining = db.query(func.count(Flight.id)).filter(
        Flight.telemetry_synced.is_(False),
        Flight.external_id.isnot(None),
    ).scalar() or 0

    return SyncStatusResponse(
        last_sync=last_sync_setting.value if last_sync_setting else None,
        sync_interval=interval_setting.value if interval_setting else None,
        provider=provider_setting.value if provider_setting else None,
        last_sync_result=_parse_result(result_setting),
        last_telemetry_sync=tele_ts.value if tele_ts else None,
        telemetry_sync_interval=tele_interval.value if tele_interval else None,
        last_telemetry_sync_result=_parse_result(tele_result),
        telemetry_remaining=telemetry_remaining,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_per_sync_status.py backend/tests/test_sync.py -v`
Expected: PASS (new + existing sync tests).

- [ ] **Step 6: Run the full backend suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/sync_manager.py backend/app/routers/sync.py backend/tests/test_per_sync_status.py
git commit -m "feat(sync): record telemetry run status and expose it in /sync/status"
```

---

### Task 2: Frontend — Auto-Sync Interval descriptor + per-sync status blocks

**Files:**
- Modify: `frontend/src/pages/IntegrationsPage.jsx`
- Test: `frontend/src/pages/IntegrationsPage.test.jsx`

**Interfaces:**
- Consumes: the telemetry fields from `GET /api/sync/status` (Task 1).
- Produces: two status blocks (metadata under Auto-Sync Interval, telemetry under Telemetry Auto-Sync) and a description under Auto-Sync Interval.

- [ ] **Step 1: Write the failing test**

In `frontend/src/pages/IntegrationsPage.test.jsx`, add a test inside `describe('IntegrationsPage', ...)`:

```js
  it('shows the auto-sync description and a telemetry status block with remaining count', async () => {
    mockMount({
      syncStatus: () => HttpResponse.json({
        provider: 'skydio', last_sync: '2026-07-11T20:00:00Z', sync_interval: '1440',
        last_telemetry_sync: '2026-07-11T20:30:00Z', telemetry_sync_interval: '30',
        last_telemetry_sync_result: { synced: 7 }, telemetry_remaining: 42,
      }),
    })
    const { user } = renderWithProviders(<IntegrationsPage />, { role: 'admin' })
    await screen.findByText('Skydio')
    await user.click(screen.getByText('Skydio'))

    // Auto-Sync Interval description present.
    expect(await screen.findByText(/pulls new flights, vehicles, batteries/i)).toBeInTheDocument()
    // Telemetry status block: its own "Last telemetry" label and the remaining count.
    expect(screen.getByText('Last telemetry')).toBeInTheDocument()
    expect(screen.getByText('42 flights')).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:run -- src/pages/IntegrationsPage.test.jsx`
Expected: FAIL — no description, no "Last telemetry" block.

- [ ] **Step 3: Generalize `SyncStatusBlock` into a presentational component**

In `frontend/src/pages/IntegrationsPage.jsx`, replace the entire `SyncStatusBlock` function (from `/** Persistent sync-status block: ... */` through its closing `}`) with:

```jsx
/** Presentational status block for one sync: state, last/next time, last-run, optional extra line. */
function SyncStatusBlock({ syncedLabel = 'Last synced', live = null, lastTime = null, intervalMin = 0, runSummary = null, runStatus = 'success', firstError = null, moreErrors = 0, extra = null }) {
  const nextSync = nextSyncLabel(lastTime, intervalMin)

  return (
    <div className="rounded-lg bg-secondary/40 border border-border p-3 space-y-1.5 text-xs">
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground w-24 shrink-0">State</span>
        {live ? (
          <span className="flex items-center gap-1.5 text-foreground">
            <Loader2 className="w-3 h-3 animate-spin" /> Syncing… ({live})
          </span>
        ) : (
          <span className="text-muted-foreground">Idle</span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span className="text-muted-foreground w-24 shrink-0">{syncedLabel}</span>
        {lastTime ? (
          <span className="text-foreground">
            {relativeTime(lastTime)} <span className="text-muted-foreground">({new Date(lastTime).toLocaleString()})</span>
          </span>
        ) : (
          <span className="text-muted-foreground">Never</span>
        )}
      </div>

      {nextSync && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-24 shrink-0">Next sync</span>
          <span className="text-foreground">{nextSync}</span>
        </div>
      )}

      {runSummary && (
        <div className="flex items-start gap-2">
          <span className="text-muted-foreground w-24 shrink-0">Last run</span>
          <div className="space-y-0.5">
            <span className="flex items-center gap-1.5 text-foreground">
              <span className={`w-2 h-2 rounded-full shrink-0 ${STATUS_DOT[runStatus] || 'bg-muted'}`} />
              {runSummary}
            </span>
            {firstError && (
              <span className="block text-red-400">
                {firstError}{moreErrors > 0 ? ` (+${moreErrors} more)` : ''}
              </span>
            )}
          </div>
        </div>
      )}

      {extra && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-24 shrink-0">{extra.label}</span>
          <span className="text-foreground">{extra.value}</span>
        </div>
      )}
    </div>
  )
}

/** Summarize a metadata sync-run object into {summary, status, firstError, moreErrors}. */
function summarizeMetaRun(run) {
  if (!run) return { summary: null, status: 'success', firstError: null, moreErrors: 0 }
  const status = run.status || (run.errors?.length ? 'partial' : 'success')
  const summary = [
    run.flights_new != null ? `${run.flights_new} flights` : null,
    run.vehicles_synced ? `${run.vehicles_synced} vehicles` : null,
    run.batteries_synced ? `${run.batteries_synced} batteries` : null,
    run.controllers_synced ? `${run.controllers_synced} controllers` : null,
    `${run.errors?.length || 0} errors`,
  ].filter(Boolean).join(', ')
  return {
    summary,
    status,
    firstError: run.errors?.length ? run.errors[0] : null,
    moreErrors: run.errors?.length ? run.errors.length - 1 : 0,
  }
}
```

- [ ] **Step 4: Render the metadata block + description under Auto-Sync Interval**

Replace the existing "Auto-Sync Interval" block:

```jsx
          {/* Auto-Sync Interval */}
          <div className="flex items-center gap-3 pt-2 border-t border-border">
            <label htmlFor="sync-interval" className="text-xs text-muted-foreground whitespace-nowrap">Auto-Sync Interval</label>
            <select
              id="sync-interval"
              value={syncInterval}
              onChange={async (e) => {
                const val = e.target.value
                setSyncInterval(val)
                try {
                  await api.put('/settings/bulk', [{ key: 'sync_interval', value: val }])
                  toast.success(val ? `Auto-sync set to every ${val} minutes` : 'Auto-sync disabled')
                } catch (err) { toast.error(err.message) }
              }}
              className="px-2 py-1 bg-secondary border border-border rounded-lg text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">Disabled</option>
              <option value="360">Every 6 hours</option>
              <option value="720">Every 12 hours</option>
              <option value="1440">Every 24 hours</option>
            </select>
            {syncStatus?.provider && (
              <span className="text-[10px] text-muted-foreground">{syncStatus.provider}</span>
            )}
          </div>
```

with (adds the description and the metadata status block, wrapping the row):

```jsx
          {/* Auto-Sync Interval */}
          <div className="pt-2 border-t border-border">
            <div className="flex items-center gap-3">
              <label htmlFor="sync-interval" className="text-xs text-muted-foreground whitespace-nowrap">Auto-Sync Interval</label>
              <select
                id="sync-interval"
                value={syncInterval}
                onChange={async (e) => {
                  const val = e.target.value
                  setSyncInterval(val)
                  try {
                    await api.put('/settings/bulk', [{ key: 'sync_interval', value: val }])
                    toast.success(val ? `Auto-sync set to every ${val} minutes` : 'Auto-sync disabled')
                  } catch (err) { toast.error(err.message) }
                }}
                className="px-2 py-1 bg-secondary border border-border rounded-lg text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">Disabled</option>
                <option value="360">Every 6 hours</option>
                <option value="720">Every 12 hours</option>
                <option value="1440">Every 24 hours</option>
              </select>
              {syncStatus?.provider && (
                <span className="text-[10px] text-muted-foreground">{syncStatus.provider}</span>
              )}
            </div>
            <p className="text-[10px] text-muted-foreground mt-1">Automatically pulls new flights, vehicles, batteries, and equipment from Skydio on this schedule. Telemetry is handled separately by Telemetry Auto-Sync below.</p>
            <div className="mt-2">
              <SyncStatusBlock
                syncedLabel="Last synced"
                live={syncType === 'full' ? 'full' : syncType === 'sync' ? 'incremental' : null}
                lastTime={syncStatus?.last_sync}
                intervalMin={Number(syncStatus?.sync_interval) || 0}
                runSummary={summarizeMetaRun(lastResult || syncStatus?.last_sync_result).summary}
                runStatus={summarizeMetaRun(lastResult || syncStatus?.last_sync_result).status}
                firstError={summarizeMetaRun(lastResult || syncStatus?.last_sync_result).firstError}
                moreErrors={summarizeMetaRun(lastResult || syncStatus?.last_sync_result).moreErrors}
              />
            </div>
          </div>
```

- [ ] **Step 5: Add the telemetry status block under Telemetry Auto-Sync**

In the existing "Telemetry Auto-Sync Interval" block, immediately after the description `<p>` (the one ending "...stops once every flight has telemetry.") and before that block's closing `</div>`, add:

```jsx
            <div className="mt-2">
              <SyncStatusBlock
                syncedLabel="Last telemetry"
                live={syncingTelemetry ? 'telemetry' : null}
                lastTime={syncStatus?.last_telemetry_sync}
                intervalMin={Number(syncStatus?.telemetry_sync_interval) || 0}
                runSummary={syncStatus?.last_telemetry_sync_result ? `${syncStatus.last_telemetry_sync_result.synced ?? 0} flights fetched` : null}
                extra={syncStatus?.telemetry_remaining != null ? { label: 'Missing', value: `${syncStatus.telemetry_remaining} flights` } : null}
              />
            </div>
```

- [ ] **Step 6: Remove the old single status block**

Delete the old bottom status render (the `{/* Sync status block */}` comment and the `<SyncStatusBlock syncStatus={syncStatus} syncType={syncType} syncingTelemetry={syncingTelemetry} lastResult={lastResult} />` element that followed the telemetry dropdown block). The two new blocks replace it.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd frontend && npm run test:run -- src/pages/IntegrationsPage.test.jsx`
Expected: PASS (new test + existing IntegrationsPage tests).

- [ ] **Step 8: Run the full frontend suite**

Run: `cd frontend && npm run test:run`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/IntegrationsPage.jsx frontend/src/pages/IntegrationsPage.test.jsx
git commit -m "feat(integrations): per-sync status blocks + auto-sync interval description"
```

---

### Task 3: Full verification sweep

**Files:** none (verification only)

- [ ] **Step 1: Full backend suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -q`
Expected: PASS.

- [ ] **Step 2: Full frontend suite**

Run: `cd frontend && npm run test:run`
Expected: PASS.

- [ ] **Step 3: Commit any sweep fixups**

```bash
git add -A
git commit -m "test: per-sync status sweep fixups"
```

---

## Self-Review

**Spec coverage:**
- Auto-Sync Interval description (metadata-only, points to telemetry) -> Task 2 Step 4.
- Telemetry status recorded on every batch run -> Task 1 Step 3.
- `/sync/status` telemetry fields + live remaining count -> Task 1 Step 4.
- Two per-sync status blocks under their controls -> Task 2 Steps 4-6.
- Backfill "flights still missing telemetry" count -> Task 2 Step 5 (`extra` line) fed by `telemetry_remaining`.

**Placeholder scan:** none; every step carries concrete code and commands.

**Type consistency:** `summarizeMetaRun(run)` returns `{summary, status, firstError, moreErrors}` and is consumed with those exact keys. `SyncStatusBlock` props (`syncedLabel`, `live`, `lastTime`, `intervalMin`, `runSummary`, `runStatus`, `firstError`, `moreErrors`, `extra`) match both call sites. Status fields (`last_telemetry_sync`, `telemetry_sync_interval`, `last_telemetry_sync_result`, `telemetry_remaining`) are identical across the backend response (Task 1) and the frontend reads (Task 2).
