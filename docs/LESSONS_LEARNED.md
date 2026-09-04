# Drone Unit Manager — Lessons Learned

A complete record of decisions, mistakes, fixes, and knowledge gained building a self-hosted drone fleet management platform from scratch across 93+ commits.

---

## Project Timeline

| Phase | Commits | Key Milestone |
|-------|---------|---------------|
| Initial release | 1 | Core platform: flights, pilots, vehicles, Skydio sync |
| Infrastructure | 2-11 | Docker CI/CD, volume permissions, user management, sync logging |
| Feature expansion | 12-22 | PDF reports, equipment detail, deep sync, flight enrichment |
| Data integration | 23-50 | Multi-format import, pilot matching, Excel/Airdata/DJI parsers |
| UI polish | 51-70 | Modern UI refresh, cross-reference links, interactive maps |
| Advanced features | 71-90 | ADS-B airspace, weather briefing, compliance, checklists, analytics |
| Code quality | 91-96 | SonarQube remediation: 1,916 issues → ~50 across 3 rounds |
| Testing & fixes | 97-110+ | Fresh install testing, fleet detail pages, bug fixes from live testing |

---

## Architecture Decisions

### Two Separate SQLite Databases
**Decision:** Main DB for relational data, separate telemetry DB for high-volume flight telemetry.
**Why:** Flight telemetry generates thousands of points per flight. Mixing it with relational data would slow down queries for pilots, vehicles, and reports.
**Result:** Clean separation. Main DB stays fast, telemetry queries don't impact the app.

### Multi-Platform Provider Architecture
**Decision:** Abstract equipment and flights with `provider_serial`, `data_source`, and `extra_data` JSON fields instead of hard-coding Skydio-specific columns.
**Why:** Originally built for Skydio, DJI, Autel, and Parrot. Even though DJI/Autel/Parrot were later removed, the abstraction allowed Airdata import to slot in without schema changes.
**Lesson:** Abstractions that map to real domain boundaries (data sources) are worth it. Abstractions for hypothetical future needs are not.

### Single Docker Container
**Decision:** One container serves both FastAPI backend and React frontend (static files served by FastAPI).
**Why:** Simplicity for self-hosted deployment on Unraid. No need for nginx, reverse proxy, or multi-container orchestration.
**Trade-off:** Can't scale frontend and backend independently, but for a self-hosted app with 1-10 users, this is irrelevant.

### SQLite Over PostgreSQL
**Decision:** SQLite with WAL journal mode for both databases.
**Why:** Zero configuration, single-file backups, perfect for self-hosted single-server deployment.
**Lesson:** SQLite handles concurrent reads well with WAL mode. The 37+ table schema runs fine with hundreds of flights and thousands of telemetry points.

### JWT Authentication (No Sessions)
**Decision:** Stateless JWT tokens with bcrypt password hashing.
**Why:** No session storage needed, no Redis dependency, works naturally with the single-container deployment.

---

## Things That Broke (And Why)

### Settings Page Freezing on Paste (Commit 61bef1c)
**Problem:** Pasting a long Skydio API token into the Settings page froze the browser.
**Root cause:** Controlled React inputs (`value={state}` + `onChange`) trigger re-renders on every character. Pasting a 200+ character token caused hundreds of re-renders in milliseconds.
**Fix:** Switched to uncontrolled inputs with `defaultValue` and `refs`. The input manages its own state, React only reads the value on save.
**Lesson:** For forms with long text fields, uncontrolled inputs avoid the re-render storm. This is counterintuitive in React (controlled is the "standard" pattern) but necessary for performance.

### Skydio API Response Parsing (Commits 36da958, 7dd8efa)
**Problem:** Sync would fail silently or miss flights.
**Root cause:** Skydio API returns nested responses with inconsistent pagination. Flight IDs had UUID formatting differences (with/without hyphens). Vehicle dedup was case-sensitive.
**Fix:** Added raw API response logging, flexible UUID matching (strip hyphens for comparison), case-insensitive dedup.
**Lesson:** When integrating with external APIs, log raw responses early. Don't trust that IDs will be consistently formatted.

### Pilot Email Matching Failures
**Problem:** Skydio sync couldn't match API users to local pilot records.
**Root cause:** Names and emails don't always match exactly between systems. "John Smith" in Skydio might be "J. Smith" locally.
**Fix:** Three-level matching fallback: exact email → last name match → email pattern match (first initial + last name).
**Lesson:** Identity matching between systems needs fuzzy logic from day one. Exact matching only works for systems you control.

