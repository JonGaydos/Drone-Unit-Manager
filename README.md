# Drone Unit Manager

A self-hosted drone fleet management platform for law enforcement, public safety, and enterprise drone programs. Track flights, pilots, certifications, equipment, maintenance, compliance, and more from a single application.

## Overview

Drone Unit Manager replaces spreadsheets, AirData subscriptions, and scattered documentation with a unified platform that your organization owns and controls. Import flight data from Skydio's Cloud API, Airdata.com exports, DJI flight logs, Excel spreadsheets, and more. Manage pilot certifications and currency, track equipment maintenance, generate compliance reports, and monitor fleet health — all from a modern web interface accessible on desktop and mobile.

The application runs as a single Docker container with no external dependencies. Your data stays on your infrastructure.

## Features

### Fleet Management
- Vehicle, battery, controller, sensor, and attachment tracking
- Equipment check-in/check-out with chain of custody (audit-logged with both the entering user and the receiving pilot), with a dedicated Checkouts page listing active and returned records
- Component-level tracking (propellers, gimbals, cameras) with flight hours and warranty
- FAA registration tracking with 2-year renewal calculation and history
- Equipment merge for deduplicating batteries, sensors, and attachments
- Pilot merge for consolidating duplicate pilot records from imports
- Battery health trending with historical readings chart
- Smart equipment dropdowns — type to search or auto-create new Fleet records

### Flight Tracking and Telemetry
- Import flights from Skydio Cloud API, Airdata.com (CSV/JSON/ZIP), DJI .txt, Litchi CSV, Parrot/ANAFI GUTMA JSON, or Excel
- Multi-file import with progress tracking and automatic deduplication
- GPS flight path visualization on interactive maps
- Altitude, speed, and battery telemetry charts
- GPX and KML export for Google Earth and GPS devices
- AGL altitude calculation from GPS data with bucket-averaged smoothing
- Per-flight detail with equipment linkage (battery, sensor, attachments, carrier)
- Automatic pilot matching via email cross-reference
- Reverse geocoding for takeoff addresses
- Telemetry sync toggle for supervisors
- Smart auto-tagging (Night Flight, High Speed, Low Battery, etc.)

### Pilot Management
- Pilot profiles with contact info, badge numbers, photos
- Certification matrix with customizable cert types and status labels
- Pilot currency tracking with admin-managed rules (configurable hours / flights / days, optionally per vehicle model)
- Performance analytics (flights by month, purpose, training hours)
- Document attachments per pilot

### Mission and Training Logs
- Mission Log for non-flight missions and operations (reason, location, case number, man-hours)
- Training Log for training events (training type, instructor, man-hours)
- Multiple pilots per entry, each with a role (PIC, Observer, Spotter, etc.) and hours
- Per-pilot and per-vehicle cross-reference links, CSV export, and import

### Unit Calendar
- Single FullCalendar view aggregating flights (per-day counts), missions, training, maintenance-due dates, and certification expirations
- Manual events and leave entries — any user can add their own; supervisors and admins can edit any
- Category show/hide toggles and Month, Week, and List views

### Drone Locations
- Dashboard Locations tile showing each active drone's last-known location
- Location is the more recent of an active equipment checkout (with a pilot) or a manually set location
- Set a drone to a named place or a pilot from the dashboard
- Admin-configurable list of named places (drone_location_places)

### Pre-Flight Operations
- Live weather briefing with GO/CAUTION/NO-GO advisory
- METAR, TAF, and hyperlocal weather from GPS coordinates
- Configurable weather thresholds per organization
- Organization Default Location pre-populates Weather, Airspace, and the dashboard weather tile (falls back to the White House when unset)
- Flight plan submission and supervisor approval workflow
- Customizable pre-flight checklist templates

