# Currency Model Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let supervisors manage currency rules, and replace the free-text vehicle model on a rule with toggles built from the fleet, so a rule can cover several models and can no longer silently match nothing.

**Architecture:** A small service lists the fleet's models, matched without regard to case or spacing. A new `currency_rule_models` table holds a rule's models (no rows means all aircraft), filled from `currency_rules.vehicle_model` by migration 0016. A shared `FleetModelPicker` component replaces the text field, and the Currency Rules card opens to `certifications.manage`.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, React 19, Vitest, Playwright.

**Spec:** `docs/specs/2026-11-19-flight-requirements-design.md`, sections "Fleet model picker", "Screens" (Currency Rules), "Data model" and "Build order". This plan is change 1 of 2. Flight Requirements (change 2, migration 0017) has its own plan later.

## Global Constraints

- Branch `currency-model-picker`, cut from `ccr-8a9ed482-y8kuri` so the spec and this plan ride along. One PR, separate commits. Commit subjects are one-line and imperative, with no attribution lines.
- The repository is public. No unit names, real pilot names, locations or tail numbers in code, tests, fixtures, commits or PR text.
- Migration 0016 is approved by the owner with this plan. Do not create a different migration or change its shape without asking.
- Currency evaluation keeps its meaning: rolling window, reviewed flights only (`counted_flights_filter()`), expiry and reminders unchanged. A rule with several models counts flights on any of them.
- Model matching ignores case and extra spaces everywhere: `normalize_model(" x10 ") == normalize_model("X10")`.
- Do not fix unrelated code or unrelated SonarCloud findings. Note them in the PR description.
- Zero new SonarCloud issues. Keep new functions under cognitive complexity 15.
- Backend tests: `cd backend && DATA_DIR=$(mktemp -d) PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 ~/venvs/dum/bin/pytest -q -p no:cacheprovider <path>`. The full suite takes over 5 minutes; give it a 10-minute timeout.
- Frontend tests: `cd frontend && npm run test:run`, lint `npm run lint`. CI uses Node 22; the container has Node 24, where one known test fails. Run with `npx -y node@22` if available; otherwise run on 24 and confirm the only failure is the one that also fails on `main`.
- Use the `impeccable` skill for interface work. No em dashes or emojis in anything written.

## Review Focus

1. **A rule whose stored model is not in the fleet** (a typo, or a model since sold). It loads with that model selected and flagged "Not in fleet", and saving without touching it keeps it. Pinned in Tasks 4 and 5.
2. **The same model spelled two ways in the fleet** (`X10` and `x10 `). It shows as one toggle with the combined count, and a rule on either spelling counts both. Pinned in Tasks 2 and 3.
3. **Restoring a backup made before 0016.** Rules come back with their models, not as All aircraft. Pinned in Task 3.
4. **Rolling back to 3.5.0.** The 0016 downgrade writes each rule's first model (alphabetical) back to `vehicle_model`, so a single-model rule behaves as before. Pinned in Task 3.
5. **A supervisor on the Settings page.** They see and can edit Currency Rules but still see no admin-only section, and a viewer sees no Currency Rules card at all. Pinned in Task 5.

---

### Task 1: Branch and baseline

- [ ] **Step 1:** `git fetch origin && git checkout -b currency-model-picker origin/ccr-8a9ed482-y8kuri`.
- [ ] **Step 2:** If `frontend/node_modules` is missing, run `cd frontend && npm ci --ignore-scripts`.
- [ ] **Step 3:** Run the full backend and frontend suites. Expected: all pass (frontend: see the Node note). Record the counts. If anything else fails before any change, stop and report it.

### Task 2: Fleet model list

**Files:**
- Create: `backend/app/services/fleet_models.py`, `backend/tests/test_fleet_models.py`
- Modify: `backend/app/routers/currency.py`

**Interfaces:**
- Produces, in `services/fleet_models.py`:
  - `normalize_model(name: str | None) -> str`: whitespace collapsed and trimmed, then `casefold()`. `None` gives `""`.
  - `fleet_models(db) -> list[dict]`: one entry per normalized model, `{"name": str, "aircraft": int, "retired": int}`, sorted by `name` case-insensitively. `aircraft` counts vehicles whose status is not `retired`; `retired` counts the rest. `name` is the most common spelling among those vehicles, ties going to the alphabetically first. Vehicles with a blank model are left out.
- Produces: `GET /api/currency/models`, guarded by `certifications.manage`, returning `fleet_models(db)`. Change 2 widens the guard to also accept `requirements.manage`.

