import json
import logging
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

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
    last_sync_result: dict | None = None
    last_telemetry_sync: str | None = None
    telemetry_sync_interval: str | None = None
    last_telemetry_sync_result: dict | None = None
    telemetry_remaining: int = 0


@router.post("/test", response_model=TestConnectionResponse)
def test_connection(
    db: DBSession,
    admin: AdminUser,
):
    ok, message, user_info = SyncManager.test_connection("skydio", db)
    return TestConnectionResponse(ok=ok, message=message, user_info=user_info)


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
            telemetry_result = SyncManager.batch_sync_telemetry(db, limit=10)
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

    synced = SyncManager.batch_sync_telemetry(db, limit=10)

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
    from app.services.audit import log_action
    logger.info("Deep sync triggered by admin")
    result = SyncManager.sync_all_deep("skydio", db)
    log_action(db, admin.id, admin.display_name, "sync_deep", "flight",
               details=f"vehicles={result.vehicles_synced}, flights_new={result.flights_new}, errors={len(result.errors)}")
    db.commit()
    return SyncResultResponse(**asdict(result))


# Location/metric flight fields mapped to the API detail keys to try, in order.
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

# Equipment flight fields mapped the same way.
_EQUIPMENT_FIELDS = {
    "battery_serial": ("battery_serial", "battery"),
    "sensor_package": ("sensor_package",),
    "attachment_top": ("attachment_top",),
    "attachment_bottom": ("attachment_bottom",),
    "attachment_left": ("attachment_left",),
    "attachment_right": ("attachment_right",),
    "carrier": ("carrier", "carriers"),
}


def _apply_first_present(flight, detail: dict, field_map: dict) -> None:
    """Fill each flight attribute in field_map from the first truthy API value
    among its candidate keys, but only when the flight field is currently empty."""
    for field, api_keys in field_map.items():
        if getattr(flight, field, None):
            continue
        for key in api_keys:
            val = detail.get(key)
            if val:
                setattr(flight, field, val)
                break


def _enrich_timestamps(flight, detail: dict) -> None:
    """Set takeoff/landing time and date from the API detail, tolerating bad values."""
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


def _enrich_duration(flight, detail: dict) -> None:
    """Set duration from the API detail, else derive it from takeoff/landing."""
    duration = detail.get("duration_seconds") or detail.get("duration") or detail.get("flight_duration")
    if duration is not None:
        flight.duration_seconds = int(float(duration))
    elif flight.takeoff_time and flight.landing_time:
        flight.duration_seconds = int((flight.landing_time - flight.takeoff_time).total_seconds())


def _enrich_pilot(flight, detail: dict, db) -> None:
    """Match a pilot by the API detail's operator name when the flight has none."""
    from app.services.sync_manager import _match_pilot
    pilot_name = detail.get("pilot_name") or detail.get("operator_name") or detail.get("user_name")
    if pilot_name and not flight.pilot_id:
        flight.pilot_id = _match_pilot(db, pilot_name)


def _enrich_vehicle(flight, detail: dict, db) -> None:
    """Match a vehicle by serial from the API detail when the flight has none."""
    from app.models.vehicle import Vehicle
    vehicle_serial = detail.get("vehicle_serial") or detail.get("serial_number") or detail.get("vehicle_id")
    if vehicle_serial and not flight.vehicle_id:
        vehicle = db.query(Vehicle).filter(
            (Vehicle.provider_serial == vehicle_serial) | (Vehicle.serial_number == vehicle_serial)
        ).first()
        if vehicle:
            flight.vehicle_id = vehicle.id


def _apply_enrichment_detail(flight, detail: dict, db):
    """Apply all enrichment data from an API detail response to a flight."""
    _enrich_timestamps(flight, detail)
    _enrich_duration(flight, detail)
    _apply_first_present(flight, detail, _ENRICHMENT_FIELDS)
    _enrich_pilot(flight, detail, db)
    _enrich_vehicle(flight, detail, db)
    _apply_first_present(flight, detail, _EQUIPMENT_FIELDS)


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

    from app.services.audit import log_action
    log_action(db, admin.id, admin.display_name, "enrich_flights", "flight",
               details=f"enriched={enriched}, deleted_with_no_detail={deleted}")
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
    from app.services.audit import log_action
    from app.models.flight import Flight

    empty = db.query(Flight).filter(
        Flight.date.is_(None),
        Flight.duration_seconds.is_(None),
    ).all()

    count = len(empty)
    for f in empty:
        db.delete(f)
    if count:
        log_action(db, admin.id, admin.display_name, "cleanup", "flight",
                   details=f"deleted {count} empty flight(s) with no date/duration")
    db.commit()

    logger.info("Cleanup: deleted %d empty flights", count)
    return {"ok": True, "deleted": count}


@router.get("/status", response_model=SyncStatusResponse)
def sync_status(
    db: DBSession,
    admin: AdminUser,
):
    from sqlalchemy import func
    from app.models.flight import Flight

    last_sync_setting = db.query(Setting).filter(Setting.key == "last_sync_timestamp").first()
    interval_setting = db.query(Setting).filter(Setting.key == "sync_interval").first()
    provider_setting = db.query(Setting).filter(Setting.key == "last_sync_provider").first()
    result_setting = db.query(Setting).filter(Setting.key == "last_sync_result").first()

    def _parse_result(setting):
        if setting and setting.value:
            try:
                parsed = json.loads(setting.value)
                if isinstance(parsed, dict):
                    return parsed
            except (ValueError, TypeError):
                return None
        return None

    tele_ts = db.query(Setting).filter(Setting.key == "last_telemetry_sync_timestamp").first()
    tele_interval = db.query(Setting).filter(Setting.key == "telemetry_sync_interval").first()
    tele_result = db.query(Setting).filter(Setting.key == "last_telemetry_sync_result").first()

    telemetry_remaining = db.query(func.count(Flight.id)).filter(
        Flight.telemetry_synced.is_(False),
        Flight.external_id.isnot(None),
    ).scalar() or 0

    return SyncStatusResponse(
        last_sync=last_sync_setting.value if last_sync_setting else None,
        sync_interval=interval_setting.value if interval_setting else None,
        provider=provider_setting.value if provider_setting else None,
        last_sync_result=_parse_result(result_setting),
        last_telemetry_sync=tele_ts.value if tele_ts else None,
        telemetry_sync_interval=tele_interval.value if tele_interval else None,
        last_telemetry_sync_result=_parse_result(tele_result),
        telemetry_remaining=telemetry_remaining,
    )


@router.post("/disconnect")
def disconnect(
    db: DBSession,
    admin: AdminUser,
):
    """Clear the Skydio credentials. The bulk settings-save guard skips empty
    secret values, so this dedicated endpoint is needed to actually clear them."""
    from app.services.audit import log_action

    for key in ("skydio_api_token", "skydio_token_id"):
        setting = db.query(Setting).filter(Setting.key == key).first()
        if setting:
            setting.value = ""

    log_action(db, admin.id, admin.display_name, "disconnect", "system",
               details="Cleared Skydio credentials")
    db.commit()
    return {"ok": True}
