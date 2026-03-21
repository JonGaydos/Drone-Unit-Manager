# Drone Unit Manager

A self-hosted drone fleet management platform for tracking flights, pilots, certifications, equipment, and maintenance. Built for law enforcement and public safety drone programs, but usable by any organization managing a drone fleet.

> **AirData alternative** — Self-hosted, no subscription fees, full data ownership.

## Features

### Flight Management
- Import flights from **Skydio Cloud API** with automatic sync
- Manual flight entry for any drone manufacturer
- **Excel/CSV import** with intelligent deduplication
- Flight review queue — verify pilot assignments and add flight purposes
- Detailed flight statistics and duration tracking

### Pilot Management
- Full pilot profiles with contact info, badge numbers, and status
- **Certification tracking** with customizable cert types, expiration dates, and renewal alerts
- **Certification matrix** — at-a-glance view of all pilots vs. all certifications
- Equipment qualifications per pilot
- Individual pilot flight hour reports

### Analytics Dashboard (Power BI-style)
- **Interactive cross-filtering** — click any chart element to filter all other charts
- Flights by purpose, by year, by pilot (pie, bar, line charts)
- Average flight duration trends
- Vehicle utilization breakdown
- Pilot leaderboard with hours and flight counts

### Fleet & Equipment
- Vehicle tracking with FAA registration, serial numbers, acquisition dates
- **Drill-down vehicle detail pages** — click any vehicle to see its full history
- Battery management with cycle counts and health tracking
- Controller, sensor package, attachment, and dock inventory
- All equipment cross-linked to flights and pilots

### Mission & Training Logs
- **Mission Log** — track operational deployments with man-hours, case numbers, multiple pilots with roles
- **Training Log** — track training sessions with type, instructor, objectives, outcomes
- Both link to pilots and drones for comprehensive hour tracking

### Certifications & Compliance
- Customizable certification types (FAA Part 107, NIST, equipment-specific, insurance, etc.)
- Expiration tracking with renewal alerts (30/60/90 day warnings)
- Category-based filtering (FAA, NIST, Equipment, Insurance, Training, Custom)
- Inline status editing — click any cell in the matrix to update
- Document uploads per certification

### Reports
- **Customizable report builder** with custom logos
- Report types: Flight Summary, Pilot Hours, Equipment Utilization, Pilot Certifications, Battery Status, Maintenance History
- Date range filtering, pilot/vehicle selection
- PDF and CSV export

### Additional Features
- **6 theme presets** — Dark, Light, Glass (glassmorphism), Grafana (ops center), Blue, High Contrast
- **Mobile responsive** — full functionality on phones and tablets
- Role-based access (Admin and Viewer roles)
- Document management with file uploads
- Maintenance scheduling and tracking
- Alert system with severity levels
- **Drone-agnostic** — works with any manufacturer, with API integration for Skydio

## Screenshots

*Screenshots coming soon*

## Quick Start

### Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/JonGaydos/Drone-Unit-Manager.git
cd Drone-Unit-Manager

# Copy environment file
cp .env.example .env

# Start the application
docker compose up -d

# Access at http://localhost:8080
# Default login: admin / admin
```

### Docker Run

```bash
docker run -d \
  --name drone-unit-manager \
  -p 8080:8000 \
  -v dum-data:/app/data \
  -e SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))") \
  -e TZ=America/Chicago \
  --restart unless-stopped \
  jongaydos/drone-unit-manager:latest
