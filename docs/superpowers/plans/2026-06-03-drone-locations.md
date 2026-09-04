# Drone Location Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dashboard "Locations" tile showing each drone's current location (a pilot or an agency-defined place), settable inline by anyone.

**Architecture:** A drone's displayed location is the more recent of (a) an active equipment checkout to a pilot, or (b) a manual location set on the vehicle. Named places live in an admin-editable Setting (default North/Central/South). New nullable columns on `vehicles` hold the manual location; two new vehicle endpoints read and set it; the dashboard renders a tile with inline dropdowns.

**Tech Stack:** FastAPI + SQLAlchemy (SQLite), React 19 + Vite. No test framework — verification uses `py_compile`, `import app.main`, seeded in-memory SQLite smoke scripts, and `npm run build` / `eslint` (the project's established pattern).

**Branch:** Work on `feat/drone-locations` off `main`.

**Verification idiom (no pytest in this repo):** "test" steps create a throwaway smoke script under `C:/Users/jgayd/.claude/plans/` (NOT in the repo), run it with `backend/.venv/Scripts/python.exe` with `PYTHONPATH` set to `backend`, confirm the printed assertions, then delete it. Backend python is `D:/Claude Projects/Drone-Unit-Manager/backend/.venv/Scripts/python.exe`.

---

### Task 0: Branch

- [ ] **Step 1: Create the feature branch**

```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" checkout main
git -C "D:/Claude Projects/Drone-Unit-Manager" pull --ff-only
git -C "D:/Claude Projects/Drone-Unit-Manager" checkout -b feat/drone-locations
```

---

### Task 1: Vehicle manual-location columns + migration

**Files:**
- Modify: `backend/app/models/vehicle.py`
- Modify: `backend/app/services/migrations.py` (append tuples to the `migrations` list, ~line 131)

- [ ] **Step 1: Add the columns to the Vehicle model**

In `backend/app/models/vehicle.py`, add these four fields after `notes` (keep the existing `created_at`/`updated_at` exactly as they are — do NOT change those):

```python
    manual_location_place: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    manual_location_pilot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pilots.id"), nullable=True)
    location_set_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    location_set_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
```

(`String`, `ForeignKey`, `DateTime`, `Optional`, `datetime` are already imported in this file.)

- [ ] **Step 2: Add the migration tuples**

In `backend/app/services/migrations.py`, append to the `migrations` list (just before the closing `]` near line 131):

```python
        # Drone location tracking (manual location set)
        ("vehicles", "manual_location_place", "ALTER TABLE vehicles ADD COLUMN manual_location_place VARCHAR(100)"),
        ("vehicles", "manual_location_pilot_id", "ALTER TABLE vehicles ADD COLUMN manual_location_pilot_id INTEGER REFERENCES pilots(id)"),
        ("vehicles", "location_set_at", "ALTER TABLE vehicles ADD COLUMN location_set_at DATETIME"),
        ("vehicles", "location_set_by_id", "ALTER TABLE vehicles ADD COLUMN location_set_by_id INTEGER REFERENCES users(id)"),
```

All nullable, no `server_default` (per the 2026-06-03 login-500 lesson — Python/nullable only on existing tables).

- [ ] **Step 3: Compile + import**

Run:
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && .venv/Scripts/python.exe -m py_compile app/models/vehicle.py app/services/migrations.py && PYTHONPATH=. .venv/Scripts/python.exe -c "import app.main; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Verify the migration is idempotent on an old-schema vehicles table**

Create `C:/Users/jgayd/.claude/plans/smoke_loc_mig.py`:
```python
from sqlalchemy import create_engine, text, inspect
import app.services.migrations as m
eng = create_engine("sqlite:///:memory:")
with eng.begin() as c:
    c.execute(text("CREATE TABLE vehicles (id INTEGER PRIMARY KEY, serial_number VARCHAR, manufacturer VARCHAR, model VARCHAR, status VARCHAR)"))
insp = inspect(eng)
migs = [
    ("vehicles", "manual_location_place", "ALTER TABLE vehicles ADD COLUMN manual_location_place VARCHAR(100)"),
    ("vehicles", "manual_location_pilot_id", "ALTER TABLE vehicles ADD COLUMN manual_location_pilot_id INTEGER"),
    ("vehicles", "location_set_at", "ALTER TABLE vehicles ADD COLUMN location_set_at DATETIME"),
    ("vehicles", "location_set_by_id", "ALTER TABLE vehicles ADD COLUMN location_set_by_id INTEGER"),
]
with eng.connect() as conn:
    m._apply_column_migrations(conn, insp, migs)
    m._apply_column_migrations(conn, inspect(eng), migs)  # second run = no-op
cols = [c["name"] for c in inspect(eng).get_columns("vehicles")]
assert all(x in cols for x in ["manual_location_place","manual_location_pilot_id","location_set_at","location_set_by_id"]), cols
print("MIG_OK", cols)
```
Run:
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && PYTHONPATH=. .venv/Scripts/python.exe "C:/Users/jgayd/.claude/plans/smoke_loc_mig.py" && rm -f "C:/Users/jgayd/.claude/plans/smoke_loc_mig.py"
```
Expected: `MIG_OK [... includes the 4 columns ...]`

- [ ] **Step 5: Commit**

```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add backend/app/models/vehicle.py backend/app/services/migrations.py
git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(locations): add vehicle manual-location columns + migration"
```

---

### Task 2: Settings — register the named-places key

**Files:**
- Modify: `backend/app/routers/settings.py` (`ALLOWED_SETTING_KEYS`, `PUBLIC_KEYS`)

The dropdown is shown to all users on the dashboard, so the places list must be readable by non-admins → it goes in BOTH sets.

- [ ] **Step 1: Add `drone_location_places` to both key sets**

In `ALLOWED_SETTING_KEYS` add `"drone_location_places",`. In `PUBLIC_KEYS` add `"drone_location_places",`.

- [ ] **Step 2: Compile + import**

```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && .venv/Scripts/python.exe -m py_compile app/routers/settings.py && PYTHONPATH=. .venv/Scripts/python.exe -c "import app.main; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add backend/app/routers/settings.py
git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(locations): allow drone_location_places setting (public-readable)"
```

---

### Task 3: Location request schema

**Files:**
- Modify: `backend/app/schemas/vehicle.py`

- [ ] **Step 1: Add the request schema**

Append to `backend/app/schemas/vehicle.py` (the file already imports `BaseModel` from pydantic; if not, add `from pydantic import BaseModel`):

```python
class VehicleLocationUpdate(BaseModel):
    pilot_id: int | None = None
    place: str | None = None
```

- [ ] **Step 2: Compile**

```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && .venv/Scripts/python.exe -m py_compile app/schemas/vehicle.py && echo OK
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add backend/app/schemas/vehicle.py
git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(locations): add VehicleLocationUpdate schema"
```

---

### Task 4: Backend endpoints (GET /locations, PATCH /{id}/location)

**Files:**
- Modify: `backend/app/routers/vehicles.py`

**CRITICAL route ordering:** `GET /api/vehicles/locations` MUST be declared ABOVE the existing `GET /{vehicle_id}` route (currently ~line 42), or "locations" gets parsed as a `vehicle_id` and 422s. The PATCH route has an extra path segment so it does not collide with `PATCH /{vehicle_id}`.

- [ ] **Step 1: Add the import**

Add to the imports at the top of `vehicles.py`:
```python
from app.schemas.vehicle import VehicleCreate, VehicleUpdate, VehicleOut, VehicleLocationUpdate
```
(extend the existing `from app.schemas.vehicle import ...` line).

- [ ] **Step 2: Add the GET /locations route ABOVE `get_vehicle`**

Insert immediately before the existing `@router.get("/{vehicle_id}", ...)`:

```python
@router.get("/locations", responses=responses(401))
def vehicle_locations(db: DBSession, user: CurrentUser):
    """Current location per active drone: the more recent of an active checkout
    (with a pilot) or a manually-set location. Readable by any user."""
    from app.models.equipment_checkout import EquipmentCheckout
    from app.models.pilot import Pilot
    vehicles = db.query(Vehicle).filter(Vehicle.status != "retired").all()
    vids = [v.id for v in vehicles]
    active = {}
    if vids:
        rows = db.query(EquipmentCheckout).filter(
            EquipmentCheckout.entity_type == "vehicle",
            EquipmentCheckout.entity_id.in_(vids),
            EquipmentCheckout.checked_in_at.is_(None),
        ).all()
        for c in rows:
            cur = active.get(c.entity_id)
            if cur is None or c.checked_out_at > cur.checked_out_at:
                active[c.entity_id] = c
    pilot_ids = {c.checked_out_by_id for c in active.values()}
    pilot_ids |= {v.manual_location_pilot_id for v in vehicles if v.manual_location_pilot_id}
    names = {}
    if pilot_ids:
        names = {p.id: p.full_name for p in db.query(Pilot).filter(Pilot.id.in_(pilot_ids)).all()}
    result = []
    for v in vehicles:
        label = v.nickname or f"{v.manufacturer} {v.model}"
        co = active.get(v.id)
        co_time = co.checked_out_at if co else None
        man_time = v.location_set_at
        location_text, source = "Unknown", "unknown"
        manual_newer = man_time is not None and (co_time is None or man_time >= co_time)
        if manual_newer:
            source = "manual"
            if v.manual_location_pilot_id:
                location_text = f"with {names.get(v.manual_location_pilot_id, 'a pilot')}"
            elif v.manual_location_place:
                location_text = v.manual_location_place
        elif co is not None:
            source = "checkout"
            location_text = f"with {names.get(co.checked_out_by_id, 'a pilot')}"
        result.append({"vehicle_id": v.id, "label": label, "location_text": location_text, "source": source})
    return result
```

- [ ] **Step 3: Add the PATCH /{vehicle_id}/location route**

Add it after the existing `update_vehicle` (PATCH `/{vehicle_id}`) route:

```python
@router.patch("/{vehicle_id}/location", responses=responses(400, 401, 404))
def set_vehicle_location(vehicle_id: int, data: VehicleLocationUpdate, db: DBSession, user: CurrentUser):
    """Manually set a drone's location to a pilot OR a named place. Any user."""
    from datetime import datetime
    from app.services.audit import log_action
    from app.models.pilot import Pilot
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail=VEHICLE_NOT_FOUND)
    if (data.pilot_id is None) == (data.place is None):
        raise HTTPException(status_code=400, detail="Provide exactly one of pilot_id or place")
    if data.pilot_id is not None:
        if not db.query(Pilot).filter(Pilot.id == data.pilot_id).first():
            raise HTTPException(status_code=404, detail="Pilot not found")
        vehicle.manual_location_pilot_id = data.pilot_id
        vehicle.manual_location_place = None
        loc_label = names_or_id = f"pilot {data.pilot_id}"
    else:
        vehicle.manual_location_pilot_id = None
        vehicle.manual_location_place = data.place
        loc_label = data.place
    vehicle.location_set_at = datetime.utcnow()
    vehicle.location_set_by_id = user.id
    log_action(db, user.id, user.display_name, "update", "vehicle", vehicle.id,
               vehicle.nickname or f"{vehicle.manufacturer} {vehicle.model}",
               details=f"Set location: {loc_label}")
    db.commit()
    return {"ok": True}
