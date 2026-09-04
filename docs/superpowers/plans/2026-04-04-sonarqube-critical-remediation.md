# SonarQube Critical Issue Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 17 SonarQube CRITICAL/MAJOR issues (excluding S6774 component-size) to reduce the issue count from 376 toward ~360, eliminating all genuinely actionable findings.

**Architecture:** Extract helpers from high-complexity functions, replace if/elif chains with dispatch dicts, reduce nesting in JSX. All changes are refactors — no new features, no API changes, no behavior changes.

**Tech Stack:** Python (FastAPI), JavaScript (React 19), Vite

---

## Files to Modify

| # | File | Tasks | What Changes |
|---|---|---|---|
| 1 | `backend/app/routers/sync.py` | Task 1 | Extract field-mapping dict in `_apply_enrichment_detail` |
| 2 | `backend/app/routers/reports.py` | Task 2 | Replace if/elif chain with dispatch dict in `_generate_chart` |
| 3 | `backend/app/routers/export.py` | Task 3 | Extract `.xlsx` constant |
| 4 | `backend/app/integrations/skydio.py` | Task 4 | Extract field-mapping dict in `_map_raw_flight` |
| 5 | `backend/app/services/dji_import.py` | Task 5 | Extract Airdata field map in `_collect_extra_columns` |
| 6 | `backend/app/routers/photos.py` | Task 6 | Extract `_generate_thumbnail` helper |
| 7 | `backend/app/routers/export.py` | Task 7 | Extract `_parse_csv_flight_row` helper |
| 8 | `frontend/src/pages/FlightDetailPage.jsx` | Task 8 | Extract `FlightEditForm` and `TelemetryCharts` sub-components |
| 9 | `frontend/src/pages/IntegrationsPage.jsx` | Task 9 | Extract `_toastImportResult` and `_processBatchResult` helpers |
| 10 | `frontend/src/pages/CompliancePage.jsx` | Task 10 | Extract `buildAttentionItems` helper |
| 11 | `frontend/src/pages/SettingsPage.jsx` | Task 11 | Flatten nesting at lines 168 and 691 |
| 12 | `frontend/src/pages/AirspacePage.jsx` | Task 12 | Extract `getSetting` to top-level |
| 13 | `frontend/src/pages/FlightsPage.jsx` | Task 13 | Extract `FlightEditRow` sub-component |

---

### Task 1: Reduce cognitive complexity in `_apply_enrichment_detail` (sync.py)

**Files:**
- Modify: `backend/app/routers/sync.py:206-268`

**SonarQube:** S3776 — Complexity 35 (limit 15)
**Verdict:** AGREE — repetitive `.get()` fallback chains can use a mapping table

- [ ] **Step 1: Replace repeated field-mapping with loop**

Replace lines 233-267 (the Location, Metrics, Equipment sections) with a dict-driven approach. Keep the Date/Time and Duration sections as-is since they have branching logic.

Find this code at line 233:
```python
    # Location
    flight.takeoff_lat = flight.takeoff_lat or detail.get("takeoff_latitude") or detail.get("takeoff_lat") or detail.get("latitude")
    flight.takeoff_lon = flight.takeoff_lon or detail.get("takeoff_longitude") or detail.get("takeoff_lon") or detail.get("longitude")
    flight.landing_lat = flight.landing_lat or detail.get("landing_latitude") or detail.get("landing_lat")
    flight.landing_lon = flight.landing_lon or detail.get("landing_longitude") or detail.get("landing_lon")
    flight.takeoff_address = flight.takeoff_address or detail.get("takeoff_address") or detail.get("location") or detail.get("address")

    # Metrics
    flight.max_altitude_m = flight.max_altitude_m or detail.get("max_altitude_m") or detail.get("max_altitude") or detail.get("max_height")
    flight.max_speed_mps = flight.max_speed_mps or detail.get("max_speed_mps") or detail.get("max_speed") or detail.get("max_ground_speed")
    flight.distance_m = flight.distance_m or detail.get("distance_m") or detail.get("total_distance") or detail.get("distance")
```

Replace with:
```python
    # Location + Metrics — apply first non-None API value if flight field is empty
    _ENRICHMENT_FIELDS = {
        "takeoff_lat": ("takeoff_latitude", "takeoff_lat", "latitude"),
        "takeoff_lon": ("takeoff_longitude", "takeoff_lon", "longitude"),
        "landing_lat": ("landing_latitude", "landing_lat"),
        "landing_lon": ("landing_longitude", "landing_lon"),
        "takeoff_address": ("takeoff_address", "location", "address"),
        "max_altitude_m": ("max_altitude_m", "max_altitude", "max_height"),
        "max_speed_mps": ("max_speed_mps", "max_speed", "max_ground_speed"),
        "distance_m": ("distance_m", "total_distance", "distance"),
    }
    for field, api_keys in _ENRICHMENT_FIELDS.items():
        if not getattr(flight, field, None):
            for key in api_keys:
                val = detail.get(key)
                if val:
                    setattr(flight, field, val)
                    break
```

