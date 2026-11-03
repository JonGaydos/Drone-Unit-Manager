# Configurable Role Permissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fixed role guards with an admin-editable permission grid, enforced by the backend on every route and read path.

**Architecture:** One code registry defines each permission key, its option type, default per role and viewer lock. A `role_permissions` table stores only admin changes. FastAPI dependencies resolve the current user's value on each request, and the frontend reads the resolved values from `/api/auth/me`.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, React 19, Vitest, Playwright.

**Spec:** `docs/specs/2026-11-02-role-permissions-design.md`. Executors read both. The default grid and the meaning of "Own" live there and are not repeated here.

## Global Constraints

- One PR on branch `role-permissions`, with separate commits. Commit subjects are one-line and imperative, with no attribution lines.
- The repository is public. Commits, PR text and docs describe this as a feature.
- Checks fail closed. An unknown key or a failure resolving a permission denies access.
- Admin always resolves to the highest value. Locked viewer cells always resolve to No or None, whatever is stored.
- Do not fix unrelated code. Note it in the PR description instead.
- Backend tests: `cd backend && DATA_DIR=$(mktemp -d) PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 ~/venvs/dum/bin/pytest -q -p no:cacheprovider <path>`. The full suite takes over 5 minutes, so give it a 10-minute timeout.
- Frontend tests: `cd frontend && npm run test:run`. Lint: `npm run lint`.
- Use the `impeccable` skill for interface work. No em dashes or emojis in anything written.

## Review Focus

1. **A setting changes while someone is signed in.** It applies on their next request without a new login. Pinned in Task 2.
2. **API tokens.** A token whose owner's role loses a permission loses it too, and no token can reach `/api/permissions`. Pinned in Task 2.
3. **View off, but a form needs a picker.** With `pilots.view` or `fleet.view` off, forms that select a pilot or equipment still work through the options endpoints. Pinned in Task 5.
4. **A login with no linked pilot.** Own never matches a `None` pilot id, so it cannot match records with no pilot. Pinned in Task 3.
5. **A partly invalid grid save.** Nothing is applied, and the error names the key. Pinned in Task 2.

---

## Route Mapping

This table is the decision record for Tasks 3 to 7. "Level" means a None / Own / All key, checked against the loaded record.

