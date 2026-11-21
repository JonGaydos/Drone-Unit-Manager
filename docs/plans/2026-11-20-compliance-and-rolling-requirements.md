# Compliance and Rolling Requirements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove currency, add rolling Flight Requirements, let requirements drive currency's 15 compliance points, and merge Flight Requirements into a three-tab Compliance page.

**Architecture:** Currency code, routes, UI and tables go. A new `rolling` period type is evaluated daily by its own service that reuses the requirement flight loading and counting; lapses and rolling excusals live in two new tables (migration 0018, which also drops the currency tables). A standing service decides which pilots cost score points, and the dashboard score uses it in place of currency. The frontend folds the requirements page into Compliance tabs.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, React 19, Vitest, Playwright.

**Spec:** `docs/specs/2026-11-20-compliance-and-rolling-requirements-design.md` (binding), on top of `docs/specs/2026-11-19-flight-requirements-design.md`.

## Global Constraints

- Branch `compliance-requirements`, cut from local `requirements-page` (`e4926b2`, the unpushed page move); its Active-at-top switch, Switch on/off and tile changes stay, the standalone page and sidebar entry are replaced by Compliance tabs. One PR. Commits with `git -c user.name=Claude -c user.email=noreply@anthropic.com commit`, one-line subjects, no trailer lines. Stage only changed files.
- Migration 0018 is approved only together with this plan; do not change its shape without asking.
- The other compliance score parts (certifications 25, registrations 20, maintenance 20, incidents 20, operating authority deductions and cap) do not change.
- Counting rules unchanged: reviewed flights that count toward unit totals.
- Status strings: periodic `met`, `on_track`, `pending_review`, `missed`, `excused`; rolling `current`, `lapsed`, `not_yet_due`, `excused`.
- Public repo: no real names or locations. No em dashes or emojis. Zero new SonarCloud issues (complexity under 15, no nested ternaries or nested template literals, no lambda capturing a loop variable, no composite asserts in tests, no unused imports, `<fieldset>` not `role="group"`). S1192 in migrations is accepted by the owner.
- Tests: backend `cd backend && DATA_DIR=$(mktemp -d) PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 ~/venvs/dum/bin/pytest -q -p no:cacheprovider <paths>` (full suite about 25 minutes); frontend `cd frontend && npx -y node@22 node_modules/vitest/vitest.mjs run [paths]`, lint `npx -y node@22 node_modules/eslint/bin/eslint.js <files>`; e2e `cd frontend && PATH=/tmp/pybin:$PATH PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright LD_LIBRARY_PATH=$HOME/.local/chrome-libs/root/usr/lib/x86_64-linux-gnu npx -y node@22 node_modules/@playwright/test/cli.js test --trace off [spec]`.
- Use the `impeccable` skill for interface work.

## Review Focus

1. **A rolling window across a month end or a DST change.** The window covers exactly N days (or weeks, or calendar months back) and the lapse date is the day the oldest needed flight ages out. Pinned in Task 3.
2. **A pilot who is both lapsed on a rolling requirement and missed a periodic one.** They cost points once, not twice. Pinned in Task 5.
3. **The daily job and a page load both seeing a lapse.** One lapse row, closed once. Pinned in Task 4.
4. **A backup made on 3.6.0 restored on 3.7.0.** It restores, skipping the currency tables, and requirements come back intact. Pinned in Task 2.
5. **A viewer opening Compliance.** Overview and Flight Requirements read-only; no Setup tab; no manage-only requests. Pinned in Task 6.

---

### Task 1: Remove currency (code and UI, tables stay until Task 2)

**Files:** delete `backend/app/routers/currency.py` and its tests (`tests/test_currency*.py`), the currency rule frontend (Settings Currency Rules card and modal, Compliance `CurrencyStatusSection` and reminders modal, Dashboard `CurrencyRiskTile`, PilotDetail Currency Status card) and their tests; modify `backend/app/main.py`, `routers/pilots.py` (Needs Attention currency items), `routers/dashboard.py` (currency status and fields), `services/requirement_eval.py` (import `counted_flights_filter` from a new home), `services/api_tokens.py` (drop `/api/currency`), `services/permissions.py` (rename the feature label "Certifications and currency" to "Certifications"; keys unchanged), `services/pilot_contacts.py` (comment), `frontend/src/lib/utils.js` (review-message text), `AuditLogPage.jsx` (drop currency entity types), e2e `currency-rules.spec.js`.