```

- [ ] **Step 4: Compile + import**

```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && .venv/Scripts/python.exe -m py_compile app/routers/vehicles.py && PYTHONPATH=. .venv/Scripts/python.exe -c "import app.main; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add backend/app/routers/vehicles.py
git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(locations): GET /vehicles/locations + PATCH /vehicles/{id}/location"
```

---

### Task 5: Backend smoke test (newer-of rule + PATCH)

**Files:**
- Temp: `C:/Users/jgayd/.claude/plans/smoke_locations.py` (run, then delete; not in repo)

- [ ] **Step 1: Write the smoke script**

```python
import app.main  # populate metadata
from datetime import datetime, timedelta
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models.vehicle import Vehicle
from app.models.pilot import Pilot
from app.models.equipment_checkout import EquipmentCheckout
from app.routers.vehicles import vehicle_locations, set_vehicle_location
from app.schemas.vehicle import VehicleLocationUpdate

eng = create_engine("sqlite:///:memory:")
@event.listens_for(eng, "connect")
def _fk(dbapi, rec):
    cur = dbapi.cursor(); cur.execute("PRAGMA foreign_keys=ON"); cur.close()
Base.metadata.create_all(eng)
S = sessionmaker(bind=eng); db = S()

class U:  # stand-in for CurrentUser
    id = 1; display_name = "Tester"
