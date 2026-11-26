# Upgrading

## Release checks: image scan and database step

The release build scans the image and stops before publishing if it finds a
fixable HIGH or CRITICAL package issue. If a build is blocked, read the scan
output in the run log. Either update the named package (rebuild, or bump the
base image or dependency) or have the owner decide whether to accept it, and
record that decision before re-running. Issues with no fix available do not
block.

Behind a reverse proxy or tunnel, set `TRUSTED_PROXIES` before upgrading (see
"Reverse Proxy" in the README). The login lock counts failures per address, so
without it every visitor shares the proxy's address.

## 3.7.2: what changes on upgrade

- **No new migration.** To go back to 3.7.1, change the Repository tag.
- **Public health check says only up or down.** `/api/health` returns
  `{"status":"ok"}`, or `{"status":"unhealthy"}` with HTTP 503 when a database
  cannot be reached. It no longer shows the version, the databases, backup and
  sync warnings or whether the API docs are served: an unauthenticated visitor
  could read them. The Docker health check and uptime monitors that check the
  status code are unaffected.
- **Admin health details.** `/api/health/details` returns the full report for
  an admin login or admin API token. Settings, General shows admins the
  version at the bottom; use it instead of curl to tell production from
  staging.
- **API Documentation card.** Shown to admins only, when the docs are on.

## 3.7.1: what changes on upgrade

3.7.0 was tagged but never deployed, so a 3.6.0 installation upgrades straight
to 3.7.1 and gets everything under "3.7.0" below as well.

- **No new migration.** 3.7.1 adds nothing beyond migration 0018 from 3.7.0.
  To go back to 3.6.0, see `ROLLBACK.md`.
- **Flights list.** A sortable **Distance** column (meters below 1 km,
  kilometers with one decimal above). **Location** shows the landing address
  when the takeoff address is empty.
- **Analytics.** The Flight Locations map zooms to fit all markers.
- **Compliance.** The Flight Requirements tab has a **Past missed periods**
  list across all pilots, filterable by requirement, with Excuse and
  Un-excuse for users with the excuse permission. Rolling requirements are not
  in it (their lapses stay on the pilot page).
- **Interface.** The page header shows the page name on every page, including
  detail pages; old `/currency` links open Compliance, Flight Requirements;
  Home and End keys work on the Compliance tabs; Fleet has no empty Actions
  column for users who cannot manage the fleet; the certification matrix puts
  the bulk-renewal checkbox beside its status icon, only on certifications
  with an expiry date; coordinates on the flight page show 7 decimals.

## 3.7.0: what changes on upgrade

- **Migration 0018 runs on start.** It adds the rolling requirement tables
  (`flight_requirement_lapses`, `flight_requirement_excusals`), each user's
  dashboard and analytics layout, and each aircraft's hourly operating cost.
  It drops `currency_rules` and `currency_rule_models` with their rows. To go
  back to 3.6.0, see `ROLLBACK.md`.
- **Currency is removed.** Rules, status, reminders, the dashboard tile, the
  pilot card, the Settings card and the Compliance section are gone. Flight
  Requirements take its place. Write down any currency rule you still need
  before upgrading and recreate it as a rolling requirement afterwards.
- **Currency API removed.** The `/api/currency` routes and the API token area
  entry are gone; calls return 404. The permission row "Certifications and
  currency" is now "Certifications" (keys unchanged).
