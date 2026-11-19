# Flight Requirements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let supervisors assign fixed-period flight requirements ("fly 1 hour in October", "15 minutes on each model per quarter", "1 hour at night in the next two weeks"), track every pilot's progress, keep each closed period's result, and score the unit on them, without changing currency or the compliance score.

**Architecture:** Two pure services hold the hard logic: period math (which period contains a date) and time windows (how many minutes of a flight fall inside a clock window or civil-twilight night). An evaluation service applies them to reviewed, counted flights for each assigned pilot; a snapshot service saves results once a period's grace time ends. A new router serves the API, the daily scheduler closes periods and sends reminders, and the frontend adds a Settings tab, a dashboard card and score, a pilot section, a pilot-list badge, calendar deadlines, a report and a digest section.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, APScheduler, `astral` (new), pytest, React 19, Vitest, Playwright.

**Spec:** `docs/specs/2026-11-19-flight-requirements-design.md`. It is binding; this plan is change 2 of its "Build order". Change 1 (currency model picker, migration 0016) is merged; this plan reuses its `normalize_model`, `fleet_models` and `FleetModelPicker`.

## Global Constraints

- Branch `flight-requirements` from `main` (already created at `3550386`). One PR, separate commits, one-line imperative subjects, no attribution lines. Commit with `git -c user.name=Claude -c user.email=noreply@anthropic.com commit`.
- Migration 0017 is approved by the owner with this plan, in the shape Task 3 states. Do not change its shape without asking.
- Currency, its reminders and the compliance score do not change in any way. Nothing here touches `_calc_compliance_score` or currency evaluation.
- Only flights that pass both `counted_flights_filter()` (reviewed) and `counted_flight_clause()` (counted toward unit totals, flight and pilot) count. Flights with an unconfirmed pilot match count once reviewed.
- Model matching uses `normalize_model` everywhere. Purpose matching compares `Flight.purpose` case-insensitively after trimming.
- Times: a takeoff stored by every source except `parrot_gutma` is naive UTC; `parrot_gutma` is local wall-clock time in the display zone. The display zone comes from `display_zone(db)`. Clock windows always use the display zone; night always uses the unit default location (`org_default_lat`, `org_default_lon`).
- Unit settings, with defaults: `requirements_grace_days` = 14, `fiscal_year_start_month` = 10.
- Statuses, exact strings: `met`, `on_track`, `pending_review`, `missed`, `excused`.
- The repository is public: no real names, locations or tail numbers anywhere, including fixtures and screenshots.
- Do not fix unrelated code or unrelated SonarCloud findings. Zero new SonarCloud issues: cognitive complexity under 15, no nested ternaries or nested template literals, no lambda capturing a loop variable, no `role="group"` on a div (use `<fieldset>`), no unused imports. S1192 in migrations is left alone.
- Backend tests: `cd backend && DATA_DIR=$(mktemp -d) PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 ~/venvs/dum/bin/pytest -q -p no:cacheprovider <path>`. Full suite takes about 25 minutes; give it a 30-minute timeout.
- Frontend tests on Node 22: `cd frontend && npx -y node@22 node_modules/vitest/vitest.mjs run [path]`; lint `npx -y node@22 node_modules/eslint/bin/eslint.js <paths>` (the repo has pre-existing lint findings; add none).
- E2E on this container: `cd frontend && PATH=/tmp/pybin:$PATH PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright LD_LIBRARY_PATH=$HOME/.local/chrome-libs/root/usr/lib/x86_64-linux-gnu npx -y node@22 node_modules/@playwright/test/cli.js test --trace off` (`/tmp/pybin/python` wraps `~/venvs/dum/bin/python`; recreate it if missing).
- Use the `impeccable` skill for interface work. Semantic theme color variables only. No em dashes or emojis in anything written.

## Review Focus

1. **A flight that crosses midnight, a period end, or a daylight saving change.** Only its minutes inside the window and inside the period count, and the hour that repeats or vanishes on a DST night is counted as real elapsed time. Pinned in Task 4.
2. **A monthly window that rolls into the next month in a short month** (19th to 5th starting January 31, or a 31st start in February). Periods tile with no gap and no overlap, and the 31st means the month's last day. Pinned in Task 3.
3. **A flight reviewed late.** Reviewed inside the grace time, it counts; reviewed after the period is saved, the saved result does not change unless an admin recalculates. Pinned in Task 7.
4. **A pilot who joins, leaves, or is excused partway through.** Joining after the period starts is excused automatically and can be un-excused; an inactive pilot drops from open periods but keeps saved history. Pinned in Tasks 6 and 7.
5. **A requirement edited while a period is open.** The open period uses the new settings; saved periods keep their snapshot; the dashboard and pilot pages agree. Pinned in Task 7.

---

## Decisions this plan makes (rulings on gaps the spec leaves)