### Compliance and Reporting
- Compliance dashboard with 0-100 score
- Expired certifications, registrations, and overdue maintenance tracking
- PDF reports with organization logo and charts
- Report types: Flight Summary, Pilot Hours, Equipment Utilization, Pilot Activity Summary, Annual Unit Report (multi-section state-of-the-unit briefing), Per-Pilot Annual Review (one PDF per pilot, bundled as zip), Pilot Certifications, Battery Status, Maintenance History
- Saved filter presets, search filter on pilot/vehicle pickers, and date-range preset chips
- CSV export on every page

### Maintenance
- Manual maintenance records with history
- Recurring schedule system (monthly, quarterly, yearly)
- Automatic alerts when maintenance is due
- Linked to specific vehicles, batteries, controllers, or organization-wide

### Activity Reports
- Incident reporting (crashes, near-misses, equipment failures)
- Success tracking (missing persons found, suspects located, evidence collected)
- Severity levels, resolution workflow, corrective actions
- Linked to flights, pilots, and vehicles

### Photo Gallery and Document Storage
- Photo uploads with date grouping and lightbox viewer
- Batch upload support
- Folder-based document storage with system folders
- Documents auto-filed from certifications, maintenance, and profiles

### Analytics
- Interactive Power BI-style cross-filtering
- Click any chart element to filter all other charts
- Flights by pilot, year, purpose, and vehicle
- Flight locations map

### Live Airspace (ADS-B)
- Real-time nearby aircraft map using airplanes.live ADS-B data
- Click-to-set location with configurable search radius (25-200 miles)
- Aircraft color-coded by altitude band with auto-refresh
- Clickable aircraft markers showing callsign, altitude, speed, heading, squawk

### Email Notifications
- Daily/weekly email digest with actionable items
- Configurable SMTP server with test email
- Per-user notification preferences (categories, frequency, send time)
- Digest includes: pending approvals, expiring certs, overdue maintenance, recent incidents

### Cross-Reference Navigation
- Every pilot, vehicle, battery, sensor, attachment, purpose code, and flight ID is a clickable link
- Navigate between related records with a single click
- Purpose codes link to filtered flight views
- Consistent orange link styling throughout the app
- Command palette (Ctrl/Cmd+K) for global search across pages, pilots, vehicles, and flights, with type-filter chips and recent jumps

### API Integrations
- Skydio Cloud API (flights, vehicles, batteries, controllers, telemetry, users)
- Multi-platform provider architecture (provider_serial, data_source, extra_data)
- Airdata.com import (CSV with 52 fields, JSON, bulk ZIP)
- DJI Go 4, Litchi, and generic CSV flight log import
- Drone-agnostic architecture for future integrations (DJI, BRINC, Parrot, Autel)
- Automatic and manual sync with intelligent deduplication
- Bulk telemetry fetching
- Persistent sync-status panel (current state, last/next sync, last-run counts, and a green/amber/red status dot including failures)
- Disconnect button to clear the stored provider token

### Security and Access Control
- Four roles: Admin, Supervisor, Pilot, Viewer
- First-run setup wizard (no default credentials)
- Login rate limiting
- File upload size limits with stream-checked size enforcement on the largest endpoints
- Activity audit log tracking destructive admin actions (role changes, password resets, backup export/import, mass-delete operations, equipment checkouts)
- Path traversal prevention on document uploads (entity_type allowlist + filename sanitization + realpath check) and backup ZIP extraction (zip-slip rejection)
- JWT authentication with configurable secret key
- Short-lived HMAC-signed photo URLs (10-minute TTL) for `<img>` tags — replaces the older JWT-in-query-param pattern
- Password policy enforcement (12+ characters, uppercase, number)
- File type whitelist validation on all uploads
- CORS restricted to specific methods and headers
- Request ID tracking (X-Request-ID header)
- Settings access control: non-admin users only see non-sensitive keys (org name/logo, sidebar, weather defaults). SMTP and integration secrets are admin-only and render as a presence marker even to admins.
- Linking and unlinking photos to flights and incidents requires Supervisor or Admin; pilots and viewers can view linked photos but not attach or detach them
- Backup import requires Admin JWT once any user exists, or a one-time install token (printed to container logs) on a fresh install