Also replace lines 261-267 (Equipment section):
```python
    # Equipment
    flight.battery_serial = flight.battery_serial or detail.get("battery_serial") or detail.get("battery")
    flight.sensor_package = flight.sensor_package or detail.get("sensor_package")
    flight.attachment_top = flight.attachment_top or detail.get("attachment_top")
    flight.attachment_bottom = flight.attachment_bottom or detail.get("attachment_bottom")
    flight.attachment_left = flight.attachment_left or detail.get("attachment_left")
    flight.attachment_right = flight.attachment_right or detail.get("attachment_right")
    flight.carrier = flight.carrier or detail.get("carrier") or detail.get("carriers")
```

Replace with:
```python
    # Equipment — same pattern
    _EQUIPMENT_FIELDS = {
        "battery_serial": ("battery_serial", "battery"),
        "sensor_package": ("sensor_package",),
        "attachment_top": ("attachment_top",),
        "attachment_bottom": ("attachment_bottom",),
        "attachment_left": ("attachment_left",),
        "attachment_right": ("attachment_right",),
        "carrier": ("carrier", "carriers"),
    }
    for field, api_keys in _EQUIPMENT_FIELDS.items():
        if not getattr(flight, field, None):
            for key in api_keys:
                val = detail.get(key)
                if val:
                    setattr(flight, field, val)
                    break
```

- [ ] **Step 2: Verify Python syntax**

Run: `python -c "import ast; ast.parse(open('backend/app/routers/sync.py').read()); print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/sync.py
git commit -m "refactor: reduce cognitive complexity in _apply_enrichment_detail (sync.py)"
```

---

### Task 2: Replace if/elif chain with dispatch dict in `_generate_chart` (reports.py)

**Files:**
- Modify: `backend/app/routers/reports.py:286-360`

**SonarQube:** S3776 — Complexity 17 (limit 15)
**Verdict:** AGREE — classic strategy pattern replacement

- [ ] **Step 1: Replace the if/elif chain**

Find the entire `_generate_chart` function starting at line 286 and replace it with:

```python
def _generate_chart(report_type: str, data: dict) -> io.BytesIO | None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = data.get("rows", [])
    if not rows:
        return None

    fig, ax = plt.subplots(figsize=(8, 3.5))
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#fafbfc")

    chart_colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16"]

    def _chart_flight_summary():
        return _chart_bar_by_key(ax, rows, "purpose", None, "Flights by Purpose", "Flights", chart_colors, plt)

    def _chart_pilot_hours():
        _chart_barh(ax, rows, "pilot", "hours", "Hours by Pilot", "Hours", chart_colors, plt)
        return True

    def _chart_equipment():
        _chart_barh(ax, rows, "vehicle", "hours", "Hours by Vehicle", "Hours", chart_colors, plt, truncate=20)
        return True

    def _chart_battery_status():
        status_counts = {}
        for r in rows:
            s = r.get("status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1
        if status_counts:
            ax.pie(list(status_counts.values()), labels=list(status_counts.keys()),
                   colors=chart_colors[:len(status_counts)],
                   autopct="%1.0f%%", startangle=90, textprops={"fontsize": 9})
            ax.set_title("Battery Status Distribution", fontsize=11, fontweight="bold", color="#334155")
        return True

    def _chart_maintenance():
        return _chart_bar_by_key(ax, rows, "type", None, "Records by Type", "Records", chart_colors, plt)

    def _chart_pilot_certs():
        summary = data.get("summary", {})
        cats = ["Active", "Expired", "Pending"]
        vals = [summary.get("total_active", 0), summary.get("total_expired", 0), summary.get("total_pending", 0)]
        ax.bar(cats, vals, color=["#10b981", "#ef4444", "#f59e0b"], edgecolor="white", linewidth=0.5)
        ax.set_ylabel("Count", fontsize=9)
        ax.set_title("Certification Status", fontsize=11, fontweight="bold", color="#334155")
        return True

    def _chart_pilot_activity():
        _chart_grouped_bars(ax, rows, "pilot", ["flight_hours", "mission_hours", "training_hours"],
                            "Hours by Pilot (Flight / Mission / Training)", plt)
        return True

    def _chart_annual():
        _chart_grouped_bars(ax, rows, "year", ["flight_hours", "mission_hours", "training_hours"],
                            "Year-over-Year Activity Hours", plt, limit=15)
        return True

    chart_dispatch = {
        "flight_summary": _chart_flight_summary,
        "pilot_hours": _chart_pilot_hours,
        "equipment_utilization": _chart_equipment,
        "battery_status": _chart_battery_status,
        "maintenance_history": _chart_maintenance,
        "pilot_certifications": _chart_pilot_certs,
        "pilot_activity_summary": _chart_pilot_activity,
        "annual_unit_report": _chart_annual,
    }

    try:
        handler = chart_dispatch.get(report_type)
        if not handler or not handler():
            plt.close(fig)
            return None

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(axis="both", labelsize=8)
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="#ffffff")
        plt.close(fig)
        buf.seek(0)
        return buf

    except Exception:
        plt.close(fig)
        return None
```