| Router | Reads | Writes |
|---|---|---|
| `flights` | list, count, review, detail, preflight-check: `flights.view`. `purposes/list`: signed-in. `purposes/usage`: `flights.review` | create: `flights.create`. PATCH: `flights.edit` level. DELETE: `flights.delete` level. bulk-delete: `flights.review` plus `flights.delete` at All. bulk-update: `flights.review`, plus `flights.edit` at All when it changes `pilot_id` or `purpose`. telemetry-status, review-status: `flights.review`. refresh, purposes: admin |
| `telemetry` | `flights.view` | none |
| `flight_plans` | `flight_plans.view` | create: `flight_plans.create`. PATCH, cancel: `flight_plans.edit` level. approve, deny, delete: `flight_plans.approve` |
| `incidents` | `incidents.view` | create: `incidents.create`. PATCH: `incidents.edit` level plus `incidents.resolve` for its fields. DELETE: `incidents.delete` |
| `mission_logs`, `training_logs` | `logs.view` | create: `logs.create`. PATCH, DELETE, roster add and remove: `logs.edit` level |
| `maintenance` | `maintenance.view` | create: `maintenance.create`. PATCH, DELETE: `maintenance.edit` level |
| `maintenance_schedules` | `maintenance.view` | complete: `schedules.complete`. create, PATCH, DELETE: `schedules.manage` |
| `equipment`, `components`, `vehicles` | `fleet.view` | `fleet.manage`, except vehicle location: `fleet.location`. Vehicle photo upload: admin |
| `equipment_checkouts` | `fleet.view` | create, check-in: `checkouts.use`. DELETE: `checkouts.delete` |
| `pilots` | `pilots.view`. `pilots.contacts` controls masking | PATCH: `pilots.edit` level, and `SUPERVISOR_ONLY_PILOT_FIELDS` need `pilots.manage`. create, DELETE, merge: `pilots.manage`. Photo upload: admin |
| `certifications`, `currency` | `certifications.view` | `certifications.manage` |
| `checklists` | `checklists.view` | complete: `checklists.complete`. Templates and completion delete: `checklists.manage` |
| `calendar` | `calendar.view`. `flight_counts` only with `flights.view` | create: `calendar.create`. PATCH, DELETE: `calendar.edit` level |
| `documents`, `photos` | `files.view`, including signed URL minting and serving by login | upload: `files.upload` level. PATCH, DELETE: `files.edit` level. restore, hold, deleted lists, photo links: `files.custody`. Purge: admin |
| `media` | `files.view` | DELETE: `files.edit` at All |
| `folders` | `files.view` | `folders.manage` |
| `alerts` | `alerts.view` | read, dismiss, dismiss-all: `alerts.dismiss` |
| `operating_authorities`, `geofences` | `authority.view` | `authority.manage` |
| `vehicle_registrations` | `registrations.view` | `registrations.manage` |
| `audit` | `audit.view` | none |
| `reports` | none | `reports.generate`, plus the view key for the report's content |
| `export` CSV, GPX, KML | `reports.export` plus the entity's view key | imports: admin |
| `dashboard` | Signed-in: stats, trends, compliance. `flights.view`: activity-by-month, top-pilots-30d, flights-by-*, avg-duration-by-year, monthly-flights, pilot-hours, pilot-performance. `fleet.view`: top-vehicles-30d, vehicle-hours, fleet-health. `maintenance.view`: maintenance-due. `certifications.view`: upcoming-expirations | none |
| `search` | Signed-in, with each result group filtered by its view key | none |
| `notifications` | Signed-in, own account. `/log` stays as is | Signed-in, own account. Override follows `digest.redirect` |
| `weather`, `adsb`, `geocode`, `settings` reads | Signed-in | Settings writes: admin |
| `auth`, `backup`, `api_tokens`, `sync`, `import_router` | Unchanged | Unchanged |

Calls made in this table, for the reviewer to check:

- `pilots/csv` stays supervisor-level by requiring `pilots.manage` and `reports.export`, because a wider default would change who can bulk-export the roster.
- Checkouts have no view row in the grid, so they follow `fleet.view`.
- Media deletion needs All, because media rows have no owner.

---

### Task 1: Branch, baseline and test fixtures

**Files:**
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Produces: fixtures `supervisor_user`, `viewer_user`, `supervisor_headers`, `viewer_headers`, and a user-linked pilot fixture `linked_pilot` (a `Pilot` linked to `pilot_user`).