p = Pilot(first_name="Jane", last_name="Doe", status="active"); db.add(p)
v = Vehicle(serial_number="SN1", manufacturer="Skydio", model="X10", status="active"); db.add(v)
db.commit()

# 1) no data -> Unknown
r = {x["vehicle_id"]: x for x in vehicle_locations(db, U)}
assert r[v.id]["location_text"] == "Unknown" and r[v.id]["source"] == "unknown", r[v.id]

# 2) active checkout -> with pilot
db.add(EquipmentCheckout(entity_type="vehicle", entity_id=v.id, checked_out_by_id=p.id,
                         checked_out_at=datetime.utcnow() - timedelta(hours=2)))
db.commit()
r = {x["vehicle_id"]: x for x in vehicle_locations(db, U)}
assert r[v.id]["source"] == "checkout" and "Jane Doe" in r[v.id]["location_text"], r[v.id]

# 3) manual set NEWER than checkout -> place wins
set_vehicle_location(v.id, VehicleLocationUpdate(place="Central"), db, U)
r = {x["vehicle_id"]: x for x in vehicle_locations(db, U)}
assert r[v.id]["source"] == "manual" and r[v.id]["location_text"] == "Central", r[v.id]

# 4) a NEWER checkout beats the older manual set
db.add(EquipmentCheckout(entity_type="vehicle", entity_id=v.id, checked_out_by_id=p.id,
                         checked_out_at=datetime.utcnow() + timedelta(hours=1)))
