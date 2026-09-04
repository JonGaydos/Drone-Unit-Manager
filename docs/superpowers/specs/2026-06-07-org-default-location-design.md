# Org Default Location — Design

Date: 2026-06-07
Project: Drone Unit Manager
Status: approved (build it). Admin input method = address search (geocode).

## Context

Weather and the flight radar (Airspace/ADS-B) each need a center lat/lon.
Today:
- **WeatherPage** starts with no location (`coords = {lat:'', lon:''}`); the
  user must enter coords / use geolocation / type an address every visit. A
  bare `/weather/briefing` 422s (requires `lat`/`lon`), so the dashboard weather
  tile stays empty.
- **AirspacePage** pre-populates from `adsb_default_lat/lon` then
  `weather_location_lat/lon` settings — but there is **no admin UI** to set
  those, so they are effectively unset.

Goal: one **organization default location** the admin sets once; Weather and the
flight radar both pre-populate from it. Falls back to the **White House**
(lat 38.8977, lon -77.0365) when unset.

## Components

### Settings keys (one source of truth)
Add three keys to `ALLOWED_SETTING_KEYS` **and** `PUBLIC_KEYS` (public so the
pages can read them without admin) in `routers/settings.py`:
- `org_default_lat` (string, e.g. "38.8977")
- `org_default_lon` (string, e.g. "-77.0365")
- `org_location_name` (string label, e.g. "White House, Washington D.C.")

These are not secrets. The existing `weather_location_*` / `adsb_default_*` keys
are left in place but no longer relied upon (Airspace switches to the org
default); not removed, to avoid touching unrelated settings.

### White House fallback constant (frontend)
A shared constant (new `frontend/src/lib/location.js`, or added to `lib/utils.js`):
```js
export const DEFAULT_ORG_LOCATION = { lat: 38.8977, lon: -77.0365, name: 'White House, Washington D.C.' }
// resolveOrgLocation(settingsArray) -> {lat:Number, lon:Number, name:String}
//   reads org_default_lat/lon/org_location_name; falls back to DEFAULT_ORG_LOCATION
//   when missing or unparseable.
```
Used by Settings, WeatherPage, AirspacePage, and the dashboard weather tile so
the fallback is identical everywhere.

### Geocode endpoint (backend)
New `routers/geocode.py`, registered in `main.py`. `GET /api/geocode?q=<address>`
(authenticated `CurrentUser`):
- Forward-geocode via Nominatim `https://nominatim.openstreetmap.org/search`,
  params `{q, format: "jsonv2", limit: 1, addressdetails: 0}`, header
  `User-Agent: "DroneUnitManager/1.0"`, timeout ~8s — mirroring the existing
  `sync_manager._reverse_geocode` pattern.
- Returns `{lat: float, lon: float, display_name: str}` from the first result.
- `404` if no match; `502` on upstream/network error (caught, logged). Never
  raises an unhandled 500.

### Settings UI — "Default Location" section (admin)
A new section in `SettingsPage.jsx`:
- Address text input + **Search** button -> `GET /api/geocode?q=`. On success,
  show the resolved place (display_name + lat/lon). On 404, toast "No match".
- **Save** persists `org_default_lat`, `org_default_lon`, `org_location_name`
  via the existing `PUT /settings/bulk`.
- Shows the current saved location (or "Defaults to the White House" when
  unset). Matches the existing settings section styling and save pattern.

### Consumers pre-populate from the org default
- **WeatherPage**: on mount, fetch `/settings`, `resolveOrgLocation()` -> set
  `coords` + `addressInput` to the name, and auto-`fetchBriefing(lat, lon)`. The
  user can still change location afterward (unchanged behavior).
- **AirspacePage**: change `applyDefaultLocation` to use `resolveOrgLocation()`
  (org default -> White House) instead of the `adsb_default`/`weather_location`
  chain. Still only applies when there is no saved/selected point.
- **DashboardPage weather tile**: it already fetches `/settings` (for the
  Locations tile). Use `resolveOrgLocation()` to call
  `/weather/briefing?lat=&lon=` so the tile populates, instead of the current
  param-less call that 422s.

## Data flow
Admin types address -> `/api/geocode` -> lat/lon/name -> Save to settings.
Weather / Airspace / dashboard read `/settings` on load -> `resolveOrgLocation`
-> center on it (or the White House) -> fetch briefing / aircraft.

## Error handling
- Geocode upstream failure -> 502, UI toasts "Lookup failed, enter coordinates
  manually" (Weather page still has manual entry + geolocation).
- Missing/garbage settings -> `resolveOrgLocation` returns the White House.
- No new failure mode for Weather/Airspace: they already handle a missing
  location; now they simply have a sensible default.

## Non-goals
- No removal/migration of the old `weather_location_*` / `adsb_default_*` keys.
- No map-click picker in Settings (address search only; the Airspace map already
  lets users click a point ad hoc).
- No reverse-geocode changes; no caching layer for geocode (admin-only,
  occasional use).

## Verification
- Backend: `py_compile` + `import app.main`; geocode route registered
  (`/api/geocode` in the OpenAPI/route list); a live Nominatim call for
  "White House" returns lat≈38.8977, lon≈-77.0365 (network-dependent manual
  check); `org_default_*` accepted by PUT/GET `/settings` (in ALLOWED + PUBLIC).
- Frontend: `npm run build` + `eslint` on changed files.
- Live: Settings -> search "White House" -> Save; reload Weather (briefing loads
  for D.C.), Airspace (map centers on D.C.), dashboard weather tile populates;
  with the setting cleared, all three still default to the White House.

## Files
- Backend: `routers/settings.py` (3 keys -> ALLOWED + PUBLIC), `routers/geocode.py`
  (new), `app/main.py` (register router).
- Frontend: `lib/location.js` (new constant + `resolveOrgLocation`),
  `pages/SettingsPage.jsx` (Default Location section), `pages/WeatherPage.jsx`
  (seed + auto-briefing), `pages/AirspacePage.jsx` (default via resolveOrgLocation),
  `pages/DashboardPage.jsx` (weather tile uses org default lat/lon).