### Docker Volume Permissions (Commit b632479)
**Problem:** App crashed on Unraid because it couldn't write to the data directory.
**Root cause:** Docker container ran as root but the mounted volume had different UID/GID permissions.
**Fix:** Ensured data directories are created in the entrypoint script with proper permissions.
**Lesson:** Always test Docker images with mounted volumes, not just built-in storage. Permission issues only appear in production.

### Query(...) vs Query() in Annotated Refactor (v2.0.3)
**Problem:** Weather briefing returned 500 Internal Server Error after SonarQube fixes.
**Root cause:** When wrapping FastAPI `Query` params in `Annotated[]`, the ellipsis (`...`) that marks a parameter as required was dropped. `Query(...)` = required, `Query()` = optional (defaults to None). Lat/lon arrived as None and crashed the haversine math.
**Fix:** Restored `Query(...)` in weather.py and geofences.py.
**Lesson:** Mechanical refactoring of function signatures is dangerous. The `...` (ellipsis) in Python has semantic meaning that's easy to miss. Always test endpoints that take query parameters after refactoring their signatures.

### Sync Data Loss — db.rollback() Wiping Flights (v2.0.5)
**Problem:** Skydio sync reported "200 flights imported" but zero flights appeared in the database.
**Root cause:** The sync had ONE `db.commit()` at the very end. Each entity sync (batteries, controllers, docks, sensors, attachments, media) had its own `try/except` with `db.rollback()`. If ANY entity sync failed, the rollback wiped ALL uncommitted data — including the 200 flights.
**Fix:** Commit after each sync section independently. Flights commit before enrichment. Each entity type commits after its own sync.
**Lesson:** Never use a single commit for a multi-phase operation where phases are independent. Each phase should commit its own data so a later failure can't undo earlier work.