- [ ] **Step 1: Write failing tests** in `test_fleet_models.py`:
  - `test_normalize_model`: `" X10 "`, `"x10"`, `"X10"` are equal; `"LEMUR  2"` equals `"lemur 2"`; `None` and `"  "` give `""`.
  - `test_fleet_models_merges_spellings`: vehicles `X10`, `x10 `, `X10` give one entry `{"name": "X10", "aircraft": 3, "retired": 0}`.
  - `test_fleet_models_counts_retired_apart`: one active and one `maintenance` X2E plus one retired X2E give `aircraft == 2, retired == 1`; a model with only retired vehicles is listed with `aircraft == 0`.
  - `test_fleet_models_skips_blank_model`.
  - `test_models_route_permissions`: admin and supervisor get 200; pilot and viewer get 403 with the default grid.
- [ ] **Step 2:** Run them. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement the service and the route. Count with one grouped query over `Vehicle.model` and `Vehicle.status`, then merge in Python by `normalize_model`.
- [ ] **Step 4:** Run `test_fleet_models.py` and `test_permission_coverage.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `Add fleet model list for currency rules`.

### Task 3: Rule models table, migration 0016 and backups

**Files:**
- Create: `backend/app/models/currency_rule_model.py` (or add the class to `currency_rule.py`, matching how other child tables are kept), `backend/migrations/versions/0016_currency_rule_models.py`, `backend/tests/test_currency_rule_models.py`
- Modify: `backend/app/models/currency_rule.py`, `backend/app/models/__init__.py`, `backend/app/routers/backup.py`

**Interfaces:**
- Produces: model `CurrencyRuleModel` on table `currency_rule_models`: `id` (autoincrement, `sqlite_autoincrement=True` as in 0014), `rule_id` (FK `currency_rules.id`, `ondelete="CASCADE"`, not null, indexed), `model` (`String(200)`, not null), unique on `(rule_id, model)`.
- Produces: `CurrencyRule.models` relationship, `cascade="all, delete-orphan"`, `lazy="selectin"`, and a read-only property `CurrencyRule.model_names -> list[str]` sorted case-insensitively. `vehicle_model` stays on the model and in the table, unused by the app, until a later release drops it.
- Produces, in `services/fleet_models.py`: `backfill_rule_models(db) -> int`: for each rule with a non-blank `vehicle_model` and no model rows, add one row with the trimmed value. Returns the number added. Used only by restore.

Migration 0016 (`revision = "0016_currency_rule_models"`, `down_revision = "0015_drop_geofences"`):
- Upgrade: create the table, then `INSERT INTO currency_rule_models (rule_id, model) SELECT id, trim(vehicle_model) FROM currency_rules WHERE vehicle_model IS NOT NULL AND trim(vehicle_model) <> ''`.
- Downgrade: `UPDATE currency_rules SET vehicle_model = (SELECT model FROM currency_rule_models m WHERE m.rule_id = currency_rules.id ORDER BY lower(model) LIMIT 1)`, then drop the table. A rule with no rows gets `NULL` (all aircraft). The docstring says extra models on a multi-model rule are lost on downgrade.

Backups:
- Add `("currency_rule_models", CurrencyRuleModel)` to `EXPORT_ORDER` in Tier 2 (after `currency_rules`, which has no FK).
- In `_restore_main_tables`, when the backup has no `currency_rule_models` key at all (made before 0016), call `backfill_rule_models(db)` inside the same transaction, before the summary entry. A backup that has the key, even empty, is restored as is.

- [ ] **Step 1: Write failing tests** in `test_currency_rule_models.py`:
  - `test_migration_copies_vehicle_model`: on a temp database at `0015_drop_geofences`, insert rules with `"X10"`, `" X2E "`, `""` and `NULL`; upgrade to `0016`. Rows: `X10` and `X2E` for the first two, none for the others.
  - `test_migration_downgrade_restores_first_model`: after upgrade, give one rule `X2E` and `LEMUR 2`, another none; downgrade. `vehicle_model` is `"LEMUR 2"` and `NULL`.
  - `test_delete_rule_deletes_models`.
  - `test_backup_includes_rule_models`: the manifest counts `currency_rule_models`.
  - `test_restore_pre_0016_backup_backfills`: a backup whose `database` has a rule with `vehicle_model: "X10"` and no `currency_rule_models` key restores with one `X10` row.
  - `test_restore_new_backup_keeps_all_aircraft`: a backup with the key present and empty, and a rule whose stale `vehicle_model` is `"X10"`, restores with no rows.
  Follow the migration-test pattern in `tests/test_autoincrement.py` and the backup pattern in `tests/test_permissions_backup.py`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement the model, migration, `EXPORT_ORDER` entry and restore backfill. Write the migration by hand in the style of 0015; check it against `alembic revision --autogenerate` run on a throwaway SQLite database so no other drift sneaks in.
- [ ] **Step 4:** Run the new tests, `test_schema.py`, `test_backup*.py` and `test_autoincrement.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `Store currency rule models in their own table`.

