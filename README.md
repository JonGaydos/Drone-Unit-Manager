# Drone Unit Manager

A self-hosted drone fleet management platform for law enforcement, public safety, and enterprise drone programs. Track flights, pilots, certifications, equipment, maintenance, compliance, and more from a single application.

## Overview

Drone Unit Manager replaces spreadsheets, AirData subscriptions, and scattered documentation with a unified platform that your organization owns and controls. Import flight data from Skydio's Cloud API or Excel spreadsheets, manage pilot certifications and currency, track equipment maintenance, generate compliance reports, and monitor fleet health — all from a modern web interface accessible on desktop and mobile.

The application runs as a single Docker container with no external dependencies. Your data stays on your infrastructure.

## Features

### Fleet Management
- Vehicle, battery, controller, sensor, and attachment tracking
- Equipment check-in/check-out with chain of custody
- Component-level tracking (propellers, gimbals, cameras) with flight hours and warranty
- FAA registration tracking with 2-year renewal calculation and history

### Flight Tracking and Telemetry
- Import flights from Skydio Cloud API or Excel spreadsheets
- GPS flight path visualization on interactive maps
- Altitude, speed, and battery telemetry charts
- Per-flight detail with equipment linkage (battery, sensor, attachments, carrier)
- Automatic pilot matching via email cross-reference
- Reverse geocoding for takeoff addresses

### Pilot Management
- Pilot profiles with contact info, badge numbers, photos
- Certification matrix with customizable cert types and status labels
- Pilot currency tracking (configurable hours-in-days rules)
- Performance analytics (flights by month, purpose, training hours)
- Document attachments per pilot

### Pre-Flight Operations
- Live weather briefing with GO/CAUTION/NO-GO advisory
- METAR, TAF, and hyperlocal weather from GPS coordinates
- Configurable weather thresholds per organization
- Flight plan submission and supervisor approval workflow
- Customizable pre-flight checklist templates

### Compliance and Reporting
- Compliance dashboard with 0-100 score
- Expired certifications, registrations, and overdue maintenance tracking
- PDF reports with organization logo and charts
- Report types: Flight Summary, Pilot Hours, Equipment Utilization, Pilot Activity Summary, Annual Unit Report, Certifications, Battery Status, Maintenance History
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

### API Integrations
- Skydio Cloud API (flights, vehicles, batteries, controllers, telemetry, users)
- Drone-agnostic architecture for future integrations (DJI, BRINC)
- Automatic and manual sync with intelligent deduplication
- Bulk telemetry fetching

### Security and Access Control
- Four roles: Admin, Supervisor, Pilot, Viewer
- First-run setup wizard (no default credentials)
- Login rate limiting
- File upload size limits
- Activity audit log tracking all changes
- Path traversal prevention
- JWT authentication with configurable secret key
- Password policy enforcement (12+ characters, uppercase, number)

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
| `SECRET_KEY` | Auto-generated | JWT signing key. Set for persistent sessions across restarts. |
| `TZ` | `UTC` | Timezone |
| `ADMIN_DEFAULT_PASSWORD` | None | Not used — setup wizard handles initial account creation |

### First-Run Setup

On first launch with an empty database, the application displays a setup wizard. Enter your organization name, your name, and create an admin account. No default credentials exist.

### Skydio API Integration

1. Log into Skydio Cloud at cloud.skydio.com
2. Go to Settings > Integrations > API Tokens
3. Create a token with read access to: Flights, Flight Telemetry, Vehicles, Batteries, Controllers, Users, Attachments, Sensor Packages
4. In Drone Unit Manager, go to Settings > Skydio Cloud API
5. Enter the API Token and Token ID
6. Click Test Connection, then Sync All

For automatic pilot matching, ensure each pilot's profile has their Skydio account email address.

### Excel Import

The application imports flight data from Excel spreadsheets with a sheet named "Skydio" containing these columns:

```
Flight ID, Vehicle, Pilot, Local Takeoff Time, Takeoff, Takeoff Address,
Takeoff Latitude, Takeoff Longitude, Land, Duration (seconds), Battery,
Sensor Package, Attachment (TOP), Attachment (BOTTOM), Attachment (LEFT),
Attachment (RIGHT), Carrier(s), Purpose
```

An optional "Pilot Info" sheet imports certification data.

## Architecture

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, SQLite
- **Frontend:** React 19, Vite, Tailwind CSS v4, Recharts, Leaflet.js
- **Database:** 34 tables, 212+ API endpoints
- **Deployment:** Single Docker container, multi-stage build

## API Documentation

Interactive API documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc) on your running instance.

## Backup and Restore

### Backup

```bash
# Stop the container first for a clean backup
docker stop drone-unit-manager
cp /path/to/data/drone_unit_manager.db /path/to/backup/
cp /path/to/data/telemetry.db /path/to/backup/
cp -r /path/to/data/uploads /path/to/backup/
docker start drone-unit-manager
```

### Restore

```bash
docker stop drone-unit-manager
cp /path/to/backup/drone_unit_manager.db /path/to/data/
cp /path/to/backup/telemetry.db /path/to/data/
cp -r /path/to/backup/uploads /path/to/data/
docker start drone-unit-manager
```

## License

MIT License. See [LICENSE](LICENSE) for details.