- [ ] **Step 1:** `git checkout -b role-permissions`, and add the spec and plan as the first commit.
- [ ] **Step 2:** Create the environment if missing: `uv venv --python 3.12 ~/venvs/dum` and install `backend/requirements.lock.txt` and `backend/requirements-dev.lock.txt`. In `frontend`, run `npm ci --ignore-scripts`.
- [ ] **Step 3:** Run the full backend and frontend suites. Expected: all pass. Record the counts. If anything fails before any change, stop and report it.
- [ ] **Step 4:** Add the fixtures, following `admin_user` and `pilot_headers`, and run `tests/test_auth.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `Add supervisor and viewer test fixtures`.

### Task 2: Permission registry, storage, API and resolved values

**Files:**
- Create: `backend/app/services/permissions.py`, `backend/app/models/role_permission.py`, `backend/app/routers/permissions.py`, `backend/migrations/versions/0011_role_permissions.py`, `backend/tests/test_permissions.py`
- Modify: `backend/app/models/__init__.py`, `backend/app/main.py`, `backend/app/routers/auth.py`, `backend/app/schemas/user.py`, `backend/app/models/document.py`

**Interfaces:**
- Produces, in `services/permissions.py`:
  - `REGISTRY: dict[str, PermissionDef]`, with `PermissionDef(key, feature, action, kind: Literal["bool", "level"], defaults: dict[str, str], viewer_locked: bool, requires: str | None)`. Values are `"yes" | "no"` or `"none" | "own" | "all"`. `requires` names the view key a change permission depends on.
  - `get_value(db, role: str, key: str) -> str`: admin gets the highest value, a locked viewer cell gets the lowest, a stored valid row wins, otherwise the default. An unknown key raises `KeyError`.
  - `can(db, user, key) -> bool`: true for `yes`, `own` or `all`.
  - `level(db, user, key) -> str`.
  - `resolved_for(db, role) -> dict[str, str]`.
  - `validate_change(role, key, value) -> str | None`: returns an error message or None.
  - `validate_grid(db, changes) -> list[str]`: includes the change-without-view rule on the resulting grid.
- Produces, in `routers/auth.py`: `require_permission(key: str)`, a dependency factory returning the user or raising 403. The returned callable carries the attribute `permission_key`.
- Produces: `UserOut.permissions: dict[str, str]` on `/me` and in the login response.

- [ ] **Step 1: Write failing tests** in `tests/test_permissions.py`:
  - `test_registry_defaults_match_spec`: a table copied from the spec's default grid, asserted for every key and role, including the count of keys.
  - `test_admin_always_highest`, including with a stored row of `no`.
  - `test_locked_viewer_ignores_stored_row`: insert a row directly with viewer `flights.edit` = `all`. `get_value` returns `none`.
  - `test_put_refuses_locked_viewer_cell`, `test_put_refuses_unknown_key`, `test_put_refuses_invalid_value`.
  - `test_put_is_atomic`: one valid and one invalid change returns 422 naming the invalid key, and nothing is stored.
  - `test_put_refuses_change_without_view`: pilot `flights.view` = `no` with `flights.edit` = `own` returns 422. Setting both together succeeds.
  - `test_put_writes_one_audit_entry_with_old_and_new`.
  - `test_reset_clears_rows_and_audits`.
  - `test_non_admin_refused`: supervisor, pilot and viewer each get 403 on GET, PUT and reset.
  - `test_change_applies_on_next_request`: a pilot token gets 200 on a guarded test route, the admin turns the key off, and the same token gets 403.
  - `test_api_token_refused_on_permissions_routes`, and `test_api_token_follows_owner_permissions`.
  - `test_me_returns_resolved_permissions`.
  - `test_last_admin_still_protected`: demoting, deactivating or deleting the last active admin is still refused.
- [ ] **Step 2:** Run the tests. Expected: FAIL on the missing module.
- [ ] **Step 3:** Implement the model, with a unique constraint on `(role, permission_key)`, and the registry using the spec's exact keys and defaults.
- [ ] **Step 4:** Write migration `0011_role_permissions`, revising `0010_local_dates_for_spreadsheet_imports`: create the table and add nullable `documents.uploaded_by_id`, foreign key to `users.id`. Include a downgrade that drops both. Update `test_schema.py` if it pins the head revision.
- [ ] **Step 5:** Implement `require_permission`, and `GET /api/permissions`, `PUT /api/permissions` and `POST /api/permissions/reset` as admin-only routes. Do not add `/api/permissions` to `SCOPE_PREFIXES`.
- [ ] **Step 6:** Run `tests/test_permissions.py tests/test_schema.py tests/test_api_tokens.py`. Expected: PASS.
- [ ] **Step 7:** Commit: `Add permission registry, storage and admin API`.

### Task 3: Flights

**Files:**
- Modify: `backend/app/routers/flights.py`, `backend/app/routers/telemetry.py`, `backend/app/services/permissions.py`
- Test: `backend/tests/test_permissions_flights.py`

**Interfaces:**
- Consumes: `require_permission`, `level`.
- Produces: `require_record_access(db, user, key, owned: bool) -> None`, in `services/permissions.py`: raises 403 unless the level is `all`, or the level is `own` and `owned` is true. Later tasks use it for every level key.
- Produces: `owns_flight(user, flight) -> bool`: true if `user.pilot_id` is not None and equals `flight.pilot_id`, or `flight.created_by_id == user.id`.

- [ ] **Step 1: Write failing tests:**
  - `test_pilot_cannot_delete_flight_by_default`, `test_supervisor_can_delete`.
  - `test_pilot_delete_when_set_to_own`: own flight 200, another pilot's 403.
  - `test_pilot_edit_own_flight` and `test_pilot_cannot_edit_others_flight`.
  - `test_own_edit_cannot_reassign_pilot`: changing `pilot_id` returns 403. Echoing the same value succeeds.
  - `test_create_for_other_pilot_is_allowed_and_needs_review`: `review_status == "needs_review"` and `created_by_id` is the caller.
  - `test_creator_can_edit_flight_logged_for_other`.
  - `test_supervisor_created_flight_needs_review`.
  - `test_edit_of_reviewed_flight_returns_to_queue`, for a pilot changing content.
  - `test_edit_echoing_values_keeps_reviewed`.
  - `test_supervisor_edit_keeps_reviewed`.
  - `test_unlinked_login_owns_only_what_it_logged`, including a flight whose `pilot_id` is None and that it did not create.
  - `test_viewer_cannot_create_edit_delete`.
  - `test_view_off_hides_list_detail_count_review_telemetry`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Convert the routes per the Route Mapping. Compare current values before treating a field as changed, as `REVIEW_FIELDS` already does. On return to the queue, set `review_status` to `needs_review`.
- [ ] **Step 4:** Run the new tests and every existing flight test. Change an existing test only where a default deliberately changed.
- [ ] **Step 5:** Commit: `Enforce permissions on flights`.

### Task 4: Operational records

**Files:**
- Modify: `backend/app/routers/flight_plans.py`, `incidents.py`, `mission_logs.py`, `training_logs.py`, `maintenance.py`, `maintenance_schedules.py`, `calendar.py`, `checklists.py`, `equipment_checkouts.py`, `alerts.py`
- Test: `backend/tests/test_permissions_records.py`

**Interfaces:**
- Consumes: `require_permission`, `require_record_access`.

- [ ] **Step 1: Write failing tests:**
  - `test_self_approval_blocked_even_when_granted`.
  - `test_incident_reporter_cannot_set_resolve_fields`, for each of `status`, `resolution`, `resolution_date` and `corrective_actions`.
  - `test_incident_reporter_can_edit_other_fields`.
  - `test_incident_resolve_granted_to_pilot_works`.
  - `test_log_edit_own_via_creator_and_via_roster`, and `test_log_edit_refused_for_others`.
  - `test_maintenance_create_sets_created_by`, and `test_maintenance_without_creator_needs_all`.
  - `test_pilot_completes_schedule_by_default`, `test_complete_refused_when_toggled_off`, `test_pilot_cannot_manage_schedule`.
  - `test_calendar_viewer_creator_cannot_edit`: a viewer who created an event before demotion gets 403.
  - `test_alert_pilot_cannot_mark_read_or_dismiss_by_default`, and `test_alert_granted_works`.
  - `test_view_off_hides_each_feature`, parametrized across these routers.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Convert per the Route Mapping. Set `created_by_id=user.id` in the mission log, training log and maintenance create routes.
- [ ] **Step 4:** Run the new tests and the existing tests for these routers. Expected: PASS.
- [ ] **Step 5:** Commit: `Enforce permissions on operational records`.

### Task 5: Fleet, pilots, certifications and pickers

**Files:**
- Modify: `backend/app/routers/equipment.py`, `components.py`, `vehicles.py`, `pilots.py`, `certifications.py`, `currency.py`, `operating_authorities.py`, `geofences.py`, `vehicle_registrations.py`, `folders.py`, `audit.py`, `backend/app/services/pilot_contacts.py`
- Test: `backend/tests/test_permissions_fleet_pilots.py`

**Interfaces:**
- Produces: `GET /api/pilots/options` returning `[{id, full_name, badge_number, status}]`, and `GET /api/fleet/options` returning `{vehicles, batteries, controllers, sensors, attachments, docks, other_equipment}`, each a list of `{id, name, status}`. Both are open to any signed-in user and contain no contact details.
- Produces: `hides_contacts(db, user) -> bool`, keeping the existing call sites but reading `pilots.contacts`. Update its callers for the new `db` argument.

- [ ] **Step 1: Write failing tests:**
  - `test_pilot_cannot_manage_components`, and `test_supervisor_can`.
  - `test_pilot_can_set_vehicle_location`.
  - `test_pilot_edits_only_own_profile`, and `test_pilot_cannot_set_supervisor_only_fields`.
  - `test_contacts_toggle`: viewer sees no email by default, and sees it when granted, in list, detail, search and flights CSV.
  - `test_options_available_with_view_off`: `pilots.view` and `fleet.view` off, options return 200 with no email or phone field.
  - `test_view_off_hides_each_feature`, parametrized.
  - `test_registrations_manage_off_for_supervisor_by_default`, and `test_grantable`.
  - `test_audit_view_grantable`, including `/api/export/audit/csv`.
  - `test_folder_manage_refused_for_pilot`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Convert per the Route Mapping, and add the options endpoints. Register `/options` before `/{id}` so it is not treated as an id.
- [ ] **Step 4:** Run the new tests and the existing tests for these routers. Expected: PASS.
- [ ] **Step 5:** Commit: `Enforce permissions on fleet, pilots and certifications`.

### Task 6: Documents, photos and media

**Files:**
- Modify: `backend/app/routers/documents.py`, `photos.py`, `media.py`
- Test: `backend/tests/test_permissions_files.py`

**Interfaces:**
- Consumes: `require_record_access`.
- Produces: `owns_document(db, user, document) -> bool`: uploaded by the user, or attached to the user's own pilot record or certification, using the logic in `_check_own_record`. `owns_photo(user, photo) -> bool`: uploaded by the user.

- [ ] **Step 1: Write failing tests:**
  - `test_upload_sets_uploaded_by`.
  - `test_own_upload_general_vehicle_and_own_record_allowed`, and `test_own_upload_other_pilot_record_refused`.
  - `test_all_upload_any_record`.
  - `test_document_without_uploader_needs_all`.
  - `test_pilot_edit_and_soft_delete_own_only`, for documents and photos.
  - `test_legal_hold_blocks_delete_even_with_all`.
  - `test_custody_routes_refused_for_pilot`.
  - `test_purge_admin_only`.
  - `test_view_off_blocks_list_view_and_signed_url_minting`.
  - `test_view_off_blocks_serving_by_login_token`.
  - `test_issued_signed_url_still_valid_until_expiry`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Convert per the Route Mapping. Photo view and thumbnail keep accepting a signature, and only the login-token branch checks `files.view`.
- [ ] **Step 4:** Run the new tests and the existing file tests, including `test_photos.py` and `test_security_batch4.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `Enforce permissions on documents and photos`.

