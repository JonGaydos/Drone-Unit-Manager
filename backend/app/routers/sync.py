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
                tdb = TelemetrySessionLocal()
                try:
                    tdb.query(TelemetryPoint).filter(TelemetryPoint.flight_id == flight.id).delete()
                    max_alt = 0
                    max_speed = 0
                    for point in telemetry_data:
                        # altitude_m is already AGL from the provider (height_above_takeoff)
                        alt = point.get("altitude_m")
                        speed = point.get("speed_mps")
                        tp = TelemetryPoint(
                            flight_id=flight.id,
                            timestamp_ms=point.get("timestamp_ms", 0),
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
            flight.telemetry_synced = True
            synced += 1
        except Exception as exc:
            logger.warning("Telemetry sync failed for flight %s: %s", flight.external_id, exc)

    db.commit()
    return synced


@router.post("/now", response_model=SyncResultResponse)
def sync_now(
    full: bool = False,
    sync_telemetry: bool = True,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
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

    # Auto-fetch telemetry for newly synced flights
    if sync_telemetry and result.flights_new > 0:
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


@router.get("/telemetry-debug/{flight_id}")
def debug_telemetry(flight_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Debug: fetch raw telemetry from Skydio API for a single flight and return first 3 points unprocessed."""
    from app.integrations.skydio import SkydioProvider, TELEMETRY_BASE
    from app.services.sync_manager import _build_creds
    from app.models.flight import Flight

    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight or not flight.external_id:
        from fastapi import HTTPException
        raise HTTPException(404, "Flight not found or no external_id")

    creds = _build_creds(db, "skydio")
    provider = SkydioProvider()

    # Fetch raw response
    resp = provider._request("GET", f"{TELEMETRY_BASE}/flight/{flight.external_id}/telemetry", creds, timeout=60.0)
    body = resp.json()

    # Return the raw structure so we can see what Skydio actually sends
    # Truncate to avoid huge responses
    raw_keys = list(body.keys()) if isinstance(body, dict) else f"type={type(body).__name__}"

    # Try to find the telemetry list
    unwrapped = body
    unwrap_path = []
    if isinstance(unwrapped, dict) and "data" in unwrapped:
        unwrapped = unwrapped["data"]
        unwrap_path.append("data")
    if isinstance(unwrapped, dict):
        for key in ("flight_telemetry", "telemetry", "points", "data"):
            val = unwrapped.get(key)
            if isinstance(val, list):
                unwrapped = val
                unwrap_path.append(key)
                break

    sample = unwrapped[:3] if isinstance(unwrapped, list) else []
    all_keys = set()
    for p in sample:
        if isinstance(p, dict):
            all_keys.update(p.keys())

    # Also try the processed provider path
    processed = provider.get_flight_telemetry(creds, flight.external_id)

    return {
        "flight_id": flight_id,
        "external_id": flight.external_id,
        "raw_top_keys": raw_keys,
        "unwrap_path": unwrap_path,
        "total_raw_points": len(unwrapped) if isinstance(unwrapped, list) else 0,
        "all_field_names": sorted(all_keys),
        "sample_raw_points": sample,
        "processed_count": len(processed) if isinstance(processed, list) else 0,
        "processed_sample": processed[:3] if isinstance(processed, list) else [],
    }


@router.post("/telemetry")
def sync_telemetry_batch(db: Session = Depends(get_db), user: User = Depends(require_admin)):
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
                (Vehicle.provider_serial == vehicle_serial) | (Vehicle.serial_number == vehicle_serial)
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


@router.post("/cleanup")
def cleanup_empty_flights(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
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
