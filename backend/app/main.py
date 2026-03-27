"""FastAPI application entry point for Drone Unit Manager.

Configures the app, registers routers, seeds default data, and serves
the React SPA in production.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine, SessionLocal
from app.models import *  # noqa: F401,F403 - Import all models to register them
from app.models.telemetry import TelemetryBase
from app.database import telemetry_engine
from app.routers import (
    auth, pilots, vehicles, flights, dashboard, settings as settings_router,
    certifications, documents, sync, telemetry, maintenance, media, alerts,
    equipment, reports, export, mission_logs, training_logs, maintenance_schedules,
    photos, folders, audit, incidents, flight_plans,
    weather, currency, equipment_checkouts, checklists,
    components, geofences,
)
from app.routers import vehicle_registrations
from app.services.scheduler import start_scheduler, stop_scheduler
from app.models.user import User
from app.models.flight import FlightPurpose
from app.models.folder import Folder

# Law-enforcement-specific flight purpose categories seeded on first run
DEFAULT_PURPOSES = [
    "Training", "Demonstration", "Manhunt", "Security", "Other Agency Assist",
    "Search Warrant", "Missing Person", "Photograph Request", "Map Scan",
    "CPTED", "Citizen Assist", "Fire", "Patrol", "Investigation",
    "Search & Rescue", "Surveillance", "Mapping", "Inspection", "Other",
]


def seed_defaults():
    """Populate default folders and flight purposes if the database is empty.

    Skips seeding when no users exist yet (initial setup not completed).
    """
    db = SessionLocal()
    try:
        # Only seed defaults after initial setup (at least one user exists)
        if db.query(User).count() == 0:
            return

        # Seed default folders
        if db.query(Folder).count() == 0:
            for name in ["General", "Certifications", "Insurance", "Maintenance", "Reports"]:
                db.add(Folder(name=name, is_system=True))
            db.commit()

        # Seed default flight purposes
        if db.query(FlightPurpose).count() == 0:
            for i, name in enumerate(DEFAULT_PURPOSES):
                db.add(FlightPurpose(name=name, sort_order=i))
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler: create tables, run migrations, seed data, start scheduler."""
    # Create tables
    Base.metadata.create_all(bind=engine)
    TelemetryBase.metadata.create_all(bind=telemetry_engine)
    from app.services.migrations import run_migrations
    run_migrations()
    seed_defaults()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Drone Unit Manager",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add a unique request ID to every request for tracing."""
    request_id = str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Register routers
app.include_router(auth.router)
app.include_router(pilots.router)
app.include_router(vehicles.router)
app.include_router(flights.router)
app.include_router(dashboard.router)
app.include_router(settings_router.router)
app.include_router(certifications.router)
app.include_router(documents.router)
app.include_router(sync.router)
app.include_router(telemetry.router)
app.include_router(maintenance.router)
app.include_router(media.router)
app.include_router(alerts.router)
app.include_router(equipment.router)
app.include_router(reports.router)
app.include_router(export.router)
app.include_router(mission_logs.router)
app.include_router(training_logs.router)
app.include_router(maintenance_schedules.router)
app.include_router(vehicle_registrations.router)
app.include_router(photos.router)
app.include_router(folders.router)
app.include_router(audit.router)
app.include_router(incidents.router)
app.include_router(flight_plans.router)
app.include_router(weather.router)
app.include_router(currency.router)
app.include_router(equipment_checkouts.router)
app.include_router(checklists.router)
app.include_router(components.router)
app.include_router(geofences.router)


@app.get("/api/health")
def health_check():
    """Health check that verifies database connectivity."""
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {"status": "ok", "app": "Drone Unit Manager", "database": "connected"}
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "app": "Drone Unit Manager", "database": "disconnected"},
        )


from sqlalchemy import text

# Serve frontend static files in production (Docker)
from fastapi.responses import FileResponse

_static_dir = str(Path(__file__).parent.parent / "static")

@app.get("/{full_path:path}", include_in_schema=False)
def serve_spa(full_path: str):
    """Serve the React SPA and its static assets in production (Docker).

    Serves the requested file if it exists, otherwise falls back to
    index.html for client-side routing. Includes path-traversal prevention.

    Args:
        full_path: The URL path requested by the client.

    Returns:
        The matching static file or index.html.
    """
    if not _static_dir or not os.path.isdir(_static_dir):
        raise HTTPException(404)
    file_path = os.path.join(_static_dir, full_path)
    resolved = os.path.realpath(file_path)
    if not resolved.startswith(os.path.realpath(_static_dir)):
        raise HTTPException(403, "Forbidden")
    if os.path.isfile(resolved):
        return FileResponse(resolved)
    index = os.path.join(_static_dir, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    raise HTTPException(404)
