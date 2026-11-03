# Configurable Role Permissions: Design

Status: approved by owner. Date: 2026-11-02.

## Intent

Today each role's abilities are fixed in code. Agencies run their units differently, so the admin should decide what supervisors, pilots and viewers can do, from one screen, without a new release. The grid also becomes the single written answer to "what can this role do", replacing guards, UI checks and manual text that can drift apart.

## Goals

- An admin sets per-feature permissions for Supervisor, Pilot and Viewer under Settings, below User Management.
- The backend enforces every setting. The UI only reflects it.
- Records with an owner support None, Own or All.
- Viewing is toggleable for each feature, and a viewer can never change unit data.

## Non-goals

- Per-user overrides or custom roles. There are still exactly four roles.
- Per-tenant or per-unit data separation. This remains one shared dataset.
- API token scope changes. Tokens still act as their owner, limited by their existing scope and read-only flag, and the owner's role permissions apply.
- Changing authentication, sessions or lockout.

## Anti-goals

The work has failed, even if the grid works, if any of these is true:

- A route has no assigned permission and silently allows access.
- A toggle shows "off" but the data is still reachable through search, export, reports, the dashboard, digests or signed links.
- A grid setting can make a viewer able to change unit data, or lock out the last admin.
- A permission failure in the check itself allows access. Checks fail closed.

## Delivery constraints (owner's decisions)

- One PR, with a thorough code review before it opens.
- Tested on staging before any production release.
- The merge gate applies: green CI and zero new SonarCloud issues.

## Permission options

Each setting is either:

- **Yes / No**
- **None / Own / All**, for records with an owner

Admin always has everything, and its column is shown locked on.

## Default grid

| Feature | Action | Key | Supervisor | Pilot | Viewer |
|---|---|---|---|---|---|
| Flights | View | `flights.view` | Yes | Yes | Yes |
| | Create | `flights.create` | Yes | Yes | locked No |
| | Edit | `flights.edit` | All | Own | locked None |
| | Delete | `flights.delete` | All | None | locked None |
| | Review, bulk actions | `flights.review` | Yes | No | locked No |
| Flight plans | View | `flight_plans.view` | Yes | Yes | Yes |
| | Create | `flight_plans.create` | Yes | Yes | locked No |
| | Edit | `flight_plans.edit` | All | Own | locked None |
| | Approve, deny, delete | `flight_plans.approve` | Yes | No | locked No |
| Incidents | View | `incidents.view` | Yes | Yes | Yes |
| | Create | `incidents.create` | Yes | Yes | locked No |
| | Edit | `incidents.edit` | All | Own | locked None |
| | Resolve or close | `incidents.resolve` | Yes | No | locked No |
| | Delete | `incidents.delete` | Yes | No | locked No |
| Mission and training logs | View | `logs.view` | Yes | Yes | Yes |
| | Create | `logs.create` | Yes | Yes | locked No |
| | Edit, delete | `logs.edit` | All | Own | locked None |
| Maintenance records | View | `maintenance.view` | Yes | Yes | Yes |
| | Create | `maintenance.create` | Yes | Yes | locked No |
| | Edit, delete | `maintenance.edit` | All | Own | locked None |
| Maintenance schedules | Complete | `schedules.complete` | Yes | Yes | locked No |
| | Create, edit, delete | `schedules.manage` | Yes | No | locked No |
| Fleet equipment | View | `fleet.view` | Yes | Yes | Yes |
| | Manage, including components | `fleet.manage` | Yes | No | locked No |
| | Update vehicle location | `fleet.location` | Yes | Yes | locked No |
| Equipment checkouts | Check out, check in | `checkouts.use` | Yes | Yes | locked No |
| | Delete | `checkouts.delete` | Yes | No | locked No |
| Pilots | View | `pilots.view` | Yes | Yes | Yes |
| | View email and phone | `pilots.contacts` | Yes | Yes | No |
| | Edit profile | `pilots.edit` | All | Own | locked None |
| | Create, delete, merge | `pilots.manage` | Yes | No | locked No |
| Certifications and currency | View | `certifications.view` | Yes | Yes | Yes |
| | Manage, send reminders | `certifications.manage` | Yes | No | locked No |
| Checklists | View | `checklists.view` | Yes | Yes | Yes |
| | Complete | `checklists.complete` | Yes | Yes | locked No |
| | Manage templates | `checklists.manage` | Yes | No | locked No |
| Calendar | View | `calendar.view` | Yes | Yes | Yes |
| | Create | `calendar.create` | Yes | Yes | locked No |
| | Edit, delete | `calendar.edit` | All | Own | locked None |
| Documents and photos | View | `files.view` | Yes | Yes | Yes |
| | Upload | `files.upload` | All | Own | locked None |
| | Edit, soft delete | `files.edit` | All | Own | locked None |
| | Restore, legal hold | `files.custody` | Yes | No | locked No |
| Folders | Manage | `folders.manage` | Yes | No | locked No |
| Alerts | View | `alerts.view` | Yes | Yes | Yes |
| | Mark read, dismiss (shared for everyone) | `alerts.dismiss` | Yes | No | locked No |
| Reports and exports | Generate reports | `reports.generate` | Yes | Yes | No |
| | Export CSV | `reports.export` | Yes | Yes | Yes |
| Operating authority, geofences | View | `authority.view` | Yes | Yes | Yes |
| | Manage | `authority.manage` | Yes | No | locked No |
| Vehicle registrations | View | `registrations.view` | Yes | Yes | Yes |
| | Manage | `registrations.manage` | No | No | locked No |
| Audit log | View | `audit.view` | No | No | No |
| Email digest | Send to another address | `digest.redirect` | Yes | No | locked No |

