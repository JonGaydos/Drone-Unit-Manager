# Staging Fixes 3.7.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the findings of the 3.7.0 staging browser test so 3.7.1 can go to production in place of 3.7.0.

**Architecture:** Small, independent changes to the flights list, the Analytics map, the Flight Requirements tab (one new read endpoint plus a list that reuses the existing excuse endpoint), and a handful of interface details. No schema change, no migration.

**Tech Stack:** FastAPI, SQLAlchemy (SQLite), React 19, Vite, Tailwind v4, Vitest, Playwright.

**Spec:** this plan's Requirements section (decisions taken after the 3.7.0 staging test, 2026-11-21).

## Requirements

1. Flights list: a Distance column; Location shows the landing address when the takeoff address is empty.
2. Analytics Flight Locations map: opens zoomed to its markers, not at world zoom.
3. Flight Requirements tab: a list of past missed periods across all pilots, with Excuse and Un-excuse for users with `requirements.excuse`.
4. Small fixes:
   - hide the empty Actions column on Fleet for users without manage rights;
   - the page header shows the page name on every page;
   - the cert matrix bulk-renewal checkbox sits beside its own status icon and appears only on certs that expire;
   - coordinates are displayed rounded to 7 decimals;
   - Home and End on the Compliance tabs;
   - `/currency` (and anything under it) goes to Compliance > Flight Requirements.

Working as intended, no change: a backdated requirement start logs misses at once; pilots and viewers see everyone's requirement progress; pilots can set vehicle locations; blank cost cells stay blank.

## Global Constraints

- No schema change and no Alembic migration in this release.
- Copy: no emojis, no em dashes, sentence case for messages, Title Case for column headers as on the existing tables.
- Public repository: no real names, places or coordinates from the unit in code, tests, fixtures or docs.
- Backend tests: `cd backend && DATA_DIR=$(mktemp -d) PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 ~/venvs/dum/bin/pytest -q -p no:cacheprovider <paths>`; remove the `DATA_DIR` afterwards.
- Frontend tests: `cd frontend && npx -y node@22 node_modules/vitest/vitest.mjs run <paths>`.
- Lint changed files: `cd frontend && npx -y node@22 node_modules/eslint/bin/eslint.js <files>`.
- Commits: one-line imperative subject, no AI attribution.

## Review Focus

1. A flight with a distance of 0 shows "0 m", not "—" (only null is "—").
2. The Analytics map inside a card that mounts hidden or at zero size still fits its markers once it has a size.
3. The missed-periods list for a pilot user shows rows but no Excuse button, and a period excused because the requirement was switched off shows no Un-excuse.
4. A cert of an expiring type with no expiry date on that cert shows no bulk checkbox.
5. A detail route such as `/flights/123` gets a page name in the header, not the app name.

---

### Task 1: Distance column and Location fallback on the flights list

**Files:**
- Modify: `backend/app/routers/flights.py` (`FLIGHT_SORTS`)
- Modify: `frontend/src/pages/FlightsPage.jsx` (header, read row, `FlightEditRow`)
- Modify: `frontend/src/lib/utils.js` (`formatDistance` beside `formatDuration`)
- Test: the backend test file that already covers `FLIGHT_SORTS` (find it with `grep -rln "sort=" backend/tests`), `frontend/src/pages/FlightsPage.test.jsx`, `frontend/src/lib/utils.test.js`

**Interfaces:**
- Produces: `formatDistance(meters: number | null | undefined) -> string`; sort key `distance_m` on `GET /api/flights?sort=distance_m`.

- [ ] **Step 1: Write the failing tests**
  - `formatDistance`: `null` and `undefined` give `'—'`; `0` gives `'0 m'`; `640.4` gives `'640 m'`; `999.6` gives `'1.0 km'`; `1234` gives `'1.2 km'`; `7900` gives `'7.9 km'`.
  - Backend `test_sort_by_distance`: three flights with `distance_m` 500, None, 50; `sort=distance_m&order=asc` returns 50, 500, then the None one; `desc` returns 500, 50, None.
  - FlightsPage: a "Distance" column header; a row with `distance_m: 1234` shows `1.2 km`; a row with `takeoff_address: null, landing_address: 'Landing Rd'` shows `Landing Rd` in Location; a row with both shows the takeoff address.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement**
  - Add `"distance_m": (Flight.distance_m,)` to `FLIGHT_SORTS`.
  - `formatDistance`: under 999.5 m show whole metres, otherwise kilometres with one decimal.
  - Add a sortable "Distance" header (right-aligned, `hidden lg:table-cell`, same pattern as Duration) right after Duration, and the matching cell in the read row and in `FlightEditRow`.
  - Location cell in both rows: `f.takeoff_address || f.landing_address || '—'`.
- [ ] **Step 4: Run the tests and lint; confirm they pass.**
- [ ] **Step 5: Commit** `Show distance and the landing address on the flights list`

### Task 2: Analytics map fits its markers

**Files:**
- Modify: `frontend/src/components/FlightMap.jsx` (`FitBounds`)
- Test: `frontend/src/components/FlightMap.test.jsx`