- [ ] **Step 2: Verify Python syntax**

Run: `python -c "import ast; ast.parse(open('backend/app/routers/reports.py').read()); print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/reports.py
git commit -m "refactor: replace if/elif chain with dispatch dict in _generate_chart"
```

---

### Task 3: Extract duplicate `.xlsx` literal (export.py)

**Files:**
- Modify: `backend/app/routers/export.py`

**SonarQube:** S1192 — Duplicate literal `.xlsx` 3 times
**Verdict:** AGREE — trivial constant extraction

- [ ] **Step 1: Add constant near the top of the file (after other constants)**

Find the existing constants area (should be near the imports). Add:

```python
EXCEL_EXTENSIONS = ('.xlsx', '.xls')
```

- [ ] **Step 2: Replace all 3 occurrences**

Replace at line 514:
```python
    if not file.filename.endswith(('.xlsx', '.xls')):
```
with:
```python
    if not file.filename.endswith(EXCEL_EXTENSIONS):
```

Replace at line 568:
```python
    if not file.filename.endswith(('.txt', '.csv', '.json', '.zip', '.xlsx', '.xls')):
```
with:
```python
    if not file.filename.endswith(('.txt', '.csv', '.json', '.zip') + EXCEL_EXTENSIONS):
```

Replace at line 576:
```python
    if file.filename.endswith(('.xlsx', '.xls')):
```
with:
```python
    if file.filename.endswith(EXCEL_EXTENSIONS):
```

- [ ] **Step 3: Verify and commit**

```bash
python -c "import ast; ast.parse(open('backend/app/routers/export.py').read()); print('OK')"
git add backend/app/routers/export.py
git commit -m "refactor: extract EXCEL_EXTENSIONS constant to remove duplicate literals"
```

---

### Task 4: Reduce complexity in `_map_raw_flight` (skydio.py)

**Files:**
- Modify: `backend/app/integrations/skydio.py:30-79`

**SonarQube:** S3776 — Complexity 25 (limit 15)
**Verdict:** PARTIAL — the `.get() or .get()` chains are justified for API adaptation, but can use a helper

- [ ] **Step 1: Add a helper function before `_map_raw_flight`**

Add after `_to_str` (around line 35), before `_map_raw_flight` (line 37):
```python
def _first_of(d: dict, *keys):
    """Return the first truthy value from dict for the given keys (matches `or` chain semantics)."""
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None
```

- [ ] **Step 2: Simplify `_map_raw_flight` using the helper**

Replace the return dict (lines ~62-86) with:
```python
    return {
        "external_id": _first_of(f, "flight_id", "uuid", "id"),
        "api_provider": "skydio",
        "date": flight_date or f.get("date"),
        "takeoff_time": takeoff_time,
        "landing_time": landing_time,
        "duration_seconds": duration,
        "takeoff_lat": _first_of(f, "takeoff_latitude", "takeoff_lat"),
        "takeoff_lon": _first_of(f, "takeoff_longitude", "takeoff_lon"),
        "landing_lat": _first_of(f, "landing_latitude", "landing_lat"),
        "landing_lon": _first_of(f, "landing_longitude", "landing_lon"),
        "takeoff_address": _first_of(f, "takeoff_address", "location"),
        "pilot_name": _first_of(f, "pilot_name", "operator_name"),
        "vehicle_serial": _first_of(f, "vehicle_serial", "serial_number"),
        "max_altitude_m": _first_of(f, "max_altitude_m", "max_altitude"),
        "max_speed_mps": _first_of(f, "max_speed_mps", "max_speed"),
        "distance_m": _first_of(f, "distance_m", "total_distance"),
        "battery_serial": _to_str(_first_of(f, "battery_serial", "battery")),
        "sensor_package": _to_str(f.get("sensor_package")),
        "attachment_top": _to_str(f.get("attachment_top")),
        "attachment_bottom": _to_str(f.get("attachment_bottom")),
        "attachment_left": _to_str(f.get("attachment_left")),
        "attachment_right": _to_str(f.get("attachment_right")),
        "carrier": _to_str(_first_of(f, "carrier", "carriers")),
    }
```

Also simplify the takeoff/landing/duration lines (~43-59) using the helper:
```python
    takeoff_str = _first_of(f, "takeoff_time", "takeoff", "start_time")
    landing_str = _first_of(f, "landing_time", "landing", "end_time")
```
and:
```python
    duration = _first_of(f, "duration_seconds", "duration")
```

- [ ] **Step 3: Verify and commit**

```bash
python -c "import ast; ast.parse(open('backend/app/integrations/skydio.py').read()); print('OK')"
git add backend/app/integrations/skydio.py
git commit -m "refactor: add _first_of helper to reduce complexity in skydio.py"
```

