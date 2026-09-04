# Scheduled telemetry auto-sync

Date: 2026-07-11
Status: Draft (pending user review)

## Problem

The 24-hour scheduled sync (`SyncManager.sync_all`) pulls flight metadata,
details, and equipment, but never fetches telemetry points. Telemetry is only
fetched on manual triggers, 10 flights at a time (the "Sync Telemetry" button
and `POST /api/sync/telemetry`, or per-flight refresh). With 1305
Excel-imported flights lacking telemetry, backfilling requires ~130 manual
clicks. There is no automatic telemetry backfill.

## Goal

Add an admin-configurable background job that periodically fetches telemetry
for a small batch of flights that are missing it, mirroring the existing
"Auto-Sync Interval" control. It must not contact the Skydio API when no
flight is missing telemetry.

## Design

### Setting

- New program setting `telemetry_sync_interval`: minutes as a string, `""`
  meaning disabled. Default disabled. Admin-writable
  (`ALLOWED_SETTING_KEYS`) and public-readable (`PUBLIC_KEYS`), same as
  `sync_interval`.

Only one setting. There is no "skip if none" toggle: skipping is unconditional
(see Behavior), so a checkbox would have no meaningful off state.

### Behavior

A new APScheduler job (`telemetry_sync`) runs every N minutes, where N is the
setting value. Each run:

1. Opens a fresh DB session.
2. If the Skydio API token is not configured, returns (no work).
3. Counts flights with `telemetry_synced = false` and `external_id` not null.
   If the count is zero, logs "no telemetry missing, skipping" and returns
   without building credentials or calling the Skydio API.
4. Otherwise fetches telemetry for up to 10 such flights (newest-first) via
   the shared batch function, sets `telemetry_synced = true` /
   `has_telemetry = true` on each, and commits.

Batch size is fixed at 10 (matches the existing manual telemetry batch). The
job is independent of the 24h metadata sync and does not touch
`last_sync_timestamp`.

Rate note: 10 telemetry calls per run; at the fastest interval (30 min) that
is at most 20 Skydio calls/hour, and zero once backfill is complete. The
provider already handles 429 rate-limit retries.

### Backend

- `scheduler.py`: add `TELEMETRY_SYNC_JOB_ID`,
  `_get_telemetry_sync_interval_minutes()`, `_run_scheduled_telemetry_sync()`,
  and `reschedule_telemetry_sync(minutes)` — each mirroring the existing
  `sync_interval` equivalents. Register the telemetry job in
  `start_scheduler` based on the setting.
- `settings.py`: add `telemetry_sync_interval` to `ALLOWED_SETTING_KEYS` and
  `PUBLIC_KEYS`; in the bulk-save handler, call
  `reschedule_telemetry_sync(...)` when `telemetry_sync_interval` is present,
  exactly as it already does for `sync_interval`.
- Refactor (targeted): move `_batch_sync_telemetry` and
  `_store_telemetry_points` from the `sync.py` router into `sync_manager.py`
  so the scheduler and the router share one tested code path instead of the
  scheduler importing a private function from a router. The two existing
  endpoints (`POST /api/sync/now`, `POST /api/sync/telemetry`) keep identical
  behavior, now calling the relocated function.

### Frontend

On Settings -> Integrations, directly below the existing "Auto-Sync Interval"
control:

- A "Telemetry Auto-Sync" dropdown: options Disabled / 30m / 1h / 2h / 6h
  (values `""` / `30` / `60` / `120` / `360`). On change, saves
  `telemetry_sync_interval` via `PUT /settings/bulk`, same pattern as the
  Auto-Sync Interval select. Seeds its initial value from the loaded settings.
- A short description line under it explaining what it does, e.g.: "Fetches
  telemetry for up to 10 flights that are missing it each run, newest first.
  Only contacts Skydio when flights are actually missing telemetry, and stops
  once every flight has telemetry."

### Testing

- Backend:
  - The scheduled telemetry job fetches telemetry for unsynced flights and
    marks them synced.
  - The early-return guard: with no unsynced flights, the job makes zero
    Skydio API calls (assert the provider/HTTP is never invoked).
  - `reschedule_telemetry_sync` adds the job for a positive interval and
    removes it for `""`/None.
  - The relocated `_batch_sync_telemetry` still works from `sync_manager`;
    existing `sync` tests remain green.
  - `telemetry_sync_interval` is admin-writable and public-readable.
- Frontend:
  - The "Telemetry Auto-Sync" dropdown renders the current value and persists
    a change to `/settings/bulk`.
  - The description text is present.

## Out of scope

- Configurable batch size (fixed at 10).
- A per-run "last telemetry sync" status/timestamp in the UI.
- Any change to telemetry storage, the chart, or the manual telemetry button.