### Task 4: Rule API and evaluation use the model list

**Files:**
- Modify: `backend/app/routers/currency.py`
- Test: `backend/tests/test_currency.py` (extend), `backend/tests/test_currency_reviewed_only.py` (run only)

**Interfaces:**
- Consumes: `normalize_model`, `CurrencyRule.models`, `CurrencyRule.model_names`.
- Produces: `RuleCreate.vehicle_models: list[str] = []` and `RuleUpdate.vehicle_models: list[str] | None = None` (`None` means leave unchanged; `[]` means all aircraft). Each name is trimmed, 1 to 200 characters; at most 50 names; duplicates under `normalize_model` are dropped, keeping the first spelling. The `vehicle_model` field is removed from both and from `RuleOut`.
- Produces: `RuleOut.vehicle_models: list[str]` (from `model_names`), and `"vehicle_models": list[str]` in each `_evaluate_rule` result in place of `"vehicle_model"`.

- [ ] **Step 1: Write failing tests** in `test_currency.py`:
  - `test_rule_with_two_models_counts_both`: rule `["X10", "X2E"]`, 3 h in 90 days; reviewed flights of 2 h on an X10 and 1.5 h on an X2E make the pilot current, and a 4 h flight on a LEMUR 2 alone does not.
  - `test_rule_model_match_ignores_case_and_spaces`: rule `["x10 "]` counts a flight on vehicle model `X10`.
  - `test_rule_without_models_counts_all_aircraft`, including a flight with no vehicle.
  - `test_model_rule_skips_flight_without_vehicle`.
  - `test_create_dedupes_models`: `["X10", "x10", "X2E"]` stores `["X10", "X2E"]`.
  - `test_patch_without_models_keeps_them` and `test_patch_empty_list_means_all_aircraft`.
  - `test_unknown_model_is_kept`: `["X11"]` saves and returns `["X11"]`.
  - `test_rule_validation`: a blank name in the list, a 201-character name and 51 names each give 422.
  - `test_status_lists_models`: `GET /api/currency/status/{pilot_id}` returns `vehicle_models`.
  Update existing tests that send or read `vehicle_model`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. In `_evaluate_rule`, build the set of normalized names once per rule and keep a flight when the set is empty or `normalize_model(f.vehicle.model)` is in it. Create and patch replace the rule's `models` rows from the cleaned list.
- [ ] **Step 4:** Run `test_currency*.py`, `test_permission*.py` and the dashboard tests (`grep -l currency backend/tests/*.py`). Expected: PASS.
- [ ] **Step 5:** Commit: `Let a currency rule cover several fleet models`.

### Task 5: Fleet model picker and supervisor access in Settings

**Files:**
- Create: `frontend/src/components/FleetModelPicker.jsx`, `frontend/src/components/FleetModelPicker.test.jsx`
- Modify: `frontend/src/pages/SettingsPage.jsx`, `frontend/src/pages/SettingsPage.test.jsx`, `frontend/src/pages/PilotDetailPage.jsx`, `frontend/src/pages/PilotDetailPage.test.jsx`, `frontend/src/test/handlers.js`

**Interfaces:**
- Consumes: `GET /api/currency/models`; rule `vehicle_models`; status `vehicle_models`; `can()` from `useAuth()`.
- Produces: `<FleetModelPicker models={[{name, aircraft, retired}]} value={string[]} onChange={(string[]) => void} />`. `value` of `[]` means All aircraft. Change 2 adds the Combined / Each separately choice around it; do not build that now.
- Produces: `normalizeModel(name)` in `frontend/src/lib/utils.js`, matching the backend rule.

Picker behavior (spec, "Fleet model picker"):
- An **All aircraft** toggle, on when `value` is empty.
- One toggle per model with `aircraft > 0`, labeled `"X10 (4)"`.
- A model with `aircraft == 0` shows only when selected, labeled with "no active aircraft".
- A selected name that matches no fleet model (by `normalizeModel`) shows selected, labeled "Not in fleet", so it can be removed deliberately.
- Turning on a model turns off All aircraft; turning off the last model turns All aircraft back on; turning on All aircraft clears the list.
- Toggles are real buttons with `aria-pressed`, usable by keyboard, and wrap on a phone.