db.commit()
r = {x["vehicle_id"]: x for x in vehicle_locations(db, U)}
assert r[v.id]["source"] == "checkout", r[v.id]

# 5) validation: both/neither -> 400
import fastapi
for bad in (VehicleLocationUpdate(), VehicleLocationUpdate(pilot_id=p.id, place="X")):
    try:
        set_vehicle_location(v.id, bad, db, U); raise SystemExit("no 400")
    except fastapi.HTTPException as e:
        assert e.status_code == 400, e.status_code
print("LOCATIONS_SMOKE_OK")
```

- [ ] **Step 2: Run it**

```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && PYTHONPATH=. .venv/Scripts/python.exe "C:/Users/jgayd/.claude/plans/smoke_locations.py" && rm -f "C:/Users/jgayd/.claude/plans/smoke_locations.py"
```
Expected: `LOCATIONS_SMOKE_OK`

(No commit — the smoke script is throwaway and lives outside the repo.)

---

### Task 6: Dashboard Locations tile

**Files:**
- Modify: `frontend/src/pages/DashboardPage.jsx`

- [ ] **Step 1: Fetch locations, pilots, and places**

In the dashboard mount `useEffect` `Promise.all`, add three entries and destructure them:

```jsx
      api.get('/vehicles/locations').catch(() => []),
      api.get('/pilots').catch(() => []),
      api.get('/settings').catch(() => []),