**Interfaces:**
- Produces: `counted_flights_filter()` moved to `backend/app/services/flight_scope.py` (same behavior).
- Produces: `GET /api/dashboard/compliance` no longer returns `pilot_currency_status`, `currency_rules_active`, `pilots_lapsed`; the score temporarily has no currency part until Task 5.
- `fleet_models.backfill_rule_models` and the pre-0016 restore backfill are removed with the currency models in Task 2.

- [ ] **Step 1:** Write failing tests: `/api/currency/*` returns 404; Needs Attention has no currency items; the compliance payload has no currency keys; the permission feature label reads "Certifications"; frontend: no Currency Rules card, no Currency Risk tile, no Currency Status card or section, no "Send currency reminders".
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Remove the code. Grep the repo for `currency` afterwards and justify every remaining hit (models and migrations until Task 2; historical migrations stay).
- [ ] **Step 4:** Run the backend tests that import dashboard, pilots, requirements, permissions and tokens, and the full frontend suite. Expected: PASS.
- [ ] **Step 5:** Commit: `Remove currency`.

### Task 2: Migration 0018 and the new tables

**Files:** create `backend/migrations/versions/0018_rolling_requirements.py`, `backend/tests/test_rolling_models.py`; modify `backend/app/models/flight_requirement.py`, `models/__init__.py`, delete `models/currency_rule.py`, modify `routers/backup.py`, `services/fleet_models.py`, `tests/test_audit_capture.py` (builders).

**Interfaces:**
- `FlightRequirementLapse` (`flight_requirement_lapses`): `requirement_id` FK cascade, `pilot_id` FK pilots cascade, `lapsed_on` Date, `recovered_on` Date nullable, `created_at`, `updated_at`; unique (requirement_id, pilot_id, lapsed_on).
- `FlightRequirementExcusal` (`flight_requirement_excusals`): `requirement_id` FK cascade, `pilot_id` FK pilots cascade, `excused_until` Date, `reason` String(500) nullable, `excused_by_id` FK users nullable, timestamps; unique (requirement_id, pilot_id).
- Migration 0018 (`down_revision = "0017_flight_requirements"`): create both tables (`sqlite_autoincrement=True`), then drop `currency_rule_models` and `currency_rules`. Downgrade: recreate the two currency tables empty (shape as in 0016/baseline) and drop the new tables.
- Backups: add both tables to `EXPORT_ORDER`; remove the currency tables from it; restoring a backup that contains `currency_rules` or `currency_rule_models` skips them; remove the pre-0016 backfill. Pilot merge reassigns both new tables (conflict keys: lapses `["requirement_id", "lapsed_on"]`, excusals `["requirement_id"]`).