- **Rolling requirements.** A new Rolling window period ("the last N days,
  weeks or months"). Each pilot is Current, Lapsed, Not yet due or Excused
  (until a date), checked daily; every lapse is saved with its start and end.
- **Score change.** Flight requirements take currency's 15 points in the
  compliance score: a pilot costs points when they missed the latest closed
  period of an active requirement or are lapsed on a rolling one now (a pilot
  counts once). Nothing is deducted while no requirement is active. The other
  parts of the score are unchanged.
- **Page move.** Flight Requirements and the requirement settings are tabs of
  the Compliance page (Overview, Flight Requirements, Setup). The sidebar has
  one Compliance entry; `/requirements` and `/settings?tab=requirements` open
  the Flight Requirements tab.
- **Background distance fill.** About four minutes after the first start, a
  background job fills distance, landing coordinates and landing time from
  stored telemetry for existing flights, then looks up landing addresses at
  one per second (about 35 to 40 minutes for a large history). Typed values are
  never replaced. It then runs daily, so a new flight gets its landing address
  the next day.
- **Hourly rates to set.** Flight cost estimates need an Hourly Operating Cost
  on each aircraft (Fleet, edit vehicle). Until one is set, flights without a
  typed cost show no cost.
- **Interface.** The desktop page header stays in place while pages scroll;
  the Dashboard and Analytics can be arranged per user (admins can save a unit
  default); the Flights selection bar is always shown to reviewers;
  Certifications has Matrix, By pilot and By urgency views.

## 3.6.0: what changes on upgrade

- **Migrations run on start.** 0016 moves each currency rule's vehicle model
  into a list; 0017 adds the Flight Requirements tables. Existing data is
  unchanged. To go back to 3.5.0, see `ROLLBACK.md` (requirement data is lost).
- **Currency rules pick models from the fleet.** The free-text model field is
  replaced by toggles, a rule can cover several models, and supervisors can
  manage currency rules (the Certifications and currency: Manage permission).
- **Currency API change for scripts.** Rules use `vehicle_models` (a list) in
  place of `vehicle_model`, in requests, responses and the currency status. A
  write that still sends `vehicle_model` is refused with 422.
- **Flight Requirements.** Fixed-period flight assignments with their own
  Settings tab, dashboard tile, pilot card, score, calendar deadlines, CSV and
  report. New permission rows: Flight requirements View (all roles), Manage and
  Excuse (supervisors by default). The compliance score is unchanged.
- **Requirement emails are off by default.** Turn on Send requirement emails in
  Settings, Flight Requirements, once SMTP is set up. The digest section is
  opt-in for each user.
- **A new daily job** closes requirement periods and, if emails are on, sends
  reminders and miss emails.
- **API tokens.** The Pilots area now also covers `/api/requirements`.
- **Before the upgrade:** rename any vehicle whose model is misspelled, so the
  model toggles show one entry per real model.

## 3.5.0: what changes on upgrade

- **Migrations run on start.** 0014 rebuilds every table so ids are never
  reused; 0015 drops the geofences table and its rows. To go back to 3.4.2,
  see `ROLLBACK.md`.
- **Geofences are removed.** The feature had an API but no screen.
- **Backups hold everything.** A backup now includes password hashes, API
  tokens, the SMTP password and the Skydio token, so a restore brings the whole
  install back. The file is not encrypted: store and share it like a password.
- **Restoring over a running install needs a typed confirmation.** Send the
  form field `confirm_restore` with the exact text `REPLACE ALL DATA` to
  `POST /api/backup/import` (admin token). Without it the restore is refused
  with 409. Everyone is signed out afterwards; passwords still work.
- **`CORS_ORIGINS` defaults to empty.** The app serves its own pages, so a
  production install needs none. Set it only for a page on another origin.
- **Login lock per address.** 10 failed sign-ins in 15 minutes lock that
  address out of the account; 50 across all addresses lock the account for
  15 minutes; a successful sign-in clears that address's count.
- **User manual rewritten.** Topics and One page views, with pictures. Every
  user can now change their own password under Settings, General.

## Restoring a backup: held items and audit entries

A restore replaces the database with the backup. If that would remove or change
a photo or document under legal hold, the restore is refused with a list of the
held items and nothing changes. To go ahead, send the form field
`confirm_holds` with the exact text `RESTORE HELD ITEMS` to
`POST /api/backup/import`. On a live install this is an API step with an admin
token: the setup screen restores only into a fresh install, which has no held
items. Each held item the restore removed or changed gets its own audit entry.
A held item the backup carries unchanged needs no confirmation.

The audit entries in a backup are added to this install's own, marked as
imported, and one summary entry records the backup date, how many were added,
and what was restored, including a telemetry or file step that failed. Backups from before the audit log recorded usernames restore the same
way.

## 3.1.10: the container fixes its data folder's ownership

From 3.1.10 the container starts as root only long enough to give the data
directory to the app's user, then drops to that user before the app starts. The
app itself still never runs as root. A data folder that is deleted and recreated,
or copied in as root, no longer stops the container: there is no manual `chown`.

The user is chosen with two variables, `PUID` and `PGID`, defaulting to `99` and
`100` (Unraid's `nobody:users`). Only files not already owned by that user are
changed, so a start does not rewrite a large data folder.

To use it, **remove `--user 99:100` from Extra Parameters** (the templates in the
repository no longer carry it). Leaving `--user` in place keeps the behaviour
described below: the container runs as that user from the start and the folder
must already be writable by it. `PUID=0` keeps root deliberately.

## To v3: the container no longer runs as root

Every version up to and including 2.2.0 ran the application as `root` inside the
container. From v3 it runs as an ordinary user, `app` (uid 1000, gid 1000).

Nothing outside `/app/data` is written at runtime, so this is the only thing
that changes: **the mapped host directory has to be writable by the user the
container runs as.** On an existing install that directory is owned by `root`,
because the container that created it was root, so it needs one of the two steps
below before the container will start.

The entrypoint checks this first and stops with an explicit message rather than
failing somewhere further in, so a container that exits immediately after an
upgrade is almost certainly this. Check the log.

### Unraid

`appdata` is conventionally owned by `nobody:users`, uid 99 gid 100. Add this to
the container's **Extra Parameters** (both templates in the repository already
carry it):

```
--user 99:100
```

Then hand the existing directory to that user, once, from the Unraid terminal:

```bash
chown -R 99:100 /mnt/user/appdata/drone-unit-manager
```

`--user` overrides the image's own user, so the uid the image was built with
stops mattering.

### Docker Compose or plain Docker

Either give the directory to uid 1000:

```bash
chown -R 1000:1000 /path/to/your/data
```

or run as whichever user already owns it:

```yaml
services:
  app:
    user: "1000:1000"   # or whatever `stat -c '%u:%g' /path/to/your/data` says
```

### Staying on root

Adding `--user 0:0` keeps the old behaviour. It is a valid escape hatch during a
migration, but it gives up what the change is for: a container escape from a
root process is an escape as root on the host.

## Checking it worked

```bash
docker exec <container> id
```

should print the uid the data directory is owned by, and

```bash
curl -s http://<host>:<port>/api/health
```

should return `{"status":"ok"}`. A container that starts but returns
`{"status":"unhealthy"}` (HTTP 503) cannot reach a database, which is usually a
data directory the process can read but cannot write.

The public endpoint says only up or down. To confirm the version and see
warnings (stale backup or sync, stopped scheduler, unwritable upload folders),
sign in as an admin: Settings, General shows the version at the bottom, and
`/api/health/details` returns the full report.