| Gap | Decision |
|---|---|
| Spec says "Requirements tab" on Pilot detail, but that page has no tabs | A "Flight Requirements" card on Pilot detail, below Currency Status |
| Where excusals live before a period is saved | A `flight_requirement_results` row with `saved_at` NULL holds the excusal override; saving fills in the rest |
| "Pilot added partway through" for All active pilots | Pilot `created_at` (local date) after the period start; for selected pilots, the `added_at` of their assignment row, whichever is later |
| "A model added to the fleet joins the next period" for All active models | A model belongs to a period when one of its non-retired vehicles has `created_at` on or before the period start |
| Emails sent "once" | A `flight_requirement_notices` table, unique on requirement, pilot, period start and kind |
| Supervisors cannot write unit settings (admin only) | `GET/PUT /api/requirements/settings` guarded by `requirements.manage` writes the two requirement settings |
| `/api/currency/models` accepts one permission key | A second route, `GET /api/requirements/models`, guarded by `requirements.manage`, returns the same `fleet_models(db)` |

---

### Task 1: Baseline and the astral dependency

**Files:**
- Modify: `backend/requirements.txt`, `backend/requirements.lock.txt`

- [ ] **Step 1:** Run the full backend and frontend suites on the branch. Expected: all pass. Record the counts. Stop and report if anything fails.
- [ ] **Step 2:** Add `astral==3.2` (or the latest 3.x on PyPI, pinned exactly) to `requirements.txt` with a one-line comment: civil twilight for night requirements. Regenerate the lock with the command the CI guard prints: `cd backend && uv pip compile requirements.txt --generate-hashes --python-platform linux --python-version 3.12 -o requirements.lock.txt`, and install it into `~/venvs/dum`.
- [ ] **Step 3:** Check `git diff requirements.lock.txt` adds only `astral` (and its dependencies, if any) and changes no other pin. If other pins moved, restore them and report.
- [ ] **Step 4:** Commit: `Add astral for civil twilight times`.

### Task 2: Period math

**Files:**
- Create: `backend/app/services/requirement_periods.py`, `backend/tests/test_requirement_periods.py`

**Interfaces:**
- Produces:
  - `PeriodType = Literal["calendar_month", "calendar_quarter", "calendar_year", "fiscal_quarter", "fiscal_year", "monthly_window", "span", "custom", "every_n_months"]`
  - `@dataclass(frozen=True) class PeriodSpec: period_type: PeriodType; start: date; end: date | None; recurring: bool; window_start_day: int | None = None; window_end_day: int | None = None; span_length: int | None = None; span_unit: Literal["days", "weeks", "months"] | None = None; every_months: int | None = None; fiscal_start_month: int = 10`
  - `period_containing(spec: PeriodSpec, day: date) -> tuple[date, date] | None`: the inclusive period holding `day`, or None (before the first period, after the end date, between monthly windows, or after a one-time period).
  - `periods_between(spec: PeriodSpec, first: date, last: date) -> list[tuple[date, date]]`: every period that overlaps `[first, last]`, in order.
  - `first_period(spec: PeriodSpec) -> tuple[date, date]`.

Rules (from the spec):
- Calendar and fiscal types: the first period is the one containing `start`, and later periods follow back to back. Fiscal quarters start at `fiscal_start_month` (10 means Oct-Dec is Q1).
- `monthly_window`: each period runs from `window_start_day` of a month to `window_end_day` of the same month, or of the next month when the end day is earlier than the start day. A day past a month's end means that month's last day. The first period is the first one whose start is on or after `start`.
- `span`: `span_length` days, weeks or months from `start`, and when recurring, the next span starts the day after. Months add by calendar month, clamped to the month's last day.
- `every_n_months`: periods of `every_months` calendar months from `start`.
- `custom`: one period `[start, end]`; `recurring` is ignored.
- One-time specs have only the first period. A recurring spec stops at `end` (no period starts after it).