**Interfaces:**
- Consumes: the existing `FitBounds({ bounds })` used by `FlightPathMap` and `FlightLocationsMap`.

- [ ] **Step 1: Write the failing test.** With the leaflet stub's `useMap()` returning a spy map (`invalidateSize`, `fitBounds`, `setView`, `getContainer` returning a div), render `FlightLocationsMap` with two flights and assert `invalidateSize` is called before `fitBounds`; then simulate the container's `ResizeObserver` callback and assert `fitBounds` is called again. Mock `ResizeObserver` in the test if jsdom lacks it.
- [ ] **Step 2: Run it and confirm it fails.**
- [ ] **Step 3: Implement.** In `FitBounds`, call `map.invalidateSize()` before fitting, and observe `map.getContainer()` with a `ResizeObserver` that re-runs the same fit when the container's width or height changes from 0 to non-zero (disconnect on cleanup). Keep the single-marker `setView(bounds[0], 15)` branch.
- [ ] **Step 4: Run the test and the Analytics page tests; confirm they pass.**
- [ ] **Step 5: Manual check.** Playwright manual shot of `/analytics` with seeded flights in two nearby places: the map shows both markers, not the world. Attach the screenshot path to the task report.
- [ ] **Step 6: Commit** `Fit the flight locations map once it has a size`

### Task 3: Past missed periods on Flight Requirements

**Files:**
- Modify: `backend/app/routers/requirements.py` (new route, declared before `/{requirement_id}` routes so the path does not clash)
- Modify: `backend/app/schemas/requirement.py` (`HistoryRowOut` gains `pilot_id: int` and `pilot_name: str` as optional fields, or a subclass `UnitHistoryRowOut`)
- Create: `frontend/src/components/requirements/MissedPeriods.jsx`
- Modify: `frontend/src/components/requirements/RequirementsTab.jsx` (render the section under the requirement list)
- Modify: `frontend/src/components/requirements/PilotRequirementsCard.jsx` (export `ExcuseButton` and `ExcuseModal` for reuse; no behaviour change)
- Modify: `frontend/src/api/client.js` only if routes are wrapped there
- Test: `backend/tests/test_requirements_api.py`, `frontend/src/components/requirements/MissedPeriods.test.jsx`

**Interfaces:**
- Consumes: `POST /api/requirements/{id}/excuse` with `{pilot_id, period_start, excused, reason?}` (exists); `excuseAction(row)` from `progress.js`; `_saved_status`, `switched_off`, `_pilot_names`.
- Produces: `GET /api/requirements/history?requirement_id=<int, optional>&include_excused=<bool, default true>` returning `list[UnitHistoryRowOut]`: every saved result (`saved_at` not null) whose status is `missed`, plus `excused` ones when `include_excused`, newest `period_end` first, then requirement name, then pilot name; capped at 500 rows. Each row is the `_pilot_history` shape plus `pilot_id` and `pilot_name`. Permission: `ViewUser` (everyone who sees requirements).

- [ ] **Step 1: Write the failing backend tests** in `test_requirements_api.py`:
  - `test_history_lists_missed_and_excused_across_pilots`: two pilots, one missed and one met saved period each; response has only the missed rows, each with `pilot_name`.
  - `test_history_filters_by_requirement` and `test_history_excludes_excused_when_asked` (`include_excused=false`).
  - `test_history_rejects_anonymous` (401) and `test_history_allows_viewer` (200).
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement the endpoint** `requirements_history(db, user, requirement_id: int | None = None, include_excused: bool = True)`; share the row-building code with `_pilot_history` rather than copying it.
- [ ] **Step 4: Run the backend tests; confirm they pass.**
- [ ] **Step 5: Write the failing frontend tests** in `MissedPeriods.test.jsx`:
  - Renders a table "Past missed periods" with Requirement, Pilot (link to `/pilots/<id>`), Period, Result, Status columns.
  - With `requirements.excuse`: a missed row shows Excuse; clicking it opens the excuse modal; submitting posts `{pilot_id, period_start, excused: true, reason}` and reloads the list. An excused row shows Un-excuse and the excusal text. A `switched_off` row shows neither.
  - Without `requirements.excuse`: no Excuse or Un-excuse buttons.
  - Empty list: "No missed periods."
  - A requirement filter select (All requirements plus each name) refetches with `requirement_id`.
- [ ] **Step 6: Run them and confirm they fail.**
- [ ] **Step 7: Implement `MissedPeriods`** reusing `ExcuseButton`, `ExcuseModal`, `periodText`, `progressText` and `excusalText`; add it to `RequirementsTab` below the requirement cards.
- [ ] **Step 8: Run the requirements test files and lint; confirm they pass.**
- [ ] **Step 9: Add an e2e case** to `frontend/e2e/flight-requirements.spec.js`: a seeded missed period appears in the list and an admin can excuse it (status changes to Excused).
- [ ] **Step 10: Commit** `List past missed periods with excuse actions`

Rolling requirements keep their lapses on the pilot page; this list covers periodic requirements only.