### Task 7: Parallel read paths, digest and currency

**Files:**
- Modify: `backend/app/routers/search.py`, `dashboard.py`, `export.py`, `reports.py`, `notifications.py`, `currency.py`, `backend/app/services/email_digest.py`, `backend/app/services/scheduler.py`
- Test: `backend/tests/test_permissions_read_paths.py`, `backend/tests/test_currency_reviewed_only.py`

**Interfaces:**
- Consumes: `can`.
- Produces: `REPORT_VIEW_KEYS: dict[str, str]`, mapping each report type to its view key. A report type with no entry is refused.
- Produces: `counted_flights_filter()`, the single currency rule used by every evaluation site. It requires `Flight.review_status == "reviewed"`.

- [ ] **Step 1: Write failing tests:**
  - `test_search_omits_group_when_view_off`, for each group.
  - `test_dashboard_lists_follow_view_keys`, and `test_unit_totals_stay_visible`.
  - `test_export_needs_both_keys`, for each CSV, GPX and KML route.
  - `test_pilots_csv_stays_supervisor_level`.
  - `test_report_refused_when_view_off`, for each report type, and `test_unknown_report_type_refused`.
  - `test_digest_sections_follow_view_keys`.
  - `test_redirect_refused_on_save_without_permission`.
  - `test_scheduled_digest_ignores_override_without_permission`, with the stored override left intact.
  - `test_unreviewed_flight_does_not_count_toward_currency`, `test_reviewed_flight_counts`, `test_edit_back_to_queue_stops_counting`, and `test_synced_flight_needs_review_to_count`.
  - `test_currency_rule_same_on_dashboard_and_status_routes`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement per the Route Mapping and the spec's "Enforcing view toggles". Replace the role-name checks in `email_digest.py` with permission checks. Apply `counted_flights_filter()` in `currency.py` and `dashboard.py`.