- [ ] **Step 1: Write failing tests** (one per line, exact values):
  - `test_calendar_month`: start 2026-10-01; 2026-10-31 gives (2026-10-01, 2026-10-31); 2026-11-01 gives (2026-11-01, 2026-11-30); one-time gives None for November.
  - `test_calendar_quarter_and_year`: 2026-11-15 gives (2026-10-01, 2026-12-31) and (2026-01-01, 2026-12-31).
  - `test_fiscal_quarter_october_start`: 2027-01-05 gives (2027-01-01, 2027-03-31); fiscal year for 2026-10-01 gives (2026-10-01, 2027-09-30) and for 2026-09-30 gives (2025-10-01, 2026-09-30).
  - `test_fiscal_quarter_other_start_month`: start month 7; 2026-08-01 gives (2026-07-01, 2026-09-30).
  - `test_monthly_window_rolls_into_next_month`: 19 to 5, start 2026-11-19; 2026-12-03 gives (2026-11-19, 2026-12-05); 2026-12-10 gives None; 2026-12-19 gives (2026-12-19, 2027-01-05).
  - `test_monthly_window_short_month`: 31 to 5, start 2027-01-31; periods are (2027-01-31, 2027-02-05), (2027-02-28, 2027-03-05); 30 to 28 in a leap year gives (2028-01-30, 2028-02-28) then (2028-02-29, 2028-03-28).
  - `test_monthly_window_same_month`: 1 to 10 gives (2026-12-01, 2026-12-10); 2026-12-11 gives None.
  - `test_span_weeks_and_months`: 2 weeks from 2026-11-19 gives (2026-11-19, 2026-12-02); recurring next is (2026-12-03, 2026-12-16); 3 months from 2026-11-30 gives (2026-11-30, 2027-02-27).
  - `test_every_n_months`: 2 months from 2026-11-01 gives (2026-11-01, 2026-12-31), then (2027-01-01, 2027-02-28).
  - `test_custom_range`: (2026-12-01, 2026-12-24); 2026-12-25 gives None.
  - `test_recurring_end_date`: monthly from 2026-10-01 ending 2026-12-15: December is a period, January is None.
  - `test_before_start_is_none`.
  - `test_periods_between_tiles_without_gaps`: recurring calendar month across 2026-10-15 to 2027-01-10 gives four consecutive months.
- [ ] **Step 2:** Run them. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement. Keep each function under complexity 15: one small helper per period family, dispatched from a dict keyed by `period_type`. Use `calendar.monthrange` for month lengths; no new date library.
- [ ] **Step 4:** Run them. Expected: PASS.
- [ ] **Step 5:** Commit: `Add period math for flight requirements`.

### Task 3: Requirement tables, migration 0017, permissions and settings keys

**Files:**
- Create: `backend/app/models/flight_requirement.py`, `backend/migrations/versions/0017_flight_requirements.py`, `backend/tests/test_flight_requirement_models.py`
- Modify: `backend/app/models/__init__.py`, `backend/app/routers/backup.py` (`EXPORT_ORDER`), `backend/app/services/permissions.py` (`_DEFAULT_GRID`), `backend/app/routers/settings.py` (`ALLOWED_SETTING_KEYS`, `PUBLIC_KEYS`), `backend/tests/test_audit_capture.py` (builders, as for `CurrencyRuleModel`), `backend/tests/test_permissions.py` (default grid table)