- [ ] **Step 1:** Write failing tests: 0017 to 0018 to 0017 on a temp database (with a currency rule row present before upgrade); backup manifest counts both new tables and no currency tables; a 3.6.0-shaped backup with currency tables restores; pilot merge moves lapses and excusals; audit builders for both models.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement; check the hand-written migration against autogenerate on a throwaway database.
- [ ] **Step 4:** Run the new tests, `test_schema.py`, `test_backup*.py`, `test_autoincrement.py`, `test_audit_capture.py`, `test_pilots.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `Add lapse and excusal tables and drop currency tables`.

### Task 3: Rolling evaluation

**Files:** create `backend/app/services/requirement_rolling.py`, `backend/tests/test_requirement_rolling.py`; modify `backend/app/schemas/requirement.py` (validation), `services/requirement_eval.py` (share helpers, do not duplicate), `services/requirement_periods.py` (`PeriodType` gains `rolling`; period functions return None for it).

**Interfaces:**
- `rolling_window(day: date, length: int, unit: str) -> tuple[date, date]`: N days or weeks ending on `day` inclusive; months: from the same day N months back plus one day (clamped), to `day`.
- `@dataclass class RollingProgress: pilot_id: int; status: str; totals: dict[str, dict]; met_by_model: dict[str, bool]; lapse_date: date | None; excused_until: date | None; excluded_no_takeoff: int; unreviewed_in_window: int`
- `evaluate_rolling(db, req, today: date) -> dict[int, RollingProgress]`: same flight loading, scope, purposes, time-of-day and counting as periodic requirements, over `rolling_window(today, ...)`. Status: `excused` when an excusal covers today; `not_yet_due` while today is before (later of requirement start and the pilot's join date) plus one window; else `current` when every required key meets every set target, else `lapsed`. `lapse_date` when current: the first future day on which the window, sliding forward with no new flights, no longer meets a target (walk the needed flights newest to oldest as currency's expiry did).
- Validation: `period_type == "rolling"` needs `span_length` 1..365 and `span_unit`; `recurring`, `end_date`, window days and every-months must be empty/false; start date required.

- [ ] **Step 1:** Write failing tests: windows for days, weeks and months across a month end and DST; current with exact target; lapse date for minutes-only, flights-only and both; each separately with one model short is lapsed; time-of-day window counted; unreviewed and non-unit flights excluded; not_yet_due for a new pilot and a new requirement; excusal until a date; validation refusals.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the new tests and the existing requirement eval and period tests. Expected: PASS.
- [ ] **Step 5:** Commit: `Evaluate rolling flight requirements`.

### Task 4: Lapse tracking, API, emails and outputs for rolling requirements

**Files:** create `backend/app/services/requirement_lapses.py` and tests; modify `routers/requirements.py`, `schemas/requirement.py`, `services/requirement_notify.py`, `services/scheduler.py`, `services/email_digest.py`, `routers/pilots.py` (Needs Attention), `routers/export.py`, `routers/reports.py`, `services/requirement_results.py` (`open_misses` and flags include open lapses).

**Interfaces:**
- `sync_lapses(db, today: date) -> tuple[list[FlightRequirementLapse], list[FlightRequirementLapse]]`: for every active rolling requirement and assigned pilot, open a lapse row when status is `lapsed` and none is open, close the open row (`recovered_on = today`) when status is `current`, `excused` or `not_yet_due`. Returns (opened, closed). Safe to run twice; runs first in `/status`, `/pilots/{id}`, `/flags` (with the existing IntegrityError guard) and in the daily job.
- API: `/status` rows for rolling requirements carry `rolling: {window_start, window_end, pilots: [RollingProgress + pilot_name]}` instead of periods; `/pilots/{id}` adds `rolling` entries and `lapses` history; `POST /api/requirements/{id}/excuse` accepts `{pilot_id, excused_until, reason}` for rolling requirements (date required, today or later; `excused_until: null` removes it); `DELETE /api/requirements/{id}/lapses/{lapse_id}` admin only, audited.
- Emails (only when requirement emails are on): reminder when `0 < lapse_date - today <= reminder_days` (notice kind `reminder`, keyed by the lapse date), lapse email on each opened lapse to the pilot and managers (notice kind `missed`, keyed by `lapsed_on`). Digest section lists currently lapsed pilots.
- Outputs: Needs Attention item "Lapsed: <name> since <date>"; flags include open lapses (so the pilot list badge and dashboard line work unchanged); CSV and report include lapse rows (status `lapsed`, period start = lapsed_on, period end = recovered_on or blank).

- [ ] **Step 1:** Write failing tests for each interface above, including: a page load and the daily job on the same day open one lapse; recovery closes it once; an excusal closes an open lapse and suppresses emails; emails off sends nothing.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the requirements API, notify, outputs, results and permission tests. Expected: PASS.
- [ ] **Step 5:** Commit: `Track rolling lapses with emails and outputs`.

### Task 5: Requirements in the compliance score

**Files:** create `backend/app/services/requirement_standing.py` and tests; modify `routers/dashboard.py`, `schemas/dashboard.py`.

**Interfaces:**
- `pilots_not_in_standing(db, today: date) -> tuple[set[int], int]`: (active pilot ids that missed the most recently saved period of any active periodic requirement, unless excused, or have an open lapse on any active rolling requirement; number of active requirements).
- `_calc_compliance_score(...)` replaces `pilots_lapsed`/`currency_rules_active` with `pilots_out_of_standing`/`requirements_active`: deduction `(pilots_out_of_standing / pilots) * 15` only when `requirements_active > 0` and `pilots > 0`.
- The compliance payload adds `pilots_out_of_standing`, `requirements_active`, a `score_breakdown` list `[{area, points_lost, detail}]` for every part (certifications, registrations, maintenance, incidents, requirements, operating authority), and keeps `requirements_score` (12-month) for display.

- [ ] **Step 1:** Write failing tests: a pilot missed on one requirement and lapsed on another counts once; excused pilots do not count; a periodic miss stops counting once a newer period of that requirement is saved; no active requirement means no deduction; every other score part gives the same result as before (characterization test against the old function's numbers); the breakdown sums to 100 minus the score (before the authority cap).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the dashboard, compliance and requirements tests. Expected: PASS.
- [ ] **Step 5:** Commit: `Count flight requirements in the compliance score`.

### Task 6: Three-tab Compliance page and rolling UI

**Files:** modify `frontend/src/pages/CompliancePage.jsx` (tabs), the requirements components (move the page body into the Flight Requirements tab and the setup cards into Setup), `FlightRequirementsPage.jsx` (delete; `/requirements` redirects), `lib/sidebarNav.js` and `CommandPalette.jsx` (remove the separate entry), `SettingsPage.jsx` (redirect target), requirement form (Rolling option with window length and unit; hides recurring, end date and period-only fields), `ThisPeriodTile.jsx`, `PilotRequirementsCard.jsx`, `RequirementSummary.js` (rolling summary, e.g. "All active pilots must have 1 hour on any aircraft in any 90 days, from Dec 1, 2026."), backend `routers/calendar.py` link target, tests.

**Behavior:**
- Tabs: Overview (score with breakdown, stat cards with "Missed or lapsed" in place of "Out of Currency", This Period section, Items Requiring Attention, 12-month requirements figure), Flight Requirements (list and progress; manage controls only with Manage), Setup (templates and settings; only with Manage). `?tab=` deep links: `overview`, `requirements`, `setup`. `/requirements` and `/settings?tab=requirements` redirect to `/compliance?tab=requirements`. Calendar links point there.
- Rolling in the list, tile and pilot card: per pilot Current (lapses on <date>), Lapsed (since <date>), Not yet due, or Excused until <date>; the pilot card shows the lapse history; excuse for rolling asks for an "until" date.
- Keep each component under complexity 15; CompliancePage edits must not add to its existing SonarCloud findings.

- [ ] **Step 1:** Load the `impeccable` skill. Write failing tests: tabs and visibility per role (viewer: no Setup, no manage requests); deep links and redirects; Missed or lapsed card; score breakdown rendering; rolling form fields and body; rolling summary sentence; rolling statuses in the tile and pilot card; rolling excuse with a date.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full frontend suite and lint on touched files. Expected: PASS, no new findings.
- [ ] **Step 5:** Commit: `Merge flight requirements into the Compliance page`.

### Task 7: Docs, release notes, end-to-end, review

**Files:** `frontend/src/pages/manual/content.json` (remove currency topics; requirements topics point at Compliance; rolling requirements; score), manual pictures (regenerate flight requirements and compliance pictures; remove the currency picture and shot), `docs/TEST_CHECKLIST.md` (replace section 38 with a rolling and score section; update 39 for the page), `docs/upgrading.md` (3.7.0 section: currency removed, API removed, migration 0018, rolling requirements, score change, page move), `ROLLBACK.md` (3.7.0 row; roll back to 3.6.0 by downgrading to `0017_flight_requirements`; currency tables come back empty), `backend/app/constants.py` (`APP_VERSION = "3.7.0"`), e2e.

- [ ] **Step 1:** E2E: create a rolling requirement from the Compliance page and see it on Overview and the dashboard tile, then delete it; remove the currency journey. Run twice.
- [ ] **Step 2:** Update the manual, pictures (demo data only, checked by eye), checklist, upgrading notes, rollback steps and version.
- [ ] **Step 3:** Run the full backend, frontend and e2e suites; migration 0018 up, down, up on a temp database copied from a 0017 schema.
- [ ] **Step 4:** Whole-branch review by a fresh reviewer on the most capable model; one fix wave.
- [ ] **Step 5:** Report to the owner and ask for the go to push. Then PR, merge on green CI and zero new SonarCloud issues, and ask before tagging `v3.7.0`.

---

## Interface improvements (added 2026-11-20; spec section "Interface improvements in the same release")

Run after Task 6 and before Task 7, so Task 7's docs, pictures and review cover them. Migration 0018 (Task 2) also adds `users.dashboard_layout` and `users.analytics_layout` (JSON, nullable) and `vehicles.hourly_operating_cost` (Float, nullable).

### Task 6a: Fixed page header
- Files: `frontend/src/components/layout/Layout.jsx`, `TopBar.jsx`, tests.
- The desktop top bar is sticky at the top of the content column (solid background, border, above page content); only the content scrolls. Phone top bar unchanged. Check pages with their own sticky elements (tables, modals, the flights bar) still layer correctly.
- Tests: the top bar has the sticky classes on desktop; a long page keeps it in view (component test on classes; e2e scroll check in Task 7).
- Commit: `Keep the page header in place while content scrolls`.

### Task 6b: Arrangeable dashboard and analytics
- Files: add `@dnd-kit/core` and `@dnd-kit/sortable` (pinned, lockfile updated with npm); create `frontend/src/components/layout/ArrangeableGrid.jsx` (+ tests) used by `DashboardPage.jsx` and `AnalyticsPage.jsx`; backend `models/user.py`, `schemas/user.py`, `routers/auth.py` (`PATCH /api/auth/me` accepts `dashboard_layout`/`analytics_layout`: `{"order": [tile ids], "hidden": [tile ids]}`, validated: known tile id strings, at most 50, no duplicates; `null` clears), `routers/settings.py` (admin keys `default_dashboard_layout`, `default_analytics_layout`, same validation), `UserOut` returns both layouts.
- Interfaces: each tile gets a stable id (e.g. `recent-flights`, `currency-risk` removed, `this-period`, `locations`); `ArrangeableGrid({ tiles: [{id, span, render, visible}], layout, defaultLayout, onSave, canSetDefault })`.
- Behavior: Edit layout / Save / Cancel / Reset to default; admins also see "Save as unit default"; unknown ids in a saved layout are ignored; new tiles appended and on; permission-hidden tiles never render; keyboard reordering in edit mode; works on touch.
- Tests: backend validation and own-account only (a user cannot set another user's layout); frontend reorder by keyboard, hide and show, save body, reset, admin default, unknown and new ids, permission-hidden tile stays hidden.
- Commit: `Let users arrange their dashboard and analytics`.

### Task 6c: Always-present flights selection bar
- Files: `frontend/src/pages/FlightsPage.jsx`, tests.
- The selection bar is always rendered above the table for users with `flights.review`: "0 selected" with every control disabled (and an accessible reason) when nothing is selected; ticking rows only updates the count and enables the controls. It is sticky just below the fixed page header (Task 6a) while the list scrolls. Same controls as today.
- Tests: the bar is present with nothing selected and its controls are disabled; ticking a row enables them and does not insert anything above the table; clearing the selection disables them again; users without review never see the bar.
- Commit: `Keep the flights selection bar in place`.

### Task 6d: Certifications views
- Files: `frontend/src/pages/CertificationsPage.jsx` (split into view components under `frontend/src/components/certifications/`), tests.
- Views per the spec: Matrix (pinned pilot column and header, status icon cells with accessible labels and the date in a tooltip), By pilot (cards), By urgency (Expired, 30, 60, 90 days, Current). View switch remembered in localStorage; By pilot default under the `sm` breakpoint when nothing is stored. Existing filters and actions keep working; bulk renew stays in the Matrix view.
- Keep each component under complexity 15; this is also the chance to bring the page's large functions down without changing behavior.
- Tests: each view renders the same data; filters apply in each view; the stored view is restored; actions open the right modals.
- Commit: `Add pilot and urgency views to certifications`.

### Task 6e: Distance and landing location from telemetry
- Files: create `backend/app/services/flight_track.py` (+ tests); modify the telemetry sync and log import paths (`services/sync_manager.py`, `services/flight_log_import.py`, `services/parrot_import.py`) to call it after telemetry is stored; `services/jobs.py` or the scheduler for a one-time, resumable background backfill (batches, newest first, progress logged, safe to rerun); reverse geocoding through the existing `_reverse_geocode` helper with its rate limit.
- Interfaces: `track_summary(points) -> {distance_m: float | None, landing_lat, landing_lon}` over ordered telemetry points; skip points with missing or out-of-range coordinates, and segments implying more than 60 m/s; `fill_track_fields(db, flight) -> bool` fills only fields that are empty; landing time = takeoff + duration when missing.
- Tests: a known square path gives the expected distance within 1%; a GPS jump is skipped; no valid points gives None; typed values are not overwritten; backfill is idempotent and resumes.
- Commit: `Work out flight distance and landing location from telemetry`.

### Task 6f: Operating cost per flight hour
- Files: `backend/app/models/vehicle.py` (column in migration 0018), vehicle schemas and routes, `routers/flights.py` (response field `operating_cost_estimate` when no manual cost), `routers/reports.py` (cost totals where reports already show hours), frontend Fleet vehicle form and vehicle detail (rate field), FlightDetailPage (shows the cost, marked "estimated" when calculated), tests.
- Rules: rate optional, 0 to 100000; estimate = round(duration hours x rate, 2); manual `operating_cost` wins; no rate and no manual cost shows nothing.
- Tests: estimate math; manual wins; no rate means no value; report totals; permissions follow `fleet.manage` for the rate.
- Commit: `Estimate flight operating cost from an hourly rate`.
