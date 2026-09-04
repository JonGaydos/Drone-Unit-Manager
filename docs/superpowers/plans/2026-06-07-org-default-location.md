# Org Default Location — Implementation Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** One admin-set organization default location (via address geocode) that Weather, the Airspace/flight-radar, and the dashboard weather tile all pre-populate from, falling back to the White House (lat 38.8977, lon -77.0365) when unset.

**Branch:** `feat/org-default-location`.
**Backend python:** `D:/Claude Projects/Drone-Unit-Manager/backend/.venv/Scripts/python.exe`, `PYTHONPATH=.` from `backend`. **Frontend:** `cd frontend && npm run build`, `npx eslint <files>`.

---

### Task 1: Backend — settings keys
**File:** `backend/app/routers/settings.py`.
- [ ] Add `org_default_lat`, `org_default_lon`, `org_location_name` to `ALLOWED_SETTING_KEYS` AND to the public set (`PUBLIC_KEYS` or equivalent that the unauthenticated/any-user `/settings` read returns — find the exact name). They are NOT secrets (do not add to SECRET_KEYS).
- [ ] py_compile.

### Task 2: Backend — geocode endpoint
**File:** new `backend/app/routers/geocode.py`; register in `backend/app/main.py`.
- [ ] Mirror `services/sync_manager.py:_reverse_geocode` for the HTTP pattern (httpx, `User-Agent: "DroneUnitManager/1.0"`, timeout ~8s).
```python
from fastapi import APIRouter, HTTPException, Query
from typing import Annotated
from app.deps import CurrentUser   # match how other routers import the auth dep
import httpx, logging
router = APIRouter(prefix="/api/geocode", tags=["geocode"])
logger = logging.getLogger(__name__)

@router.get("")
def geocode(q: Annotated[str, Query(min_length=2, max_length=200)], user: CurrentUser):
    try:
        resp = httpx.get("https://nominatim.openstreetmap.org/search",
                         params={"q": q, "format": "jsonv2", "limit": 1, "addressdetails": 0},
                         headers={"User-Agent": "DroneUnitManager/1.0"}, timeout=8.0)
        resp.raise_for_status()
        results = resp.json()
    except Exception as e:
        logger.warning("Geocode lookup failed for %r: %s", q, e)
        raise HTTPException(status_code=502, detail="Geocoding service unavailable")
    if not results:
        raise HTTPException(status_code=404, detail="No match for that address")
    r = results[0]
    return {"lat": float(r["lat"]), "lon": float(r["lon"]), "display_name": r.get("display_name", q)}
```
- [ ] VERIFY the `CurrentUser` dependency import path + the router-registration line by reading an existing simple router (e.g. `routers/adsb.py`) and `main.py`'s `include_router` calls; match them exactly (prefix may be set at include time instead — follow the local convention).
- [ ] Register the router in main.py next to the other `include_router` calls.
- [ ] py_compile + `import app.main` (IMPORT_OK) + confirm `/api/geocode` appears in `app.routes`.

### Task 3: Frontend — shared location helper
**File:** new `frontend/src/lib/location.js`.
```js
export const DEFAULT_ORG_LOCATION = { lat: 38.8977, lon: -77.0365, name: 'White House, Washington D.C.' }

// settings: array of {key, value} from GET /settings
export function resolveOrgLocation(settings) {
  const find = (k) => settings?.find(s => s.key === k)?.value
  const lat = Number.parseFloat(find('org_default_lat'))
  const lon = Number.parseFloat(find('org_default_lon'))
  const name = find('org_location_name')
  if (Number.isFinite(lat) && Number.isFinite(lon)) return { lat, lon, name: name || `${lat}, ${lon}` }
  return { ...DEFAULT_ORG_LOCATION }
}
```

### Task 4: Frontend — Settings "Default Location" section
**File:** `frontend/src/pages/SettingsPage.jsx`.
- [ ] Add a new card/section "Default Location" (match existing section markup). State: `addressQuery`, `geoResult` ({lat,lon,display_name}|null), `geoLoading`. Show the current saved value from settings (`org_location_name` + lat/lon) or "Defaults to the White House" when unset.
- [ ] **Search** button -> `api.get('/geocode?q=' + encodeURIComponent(addressQuery))`; on success set `geoResult` and show it; on error toast (404 -> "No match"; else "Lookup failed").
- [ ] **Save** -> `api.put('/settings/bulk', [{key:'org_default_lat',value:String(geoResult.lat)},{key:'org_default_lon',value:String(geoResult.lon)},{key:'org_location_name',value:geoResult.display_name}])`; toast success; refresh local settings. Use the page's existing toast + settings-refresh pattern (inspect how other sections save).
- [ ] Place it near the other org/branding settings. Admin-only section if the page gates by role (follow existing pattern; the keys are public-read but only admins should write — the bulk PUT is already admin-gated server-side).

### Task 5: Frontend — Weather pre-populates
**File:** `frontend/src/pages/WeatherPage.jsx`.
- [ ] On mount (new effect), fetch `/settings`, `resolveOrgLocation(settings)`, set `coords` to the resolved lat/lon (as strings, matching current state shape), set `addressInput` to the name, and call `fetchBriefing(lat, lon)` so the briefing loads immediately. Guard so it only auto-loads once on mount and does not clobber a user who has already entered coords. Keep all existing manual-entry / geolocation behavior.

### Task 6: Frontend — Airspace default via org location
**File:** `frontend/src/pages/AirspacePage.jsx` (`applyDefaultLocation`, ~117-123).
- [ ] Replace the `adsb_default_lat || weather_location_lat` chain with `const { lat, lon } = resolveOrgLocation(settings)` and `setMapCenter([lat, lon])`. Import `resolveOrgLocation`. Keep the "only if no saved/selected point" guard.

### Task 7: Frontend — Dashboard weather tile
**File:** `frontend/src/pages/DashboardPage.jsx`.
- [ ] Find the `/weather/briefing` fetch (currently param-less -> 422). It already fetches `/settings` (Locations tile). Use `resolveOrgLocation(settings)` to call `/weather/briefing?lat=${lat}&lon=${lon}`. Keep the existing `.catch(()=>null)` so a weather outage never breaks the dashboard. (Mind fetch ordering: ensure settings are available before building the briefing URL; if the dashboard fetches in parallel, fetch settings first or compute the URL after settings resolve.)

### Task 8: Verify
- [ ] Backend: py_compile changed/new files; `import app.main` IMPORT_OK; `/api/geocode` route present; quick live check (network) `GET https://nominatim.openstreetmap.org/search?q=White House&format=jsonv2&limit=1` returns lat≈38.8977 (sanity that the upstream + parsing shape is right) — OR call the running app's `/api/geocode` if convenient. Do NOT block on network; note if unreachable.
- [ ] Frontend: `npm run build` succeeds; `eslint` on the 5 changed/new files — no NEW errors vs baseline.
- [ ] Commit in logical groups (backend; frontend helper+settings; frontend consumers). Do NOT push.

---

## Self-review (against spec)
- 3 public settings keys -> Task 1. ✓
- Geocode endpoint (404/502, Nominatim, auth) -> Task 2. ✓
- Shared White-House fallback helper -> Task 3, used in Tasks 4-7. ✓
- Settings address-search section -> Task 4. ✓
- Weather + Airspace + dashboard pre-populate -> Tasks 5-7. ✓
- Old keys untouched -> by omission. ✓
- Risk: dashboard fetch ordering (settings before briefing URL) -> flagged in Task 7.