## Quick Start

### Docker

```bash
docker run -d \
  --name drone-unit-manager \
  -p 3014:8000 \
  -v /path/to/data:/app/data \
  -e TZ=America/Chicago \
  ghcr.io/jongaydos/drone-unit-manager:latest
```

Open `http://localhost:3014` and complete the setup wizard.

### Docker Compose

```yaml
services:
  app:
    image: ghcr.io/jongaydos/drone-unit-manager:latest
    ports:
      - "3014:8000"
    volumes:
      - ./data:/app/data
    environment:
      - TZ=America/Chicago
    restart: unless-stopped
```

```bash
docker compose up -d
```

### Upgrading

Normal upgrades are a plain pull and restart:

```bash
docker compose pull && docker compose up -d
```

The database schema is managed by Alembic. On startup the container runs `alembic upgrade head`, so any pending schema migrations apply automatically against your existing data volume. No manual schema steps are required. Back up the data directory before a major upgrade as a precaution.

### Unraid

1. Add container from the Community Applications template, or manually:
   - Repository: `ghcr.io/jongaydos/drone-unit-manager:latest`
   - Port: 3014 -> 8000
   - Path: /mnt/user/appdata/drone-unit-manager -> /app/data
2. Start the container
3. Open the WebUI and complete setup

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Internal server port |
| `SECRET_KEY` | Auto-generated, persisted to `data/.secret_key` | JWT signing + photo URL signing key. Set explicitly to share sessions across containers. |
| `TZ` | `UTC` | Timezone |

### First-Run Setup

On first launch with an empty database, the application displays a setup wizard. There are three steps:

1. **Organization** — Org name, your name, email.
2. **Admin Account** — Username + password (12+ chars, 1 uppercase, 1 number).
3. **Optional Setup** — Upload an organization logo, configure the Skydio Cloud API integration, configure SMTP for email digests, and/or import existing flight logs (DJI, Litchi, Airdata, Parrot, Skydio formats — auto-detected). Each section is independently skippable and can be set up later from **Settings**.

No default credentials exist. The first account created becomes the admin.

Alternatively, restore from a backup ZIP on the setup screen using the install token printed to the container logs at first boot.

### Recommended Getting Started Workflow

Follow these steps in order for the best experience:

1. **Initial Setup** — Complete the setup wizard to create your admin account and organization
2. **Import Excel Data** — If you have existing flight data in Excel spreadsheets, import them first via Settings > Integrations > Flight Log Import. This creates your pilots, vehicles, and flight history in one step. You can also import Airdata CSV/JSON/ZIP or DJI .txt files at this stage.
3. **Set Up Pilot Profiles** — Go to the Pilots page and add email addresses to each pilot. This is critical for API sync matching — the system matches API pilots to local profiles by email address.
4. **Connect Skydio API** — Now go to Settings > Integrations > Skydio, enter your API credentials, and sync. Because pilots already have email addresses, the sync will automatically match Skydio users to your pilots.
5. **Sync Telemetry** — After the initial sync, click "Sync Telemetry (10)" repeatedly to backfill GPS/altitude data for your flights. Each click fetches data for 10 flights.
6. **Configure Settings** — Set up weather thresholds, certification types, sidebar layout, email notifications, and any other preferences.

### Skydio API Integration

1. Log into Skydio Cloud at cloud.skydio.com
2. Go to Settings > Integrations > API Tokens
3. Create a token with read access to: Flights, Flight Telemetry, Vehicles, Batteries, Controllers, Users, Attachments, Sensor Packages
4. In Drone Unit Manager, go to Settings > Integrations tab > Skydio
5. Enter the API Token and Token ID
6. Click Test Connection, then Sync Now