---

### Task 5: Simplify `_collect_extra_columns` (dji_import.py)

**Files:**
- Modify: `backend/app/services/dji_import.py:240-282`

**SonarQube:** S3776 — Complexity 27 (limit 15)
**Verdict:** PARTIAL — the Airdata field map is already a dict; the inner loop can be simplified

- [ ] **Step 1: Simplify the Airdata field lookup**

Find the Airdata loop at lines 275-282:
```python
    for csv_key, extra_key in airdata_extra_fields.items():
        for header in (fieldnames or []):
            if header.lower().strip() == csv_key:
                val = row.get(header)
                if val and val.strip():
                    parsed_val = _parse_float(val)
                    extra[extra_key] = parsed_val if parsed_val is not None else val.strip()
                break
```

Replace with:
```python
    # Build a lowercase lookup for fieldnames
    header_lookup = {h.lower().strip(): h for h in (fieldnames or [])}
    for csv_key, extra_key in airdata_extra_fields.items():
        header = header_lookup.get(csv_key)
        if header:
            val = row.get(header)
            if val and val.strip():
                parsed_val = _parse_float(val)
                extra[extra_key] = parsed_val if parsed_val is not None else val.strip()
```

- [ ] **Step 2: Verify and commit**

```bash
python -c "import ast; ast.parse(open('backend/app/services/dji_import.py').read()); print('OK')"
git add backend/app/services/dji_import.py
git commit -m "refactor: simplify Airdata field lookup in _collect_extra_columns"
```

---

### Task 6: Extract thumbnail generation from `upload_photo` (photos.py)

**Files:**
- Modify: `backend/app/routers/photos.py:85-190`

**SonarQube:** S3776 — Complexity 20 (limit 15)
**Verdict:** PARTIAL — extract thumbnail generation to reduce function length

- [ ] **Step 1: Add helper function before `upload_photo`**

Add before the `@router.post("/upload"` decorator (before line 85):

```python
def _generate_thumbnail(file_path: str, photo_dir: str, stored_name: str) -> str | None:
    """Generate a JPEG thumbnail for an uploaded image. Returns thumbnail path or None."""
    try:
        img = PILImage.open(file_path)
        img.thumbnail((THUMB_WIDTH, THUMB_WIDTH * 10), PILImage.LANCZOS)
        thumb_name = f"thumb_{stored_name}"
        thumb_path = os.path.join(photo_dir, thumb_name)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(thumb_path, "JPEG", quality=85)
        return thumb_path
    except (IOError, OSError) as e:
        logger.warning("Thumbnail generation failed: %s", e)
        return None
```

- [ ] **Step 2: Replace inline thumbnail code in `upload_photo`**

Find lines 170-182 inside `upload_photo`:
```python
    # Generate thumbnail
    try:
        img = PILImage.open(file_path)
        img.thumbnail((THUMB_WIDTH, THUMB_WIDTH * 10), PILImage.LANCZOS)
        thumb_name = f"thumb_{stored_name}"
        thumb_path = os.path.join(photo_dir, thumb_name)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(thumb_path, "JPEG", quality=85)
        photo.thumbnail_path = thumb_path
    except (IOError, OSError) as e:
        logger.warning("Thumbnail generation failed for photo %s: %s", photo.id, e)
        photo.thumbnail_path = None
```

Replace with:
```python
    # Generate thumbnail
    photo.thumbnail_path = _generate_thumbnail(file_path, photo_dir, stored_name)
```

- [ ] **Step 3: Verify and commit**

```bash
python -c "import ast; ast.parse(open('backend/app/routers/photos.py').read()); print('OK')"
git add backend/app/routers/photos.py
git commit -m "refactor: extract _generate_thumbnail helper from upload_photo"
```

---

### Task 7: Extract CSV flight row parser from `import_flights_csv` (export.py)

**Files:**
- Modify: `backend/app/routers/export.py:457-506`

**SonarQube:** S3776 — Complexity 29 (limit 15)
**Verdict:** PARTIAL — extract the row parsing to a helper

- [ ] **Step 1: Add helper function before `import_flights_csv`**

Add before line 457:

