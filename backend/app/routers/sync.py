import logging
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.constants import UTC_OFFSET
from app.deps import DBSession, AdminUser
from app.models.setting import Setting
from app.services.sync_manager import SyncManager, SyncResult
from app.responses import responses

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
    db: DBSession,
    admin: AdminUser,
):
    ok, message, user_info = SyncManager.test_connection("skydio", db)
    return TestConnectionResponse(ok=ok, message=message, user_info=user_info)


def _parse_timestamp_ms(ts) -> int:
    """Parse a timestamp value (ISO string or epoch ms) to integer milliseconds."""
    if isinstance(ts, str):
        try:
            from datetime import datetime as dt
            parsed = dt.fromisoformat(ts.replace("Z", UTC_OFFSET))
            return int(parsed.timestamp() * 1000)
        except (ValueError, AttributeError):
            return 0
    elif isinstance(ts, (int, float)):
        return int(ts)
    return 0


def _store_telemetry_points(flight, telemetry_data: list, session_factory, point_model):
    """Store telemetry points in the telemetry DB and update flight max metrics."""
    tdb = session_factory()
    try:
        tdb.query(point_model).filter(point_model.flight_id == flight.id).delete()
        max_alt = 0
        max_speed = 0
        for point in telemetry_data:
            alt = point.get("altitude_m")
            speed = point.get("speed_mps")
            tp = point_model(
                flight_id=flight.id,
                timestamp_ms=_parse_timestamp_ms(point.get("timestamp_ms")),
                lat=point.get("lat"),
                lon=point.get("lon"),
                altitude_m=float(alt) if alt is not None else None,
                speed_mps=float(speed) if speed is not None else None,
                battery_pct=point.get("battery_pct"),
                heading_deg=point.get("heading_deg"),
            )
            tdb.add(tp)
            if alt is not None and float(alt) > max_alt:
                max_alt = float(alt)
            if speed is not None and float(speed) > max_speed:
                max_speed = float(speed)
        tdb.commit()
        flight.max_altitude_m = max_alt
        flight.max_speed_mps = max_speed
    finally:
        tdb.close()


def _batch_sync_telemetry(db: Session, limit: int = 10) -> int:
    """Fetch telemetry for up to `limit` flights without it. Returns count synced."""
    from app.integrations.skydio import SkydioProvider
    from app.services.sync_manager import _build_creds
    from app.models.telemetry import TelemetryPoint
    from app.models.flight import Flight
    from app.database import TelemetrySessionLocal

    creds = _build_creds(db, "skydio")
    if not creds.api_token:
        return 0

    provider = SkydioProvider()
    flights = db.query(Flight).filter(
        Flight.telemetry_synced.is_(False),
        Flight.external_id.isnot(None),
    ).order_by(Flight.date.desc().nulls_last()).limit(limit).all()

    synced = 0
    for flight in flights:
        try:
            telemetry_data = provider.get_flight_telemetry(creds, flight.external_id)
            if telemetry_data and len(telemetry_data) > 0:
                _store_telemetry_points(flight, telemetry_data, TelemetrySessionLocal, TelemetryPoint)
            flight.telemetry_synced = True
            flight.has_telemetry = True
            synced += 1
        except Exception as exc:
            logger.warning("Telemetry sync failed for flight %s: %s", flight.external_id, exc)

    db.commit()
    return synced


@router.post("/now", response_model=SyncResultResponse)
def sync_now(
    db: DBSession,
    admin: AdminUser,
    full: bool = False,
    sync_telemetry: bool = True):
    """Run a sync, optionally followed by batch telemetry fetch.

    Args:
        full: If True, fetch all flights and clean up empties.
        sync_telemetry: If True (default), auto-fetch telemetry for up to 10 un-synced flights after sync.
    """
    from app.services.audit import log_action
    logger.info("Manual sync triggered by admin (full=%s, sync_telemetry=%s)", full, sync_telemetry)
    result = SyncManager.sync_all("skydio", db, full_sync=full)

    if full:
        # After full sync, clean up any flights with no useful data
        from app.models.flight import Flight
        empty = db.query(Flight).filter(
            Flight.date.is_(None),
            Flight.duration_seconds.is_(None),
        ).all()
        if empty:
            for f in empty:
                db.delete(f)
            db.commit()
            logger.info("Auto-cleanup: removed %d empty flights", len(empty))
            result.errors.append(f"Auto-cleaned {len(empty)} flights with no data")

    # Auto-fetch telemetry for flights that don't have it yet
    if sync_telemetry:
        try:
            telemetry_result = _batch_sync_telemetry(db, limit=10)
            if telemetry_result > 0:
                logger.info("Auto-synced telemetry for %d flights", telemetry_result)
        except Exception as e:
            logger.warning("Auto telemetry sync failed: %s", e)

    log_action(db, admin.id, admin.display_name, "sync", "system",
               details=f"{'Full' if full else 'Incremental'} sync: {result.flights_new} new flights, {result.vehicles_synced} vehicles")
    db.commit()
    return SyncResultResponse(**asdict(result))


@router.post("/telemetry", responses=responses(401))
def sync_telemetry_batch(db: DBSession, user: AdminUser):
    """Fetch telemetry for up to 10 flights that don't have it yet."""
    from sqlalchemy import func
    from app.models.flight import Flight

    synced = _batch_sync_telemetry(db, limit=10)

    remaining = db.query(func.count(Flight.id)).filter(
        Flight.telemetry_synced.is_(False),
        Flight.external_id.isnot(None),
    ).scalar()

    return {"synced": synced, "remaining": max(0, remaining)}


@router.post("/deep", response_model=SyncResultResponse)
def sync_deep(
    db: DBSession,
    admin: AdminUser,
):
    logger.info("Deep sync triggered by admin")
    result = SyncManager.sync_all_deep("skydio", db)
    return SyncResultResponse(**asdict(result))


