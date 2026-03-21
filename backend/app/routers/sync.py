import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.setting import Setting
from app.models.user import User
from app.routers.auth import require_admin
from app.services.sync_manager import SyncManager, SyncResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str
    user_info: dict = {}


class SyncResultResponse(BaseModel):
    vehicles_synced: int = 0
    flights_new: int = 0
    flights_skipped: int = 0
    batteries_synced: int = 0
    controllers_synced: int = 0
    docks_synced: int = 0
    sensors_synced: int = 0
    attachments_synced: int = 0
    media_synced: int = 0
    users_synced: int = 0
    errors: list[str] = []


class SyncStatusResponse(BaseModel):
    last_sync: str | None = None
    sync_interval: str | None = None
    provider: str | None = None


@router.post("/test", response_model=TestConnectionResponse)
def test_connection(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    ok, message, user_info = SyncManager.test_connection("skydio", db)
    return TestConnectionResponse(ok=ok, message=message, user_info=user_info)


@router.post("/now", response_model=SyncResultResponse)
def sync_now(
    full: bool = False,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    logger.info("Manual sync triggered by admin (full=%s)", full)
    result = SyncManager.sync_all("skydio", db, full_sync=full)
    return SyncResultResponse(**asdict(result))


@router.post("/deep", response_model=SyncResultResponse)
def sync_deep(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    logger.info("Deep sync triggered by admin")
    result = SyncManager.sync_all_deep("skydio", db)
    return SyncResultResponse(**asdict(result))


@router.post("/enrich", response_model=SyncResultResponse)
def enrich_flights(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Fetch full details for flights that have no date/pilot/duration."""
    from app.integrations.skydio import SkydioProvider
    from app.models.flight import Flight
    from app.models.vehicle import Vehicle
    from app.services.sync_manager import _build_creds, _match_pilot

    result = SyncResult()

    creds = _build_creds(db, "skydio")
    if not creds.api_token:
        result.errors.append("API token not configured")
        return SyncResultResponse(**asdict(result))

    provider = SkydioProvider()

    # Find flights with no useful data
    empty_flights = db.query(Flight).filter(
        Flight.api_provider == "skydio",
        Flight.date.is_(None),
        Flight.external_id.isnot(None),
    ).all()

    logger.info("Found %d flights needing enrichment", len(empty_flights))

    enriched = 0
    deleted = 0

    for flight in empty_flights:
        detail = provider.get_flight_detail(creds, flight.external_id)

        if not detail:
            # Could not fetch details — delete the empty flight
            db.delete(flight)
            deleted += 1
            continue

        # Try to extract useful data from the detail response
        # Log ALL keys so we know what Skydio returns
        logger.info("Enriching flight %s with keys: %s", flight.external_id, list(detail.keys()))

        # Date / time
        takeoff_str = detail.get("takeoff_time") or detail.get("start_time") or detail.get("created_at")
        landing_str = detail.get("landing_time") or detail.get("end_time")

        if takeoff_str:
            try:
                from datetime import datetime
                takeoff = datetime.fromisoformat(takeoff_str.replace("Z", "+00:00"))
                flight.takeoff_time = takeoff
                flight.date = takeoff.date()
            except (ValueError, AttributeError):
                pass

        if landing_str:
            try:
                from datetime import datetime
                flight.landing_time = datetime.fromisoformat(landing_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        # Duration
        duration = detail.get("duration_seconds") or detail.get("duration") or detail.get("flight_duration")
        if duration is not None:
            flight.duration_seconds = int(float(duration))
        elif flight.takeoff_time and flight.landing_time:
            flight.duration_seconds = int((flight.landing_time - flight.takeoff_time).total_seconds())

        # Location
        flight.takeoff_lat = flight.takeoff_lat or detail.get("takeoff_latitude") or detail.get("takeoff_lat") or detail.get("latitude")
        flight.takeoff_lon = flight.takeoff_lon or detail.get("takeoff_longitude") or detail.get("takeoff_lon") or detail.get("longitude")
        flight.landing_lat = flight.landing_lat or detail.get("landing_latitude") or detail.get("landing_lat")
        flight.landing_lon = flight.landing_lon or detail.get("landing_longitude") or detail.get("landing_lon")
        flight.takeoff_address = flight.takeoff_address or detail.get("takeoff_address") or detail.get("location") or detail.get("address")

        # Speed / altitude / distance
        flight.max_altitude_m = flight.max_altitude_m or detail.get("max_altitude_m") or detail.get("max_altitude") or detail.get("max_height")
        flight.max_speed_mps = flight.max_speed_mps or detail.get("max_speed_mps") or detail.get("max_speed") or detail.get("max_ground_speed")
        flight.distance_m = flight.distance_m or detail.get("distance_m") or detail.get("total_distance") or detail.get("distance")

        # Pilot
        pilot_name = detail.get("pilot_name") or detail.get("operator_name") or detail.get("user_name")
        if pilot_name and not flight.pilot_id:
            flight.pilot_id = _match_pilot(db, pilot_name)

        # Vehicle
        vehicle_serial = detail.get("vehicle_serial") or detail.get("serial_number") or detail.get("vehicle_id")
        if vehicle_serial and not flight.vehicle_id:
            vehicle = db.query(Vehicle).filter(
                (Vehicle.skydio_vehicle_serial == vehicle_serial) | (Vehicle.serial_number == vehicle_serial)
            ).first()
            if vehicle:
                flight.vehicle_id = vehicle.id

        # Equipment
        flight.battery_serial = flight.battery_serial or detail.get("battery_serial") or detail.get("battery")
        flight.sensor_package = flight.sensor_package or detail.get("sensor_package")
        flight.attachment_top = flight.attachment_top or detail.get("attachment_top")
        flight.attachment_bottom = flight.attachment_bottom or detail.get("attachment_bottom")
        flight.attachment_left = flight.attachment_left or detail.get("attachment_left")
        flight.attachment_right = flight.attachment_right or detail.get("attachment_right")
        flight.carrier = flight.carrier or detail.get("carrier") or detail.get("carriers")

        # Check if we actually got useful data
        if flight.date or flight.duration_seconds or flight.pilot_id:
            enriched += 1
        else:
            # Still empty after enrichment — delete
            db.delete(flight)
            deleted += 1

    db.commit()

    result.flights_new = enriched
    result.flights_skipped = deleted
    if deleted > 0:
        result.errors.append(f"Deleted {deleted} flights with no available data")

    logger.info("Enrichment complete: %d enriched, %d deleted", enriched, deleted)
    return SyncResultResponse(**asdict(result))


@router.get("/status", response_model=SyncStatusResponse)
def sync_status(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    last_sync_setting = db.query(Setting).filter(Setting.key == "last_sync_timestamp").first()
    interval_setting = db.query(Setting).filter(Setting.key == "sync_interval").first()
    provider_setting = db.query(Setting).filter(Setting.key == "last_sync_provider").first()

    return SyncStatusResponse(
        last_sync=last_sync_setting.value if last_sync_setting else None,
        sync_interval=interval_setting.value if interval_setting else None,
        provider=provider_setting.value if provider_setting else None,
    )