```python
def _parse_csv_flight_row(row: dict, db) -> Flight:
    """Parse a single CSV row into a Flight object with pilot lookup."""
    flight = Flight(
        date=row.get("Date") or None,
        purpose=row.get("Purpose") or None,
        duration_seconds=int(row[COL_DURATION_S]) if row.get(COL_DURATION_S) else None,
        takeoff_address=row.get("Takeoff Address") or None,
        takeoff_lat=float(row[COL_TAKEOFF_LAT]) if row.get(COL_TAKEOFF_LAT) else None,
        takeoff_lon=float(row[COL_TAKEOFF_LON]) if row.get(COL_TAKEOFF_LON) else None,
        max_altitude_m=float(row[COL_MAX_ALTITUDE_M]) if row.get(COL_MAX_ALTITUDE_M) else None,
        max_speed_mps=float(row[COL_MAX_SPEED_MPS]) if row.get(COL_MAX_SPEED_MPS) else None,
        case_number=row.get(COL_CASE_NUMBER) or None,
        notes=row.get("Notes") or None,
        review_status="reviewed",
        pilot_confirmed=True,
    )
    pilot_name = row.get("Pilot", "").strip()
    if pilot_name:
        parts = pilot_name.split(" ", 1)
        if len(parts) == 2:
            pilot = db.query(Pilot).filter(
                Pilot.first_name == parts[0], Pilot.last_name == parts[1]
            ).first()
            if pilot:
                flight.pilot_id = pilot.id
    return flight
```

- [ ] **Step 2: Simplify `import_flights_csv` to use the helper**

Replace the for loop body (lines 474-503):
```python
    for i, row in enumerate(reader):
        try:
            flight = Flight(
                date=row.get("Date") or None,
                ...
            )
            pilot_name = row.get("Pilot", "").strip()
            ...
            db.add(flight)
            imported += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")
```

With:
```python
    for i, row in enumerate(reader):
        try:
            flight = _parse_csv_flight_row(row, db)
            db.add(flight)
            imported += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")
```

- [ ] **Step 3: Verify and commit**

```bash
python -c "import ast; ast.parse(open('backend/app/routers/export.py').read()); print('OK')"
git add backend/app/routers/export.py
git commit -m "refactor: extract _parse_csv_flight_row helper from import_flights_csv"
```

---

### Task 8: Split FlightDetailPage into sub-components

**Files:**
- Create: `frontend/src/pages/FlightDetailEditForm.jsx`
- Create: `frontend/src/pages/FlightDetailCharts.jsx`
- Modify: `frontend/src/pages/FlightDetailPage.jsx`

**SonarQube:** S3776 — Complexity 38 (limit 15) — worst JS issue
**Verdict:** AGREE — massive single component needs decomposition

**NOTE:** This is the largest task. The FlightDetailPage is ~500 lines. We extract two sub-components:
1. The edit form (inline editing fields) → `FlightDetailEditForm.jsx`
2. The telemetry charts (altitude, speed, battery) → `FlightDetailCharts.jsx`

This task requires careful reading of the full component to identify the exact extraction boundaries. The implementer should read the full file first, identify the edit form JSX block and the chart rendering block, then extract them as separate components that receive props.

**Approach:** Rather than prescribing exact JSX (which would be 200+ lines), the implementer should:
1. Find the `{editing ? (` ternary block (line ~231) — extract the edit branch as `<FlightDetailEditForm editForm={editForm} setEditForm={setEditForm} pilots={pilots} vehicles={vehicles} purposes={purposes} batteries={batteries} sensors={sensors} attachments={attachments} onSave={handleSave} onCancel={() => setEditing(false)} />`
2. Find the telemetry chart section (~line 435, contains multiple `<ResponsiveContainer>` blocks for altitude/speed/battery charts) — extract it as `<FlightDetailCharts telemetry={telemetry} />`
3. Import both into FlightDetailPage

- [ ] **Step 1: Read full FlightDetailPage.jsx and identify extraction boundaries**
- [ ] **Step 2: Create FlightDetailEditForm.jsx with the edit form JSX**
- [ ] **Step 3: Create FlightDetailCharts.jsx with the telemetry charts**
- [ ] **Step 4: Update FlightDetailPage.jsx imports and replace inline blocks**
- [ ] **Step 5: Build frontend**