- [ ] **Step 1: Write failing tests:**
  - `FleetModelPicker.test.jsx`: All aircraft pressed for `[]`; clicking a model calls `onChange(["X10"])`; clicking the only selected model calls `onChange([])`; clicking All aircraft calls `onChange([])`; a retired-only model is hidden until selected; `["x11"]` with no X11 in the fleet shows "Not in fleet"; `["x10"]` with fleet `X10` shows the X10 toggle pressed, not "Not in fleet".
  - `SettingsPage.test.jsx`: a supervisor (`certifications.manage` yes) sees Currency Rules and can create a rule, and the request body has `vehicle_models`; a viewer sees no Currency Rules card; an admin still sees everything they saw before; the rule list reads `"X10, X2E only"` for a two-model rule; the text field `#rule-vmodel` is gone.
  - `PilotDetailPage.test.jsx`: the Model column shows `"X10, X2E"` and `"All"` for an empty list.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Load the `impeccable` skill. Build the picker and wire it into the currency rule modal in place of the text field. In `SettingsPage.jsx`, load `/currency/rules` and `/currency/models` and render the Currency Rules card and modal when `can('certifications.manage')`, not `isAdmin`; leave the users and pilots loads under `isAdmin`. Update the card's help text: the model is chosen from the fleet, and no selection means all aircraft. Add MSW handlers for `/api/currency/models`.
- [ ] **Step 4:** Run `npm run test:run` and `npm run lint`. Expected: PASS, no new lint findings.
- [ ] **Step 5:** Commit: `Pick currency rule models from the fleet and open rules to supervisors`.

### Task 6: Manual, checklist and end-to-end

**Files:**
- Modify: `frontend/src/pages/manual/content.json`, `frontend/manual-shots/shots.js`, `frontend/manual-shots/seed-demo.js` (only if the demo fleet lacks two models), `frontend/public/manual-pictures/pilots-pilot-currency.png`, `docs/TEST_CHECKLIST.md`, `frontend/e2e/`

- [ ] **Step 1:** Add an e2e journey: an admin creates a rule on one fleet model from the picker, and the rule list shows that model. Reuse the saved admin token. Run `cd frontend && npm run e2e`. Expected: PASS. If the pinned Playwright cannot find Chromium, use `/opt/pw-browsers/chromium` through a local override that is not committed.
- [ ] **Step 2:** Update the manual's currency topic (around `content.json` lines 1106 to 1120): supervisors and admins open Currency Rules; models are toggles from the fleet; All aircraft when none are picked; several models count together; "Not in fleet" means the model should be fixed. Keep the existing tone.
- [ ] **Step 3:** In `shots.js`, have the `pilots-pilot-currency.png` shot toggle one demo model, then run `npm run manual:shots` for that picture only. Check the picture shows demo data only.
- [ ] **Step 4:** Add a Currency Rules section to `docs/TEST_CHECKLIST.md`: supervisor access, picker behavior, a two-model rule, an existing rule after upgrade, and restore of a pre-upgrade backup.
- [ ] **Step 5:** Commit: `Document the currency model picker`.

### Task 7: Full review and PR

- [ ] **Step 1:** Run the full backend, frontend and e2e suites. Expected: all pass.
- [ ] **Step 2:** On a copy of a 3.5.0-shaped database with rules, run `alembic upgrade head`, `downgrade -1`, `upgrade head`. Expected: no errors, and rule behavior unchanged after the round trip for single-model rules.
- [ ] **Step 3:** Run a whole-branch code review at high effort with a fresh reviewer, giving it the spec, this plan and the diff. Fix every confirmed issue, each with a test.
- [ ] **Step 4:** Check the diff and all commit messages against the public-repo constraint.
- [ ] **Step 5:** Report results to the owner and ask for the go to push. Do not push before that.
- [ ] **Step 6:** After the go, push and open one PR with Summary and Test Plan sections, plus upgrade notes: supervisors now see Currency Rules; migration 0016 runs on start; the currency API now uses `vehicle_models` (a list) in place of `vehicle_model`; rollback needs `alembic downgrade` to `0015_drop_geofences` and keeps only the first model of a multi-model rule. The release PR later copies these rollback steps into `ROLLBACK.md`. Follow the merge gate: green CI and zero new SonarCloud issues.
- [ ] **Step 7:** Hand the staging pass to the owner (staging runs `:main`). Production stays pinned until a version tag. Do not tag.