**Interfaces:**
- Produces models (all with `id` autoincrement; FKs `ondelete="CASCADE"` on `requirement_id`; children via relationships with `cascade="all, delete-orphan"`, `back_populates`, `lazy="selectin"` so audit capture records removals):
  - `FlightRequirement` (`flight_requirements`): `name` String(200), `description` String(1000) nullable, `period_type` String(30), `start_date` Date, `end_date` Date nullable, `recurring` Boolean, `window_start_day`, `window_end_day`, `span_length`, `every_months` Integer nullable, `span_unit` String(10) nullable, `target_minutes` Integer nullable, `target_flights` Integer nullable, `model_mode` String(20) (`all`, `combined`, `each`, `each_all_active`), `time_mode` String(10) (`any`, `clock`, `night`), `window_start_time`, `window_end_time` Time nullable, `reminder_days` Integer default 7, `is_active` Boolean default True, `created_at`, `updated_at` (`UTCDateTime`), `created_by_id`, `modified_by_id` FK users nullable. Relationships `models`, `pilots`, `purposes`.
  - `FlightRequirementModel` (`flight_requirement_models`): `requirement_id`, `model` String(200); unique (requirement_id, model).
  - `FlightRequirementPilot` (`flight_requirement_pilots`): `requirement_id`, `pilot_id` FK pilots cascade, `added_at` UTCDateTime server default now; unique (requirement_id, pilot_id).
  - `FlightRequirementPurpose` (`flight_requirement_purposes`): `requirement_id`, `purpose` String(100); unique.
  - `FlightRequirementResult` (`flight_requirement_results`): `requirement_id`, `pilot_id` FK pilots cascade, `period_start`, `period_end` Date, `status` String(20) nullable, `totals` JSON nullable (`{"<model or *>": {"minutes": int, "flights": int}}`), `target_snapshot` JSON nullable, `excused` Boolean nullable (NULL = no override), `excused_by_id` FK users nullable, `excused_reason` String(500) nullable, `saved_at` UTCDateTime nullable (NULL = open-period override only); unique (requirement_id, pilot_id, period_start).
  - `FlightRequirementTemplate` (`flight_requirement_templates`): `name` String(200) unique, `settings` JSON, timestamps, created and modified by.
  - `FlightRequirementNotice` (`flight_requirement_notices`): `requirement_id`, `pilot_id`, `period_start` Date, `kind` String(20) (`assigned`, `reminder`, `missed`), `sent_at` UTCDateTime; unique (requirement_id, pilot_id, period_start, kind).
  - `FlightRequirement.to_period_spec(fiscal_start_month: int) -> PeriodSpec` (Task 2's type).
- Produces permission rows in a new `("Flight requirements", ...)` group after "Certifications and currency": `requirements.view` (VIEW: YES, YES, YES), `requirements.manage` ("Create, edit, delete, templates": YES, NO, LOCKED), `requirements.excuse` ("Excuse a pilot": YES, NO, LOCKED).
- Produces settings keys `requirements_grace_days`, `fiscal_year_start_month` in `ALLOWED_SETTING_KEYS` and `PUBLIC_KEYS`.

Migration 0017 (`revision = "0017_flight_requirements"`, `down_revision = "0016_currency_rule_models"`): create the seven tables above with `sqlite_autoincrement=True`; downgrade drops them in reverse FK order. No data copy.

- [ ] **Step 1: Write failing tests:** the migration upgrades from 0016 and downgrades cleanly on a temp database (pattern: `tests/test_currency_rule_models.py`); deleting a requirement deletes its children and results; a backup manifest counts all seven tables; `test_registry_defaults_match_spec` includes the three new keys; removing a model or pilot from a requirement records a delete audit entry; the two settings keys are accepted by `PUT /api/settings` for an admin and readable by a pilot.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. Check the hand-written migration against `alembic revision --autogenerate` run on a throwaway SQLite database. Add the tables to `EXPORT_ORDER` after `currency_rule_models` (requirements, templates) and after `pilots` (children, results, notices).
- [ ] **Step 4:** Run the new tests, `test_schema.py`, `test_backup*.py`, `test_autoincrement.py`, `test_audit_capture.py`, `test_permission*.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `Add flight requirement tables and permissions`.

### Task 4: Flight intervals, clock windows and night

**Files:**
- Create: `backend/app/services/requirement_time.py`, `backend/tests/test_requirement_time.py`

**Interfaces:**
- Consumes: `display_zone` from `app/services/local_time.py`.
- Produces:
  - `LOCAL_WALL_CLOCK_SOURCES = frozenset({"parrot_gutma"})`
  - `flight_interval(flight, zone: ZoneInfo) -> tuple[datetime, datetime] | None`: aware start and end in `zone`, from `takeoff_time` and `duration_seconds` (falling back to `landing_time` when duration is missing). None when there is no takeoff time or no length.
  - `clock_windows(day: date, start: time, end: time, zone) -> list[tuple[datetime, datetime]]`: the window that starts on `day`; when `end <= start` it ends on the next day.
  - `night_window(day: date, lat: float, lon: float, zone) -> tuple[datetime, datetime]`: end of evening civil twilight on `day` to start of morning civil twilight on the next day, from `astral`.
  - `minutes_inside(interval, windows, clip: tuple[datetime, datetime]) -> float`: elapsed minutes of `interval` inside the union of `windows`, also inside `clip` (the period from its first day's midnight to the midnight after its last day). Compute on UTC instants so DST is real elapsed time.
  - `windows_for_period(time_mode, period, settings) -> list[tuple[datetime, datetime]]`: every window from the day before the period through its last day.

- [ ] **Step 1: Write failing tests:**
  - `test_parrot_takeoff_is_local`: a `parrot_gutma` takeoff 2026-11-19 22:00 stays 22:00 local; a `skydio_api` takeoff 2026-11-20 04:00 is 22:00 Chicago the day before.
  - `test_no_takeoff_gives_none`.
  - `test_partial_overlap`: 05:30 to 06:15 in a 00:00 to 06:00 window gives 30 minutes.
  - `test_window_crossing_midnight`: 18:00 to 02:00; a flight 01:00 to 03:00 gives 60.
  - `test_flight_longer_than_window` and `test_flight_spanning_two_nights` (two windows summed).
  - `test_clipped_to_period_end`: a flight 23:30 on the period's last day to 00:30 gives 30 minutes with an any-time window.
  - `test_dst_fall_back`: 2026-11-01 00:30 to 02:30 Chicago, clock window 00:00 to 06:00, gives 180 elapsed minutes.
  - `test_night_window_matches_published`: for a fixed public test location (Greenwich, 51.4769, 0.0) on 2026-06-21, civil dusk and dawn within 2 minutes of the values `astral` documents for that date; assert the window is about 4 hours 30 minutes long within 5 minutes.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. On a polar day with no civil twilight, `astral` raises; treat that day as having no night window.
- [ ] **Step 4:** Run them. Expected: PASS.
- [ ] **Step 5:** Commit: `Measure flight minutes inside clock and night windows`.

### Task 5: Progress evaluation

**Files:**
- Create: `backend/app/services/requirement_eval.py`, `backend/tests/test_requirement_eval.py`

**Interfaces:**
- Consumes: Tasks 2 to 4; `counted_flights_filter` (`app/routers/currency.py`); `counted_flight_clause` (`app/services/flight_scope.py`); `normalize_model`, and `Vehicle`.
- Produces:
  - `assigned_pilots(db, req) -> list[Pilot]`: selected pilots that are active, or every active pilot.
  - `scope_models(db, req, period_start: date) -> list[str] | None`: None for `all` and `combined` with no rows; the requirement's model rows for `combined` and `each`; for `each_all_active`, the `fleet_models` names that have a non-retired vehicle created on or before `period_start`.
  - `@dataclass class PilotProgress: pilot_id: int; status: str; totals: dict[str, dict]; met_by_model: dict[str, bool]; excluded_no_takeoff: int; unreviewed_in_period: int; excused: bool; excused_reason: str | None`
  - `evaluate_period(db, req, period: tuple[date, date], today: date, grace_days: int) -> dict[int, PilotProgress]`.

Rules (spec, Evaluation and Time of day): flights load once for all assigned pilots, filtered by both count rules, by purpose when the requirement has purposes, and by date from the day before the period start through its end. With `time_mode == "any"`, a flight counts when `Flight.date` is inside the period, with its whole `duration_seconds`. With a window, a flight with no interval is counted in `excluded_no_takeoff`, and otherwise counts its `minutes_inside` minutes, and one flight when that is above zero. Totals are keyed by the display spelling of the model (from `fleet_models`), or `"*"` for all and combined. Status: `met` when every required key reaches both targets that are set; else `on_track` while `today <= period_end`; else `pending_review` while `today <= period_end + grace_days`; else `missed`. `excused` overrides any status but `met`. Excused: a stored override row wins; otherwise automatic when the pilot joined after the period start (see Decisions). `unreviewed_in_period` counts that pilot's flights in the period with `review_status != "reviewed"` that would otherwise count.

- [ ] **Step 1: Write failing tests:** met on hours only, flights only, and both; combined counts any selected model; each separately fails when one model is short; `each_all_active` ignores a model whose only vehicle was created after the period start; a purpose filter excludes other purposes and flights with no purpose; an unreviewed flight and a flight excluded from totals do not count, and the unreviewed one shows in `unreviewed_in_period`; a flight with no takeoff time is excluded from a clock-window requirement and counted in `excluded_no_takeoff`, but counts for an any-time requirement; on_track, pending_review and missed by date; a pilot created mid-period is excused, and an override row with `excused = False` removes it; an inactive pilot is not assigned.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. One query for flights with `joinedload(Flight.vehicle)`; small helpers for loading, scoping, totals and status so each stays under complexity 15.
- [ ] **Step 4:** Run them. Expected: PASS.
- [ ] **Step 5:** Commit: `Evaluate pilot progress on flight requirements`.

### Task 6: Snapshots, flags and the score

**Files:**
- Create: `backend/app/services/requirement_results.py`, `backend/tests/test_requirement_results.py`

**Interfaces:**
- Consumes: Task 5.
- Produces:
  - `close_due_periods(db, today: date) -> list[FlightRequirementResult]`: for every requirement (active or not) and every period from its first period whose `end + grace_days < today` (a requirement created for a past month is saved on first read), save each assigned pilot's result once (fill an existing override row, or insert). Already-saved rows are left alone. Returns the rows saved now (status `met`, `missed` or `excused`). Safe to run twice.
  - `recalculate_period(db, req, period_start: date, actor) -> int`: re-evaluates and overwrites that period's saved rows (keeping excusals), audited as `recalculate` on the requirement.
  - `open_misses(db, pilot_ids: list[int] | None = None) -> dict[int, list[dict]]`: per pilot, saved `missed` results not cleared. A miss clears when the same requirement's next saved result for that pilot is `met`, or when the miss is excused (`excused = True`).
  - `requirements_score(db, today: date) -> float | None`: met over (met + missed) for saved results whose `period_end` is within the 365 days before `today`; None when there are none. Excused results are left out.
  - `target_snapshot(req) -> dict`: name, period type, targets, model mode and models, time mode and window, purposes.

- [ ] **Step 1: Write failing tests:** a period inside its grace time is not saved, and is saved the day after; running twice saves nothing new; editing the requirement's target after a save does not change the saved row; re-reviewing a flight after a save does not change it; `recalculate_period` changes it and writes an audit entry; a miss is open until the next period is met, or until excused; a one-time miss clears only by excusal; the score over met 3, missed 1, excused 2 is 0.75; a result older than 365 days is left out; no results gives None.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run them. Expected: PASS.
- [ ] **Step 5:** Commit: `Save closed requirement periods and score them`.

### Task 7: Requirements API

**Files:**
- Create: `backend/app/routers/requirements.py`, `backend/app/schemas/requirement.py`, `backend/tests/test_requirements_api.py`
- Modify: `backend/app/main.py` (include router), `backend/tests/test_permission_coverage.py` (`EXPECTED_ROUTE_KEYS`)

**Interfaces:**
- Consumes: Tasks 2 to 6; `fleet_models`; `audit` helpers as used by `currency.py`.
- Produces routes (guard in brackets):
  - `GET /api/requirements` [view]: list with definition fields, `models`, `purposes`, `pilot_ids`, and `current_period` (start, end, days_left) or null.
  - `POST /api/requirements`, `PATCH /api/requirements/{id}`, `DELETE /api/requirements/{id}` [manage]. Validation: name 1 to 200; at least one of `target_minutes` (1 to 100000) and `target_flights` (1 to 10000); period fields required by `period_type` (window days 1 to 31, span length 1 to 365, every months 1 to 24, custom needs `end_date >= start_date`); `time_mode == "clock"` needs both times; `time_mode == "night"` returns 422 "Set the unit default location in Settings before using night" when either location setting is blank; `models` required for `combined`/`each` (2 or more for either), ignored for `all`/`each_all_active`; models deduped by `normalize_model` and purposes case-insensitively, as in currency rules; `reminder_days` 0 to 60. Create, activation and newly added pilots trigger the assignment email (Task 8's `notify_assigned`).
  - `GET /api/requirements/status` [view]: current period per active requirement with each assigned pilot's `PilotProgress`, plus `score` from `requirements_score`. Runs `close_due_periods` first.
  - `GET /api/requirements/pilots/{pilot_id}` [view]: current progress per requirement and saved history (newest first). Runs `close_due_periods` first.
  - `POST /api/requirements/{id}/excuse` [excuse]: body `{pilot_id, period_start, excused: bool, reason?}`; upserts the override, or updates a saved row (and its status: excused, or re-evaluated when un-excused). Audited.
  - `POST /api/requirements/{id}/recalculate` [manage]: body `{period_start}`; admin only inside the handler (spec: "An admin can recalculate"); audited.
  - `GET /api/requirements/flags` [view]: `{pilot_id: [{requirement_id, name, period_start, period_end}]}` from `open_misses`.
  - `GET /api/requirements/models` [manage]: `fleet_models(db)`.
  - `GET, PUT /api/requirements/settings` [view / manage]: `{grace_days: 0..60, fiscal_year_start_month: 1..12}`.
  - `GET, POST /api/requirements/templates`, `PATCH, DELETE /api/requirements/templates/{id}` [manage]: a template stores every requirement field except `start_date`, `end_date` and `pilot_ids`.

- [ ] **Step 1: Write failing tests:** CRUD round trip with models, purposes and pilots; each validation rule above gives 422 (one parametrized test); night refused without a location; supervisor allowed and pilot and viewer refused on every manage and excuse route, viewer and pilot allowed on view routes; excusing an open period, then un-excusing; excusing a saved miss clears its flag; recalculate refused for a supervisor and allowed for an admin; editing a requirement mid-period changes the status endpoint's open period but not a saved one; templates exclude dates and pilots; settings round trip and range checks; `test_permission_coverage.py` passes with the new routes declared.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. Put request and response models in `schemas/requirement.py`; keep handlers thin.
- [ ] **Step 4:** Run the new tests and `test_permission*.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `Add the flight requirements API`.

### Task 8: Emails, digest section and the daily job

**Files:**
- Create: `backend/app/services/requirement_notify.py`, `backend/tests/test_requirement_notify.py`
- Modify: `backend/app/services/email_digest.py`, `backend/app/services/scheduler.py`, `backend/app/routers/requirements.py`, `backend/app/models/notification_preference.py` (default categories)

**Interfaces:**
- Consumes: `send_email` and `render_*` style from `email_digest.py`; `FlightRequirementNotice`; Tasks 5 and 6.
- Produces:
  - `notify_assigned(db, req, pilot_ids: list[int]) -> int`, `send_due_reminders(db, today: date) -> int`, `notify_missed(db, results: list[FlightRequirementResult]) -> int`. Each sends at most once per (requirement, pilot, period start, kind), records a notice row only after a successful send, skips silently when SMTP is not set up or the address is blank, and returns the number sent.
  - Reminder: for each active requirement's open period where `period_end - today == reminder_days` (and `reminder_days > 0`), each assigned pilot not `met` and not excused.
  - Miss email: to the pilot, and to every active user whose role holds `requirements.manage`, one email per saved miss batch per recipient.
  - Digest section `requirements` (permission `requirements.view`): open periods ending within 7 days with pilots not met, periods pending review with their unreviewed flight count, and misses saved in the last 7 days. Add `requirements` to the default `categories` value for new preferences.
  - Scheduler: a daily job at the maintenance alert hour, id `requirements_daily`, that runs `close_due_periods`, then `notify_missed` on the rows it saved, then `send_due_reminders`, each in its own session and try block, logged.

- [ ] **Step 1: Write failing tests:** with SMTP stubbed (follow the existing digest and currency reminder tests), an assignment sends one email per pilot and a second call sends none; a reminder is sent on exactly `reminder_days` before the end and not to a met or excused pilot; a miss emails the pilot and a supervisor but not a viewer; no SMTP means nothing is sent and nothing recorded; the digest includes the section for a viewer and leaves it out when the category is off or the role lacks view; the daily job runs the three steps and tolerates a failure in one.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. Escape every user-provided value in email HTML (`html.escape`), as the currency reminder does.
- [ ] **Step 4:** Run the new tests and the existing digest, notification and scheduler tests. Expected: PASS.
- [ ] **Step 5:** Commit: `Email requirement assignments, reminders and misses`.

### Task 9: Needs Attention, calendar, CSV and PDF report

**Files:**
- Modify: `backend/app/routers/pilots.py` (`get_pilot_needs_attention`), `backend/app/routers/calendar.py`, `backend/app/routers/export.py`, `backend/app/routers/reports.py`
- Test: `backend/tests/test_requirement_outputs.py`

**Interfaces:**
- Consumes: `open_misses`, `evaluate_period`, `periods_between`.
- Produces:
  - Needs Attention: with `requirements.view`, one red item per open miss, category `requirement`, text `Missed requirement: <name> (<period>)`.
  - Calendar: with `requirements.view`, one all-day event per period end inside `[start, end]` for active requirements, `source: "requirement"`, `title: "Due: <name>"`, `category: "requirement"`, link to `/settings?tab=requirements`.
  - `GET /api/export/requirements/{id}/csv` [`requirements.view` and `reports.export`]: saved results with columns Requirement, Period start, Period end, Pilot, Status, Minutes, Flights, Per model, Excused reason. Follow the existing CSV export helpers, including formula-injection escaping.
  - Report type `flight_requirements` in `_dispatch_report` and `REPORT_VIEW_KEYS` (`requirements.view`, `flights.view`): filters by the config date range; summary (requirements, results, met, missed, excused, score) and one row per saved result, using the existing PDF table renderer.

- [ ] **Step 1: Write failing tests:** a missed pilot's Needs Attention has the item and loses it after excusal; calendar shows one deadline per period in range and none without view; CSV has the header and a row per result and escapes a name starting with `=`; the report returns rows and is refused without `requirements.view`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the new tests and the existing pilots, calendar, export and reports tests. Expected: PASS.
- [ ] **Step 5:** Commit: `Show requirements in needs attention, calendar, CSV and reports`.

### Task 10: Settings, Flight Requirements tab

**Files:**
- Create: `frontend/src/components/requirements/RequirementForm.jsx`, `frontend/src/components/requirements/RequirementSummary.js`, `frontend/src/components/requirements/RequirementsTab.jsx`, and a test for each
- Modify: `frontend/src/components/FleetModelPicker.jsx` (optional `mode` and `onModeChange` props), `frontend/src/pages/SettingsPage.jsx` (tab), `frontend/src/test/handlers.js`, `frontend/src/test/permissions.js`

**Interfaces:**
- Consumes: Task 7 routes; `FleetModelPicker`; `can()`.
- Produces: `describeRequirement(form, { pilots, fiscalStartMonth }) -> string` in `RequirementSummary.js`, giving the spec's live summary sentence; for example, a recurring calendar quarter, all active pilots, 15 minutes, each of X10, X2E, LEMUR 2, starting Q4 2026, no end gives "Every quarter, all active pilots must fly 15 min on each of: X10, X2E, LEMUR 2, starting Q4 2026, no end date."

Tab behavior:
- Tab `requirements`, label "Flight Requirements", shown with `requirements.manage`; deep link `/settings?tab=requirements`.
- List: name, period, target, status chip (active/inactive), and actions Edit, Duplicate ("Copy of <name>", opens the form, nothing saved until Save), Save as template, Delete (confirm).
- Form fields per the spec's "Requirement definition" table; only the fields for the chosen period type show; Night is disabled with the reason when the unit location is not set (`org_default_lat` from `/api/settings`); the model picker shows Combined / Each separately when two or more models are selected, and an "All active models" choice under Each separately; purposes as toggle chips from `/api/flights/purposes/list`, default All purposes; Applies to: All active pilots or a pilot multi-select from `/api/pilots/options`; the live summary under the form.
- Templates: a list with rename and delete; "New from template" fills the form.
- Requirement settings: grace days and fiscal year start month, saved through `/api/requirements/settings`.

- [ ] **Step 1: Load the `impeccable` skill. Write failing tests:** `describeRequirement` produces both spec example sentences exactly; the tab is hidden without `requirements.manage`; creating sends the expected body; switching period type shows only its fields; Night disabled without a location; two models show Combined / Each separately; Duplicate opens a prefilled form named "Copy of ..."; a template fills the form without dates or pilots; settings save.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. Keep each component under complexity 15 per function; split the form into field-group components when needed.
- [ ] **Step 4:** Run the full frontend suite and lint on the touched files. Expected: PASS, no new findings.
- [ ] **Step 5:** Commit: `Add the Flight Requirements settings tab`.

### Task 11: Dashboard, Compliance, Pilot and Pilots pages, calendar, reports and digest preferences

**Files:**
- Create: `frontend/src/components/requirements/ThisPeriodTile.jsx`, `frontend/src/components/requirements/PilotRequirementsCard.jsx`, and tests
- Modify: `frontend/src/pages/DashboardPage.jsx`, `frontend/src/pages/CompliancePage.jsx`, `frontend/src/pages/PilotDetailPage.jsx`, `frontend/src/pages/PilotsPage.jsx`, `frontend/src/pages/CalendarPage.jsx` (only if a new `source` needs a color or link), `frontend/src/pages/ReportsPage.jsx`, `frontend/src/components/settings/DigestPreferencesCard.jsx`, their tests, `frontend/src/test/handlers.js`

**Interfaces:**
- Consumes: `/api/requirements/status`, `/api/requirements/pilots/{id}`, `/api/requirements/flags`, CSV export, report type `flight_requirements`.

Behavior:
- Dashboard "This Period" tile (with `requirements.view`): per active requirement, days left, met count over assigned, and each pilot's progress, for example "X10 12/15m, X2E done", plus a line naming pilots with an open miss (from `/api/requirements/flags`); empty state when there are no active requirements.
- Compliance page: a "Requirements" score next to the compliance score, "No results yet" when null. The compliance score is unchanged.
- Pilot detail: a "Flight Requirements" card below Currency Status with current progress (including "N flights left out: no takeoff time" and "N flights awaiting review" when above zero), a history table, an Excuse / Un-excuse action with `requirements.excuse`, and a CSV link with `reports.export`.
- Pilots list: a "Missed requirement" badge from `/api/requirements/flags`, using the semantic danger variables.
- Calendar: requirement deadlines render with their own category color and link.
- Reports: "Flight Requirements" in the report type list when the user has `requirements.view`.
- Digest preferences: a "Flight requirements" category toggle.

- [ ] **Step 1: Load the `impeccable` skill. Write failing tests** for each bullet, including hidden states without `requirements.view`, and a test that the compliance score value is unchanged by requirements data.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. Keep `CompliancePage.jsx` edits small; it has existing SonarCloud findings that are not this task's to fix.
- [ ] **Step 4:** Run the full frontend suite and lint on the touched files. Expected: PASS, no new findings.
- [ ] **Step 5:** Commit: `Show requirement progress on dashboard, compliance and pilot pages`.

### Task 12: Manual, checklist and end-to-end

**Files:**
- Modify: `frontend/src/pages/manual/content.json` (and `topics.js` if topics are registered there), `frontend/manual-shots/shots.js`, `frontend/manual-shots/seed-demo.js` (demo requirement), `frontend/public/manual-pictures/` (new pictures), `docs/TEST_CHECKLIST.md`, `frontend/e2e/`

- [ ] **Step 1:** Add an e2e journey: an admin creates a calendar-month requirement for all active pilots, sees it on the dashboard tile and the Settings list, then deletes it in a `finally`. Unique name per run. Run it twice. Expected: PASS.
- [ ] **Step 2:** Add manual topics: creating a requirement (period types with the spec's examples), time of day and night, models and purposes, excusing, history and the score, emails, templates. Keep the manual's tone. Run `content.test.js` and `topics.test.js`.
- [ ] **Step 3:** Add manual pictures from demo data only (the tab, the form with a summary, the dashboard tile, the pilot card) and check each one.
- [ ] **Step 4:** Add `docs/TEST_CHECKLIST.md` section 39, Flight Requirements, covering each Review Focus item, permissions per role, emails with SMTP pointed at a test inbox, and restore of a backup with requirements. Add its results row.
- [ ] **Step 5:** Commit: `Document flight requirements`.

### Task 13: Full review and PR

- [ ] **Step 1:** Run the full backend, frontend and e2e suites. Expected: all pass.
- [ ] **Step 2:** Run migration 0017 up, down and up on a temp database copied from a 0016 schema with rules. Expected: no errors.
- [ ] **Step 3:** Whole-branch review at high effort by a fresh reviewer on the most capable model, with the spec, this plan and the diff. Fix confirmed issues in one wave, each with a test.
- [ ] **Step 4:** Check the diff and commit messages against the public-repo constraint.
- [ ] **Step 5:** Report to the owner and ask for the go to push. Do not push before that.
- [ ] **Step 6:** After the go, push, open one PR (Summary, Upgrade notes, Test Plan), and merge when CI is green and SonarCloud reports zero new issues. Upgrade notes: migration 0017 runs on start; new permission rows and their defaults; the new daily job sends emails only when SMTP is set up and requirements exist; rollback is `alembic downgrade 0016_currency_rule_models`, which drops all requirement data, so take a backup first. Do not tag.