def _apply_enrichment_detail(flight, detail: dict, db):
    """Apply all enrichment data from an API detail response to a flight."""
    from app.services.sync_manager import _match_pilot

    # Date / time
    takeoff_str = detail.get("takeoff_time") or detail.get("start_time") or detail.get("created_at")
    landing_str = detail.get("landing_time") or detail.get("end_time")
    if takeoff_str:
        try:
            takeoff = datetime.fromisoformat(takeoff_str.replace("Z", UTC_OFFSET))
            flight.takeoff_time = takeoff
            flight.date = takeoff.date()
        except (ValueError, AttributeError):
            pass
    if landing_str:
        try:
            flight.landing_time = datetime.fromisoformat(landing_str.replace("Z", UTC_OFFSET))
        except (ValueError, AttributeError):
            pass

    # Duration
    duration = detail.get("duration_seconds") or detail.get("duration") or detail.get("flight_duration")
    if duration is not None:
        flight.duration_seconds = int(float(duration))
    elif flight.takeoff_time and flight.landing_time:
        flight.duration_seconds = int((flight.landing_time - flight.takeoff_time).total_seconds())

    # Location + Metrics — apply first truthy API value if flight field is empty
    _ENRICHMENT_FIELDS = {
        "takeoff_lat": ("takeoff_latitude", "takeoff_lat", "latitude"),
        "takeoff_lon": ("takeoff_longitude", "takeoff_lon", "longitude"),
        "landing_lat": ("landing_latitude", "landing_lat"),
        "landing_lon": ("landing_longitude", "landing_lon"),
        "takeoff_address": ("takeoff_address", "location", "address"),
        "max_altitude_m": ("max_altitude_m", "max_altitude", "max_height"),
        "max_speed_mps": ("max_speed_mps", "max_speed", "max_ground_speed"),
        "distance_m": ("distance_m", "total_distance", "distance"),
    }
    for field, api_keys in _ENRICHMENT_FIELDS.items():
        if not getattr(flight, field, None):
            for key in api_keys:
                val = detail.get(key)
                if val:
                    setattr(flight, field, val)
                    break

    # Pilot
    pilot_name = detail.get("pilot_name") or detail.get("operator_name") or detail.get("user_name")
    if pilot_name and not flight.pilot_id:
        flight.pilot_id = _match_pilot(db, pilot_name)

    # Vehicle
    from app.models.vehicle import Vehicle
    vehicle_serial = detail.get("vehicle_serial") or detail.get("serial_number") or detail.get("vehicle_id")
    if vehicle_serial and not flight.vehicle_id:
        vehicle = db.query(Vehicle).filter(
            (Vehicle.provider_serial == vehicle_serial) | (Vehicle.serial_number == vehicle_serial)
        ).first()
        if vehicle:
            flight.vehicle_id = vehicle.id

    # Equipment — same pattern
    _EQUIPMENT_FIELDS = {
        "battery_serial": ("battery_serial", "battery"),
        "sensor_package": ("sensor_package",),
        "attachment_top": ("attachment_top",),
        "attachment_bottom": ("attachment_bottom",),
        "attachment_left": ("attachment_left",),
        "attachment_right": ("attachment_right",),
        "carrier": ("carrier", "carriers"),
    }
    for field, api_keys in _EQUIPMENT_FIELDS.items():
        if not getattr(flight, field, None):
            for key in api_keys:
                val = detail.get(key)
                if val:
                    setattr(flight, field, val)
                    break


@router.post("/enrich", response_model=SyncResultResponse)
def enrich_flights(
    db: DBSession,
    admin: AdminUser,
):
    """Fetch full details for flights that have no date/pilot/duration."""
    from app.integrations.skydio import SkydioProvider
    from app.models.flight import Flight
    from app.services.sync_manager import _build_creds

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
            db.delete(flight)
            deleted += 1
            continue

        logger.info("Enriching flight %s with keys: %s", flight.external_id, list(detail.keys()))
        _apply_enrichment_detail(flight, detail, db)

        if flight.date or flight.duration_seconds or flight.pilot_id:
            enriched += 1
        else:
            db.delete(flight)
            deleted += 1

    db.commit()

    result.flights_new = enriched
    result.flights_skipped = deleted
    if deleted > 0:
        result.errors.append(f"Deleted {deleted} flights with no available data")

    logger.info("Enrichment complete: %d enriched, %d deleted", enriched, deleted)
    return SyncResultResponse(**asdict(result))


@router.post("/cleanup")
def cleanup_empty_flights(
    db: DBSession,
    admin: AdminUser,
):
    """Delete all flights that have no date, no duration, and no location."""
    from app.models.flight import Flight

    empty = db.query(Flight).filter(
        Flight.date.is_(None),
        Flight.duration_seconds.is_(None),
    ).all()

    count = len(empty)
    for f in empty:
        db.delete(f)
    db.commit()

    logger.info("Cleanup: deleted %d empty flights", count)
    return {"ok": True, "deleted": count}


@router.get("/status", response_model=SyncStatusResponse)
def sync_status(
    db: DBSession,
    admin: AdminUser,
):
    last_sync_setting = db.query(Setting).filter(Setting.key == "last_sync_timestamp").first()
    interval_setting = db.query(Setting).filter(Setting.key == "sync_interval").first()
    provider_setting = db.query(Setting).filter(Setting.key == "last_sync_provider").first()

    return SyncStatusResponse(
        last_sync=last_sync_setting.value if last_sync_setting else None,
        sync_interval=interval_setting.value if interval_setting else None,
        provider=provider_setting.value if provider_setting else None,
    )