### UNIQUE Constraint Crash Wiping All Flights (v2.0.8)
**Problem:** Sync imported 200 flights but they all disappeared because of a sensor serial number conflict.
**Root cause:** Multiple flights referenced the same sensor serial `3z-t5nt`. The `_ensure_simple_equipment()` function checked if the sensor existed, didn't find it, and added it. But the next flight also checked, also didn't find it (because it hadn't been flushed), and tried to add a duplicate. The UNIQUE constraint exploded, triggering `db.rollback()` which wiped all 200 flights.
**Fix:** Add `db.flush()` immediately after each equipment record insert so subsequent queries see it.
**Lesson:** When creating records inside a loop that checks for existence first, flush after each insert. SQLAlchemy's session cache doesn't make unflushed inserts visible to subsequent queries in the same transaction.

### Duplicate Index on Fresh Install (v2.0.4)
**Problem:** App crashed on first boot with a clean database: `index ix_flights_date already exists`.
**Root cause:** The Flight model's `date` column had both an explicit `Index('ix_flights_date', 'date')` in `__table_args__` AND `index=True` on the column definition. On existing databases this was invisible (index already existed from first creation). Only fresh installs triggered the duplicate.
**Fix:** Removed `index=True` from the column since the explicit Index already covers it.
**Lesson:** Duplicate index definitions are silent on existing databases. Always test with a completely clean database.

### Weather METAR String Comparison Crash
**Problem:** Weather briefing crashed with `TypeError: '<' not supported between instances of 'str' and 'int'`.
**Root cause:** METAR visibility comes back as `"10+"` (a string) instead of a number. The threshold comparison tried `"10+" < 1` which Python rejects.
**Fix:** Cast values to float with try/except before comparison.
**Lesson:** External API data types are never guaranteed. Always cast/validate before arithmetic operations.

### Document Viewing "Not Authenticated"
**Problem:** Clicking "View" on any uploaded document showed a "Not authenticated" error.
**Root cause:** Documents were linked via plain `<a href="/api/documents/{id}/view">` which opens in a new browser tab without the JWT token.
**Fix:** Replaced with authenticated fetch using the JWT header, converting response to blob, and opening via `URL.createObjectURL()`.
**Lesson:** Any link that opens an API endpoint in a new tab/window loses authentication context. Use blob URLs for authenticated file downloads.

### N/A Equipment Records from Excel Import
**Problem:** Fleet showed "N/A" sensors and attachments as real equipment items.
**Root cause:** Excel spreadsheet had literal "N/A" strings in sensor and attachment columns. The `_ensure_equipment_records()` function treated "N/A" as a valid serial number and created fleet records for it.
**Fix:** Skip "N/A", "NONE", "NA", "-", "--" values in equipment auto-creation.
**Lesson:** Always filter sentinel values from imported data. "N/A" in a spreadsheet means "no data," not a serial number.

### ADS-B Error Toasts on Auto-Refresh (Commit 24ae169)
**Problem:** The airspace map showed error toasts every 5 seconds when the ADS-B API was unreachable.
**Root cause:** Auto-refresh called the API on a timer, and each failure triggered a visible error notification.
**Fix:** Suppress error toasts on auto-refresh. Only show errors on manual refresh.
**Lesson:** Background polling should fail silently. Only user-initiated actions should show error feedback.

---

## SonarQube Remediation — What We Learned

### The Journey: 1,916 → ~50 Issues in 3 Rounds

**Round 1 (v2.0.0):** 1,916 → 684 (1,232 fixed)
- Annotated type hints for FastAPI dependencies (504 issues — 26% of total)
- Pydantic optional defaults (113)
- HTTPException response docs (179 endpoints)
- JS bugs: boolean leak in FlightMap, dead ternaries, sort comparator
- Mechanical JS: Number.*, replaceAll, unused imports/vars
- Label accessibility, keyboard handlers
- Nested ternaries, array index keys

**Round 2 (v2.0.1):** 684 → 519 (165 fixed)
- Remaining Annotated conversions for Query/File/Form params
- More negated conditions, replaceAll, unused vars
- Modal ARIA roles, globalThis, optional chaining
- Python cognitive complexity: sync_manager (222→50), excel_import (146→30)
- Duplicated string constants

**Round 3 (v2.0.2):** 519 → ~360 (160 fixed)
- Modal button overlay pattern (replaced onClick on divs with invisible button)
- More negated conditions, tabIndex cleanup
- Python complexity: dji_import, skydio, reports, weather, scheduler, migrations
- Self-assignment bug in export.py
- Remaining string constants

### Key SonarQube Lessons

1. **PropTypes on React 19 is noise.** 308 of our issues are S6774 (PropTypes validation). React 19 deprecated PropTypes. The real fix is TypeScript, not adding a deprecated package. SonarCloud's free plan doesn't allow disabling rules.

2. **Mechanical refactoring introduces subtle bugs.** The Query(...) → Query() bug was invisible to syntax checks, AST parsing, and even our code review. It only appeared at runtime. Automated refactoring of function signatures needs endpoint-level testing.

3. **Accessibility fixes can create new issues.** Adding `role="button"` and `role="dialog"` to divs fixed S1082 (keyboard events) but created S6819 (prefer native elements) and S6847 (non-interactive handlers). The correct fix was native `<button>` elements from the start.

4. **Cognitive complexity extraction is the riskiest refactor.** Splitting a 222-complexity function into 24 helpers is valuable but every extracted helper is a potential scope bug (missing variable, wrong parameter, dropped return value). We traced every call chain manually.

5. **`Number.isNaN` is not a drop-in replacement for `isNaN`.** `Number.isNaN("abc")` returns false, `isNaN("abc")` returns true. We had to verify every replacement was receiving a number, not a string.

6. **`globalThis` vs `window` is cosmetic for browser apps.** SonarQube flags `window.location` as S7764, but for a browser-only React app, `globalThis` adds no value. We fixed it anyway for a clean dashboard.

---

## Patterns That Worked Well

### Orange Cross-Reference Links
Every pilot, vehicle, battery, sensor, attachment, purpose code, and flight ID is clickable with `text-primary hover:underline` styling. This makes the app feel like a connected system, not a collection of separate pages.

### Uncontrolled Inputs with Refs for Settings
Forms that save on explicit button click (not on every keystroke) work better with `defaultValue` + `ref.current.value` than with controlled state. No re-render storms, no stale state issues.

### Data-Driven Section Builders (Email Digest)
Instead of a giant if/else chain for digest sections, we use an array of `(key, access_check, builder_function)` tuples. Adding a new section is one line, not a new if branch.

### Shared Dependency Type Aliases (deps.py)
`DBSession = Annotated[Session, Depends(get_db)]` defined once, imported everywhere. Eliminates 500+ repeated `Depends()` calls and makes endpoint signatures readable.

### Separate Telemetry Database
High-volume write operations (telemetry sync) don't lock the main database. Queries for pilots, vehicles, and reports stay fast.

### Format Auto-Detection for Imports
`detect_format()` sniffs file content to determine if it's DJI, Litchi, Airdata CSV, or Airdata JSON. Users don't need to select the format manually, and it handles edge cases like Airdata CSVs with feet vs. meters.

---

---

## Testing Round Findings (v2.0.4 — v2.1.0+)

### Fresh Install Testing Checklist
We created a 33-section test checklist (`docs/TEST_CHECKLIST.md`) and tested from a completely clean database. Key findings:

| Section | Result | Issues Found |
|---------|--------|-------------|
| 1. First-Run Setup | PASS | Duplicate index crash on fresh DB (fixed v2.0.4) |
| 2. Dashboard | PASS | — |
| 3. Settings | PASS | Weather thresholds not saving (key not in allowlist), sidebar missing Airspace |
| 4. Users | PASS | — |
| 5. Integrations/Sync | PASS after fixes | Flights wiped by rollback, UNIQUE constraint crash, missing sync interval UI |
| 6. Pilots | PASS | Delete button actually deactivates (confusing UX) |
| 7-9. Fleet | PASS | Sensors/Attachments/Docks had no detail pages (built v2.1.0) |
| 11. Flights | PASS | Flights need manual "Refresh from API" for full details |
| 13. DJI Import | KNOWN LIMIT | Binary encrypted .txt files not supported |
| 14. Flight Plans | PASS | Pilot can already edit pending plans |
| 15. Checklists | PASS | Same document viewing auth issue |
| 20. Activity Reports | PASS | Success form showed damage/cost fields (fixed) |
| 21. Weather | FAIL then PASS | METAR string comparison crash (fixed) |

### Recommended Getting Started Workflow
Based on testing, the optimal onboarding order is:
1. Initial setup (create admin account)
2. Import Excel data FIRST (creates pilots, vehicles, flights)
3. Add email addresses to pilot profiles
4. THEN connect Skydio API (pilot matching works because emails exist)
5. Sync telemetry (10 at a time)
6. Configure settings

This order matters because Skydio matches pilots by email. If pilots don't have emails when you first sync, the flights won't be linked to pilots.

---

## What We'd Do Differently

### TypeScript from the Start
308 PropTypes issues could have been zero with TypeScript. Type safety would have caught bugs earlier (like the `Query()` vs `Query(...)` issue) and eliminated the entire PropTypes rule from SonarQube.

### Test Suite Before Refactoring
No automated tests meant every refactor required manual verification. A basic test suite covering login, CRUD, sync, and import would have caught the weather.py bug before it reached production.

### Consistent Modal Component from Day One
Every page had its own inline modal pattern (`<div onClick={onClose}>...<div onClick={e => e.stopPropagation()}>`). If we'd used the shared `Modal.jsx` component everywhere from the start, the 98-issue modal accessibility fix would have been a one-file change instead of a 16-file change.

### API Contract Testing for Skydio
Multiple rounds of parsing fixes suggest we needed mock API responses and contract tests. When the API returns unexpected formats, the app should degrade gracefully instead of crashing.

### Fresh Install Testing from Day One
The duplicate index crash, weather threshold allowlist issue, and sync rollback bug were all invisible on existing databases. They only appeared on fresh installs. Every release should be tested from a completely empty database.

### Commit-per-Section in Multi-Phase Operations
The sync data loss bug taught us that multi-phase operations (sync flights → sync batteries → sync controllers → ...) should commit after each phase. A single commit at the end means any failure undoes everything.

---

## Infrastructure Notes

### Unraid Deployment
- Docker image: `ghcr.io/jongaydos/drone-unit-manager:latest`
- Port mapping: 3014 → 8000
- Volume: `/mnt/user/appdata/drone-unit-manager` → `/app/data`
- Contains: SQLite DBs, uploaded documents, photos, media cache

### Backup Strategy
```bash
# Stop container, copy data directory
cp -r /mnt/user/appdata/drone-unit-manager /mnt/user/backups/drone-$(date +%Y%m%d)
```
Two SQLite files: `drone_unit_manager.db` (main) and `telemetry.db`. Plus `uploads/` directory for documents and photos.

### Git Tags for Rollback
- `v1.0.0-backup` — last known good state before SonarQube work
- `v2.0.0` through `v2.0.9` — SonarQube fixes
- `v2.1.0` — fleet detail pages (sensors, attachments, docks)
- Rollback: `git reset --hard v1.0.0-backup && git push --force origin main`

### SMTP Configuration
- Port 465 = SMTP_SSL (Gmail)
- Port 587 = STARTTLS
- Common mistake: using port 587 with SSL or port 465 with STARTTLS

---

## Stats

| Metric | Value |
|--------|-------|
| Total commits | 110+ |
| Lines of code | 33,000+ |
| Files | 160+ |
| Database tables | 37+ |
| API endpoints | 250+ |
| SonarQube issues fixed | ~1,860 |
| Python helper functions extracted | 68+ |
| Frontend pages | 25+ |
| Report types | 8 |
| Import formats supported | 6 (Skydio API, Airdata JSON, Airdata CSV, Airdata ZIP, DJI .txt, Excel) |
| Testing bugs found & fixed | 15+ |
| Fleet detail pages | 6 (Vehicle, Battery, Controller, Sensor, Attachment, Dock) |
| Version tags | v1.0.0-backup through v2.1.0+ |