- [ ] **Step 4:** Run the new tests and the existing search, dashboard, export, report, notification and currency tests. Expected: PASS, changing existing tests only where the spec changed behavior.
- [ ] **Step 5:** Commit: `Apply view permissions to search, exports, reports and digests`.

### Task 8: Backup and restore

**Files:**
- Modify: `backend/app/routers/backup.py`
- Test: `backend/tests/test_permissions_backup.py`

**Interfaces:**
- Consumes: `validate_change`, `validate_grid`.

- [ ] **Step 1: Write failing tests:**
  - `test_backup_includes_role_permissions`, and `test_restore_round_trip`.
  - `test_older_backup_restores_defaults`: an archive with no such table.
  - `test_restore_drops_locked_viewer_row`, `test_restore_drops_unknown_key`, `test_restore_drops_change_without_view_row`.
  - `test_older_backup_documents_restore_without_uploader`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Add the model to `EXPORT_ORDER`, and filter its rows in `_prepare_restore_rows`.
- [ ] **Step 4:** Run the new tests and `tests/test_backup_restore.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `Include role permissions in backup and restore`.

### Task 9: Route coverage and permission matrix gates

**Files:**
- Create: `backend/tests/test_permission_coverage.py`, `backend/tests/test_permission_matrix.py`
- Modify: `backend/app/routers/auth.py` (remove `require_manager` and `ManagerUser` if unused), `backend/app/deps.py`

**Interfaces:**
- Consumes: the `permission_key` attribute on `require_permission` dependencies.
- Produces: explicit allowlists `ADMIN_ONLY_ROUTES`, `SIGNED_IN_ROUTES` and `PUBLIC_ROUTES` in the coverage test, keyed by method and path.

- [ ] **Step 1:** Write `test_every_route_is_classified`. It walks `app.routes`, inspects each route's dependant tree, and fails with the route's name unless the route has a `permission_key`, depends on `require_admin`, or is on an allowlist. A route may not be in two classes. Write `test_no_stale_allowlist_entries`.
- [ ] **Step 2:** Write `test_every_registry_key_is_used`: each key is used by a route or by a named non-route check.
- [ ] **Step 3:** Write the matrix tests, parametrized from the Route Mapping: for each key and role, one representative route returns the expected status at the default, and flipping the toggle changes it. Flip dependent keys with their view key on.
- [ ] **Step 4:** Run them. Fix every failure in the owning router, not in the allowlist, unless the Route Mapping says signed-in.
- [ ] **Step 5:** Run the full backend suite. Expected: all pass. Report the count against the Task 1 baseline.
- [ ] **Step 6:** Commit: `Add route coverage and permission matrix tests`.

### Task 10: Frontend permissions

**Files:**
- Modify: `frontend/src/contexts/AuthContext.jsx`, its test, the 33 files that use role checks (find them with `grep -rlE "isAdmin|isSupervisor|isPilot|isManager|isViewer|\.role\b" frontend/src`), the sidebar and command palette, and pages that load `/pilots` or fleet lists only to fill pickers.

**Interfaces:**
- Consumes: `user.permissions`, `/api/pilots/options`, `/api/fleet/options`.
- Produces: `can(key) -> boolean` and `level(key) -> "none"|"own"|"all"` from `useAuth()`. `canRecord(key, ownedBool) -> boolean`. `isAdmin` stays for admin-only pages. `isManager` is removed.

- [ ] **Step 1: Write failing tests** in `AuthContext.test.jsx`: `can` follows the map, an unknown key is false, a missing map is false, and `canRecord` handles none, own and all. Add page tests: the delete control is hidden for a default pilot and shown at `own` on their own flight only, the navigation entry is hidden with its view off, and a flight form's pilot picker loads from options with `pilots.view` off.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement the helpers and replace the role checks using the Route Mapping's keys. Leave `AdminRoute` alone. Handle a 403 on a page by showing the existing empty or error state.
- [ ] **Step 4:** Run `npm run test:run` and `npm run lint`. Expected: PASS, with no new lint errors.
- [ ] **Step 5:** Commit: `Use permissions throughout the frontend`.

### Task 11: Permissions grid

**Files:**
- Create: `frontend/src/components/settings/RolePermissionsGrid.jsx` and its test
- Modify: `frontend/src/pages/SettingsPage.jsx`

**Interfaces:**
- Consumes: `GET /api/permissions`, `PUT /api/permissions`, `POST /api/permissions/reset`.

- [ ] **Step 1:** Load the `impeccable` skill. Write failing tests: renders every feature and action from the API response, Admin shows locked on, locked viewer cells are disabled with a reason, turning off a view also turns off its dependent settings in the draft, save sends only changes, discard restores, a server error shows and keeps the draft, and reset asks for confirmation.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Build the grid from the API response, placed directly below the User Management card and shown only to admins. On a narrow screen, show one card per feature with a role selector, so every setting is reachable on a phone. Update the static role descriptions to say permissions are configurable.
- [ ] **Step 4:** Run `npm run test:run` and `npm run lint`. Expected: PASS.
- [ ] **Step 5:** Commit: `Add role permissions grid to settings`.

### Task 12: Documentation and end-to-end

**Files:**
- Modify: `docs/USER_MANUAL.md` section 18, `frontend/src/pages/UserManualPage.jsx`, `docs/TEST_CHECKLIST.md`, `README.md`, `ROLLBACK.md`, `frontend/e2e/`

- [ ] **Step 1:** Add an e2e journey: the admin grants a pilot flight delete at Own, and a pilot deletes their own flight but cannot delete another's. Reuse the existing auth setup.
- [ ] **Step 2:** Run `cd frontend && npm run e2e`. Expected: PASS. Update journeys only where a default deliberately changed. Chromium is preinstalled; if the pinned Playwright cannot find it, launch with `/opt/pw-browsers/chromium` through a local override that is not committed.
- [ ] **Step 3:** Update the docs. `ROLLBACK.md` gets the downgrade step for migration 0011. `docs/TEST_CHECKLIST.md` gets a staging pass with one login per role.
- [ ] **Step 4:** Write the upgrade notes as a section of the PR description: what changes for each role by default, and the warning that pilots can show as lapsed until the review queue is cleared.
- [ ] **Step 5:** Commit: `Document role permissions`.

### Task 13: Full review and PR

- [ ] **Step 1:** Run the full backend, frontend and e2e suites. Expected: all pass.
- [ ] **Step 2:** Run the migration both ways on a temp database: `alembic upgrade head`, `downgrade -1`, `upgrade head`. Expected: no errors.
- [ ] **Step 3:** Run a whole-branch code review at high effort with a fresh reviewer, giving it the spec, the plan and the diff. Fix every confirmed issue, each with a test.
- [ ] **Step 4:** Check the diff and all commit messages for wording that violates the public-repo constraint.
- [ ] **Step 5:** Report the results to the owner and ask for the go to push. Do not push before that.
- [ ] **Step 6:** After the go, push and open one PR with Summary and Test Plan sections plus the upgrade notes. Follow the merge gate: green CI and zero new SonarCloud issues.
- [ ] **Step 7:** Hand the staging pass to the owner. Staging runs `:main`, so the merged code reaches it after merge, and production stays pinned until a version tag is pushed. Do not tag.