### Task 4: Page names, /currency redirect and Home/End on the tabs

**Files:**
- Modify: `frontend/src/components/layout/Layout.jsx` (`pageTitles`)
- Modify: `frontend/src/App.jsx` (route)
- Modify: `frontend/src/pages/CompliancePage.jsx` (`ComplianceTabs` key handler)
- Test: `frontend/src/components/layout/Layout.test.jsx`, `frontend/src/pages/CompliancePage.test.jsx`, `frontend/src/App.test.jsx` or the existing routing test

**Interfaces:**
- Produces: `pageTitle(pathname: string) -> string` exported from `Layout.jsx`.

- [ ] **Step 1: Write the failing tests**
  - `pageTitle`: `'/compliance'` gives `'Compliance'`; `'/flights/123'` gives `'Flight Details'`; `'/pilots/4'` gives `'Pilot Details'`; `'/fleet/vehicles/2'` gives `'Vehicle Details'`; `'/flights'` still gives `'Flights'`; an unknown path gives `'Drone Unit Manager'`.
  - Compliance tabs: Home focuses and selects the first tab, End the last; both call `preventDefault` (the page does not scroll).
  - Routing: `/currency` and `/currency/anything` land on `/compliance?tab=requirements`.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement**
  - `pageTitle` matches exact paths first, then patterns via `matchPath`. Give every route in `App.jsx` a title, using the sidebar's label for list pages and "<Thing> Details" for `:id` routes (Flight, Pilot, Vehicle, Battery, Controller, Sensor, Attachment, Dock, Equipment for `/fleet/other/:id`).
  - Add `<Route path="/currency/*" element={<LegacyRequirementsRedirect />} />` beside the `/requirements` route.
  - Tabs: Home goes to index 0, End to the last index, with `e.preventDefault()`; arrows unchanged.
- [ ] **Step 4: Run the tests and lint; confirm they pass.**
- [ ] **Step 5: Commit** `Name every page in the header and redirect old currency links`

### Task 5: Fleet Actions column, cert checkbox and coordinate rounding

**Files:**
- Modify: `frontend/src/pages/FleetPage.jsx` (table at about line 151)
- Modify: `frontend/src/components/certifications/MatrixView.jsx` (`MatrixCell`)
- Modify: `frontend/src/pages/FlightDetailPage.jsx` (`coordinates`, edit form initial values)
- Modify: `frontend/src/lib/utils.js` (`roundCoord`)
- Test: `frontend/src/pages/FleetPage.test.jsx`, `frontend/src/pages/CertificationsPage.test.jsx`, `frontend/src/pages/FlightDetailPage.test.jsx`, `frontend/src/lib/utils.test.js`

**Interfaces:**
- Produces: `roundCoord(value: number | null | undefined) -> number | null` (7 decimals, null stays null).

- [ ] **Step 1: Write the failing tests**
  - Fleet: as a user without manage rights, no "Actions" header and no empty cell per row; with manage rights the column is there; the empty-state `colSpan` matches the column count in both cases.
  - Matrix: with manage rights, no checkbox on a cert whose type has `has_expiration: false`, and none on a cert of an expiring type with no `expiration_date`; a checkbox on an expiring cert, rendered inside the same flex group as its status icon (not absolutely positioned).
  - `roundCoord(45.123456799999997)` is `45.1234568`; `roundCoord(null)` is `null`.
  - Flight detail shows `45.1234568, -100.9876543` for a landing of `45.123456799999997, -100.98765430000001`, and the edit form starts with the rounded values.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement**
  - Fleet: render the Actions header and cell only when the row-actions condition is true for the current user; fix `colSpan`.
  - Matrix: `selectable = ctx.canManage && id && ct.has_expiration && cell.cert?.expiration_date`; place the checkbox and `CertStatusIcon` in an inline flex group centred in the cell; remove `absolute top-1 left-1`.
  - `roundCoord` uses `Math.round(value * 1e7) / 1e7`; use it in `coordinates()` and in the edit form's initial coordinate values.
- [ ] **Step 4: Run the tests and lint; confirm they pass.**
- [ ] **Step 5: Commit** `Tidy the fleet table, cert checkboxes and coordinate display`

### Task 6: Version 3.7.1 and release documents

**Files:**
- Modify: `backend/app/constants.py` (`APP_VERSION = "3.7.1"`)
- Modify: `ROLLBACK.md` (3.7.1 row; rollback from 3.7.1 is the same as from 3.7.0, no new migration)
- Modify: `docs/upgrading.md` (3.7.1 notes; background fill time "about 35 to 40 minutes" for a large history)
- Modify: `docs/TEST_CHECKLIST.md` (section 41, "Staging Fixes in 3.7.1", one checkbox per requirement above, plus a row in the results table)
- Modify: the user manual content (`frontend/src/pages/manual/content.json`) where it describes the flights list columns and the Flight Requirements tab

- [ ] **Step 1: Make the edits.**
- [ ] **Step 2: Run the full frontend suite, lint on changed files, and the backend suite; all pass.**
- [ ] **Step 3: Commit** `Prepare 3.7.1`