```

## Installation

### Docker on Windows (Docker Desktop)

#### Prerequisites
- [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/) installed and running
- WSL 2 backend enabled (Docker Desktop will prompt you)

#### Steps

1. **Install Docker Desktop**
   - Download from https://docs.docker.com/desktop/install/windows-install/
   - Run the installer and restart when prompted
   - Open Docker Desktop and ensure it shows "Docker Desktop is running"

2. **Clone and start**
   ```powershell
   git clone https://github.com/JonGaydos/Drone-Unit-Manager.git
   cd Drone-Unit-Manager
   copy .env.example .env
   docker compose up -d
   ```

3. **Access the app**
   - Open http://localhost:8080
   - Login with `admin` / `admin`
   - **Change the admin password immediately** in Settings

4. **Verify it's running**
   ```powershell
   docker ps
   docker logs drone-unit-manager
   ```

### Docker on Unraid

#### Method 1: Docker Compose (Recommended)

1. Install the **Compose Manager** plugin from Community Applications
2. Create a new compose stack named `drone-unit-manager`
3. Paste the following compose file:

```yaml
services:
  drone-unit-manager:
    image: jongaydos/drone-unit-manager:latest
    container_name: drone-unit-manager
    ports:
      - "8080:8000"
    volumes:
      - /mnt/user/appdata/drone-unit-manager:/app/data
    environment:
      - TZ=America/Chicago
    restart: unless-stopped
```

4. Click **Compose Up**
5. Access at `http://YOUR_UNRAID_IP:8080`

#### Method 2: Community Applications Template

1. Go to the **Apps** tab in Unraid
2. Search for "Drone Unit Manager"
3. Click **Install**
4. Configure the port and appdata path
5. Click **Apply**

#### Method 3: Manual Docker Container

1. Go to the **Docker** tab in Unraid
2. Click **Add Container**
3. Fill in:
   - **Name:** `drone-unit-manager`
   - **Repository:** `jongaydos/drone-unit-manager:latest`
   - **Port Mapping:** Host `8080` → Container `8000`
   - **Path Mapping:** Host `/mnt/user/appdata/drone-unit-manager` → Container `/app/data`
   - **Variable:** `TZ` = `America/Chicago`
4. Click **Apply**

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | Host port to expose the application |
| `SECRET_KEY` | Auto-generated | JWT signing key. Auto-generated on first run if not set |
| `TZ` | `America/Chicago` | Timezone for date/time display |
| `DATABASE_URL` | `sqlite:////app/data/drone_unit_manager.db` | Database connection string |

### Connecting Skydio Cloud API

1. Go to **Settings** in the app
2. Enter your Skydio API Token and Token ID
3. Click **Test Connection** to verify
4. Click **Sync Now** to pull flights, vehicles, batteries, and other data
5. Set a sync interval for automatic updates

### Importing Existing Data

1. Go to **Settings** → **Import Data**
2. Upload your Excel spreadsheet (.xlsx)
3. The importer supports:
   - **Skydio flight exports** — maps Flight ID, Vehicle, Pilot, Times, Location, Purpose
   - **Pilot certification data** — creates pilots, cert types, and assignments
4. Duplicate flights are automatically detected and skipped

### Data Backup

All data is stored in the `/app/data` volume:
- `drone_unit_manager.db` — Main database
- `uploads/` — Uploaded documents and files

**To backup:**
```bash
# Docker
docker cp drone-unit-manager:/app/data ./backup

# Unraid
cp -r /mnt/user/appdata/drone-unit-manager /mnt/user/backup/dum-backup
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Frontend** | React 19, Tailwind CSS v4, Recharts, Lucide Icons |
| **Backend** | Python 3.12, FastAPI, SQLAlchemy, Pydantic |
| **Database** | SQLite (zero configuration) |
| **PDF Reports** | WeasyPrint, Jinja2 |
| **API Integration** | Skydio Cloud API (extensible to other providers) |
| **Container** | Docker (multi-stage build) |

## API Documentation

The app exposes a full REST API. When running, visit:
- **Swagger UI:** `http://localhost:8080/docs`
- **ReDoc:** `http://localhost:8080/redoc`

## Adding Support for Other Drone Manufacturers

The app uses a pluggable provider architecture. To add a new drone manufacturer:

1. Create a new file in `backend/app/integrations/`
2. Implement the `DroneProvider` base class
3. Register the provider with `register_provider()`
4. The new provider will automatically appear in Settings

See `backend/app/integrations/skydio.py` for a complete reference implementation.

## Contributing

Contributions are welcome! Please open an issue or pull request on GitHub.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

Built with [Claude Code](https://claude.ai/claude-code) by Anthropic.