```
Extend the `.then(([s, t, f, m, c, tp, tv, ac, w]) => {` destructure to `([s, t, f, m, c, tp, tv, ac, w, locs, pilotList, settingsList]) => {` and inside set new state:

```jsx
      setLocations(Array.isArray(locs) ? locs : [])
      setPilots(Array.isArray(pilotList) ? pilotList.filter(p => p.status === 'active') : [])
      const placesRow = Array.isArray(settingsList) ? settingsList.find(s => s.key === 'drone_location_places') : null
      let places = ['North', 'Central', 'South']
      if (placesRow?.value) { try { const j = JSON.parse(placesRow.value); if (Array.isArray(j) && j.length) places = j } catch { /* keep default */ } }
      setLocationPlaces(places)
```
Add the state declarations near the other `useState`s:
```jsx
  const [locations, setLocations] = useState([])
  const [pilots, setPilots] = useState([])
  const [locationPlaces, setLocationPlaces] = useState(['North', 'Central', 'South'])
```

- [ ] **Step 2: Add a `LocationsTile` component**

Add near the other tile components (after `ListTile`). It builds a dropdown whose option values encode type: `place:<name>` or `pilot:<id>`.

```jsx
function LocationsTile({ items, pilots, places, onChange, colSpan = 'lg:col-span-4' }) {
  return (
    <Tile className={`${colSpan} overflow-hidden`}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5"><Box className="w-4 h-4 text-primary" /> Locations</h3>
      </div>
      {items.length === 0 ? (
        <div className="p-4 text-center text-xs text-muted-foreground">No drones</div>
      ) : (
        <ul className="divide-y divide-border">
          {items.map(it => (
            <li key={it.vehicle_id} className="flex items-center justify-between gap-3 px-4 py-2.5">
              <div className="min-w-0">
                <p className="text-sm text-foreground truncate">{it.label}</p>
                <p className="text-xs text-muted-foreground truncate">{it.location_text}</p>
              </div>
              <select
                className="h-8 rounded-md border border-border bg-secondary px-2 text-xs text-foreground max-w-[10rem]"
                value=""
                onChange={(e) => { if (e.target.value) onChange(it.vehicle_id, e.target.value) }}
              >
                <option value="">Set location…</option>
                <optgroup label="Places">
                  {places.map(pl => <option key={`place:${pl}`} value={`place:${pl}`}>{pl}</option>)}
                </optgroup>
                <optgroup label="Pilots">
                  {pilots.map(p => <option key={`pilot:${p.id}`} value={`pilot:${p.id}`}>{p.first_name} {p.last_name}</option>)}
                </optgroup>
              </select>
            </li>
          ))}
        </ul>
      )}
    </Tile>
  )
}
```

- [ ] **Step 3: Add the change handler + render the tile**

Add a handler in the `DashboardPage` component body:
```jsx
  const handleSetLocation = async (vehicleId, encoded) => {
    const [type, val] = encoded.split(':')
    const body = type === 'pilot' ? { pilot_id: Number(val) } : { place: val }
    try {
      await api.patch(`/vehicles/${vehicleId}/location`, body)
      const locs = await api.get('/vehicles/locations').catch(() => locations)
      setLocations(Array.isArray(locs) ? locs : [])
    } catch (err) { toast.error(err.message) }
  }
```
(Import `useToast` from `@/contexts/ToastContext` and `const { toast } = useToast()` if the page doesn't already have it — check the top of the component; if `toast` is unavailable, add it.)

Render the tile in the grid (place it alongside the other tiles; pick a sensible `colSpan`):
```jsx
        <LocationsTile items={locations} pilots={pilots} places={locationPlaces} onChange={handleSetLocation} />
```

- [ ] **Step 4: Build + lint**

```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build && npx eslint src/pages/DashboardPage.jsx
```
Expected: build succeeds; no NEW eslint errors (pre-existing baseline only).

- [ ] **Step 5: Commit**

```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add frontend/src/pages/DashboardPage.jsx
git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(locations): dashboard Locations tile with inline set-location dropdown"
```

---

### Task 7: Settings — manage named places (admin)

**Files:**
- Modify: `frontend/src/pages/SettingsPage.jsx`

Mirror the existing `mission_purposes` add/remove list editor. Store as JSON under `drone_location_places`; default North/Central/South.

- [ ] **Step 1: Add local state + load**

Near the other `useState`s add:
```jsx
  const [dronePlaces, setDronePlaces] = useState(['North', 'Central', 'South'])
```
In the settings load `useEffect` (after the existing JSON parses), add:
```jsx
      if (map.drone_location_places) {
        try { const j = JSON.parse(map.drone_location_places); if (Array.isArray(j)) setDronePlaces(j) } catch { /* keep default */ }
      }
```

- [ ] **Step 2: Add the editor section (admin only) in the General tab body**

Insert a new card alongside the Mission Purposes section:
```jsx
      {isAdmin && (
        <div className="bg-card border border-border rounded-xl p-6">
          <h2 className="text-lg font-semibold text-foreground mb-1">Drone Locations</h2>
          <p className="text-xs text-muted-foreground mb-3">Named places shown in the dashboard location dropdown (pilots are always available too).</p>
          <div className="space-y-2 mb-3">
            {dronePlaces.map((pl, i) => (
              <div key={i} className="flex gap-2">
                <input
                  className="flex-1 px-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm"
                  value={pl}
                  onChange={(e) => setDronePlaces(dronePlaces.map((x, xi) => xi === i ? e.target.value : x))}
                />
                <button type="button" className="px-3 py-2 text-sm text-red-400 hover:bg-red-500/10 rounded-lg"
                  onClick={() => setDronePlaces(dronePlaces.filter((_, xi) => xi !== i))}>Remove</button>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <button type="button" className="px-3 py-2 text-sm bg-secondary border border-border rounded-lg text-foreground"
              onClick={() => setDronePlaces([...dronePlaces, ''])}>Add place</button>
            <button type="button" className="px-3 py-2 text-sm bg-primary text-primary-foreground rounded-lg"
              onClick={async () => {
                const cleaned = dronePlaces.map(s => s.trim()).filter(Boolean)
                try {
                  await api.put('/settings/bulk', [{ key: 'drone_location_places', value: JSON.stringify(cleaned) }])
                  setDronePlaces(cleaned)
                  toast.success('Locations saved')
                } catch (err) { toast.error(err.message) }
              }}>Save locations</button>
          </div>
        </div>
      )}
```
(`toast` is already available in this page via `useToast`; confirm and reuse it.)

- [ ] **Step 3: Build + lint**

```bash
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build && npx eslint src/pages/SettingsPage.jsx
```
Expected: build succeeds; no NEW eslint errors.

- [ ] **Step 4: Commit**

```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add frontend/src/pages/SettingsPage.jsx
git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(locations): admin-editable named places in Settings"
```

---

### Task 8: Final verification + live retest checklist

- [ ] **Step 1: Whole-app compile/build**

```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && PYTHONPATH=. .venv/Scripts/python.exe -c "import app.main; print('BACKEND_OK')"
cd "D:/Claude Projects/Drone-Unit-Manager/frontend" && npm run build
```
Expected: `BACKEND_OK` and a clean vite build.

- [ ] **Step 2: Live retest (after deploy, with a token)** — record results, do not skip:
  - Dashboard shows the Locations tile listing each active drone with "Unknown" (or current) location.
  - Set a drone to "Central" via the dropdown → row updates to "Central".
  - Set a drone to a pilot → row shows "with <pilot>".
  - Check a drone out to a pilot via Equipment Checkouts more recently than the manual set → tile flips to "with <pilot>" (newer wins); check it back in and set a manual place → place shows.
  - In Settings (as admin) add/remove a place and Save → it appears in the dropdown; defaults are North/Central/South when never set.
  - As a non-admin user, confirm the dropdown still lists places (PUBLIC_KEYS) and you can change a location (anyone can).

- [ ] **Step 3: Finish the branch** — use `superpowers:finishing-a-development-branch` (merge to main / PR per Jonathan's call; push only when he asks).

---

## Self-review (against the spec, Feature 2)

- Named places setting, default North/Central/South, admin-editable → Task 2 + Task 7. ✓
- Vehicle manual location columns (place OR pilot, set_at, set_by) → Task 1. ✓
- "Whichever is newer" rule (active checkout vs manual) → Task 4 GET + Task 5 smoke. ✓
- Dashboard Locations tile, one row per active drone, inline dropdown (pilots + places), anyone can change → Task 6. ✓
- `PATCH /vehicles/{id}/location` any user, audit-logged → Task 4. ✓
- Migration safety (nullable, no server_default) → Task 1. ✓
- Route-ordering pitfall (GET /locations before /{vehicle_id}) → called out in Task 4. ✓
- No placeholders; every step has exact code/commands. ✓