The sync buttons:
- **Sync Now** — Fetches new flights since last sync, plus telemetry for up to 10 flights
- **Full Sync** — Fetches all flights, cleans up empty records, plus telemetry
- **Sync Telemetry (10)** — Fetches GPS/altitude telemetry data for 10 flights that don't have it yet. Click repeatedly to backfill all flights.

For automatic pilot matching, ensure each pilot's profile has their Skydio account email address before syncing.

### Excel Import

The application imports flight data from Excel spreadsheets (.xlsx). Use the Flight Log Import section in Settings > Integrations with Auto-detect format selected.

A sheet named "Skydio" should contain these columns:

```
Flight ID, Vehicle, Pilot, Local Takeoff Time, Takeoff, Takeoff Address,
Takeoff Latitude, Takeoff Longitude, Land, Duration (seconds), Battery,
Sensor Package, Attachment (TOP), Attachment (BOTTOM), Attachment (LEFT),
Attachment (RIGHT), Carrier(s), Purpose
```

An optional "Pilot Info" sheet imports pilot profiles and certification data. The import automatically creates pilots and vehicles that don't exist yet.

### Airdata Import

Import flights from Airdata.com in multiple formats:

- **Airdata CSV**: Single-flight export with 52 data columns (altitude, gimbal, RC inputs, battery temperature, flight mode)
- **Airdata JSON**: Single-flight JSON export with channel-based telemetry
- **Airdata ZIP**: Bulk export of all flights (ZIP of JSON files)

Upload via Settings > Integrations tab > Flight Log Import. Select multiple files at once using Ctrl+click. Existing flights are automatically deduplicated by flight ID.

### DJI and Litchi Import

Import flight logs from DJI Go 4 (.txt files) or Litchi (.csv files). The application auto-detects the format and extracts telemetry data including GPS path, altitude, speed, and battery.

## Architecture

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, SQLite
- **Frontend:** React 19, Vite, Tailwind CSS v4, Recharts, Leaflet.js
- **Database:** 37+ tables, 250+ API endpoints
- **Schema:** Managed by Alembic migrations (a baseline migration plus future revisions); `alembic upgrade head` runs automatically at startup
- **Telemetry:** Separate SQLite database for high-volume flight telemetry (created directly from its own metadata, not under Alembic)
- **Deployment:** Single Docker container, multi-stage build

## API Documentation

Interactive API documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc) on your running instance.

## Backup and Restore

The application has built-in backup and restore — no container stop required.

### Backup (in-app)

Go to **Settings → General → Backup & Restore** and click **Export Backup**. Choose whether to include telemetry (much larger). The download is a ZIP containing every table as JSON plus all uploaded files.

The export is admin-only and audit-logged.

### Restore (fresh install)

On a fresh install, the **Restore from a backup instead?** option on the setup screen accepts a backup ZIP plus the one-time install token. The install token is generated at container startup when no users exist and is available in two places:

```bash
# Option 1: container logs
docker logs drone-unit-manager 2>&1 | grep -A1 "install token"

# Option 2: file in the data volume (openable in Notepad)
cat /path/to/data/install_token.txt
```

The token is automatically retired after a successful fresh-install restore.

### Restore (existing install)

Once any user exists, the in-app restore option is no longer shown. The `POST /backup/import` endpoint still accepts a backup ZIP, but requires an Admin bearer token, so an existing-install restore is performed against the API directly (for example with `curl`) rather than through the UI. The simplest path to a clean restore is a fresh data volume plus the fresh-install flow above.

### Filesystem backup (fallback)

If you'd rather snapshot the data directory directly:

```bash
docker stop drone-unit-manager
cp /path/to/data/drone_unit_manager.db /path/to/backup/
cp /path/to/data/telemetry.db /path/to/backup/
cp -r /path/to/data/uploads /path/to/backup/
docker start drone-unit-manager
```

## License

MIT License. See [LICENSE](LICENSE) for details.