Run: `cd frontend && npx vite build`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/FlightDetailEditForm.jsx frontend/src/pages/FlightDetailCharts.jsx frontend/src/pages/FlightDetailPage.jsx
git commit -m "refactor: extract FlightDetailEditForm and FlightDetailCharts sub-components"
```

---

### Task 9: Reduce complexity in `handleImport` (IntegrationsPage.jsx)

**Files:**
- Modify: `frontend/src/pages/IntegrationsPage.jsx:385-439`

**SonarQube:** S3776 — Complexity 27 (limit 15)
**Verdict:** AGREE — extract toast logic and batch result processing

- [ ] **Step 1: Add helper functions inside the FlightLogImport component, before handleImport**

Find the line before `const handleImport = async () => {` and add:

```javascript
  const toastImportResult = (res) => {
    if (res.error) {
      toast.error(res.error)
    } else if (res.total !== undefined) {
      toast.success(`Bulk import: ${res.imported} imported, ${res.skipped} skipped out of ${res.total} files`)
    } else if (res.skipped) {
      toast.info('Flight already exists (skipped)')
    } else if (res.flight_id) {
      toast.success(`Imported flight #${res.flight_id} with ${res.points_imported} telemetry points`)
    } else {
      toast.success(`Imported ${res.points_imported || res.imported || res.flights_imported || 0} flights successfully`)
    }
  }

  const processBatchResult = (batch, res, fileName) => {
    if (res.total !== undefined) {
      batch.imported += res.imported || 0
      batch.skipped += res.skipped || 0
      if (res.errors?.length) batch.errors.push(...res.errors)
    } else if (res.skipped) {
      batch.skipped++
    } else if (res.error) {
      batch.errors.push(`${fileName}: ${res.error}`)
    } else {
      batch.imported++
    }
  }
```

- [ ] **Step 2: Simplify handleImport to use the helpers**

Replace the full `handleImport` function with:

```javascript
  const handleImport = async () => {
    if (files.length === 0) return
    setImporting(true)
    setResult(null)
    setProgress(null)

    try {
      if (files.length === 1) {
        const res = await importSingleFile(files[0])
        setResult(res)
        toastImportResult(res)
      } else {
        const batch = { total: files.length, imported: 0, skipped: 0, errors: [] }
        for (let i = 0; i < files.length; i++) {
          setProgress(`Processing ${i + 1} of ${files.length}: ${files[i].name}`)
          try {
            const res = await importSingleFile(files[i])
            processBatchResult(batch, res, files[i].name)
          } catch (err) {
            batch.errors.push(`${files[i].name}: ${err.message}`)
          }
        }
        setResult(batch)
        setProgress(null)
        toast.success(`Batch import: ${batch.imported} imported, ${batch.skipped} skipped out of ${batch.total}`)
        if (batch.errors.length) toast.warning(`${batch.errors.length} error(s) during import`)
      }
    } catch (err) {
      toast.error(err.message)
    } finally {
      setImporting(false)
      setProgress(null)
    }
  }
```

- [ ] **Step 3: Build and commit**

```bash
cd frontend && npx vite build
git add frontend/src/pages/IntegrationsPage.jsx
git commit -m "refactor: extract toast and batch helpers from handleImport"
```

---

### Task 10: Extract `buildAttentionItems` from CompliancePage

**Files:**
- Modify: `frontend/src/pages/CompliancePage.jsx:101-160`

**SonarQube:** S3776 — Complexity 25 (limit 15)
**Verdict:** PARTIAL — extract the attention items builder to a standalone function

- [ ] **Step 1: Add helper function outside the component**

Find the line before `export default function CompliancePage()` and add:

```javascript
function buildAttentionItems(data) {
  const items = []
  if (data.expired_certifications > 0) {
    items.push({ type: 'Expired Certifications', count: data.expired_certifications, severity: 'critical', link: '/certifications' })
  }
  if (data.expiring_certifications?.length > 0) {
    for (const c of data.expiring_certifications) {
      items.push({
        type: 'Expiring Certification',
        detail: `Pilot #${c.pilot_id} - ${c.days_remaining} days remaining`,
        severity: c.days_remaining <= 30 ? 'high' : 'medium',
        link: '/certifications',
      })
    }
  }
  if (data.expired_registrations > 0) {
    items.push({ type: 'Expired FAA Registrations', count: data.expired_registrations, severity: 'critical', link: '/fleet' })
  }
  if (data.overdue_maintenance > 0) {
    items.push({ type: 'Overdue Maintenance', count: data.overdue_maintenance, severity: 'high', link: '/maintenance' })
  }
  if (data.unreviewed_flights > 0) {
    items.push({ type: 'Unreviewed Flights', count: data.unreviewed_flights, severity: 'medium', link: '/flights' })
  }
  if (data.open_incidents > 0) {
    items.push({ type: 'Open Incidents', count: data.open_incidents, severity: 'high', link: '/incidents' })
  }
  if (data.pending_flight_plans > 0) {
    items.push({ type: 'Pending Flight Plans', count: data.pending_flight_plans, severity: 'low', link: '/flight-plans' })
  }
  const severityOrder = { critical: 0, high: 1, medium: 2, low: 3 }
  items.sort((a, b) => (severityOrder[a.severity] ?? 9) - (severityOrder[b.severity] ?? 9))
  return items
}
```

**Note:** Read the full attention items block from the component first to ensure ALL conditional pushes are captured — the list above is based on what was read but the implementer must verify against the actual file.

- [ ] **Step 2: Replace inline attention items building**

Inside the component, replace the `const attentionItems = []` block and all the conditional pushes with:

```javascript
  const attentionItems = buildAttentionItems(data)
```

- [ ] **Step 3: Build and commit**

```bash
cd frontend && npx vite build
git add frontend/src/pages/CompliancePage.jsx
git commit -m "refactor: extract buildAttentionItems helper from CompliancePage"
```

---

### Task 11: Flatten nesting in SettingsPage (two locations)

**Files:**
- Modify: `frontend/src/pages/SettingsPage.jsx:168` and `:691`

**SonarQube:** S2004 — Functions nested more than 4 levels deep (2 locations)
**Verdict:** PARTIAL — minor restructuring

- [ ] **Step 1: Fix line ~168 — extract settings loader**

Find the nested `.then()` chain around lines 162-171:
```javascript
      if (map.mission_purposes) {
        try { setMissionPurposes(JSON.parse(map.mission_purposes)) } catch { /* invalid JSON */ }
      } else {
        // Load default purposes from the database
        api.get('/flights/purposes/list').then(purposes => {
          if (Array.isArray(purposes) && purposes.length > 0) {
            setMissionPurposes(purposes.map(p => p.name))
          }
        }).catch(() => {})
      }
```

Replace with a flatter version:
```javascript
      if (map.mission_purposes) {
        try { setMissionPurposes(JSON.parse(map.mission_purposes)) } catch { /* invalid JSON */ }
      } else {
        loadDefaultPurposes()
      }
```

And add `loadDefaultPurposes` as a separate function inside the component (before the useEffect):
```javascript
  const loadDefaultPurposes = () => {
    api.get('/flights/purposes/list').then(purposes => {
      if (Array.isArray(purposes) && purposes.length > 0) {
        setMissionPurposes(purposes.map(p => p.name))
      }
    }).catch(() => {})
  }
```

- [ ] **Step 2: Fix line ~691 — flatten onKeyDown handler**

Find the `onKeyDown` handler around line 703:
```javascript
              onKeyDown={e => {
                if (e.key === 'Enter' && newPurpose.trim()) {
                  setMissionPurposes(prev => [...prev, newPurpose.trim()])
                  setNewPurpose('')
                }
              }}
```

Extract to a named handler inside the component:
```javascript
  const handlePurposeKeyDown = (e) => {
    if (e.key === 'Enter' && newPurpose.trim()) {
      setMissionPurposes(prev => [...prev, newPurpose.trim()])
      setNewPurpose('')
    }
  }
```

Then replace inline with: `onKeyDown={handlePurposeKeyDown}`

- [ ] **Step 3: Build and commit**

```bash
cd frontend && npx vite build
git add frontend/src/pages/SettingsPage.jsx
git commit -m "refactor: flatten nesting in SettingsPage to resolve S2004"
```

---

### Task 12: Extract setting lookup in AirspacePage

**Files:**
- Modify: `frontend/src/pages/AirspacePage.jsx:121-124`

**SonarQube:** S2004 — Nested function more than 4 levels
**Verdict:** PARTIAL — trivial extraction

- [ ] **Step 1: Move the `get` helper outside the useEffect**

Find the useEffect around line 118-131:
```javascript
  useEffect(() => {
    if (selectedPoint) return
    api.get('/settings').then(settings => {
      const get = (key) => {
        const s = settings.find(s => s.key === key)
        return s ? s.value : null
      }
      const wLat = get('adsb_default_lat') || get('weather_location_lat')
      const wLon = get('adsb_default_lon') || get('weather_location_lon')
      if (wLat && wLon) {
        setMapCenter([Number.parseFloat(wLat), Number.parseFloat(wLon)])
      }
    }).catch(() => {})
  }, [])
```

Replace with:
```javascript
  useEffect(() => {
    if (selectedPoint) return
    api.get('/settings').then(settings => {
      const findSetting = (key) => settings.find(s => s.key === key)?.value ?? null
      const wLat = findSetting('adsb_default_lat') || findSetting('weather_location_lat')
      const wLon = findSetting('adsb_default_lon') || findSetting('weather_location_lon')
      if (wLat && wLon) {
        setMapCenter([Number.parseFloat(wLat), Number.parseFloat(wLon)])
      }
    }).catch(() => {})
  }, [])
```

This replaces the nested `get` function with an inline arrow that uses optional chaining, removing one nesting level.

- [ ] **Step 2: Build and commit**

```bash
cd frontend && npx vite build
git add frontend/src/pages/AirspacePage.jsx
git commit -m "refactor: flatten setting lookup in AirspacePage useEffect"
```

---

### Task 13: Extract FlightEditRow from FlightsPage

**Files:**
- Modify: `frontend/src/pages/FlightsPage.jsx:424-470`

**SonarQube:** S3776 — Complexity 17 (limit 15)
**Verdict:** PARTIAL — the inline edit row JSX adds complexity; extract to a component

- [ ] **Step 1: Extract the edit row as a component**

Find the `{filtered.map(f => editingId === f.id ? (` block at line 424.

Add a new component before the main export (or at the bottom of the file):

```javascript
function FlightEditRow({ f, editForm, setEditForm, pilots, purposes, onSave, onCancel, normalizeDateValue, sortPilotsActiveFirst, sortByName }) {
  return (
    <tr className="border-b border-border/50 bg-accent/20">
      <td className="px-4 py-2 text-foreground text-xs font-mono" title={f.external_id || ''}>{f.external_id ? f.external_id.slice(0, 8) : '—'}</td>
      <td className="px-4 py-2">
        <input type="date" value={editForm.date} onChange={e => setEditForm({...editForm, date: e.target.value})}
          onBlur={e => { const n = normalizeDateValue(e.target.value); if (n !== e.target.value) setEditForm(prev => ({...prev, date: n})) }}
          className="w-full px-2 py-1 bg-secondary border border-border rounded text-foreground text-sm" />
      </td>
      <td className="px-4 py-2">
        <select value={editForm.pilot_id} onChange={e => setEditForm({...editForm, pilot_id: e.target.value})}
          className="w-full px-2 py-1 bg-secondary border border-border rounded text-foreground text-sm">
          <option value="">Unassigned</option>
          {sortPilotsActiveFirst(pilots).map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
        </select>
      </td>
      <td className="px-4 py-2 hidden md:table-cell text-foreground">{f.vehicle_name || '—'}</td>
      <td className="px-4 py-2 hidden md:table-cell">
        <select value={editForm.purpose} onChange={e => setEditForm({...editForm, purpose: e.target.value})}
          className="w-full px-2 py-1 bg-secondary border border-border rounded text-foreground text-sm">
          <option value="">None</option>
          {sortByName(purposes, 'name').map(p => <option key={p.id} value={p.name}>{p.name}</option>)}
        </select>
      </td>
      <td className="px-4 py-2 text-right">
        <input type="number" value={editForm.duration_seconds} onChange={e => setEditForm({...editForm, duration_seconds: e.target.value})}
          className="w-20 px-2 py-1 bg-secondary border border-border rounded text-foreground text-sm text-right" placeholder="sec" />
      </td>
      <td className="px-4 py-2 hidden lg:table-cell text-foreground">{f.takeoff_address || '—'}</td>
      <td className="px-4 py-2">
        <button onClick={() => setEditForm({...editForm, review_status: editForm.review_status === 'reviewed' ? 'needs_review' : 'reviewed'})}
          className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium cursor-pointer ${
            editForm.review_status === 'needs_review' ? 'bg-amber-500/15 text-amber-400' : 'bg-emerald-500/15 text-emerald-400'
          }`}>
          {editForm.review_status === 'needs_review' ? 'Needs Review' : 'Reviewed'}
        </button>
      </td>
      <td className="px-4 py-2 text-right">
        <div className="flex items-center justify-end gap-1">
          <button onClick={onSave} title="Save" className="p-1.5 text-emerald-400 hover:bg-emerald-500/15 rounded">
            <Check className="w-4 h-4" />
          </button>
          <button onClick={onCancel} title="Cancel" className="p-1.5 text-muted-foreground hover:bg-accent/30 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>
      </td>
    </tr>
  )
}
```

**Note:** The `Check` and `X` imports are already at the top of FlightsPage.jsx. The implementer should verify the exact import names before creating this component.

- [ ] **Step 2: Replace inline edit row in the map**

Replace the edit row ternary (line 424 through the closing `</tr>` of the edit row ~line 470) with:

```javascript
            {filtered.map(f => editingId === f.id ? (
              <FlightEditRow key={f.id} f={f} editForm={editForm} setEditForm={setEditForm}
                pilots={pilots} purposes={purposes} onSave={saveEditing} onCancel={cancelEditing}
                normalizeDateValue={normalizeDateValue} sortPilotsActiveFirst={sortPilotsActiveFirst} sortByName={sortByName} />
            ) : (
```

- [ ] **Step 3: Build and commit**

```bash
cd frontend && npx vite build
git add frontend/src/pages/FlightsPage.jsx
git commit -m "refactor: extract FlightEditRow component from FlightsPage"
```

---

## Verification

After all 13 tasks:

1. **Python syntax check:** `python -c "import ast; [ast.parse(open(f).read()) for f in ['backend/app/routers/sync.py','backend/app/routers/reports.py','backend/app/routers/export.py','backend/app/integrations/skydio.py','backend/app/services/dji_import.py','backend/app/routers/photos.py']]; print('All OK')"`

2. **Frontend build:** `cd frontend && npx vite build`

3. **API smoke test:** After Docker rebuild, hit key endpoints:
   - `GET /api/flights?per_page=1` — flights still load
   - `GET /api/dashboard/compliance` — compliance still calculates
   - `GET /api/photos` — photos still list
   - `POST /api/reports/generate` with `{"report_type":"flight_summary"}` — reports still generate

4. **SonarCloud re-scan:** Push to GitHub, wait for SonarCloud analysis, verify CRITICAL count drops from 37 toward ~20.

---

## Expected Impact

| Category | Before | After (estimated) |
|---|---|---|
| S3776 CRITICAL (Python) | 29 | ~17 (12 fixed or reduced below threshold) |
| S3776 CRITICAL (JS) | 4 | ~1 (FlightDetail, Integrations, Compliance fixed) |
| S2004 CRITICAL (JS) | 3 | 0 (all 3 fixed) |
| S1192 CRITICAL (Python) | 1 | 0 (fixed) |
| **Total CRITICAL** | **37** | **~18** |