## Outside the grid

**Admin only, never delegable:** user management, the permission grid, settings and integrations, backup and restore, API tokens, bulk imports, flight purposes, and permanent purge.

**Any signed-in user, own account only:** own password, theme, profile and notification preferences. These are not unit data, so a viewer keeps them.

**Always enforced, whatever the grid says:**

- Nobody approves a flight plan they submitted.
- A legal hold blocks delete and purge.
- The last active admin cannot be demoted, deactivated or deleted.
- A viewer can never hold a change permission. This is enforced in three places: the write API refuses it, the runtime check ignores any stored value for a locked viewer cell (including one from a restored backup), and the UI greys it out.

## Meaning of "Own"

"Own" is a fixed rule per record type:

| Record | Own means |
|---|---|
| Flight | `pilot_id` matches the user's linked pilot, or the user logged it |
| Flight plan | submitted by the user |
| Incident | reported by the user |
| Mission and training log | the user created it, or their linked pilot is on the roster |
| Maintenance record | the user created it |
| Calendar event | the user created it |
| Pilot profile | the user's linked pilot |
| Photo | uploaded by the user |
| Document | uploaded by the user, or attached to the user's own pilot record or certification |

Consequences to build for:

- A login with no linked pilot owns no pilot profile, and only the flights it logged.
- `create_flight` must set `created_by_id`, so a pilot who logs a flight for someone else can correct it.
- `created_by_id` exists on the mission log, training log and maintenance record models, but in the backend it is set only by the generic importer (`routers/import_router.py`), and the manual create routes do not set it. Those routes must set it from now on. Records with no recorded creator are editable only by a role with All, apart from a roster match on logs. They are not backfilled, because guessing an owner would be wrong. This means pilots will at first own few existing maintenance records.
- Documents have no uploader column. Add `uploaded_by_id`, nullable, through an Alembic migration.
- A user with Own edit on flights cannot reassign a flight to a different pilot. Only All can.
- A pilot may log a new flight for another pilot (owner's decision). The flight enters the review queue like any other, and that review is the control.

## Behavior changes tied to this design

- **New flights:** a flight logged by hand always starts as needs review, for any role and any target pilot. `create_flight` already does this, so tests must pin it.
- **Reviewed flights:** when a user without `flights.review` changes a non-review field on a reviewed flight, the flight returns to the review queue. Edits by a user with `flights.review` keep the status. Echoing unchanged values does not count as a change.
- **Pilot currency (owner's decision):** only flights with `review_status` of reviewed count toward currency, from every source, including synced and imported flights. Flights awaiting review, including one sent back after an edit, stop counting until a supervisor reviews them. Every place that evaluates currency must use the same rule. Release notes must warn that pilots can show as lapsed on upgrade until the review queue is cleared.
- **Incidents:** `status`, `resolution`, `resolution_date` and `corrective_actions` need `incidents.resolve`. Other fields need `incidents.edit`.
- **Email digest:** a stored address override is honored only while the role holds `digest.redirect`, on both preference save and scheduled send. A role without it uses the account address. Stored overrides are kept, not erased.
- **Digest and report content:** sections follow the matching view permission instead of role names.

## Builder's calls made in this design

These were decided by the design author, not the owner, and the owner can overrule them when reading this document.

- **`files.upload` Own:** keeps today's rule. Own may upload general documents, vehicle documents and photos, and may attach to a pilot record or certification only if it is the user's own. All may attach to anyone's.
- **Alerts:** read and dismissed remain single shared flags, with no per-user table. Both actions need `alerts.dismiss`, so by default pilots no longer clear alerts for the whole unit.
- **Change without view:** a role cannot hold a change permission while that feature's view is off. The write API refuses the combination and the grid turns dependent settings off with the view. Restored rows that break this rule are dropped. `pilots.contacts` also needs `pilots.view`.
- **Added view rows:** checklists, calendar, alerts, operating authority and vehicle registrations gained a View row so every feature's viewing can be toggled.

## Enforcing view toggles

Every read path must check the matching view key, not only the feature's own routes. The parallel paths are search, command palette, dashboard lists, analytics, reports, CSV and GPX or KML export, alerts, digests, flight telemetry, media, and photo and document serving, including minting signed URLs.

- CSV export requires both `reports.export` and the entity's view key.
- **Scope of a view toggle (owner's decision):** it hides the feature's own pages, lists, search results, exports and report sections. Names on other features' records stay visible, so a flight still shows its pilot's name with `pilots.view` off, and forms keep their pilot and vehicle pickers. Contact details are the exception: they follow `pilots.contacts` everywhere.
- Unit-wide totals with no names stay visible to every signed-in user. Feature-specific counts and charts, such as flight charts, incident stats and per-pilot hours, follow that feature's view key: `flights.view` for flight charts. A per-pilot chart needs only `flights.view`, by the name rule above.
- `/compliance` stays visible because it is a unit-wide score, and its named lists follow their view keys.
- Turning off a view hides the matching navigation entry.
- A signed URL already issued remains valid until its 10-minute expiry.

## Storage and enforcement

- New table `role_permissions` with `role`, `permission_key`, `value`, and a unique constraint on role and key. It stores admin changes only.
- Defaults live in one code registry, which also holds each key's feature label, action label, option type and viewer lock. A missing row means the default, so a future feature gets a safe default without a data migration.
- An unknown key or invalid value is refused on write and ignored on read, falling back to the default.
- Backend dependency `require_permission("key")` replaces role aliases on routes. For None / Own / All, a helper returns the level and the route applies the ownership rule to the loaded record.
- Permissions load once per request, as the role already does. A change applies from each user's next request and does not end sessions.
- `require_manager` and the frontend's `isManager` are unused legacy. Remove them if the build confirms that.

## API

- `GET /api/permissions`: registry plus current values. Admin only.
- `PUT /api/permissions`: bulk update. Admin only. Validates all, applies atomically, and writes one audit entry listing role, key, old value and new value for each change.
- `POST /api/permissions/reset`: back to defaults, audited the same way.
- `/api/auth/me` and the login response include the current user's resolved permissions.

## Interface

- Location: Settings, in the same card column, directly below User Management. Admin only.
- A grid grouped by feature, with Supervisor, Pilot and Viewer columns and Admin shown locked on.
- Locked viewer cells are greyed out with a short reason.
- It must work on a phone. The owner often uses a phone, so the grid cannot rely on a wide table alone.
- Save and discard, plus "Reset to defaults" with a confirmation.
- The static role descriptions in User Management are updated to say permissions are configurable.
- The frontend gains `can(key)` and `level(key)` from `AuthContext`, replacing role checks throughout. `AdminRoute` stays for admin-only pages.
- Use the `impeccable` skill for this interface work.

## Backup and restore

- `role_permissions` joins `EXPORT_ORDER`, so backups carry it.
- A backup without that table restores to defaults, because the wipe-and-reload leaves it empty.
- Restored rows pass the same validation as the write API. Invalid rows, locked viewer rows and change-without-view rows are dropped.

## Upgrade and rollback

- Upgrading applies the default grid, which intentionally tightens some pilot abilities and differs from earlier releases. Release notes must list what changes for each role.
- Migrations: create `role_permissions`, and add `documents.uploaded_by_id`. `ROLLBACK.md` is updated with the downgrade step, following the existing procedure: run the downgrade inside the new image before switching back.

## Testing

- **Coverage test:** walks every registered route and fails if a route has neither a permission, an explicit admin-only marker, nor an explicit own-account or public marker. This is the main protection against a missed mapping.
- **Matrix test:** every key against every role at its default, plus flipping each toggle and confirming the behavior changes. Dependent keys are flipped with their view key on.
- **Read-path tests:** with each view off, search, export, reports, dashboard lists, digests and signed URL minting return nothing for that feature.
- **Always-enforced tests:** viewer lock including a restored row, last admin, self-approval, legal hold.
- **Currency tests:** an unreviewed flight does not count, a reviewed one does, and an edit that sends a flight back removes it until it is reviewed again.
- **Ownership tests:** own versus another user's record for each record type, a login with no linked pilot, and a pre-existing record with no creator.
- **Frontend tests:** the grid, plus UI gating with `can()` and `level()`.
- Existing 403 tests are updated only where a default deliberately changed.

## Documentation

Update `docs/USER_MANUAL.md` section 18, the in-app manual page, `docs/TEST_CHECKLIST.md`, `README.md` security text, and `ROLLBACK.md`.

## Left to the builder

- Component and hook structure for the grid.
- Internal naming apart from the permission keys above, and how routes are converted.
- The order of commits, keeping backend, frontend and tests as separate commits within the one PR.
- The mobile layout for the grid, as long as every setting is reachable on a phone.
