# Per-sync status and Auto-Sync Interval descriptor

Date: 2026-07-11
Status: Draft (pending user review)

## Problem

On Settings -> Integrations (Skydio card), two issues:

1. The "Auto-Sync Interval" dropdown has no description, unlike "Telemetry
   Auto-Sync" (which got a clear one). Users cannot tell what the scheduled
   metadata sync does.
2. There is a single status block (State / Last synced / Next sync / Last run)
   that reflects only the metadata sync. The telemetry auto-sync has no status
   of its own, so users cannot see when it last ran, when it runs next, or how
   much backfill remains.

## Goal

- Give the "Auto-Sync Interval" control an accurate description mirroring the
  telemetry one.
- Give each automatic sync its own status block directly under its control:
  metadata status under "Auto-Sync Interval", telemetry status under
  "Telemetry Auto-Sync", including a live "flights still missing telemetry"
  backfill count.

## Design

### Accuracy note

The scheduled metadata auto-sync (`_run_scheduled_sync` -> `SyncManager.sync_all`)
pulls flights, vehicles, batteries, controllers, docks, sensors, attachments,
and media. It does NOT fetch telemetry. Telemetry is handled by the separate
telemetry auto-sync. The manual "Sync Now"/"Full Sync" buttons DO also fetch a
telemetry batch, which is why their button descriptors mention telemetry; the
scheduled job does not. The new Auto-Sync Interval description must reflect the
scheduled (metadata-only) behavior.

### Backend

1. Record telemetry-run status. In `SyncManager.batch_sync_telemetry`, after the
   fetch loop and before returning, persist two settings:
   - `last_telemetry_sync_timestamp` = current UTC ISO string.
   - `last_telemetry_sync_result` = JSON `{"synced": <count>}`.
   This captures every actual telemetry fetch (scheduled job, manual "Sync
   Telemetry", and the telemetry batch inside "Sync Now"). The scheduled job's
   skip guard returns before calling the batch when nothing is missing, so a
   caught-up fleet does not update the timestamp (the status shows the last
   real fetch).

2. Extend `GET /api/sync/status` (`SyncStatusResponse` + handler) with:
   - `last_telemetry_sync: str | None` (from `last_telemetry_sync_timestamp`).
   - `telemetry_sync_interval: str | None` (from the setting).
   - `last_telemetry_sync_result: dict | None` (parsed JSON, tolerating garbage
     like the existing `last_sync_result`).
   - `telemetry_remaining: int` = live count of flights with
     `telemetry_synced = false` AND `external_id` not null.
   The existing metadata fields are unchanged.

### Frontend (`IntegrationsPage.jsx`, `ProviderCard`)

1. Add a description under the "Auto-Sync Interval" dropdown, styled like the
   telemetry description: "Automatically pulls new flights, vehicles,
   batteries, and equipment from Skydio on this schedule. Telemetry is handled
   separately by Telemetry Auto-Sync below."

2. Generalize `SyncStatusBlock` into a presentational component driven by props
   (`syncedLabel`, `live`, `lastTime`, `intervalMin`, `runSummary`,
   `runStatus`, `firstError`, `moreErrors`, `extra`) instead of reading
   `syncStatus` directly. The parent computes each block's `runSummary`.

3. Render two status blocks:
   - Metadata, directly under "Auto-Sync Interval": `syncedLabel="Last synced"`,
     `live` = full/incremental when a metadata sync is running, `lastTime` =
     `last_sync`, `intervalMin` = `sync_interval`, `runSummary` = the existing
     flights/vehicles/batteries/errors summary.
   - Telemetry, directly under "Telemetry Auto-Sync": `syncedLabel="Last
     telemetry"`, `live` = telemetry when a telemetry sync is running,
     `lastTime` = `last_telemetry_sync`, `intervalMin` =
     `telemetry_sync_interval`, `runSummary` = `"<synced> flights fetched"` from
     `last_telemetry_sync_result`, and `extra` = a "Missing" line showing
     `"<telemetry_remaining> flights"` (the backfill count; hidden when the
     count is unavailable).
   The single bottom status block is removed in favor of these two.

Both `handleSync` and `handleSyncTelemetry` already refetch `/sync/status` in
their `finally` blocks, so both blocks stay current after manual actions with
no handler change.

### Testing

- Backend:
  - `SyncManager.batch_sync_telemetry` writes `last_telemetry_sync_timestamp`
    and `last_telemetry_sync_result` after a run.
  - `GET /api/sync/status` returns the telemetry fields and a correct
    `telemetry_remaining` count (e.g. seed two unsynced flights with
    external_id -> 2; one synced -> excluded).
- Frontend:
  - The telemetry status block renders "Last telemetry" and the
    "flights still missing telemetry" count from a mocked `/sync/status`.
  - The Auto-Sync Interval description text is present.

## Out of scope

- Changing sync behavior, intervals, or the manual buttons.
- Tracking per-run telemetry error lists (only the synced count is stored).
- A separate "last checked" timestamp for guard-skipped telemetry runs.
