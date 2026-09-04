"""Sync orchestrator - coordinates data sync between Skydio Cloud API and local DB."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants import API_TOKEN_NOT_CONFIGURED, UTC_OFFSET
from app.integrations.base import ProviderCredentials
from app.integrations.registry import get_provider
from app.models.vehicle import Vehicle
from app.models.flight import Flight
from app.models.battery import Battery
from app.models.controller import Controller
from app.models.dock import Dock
from app.models.sensor import SensorPackage
from app.models.attachment import Attachment
from app.models.media import MediaFile
from app.models.pilot import Pilot
from app.models.setting import Setting

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
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
    errors: list[str] = field(default_factory=list)


def _get_setting(db: Session, key: str, default: str = "") -> str:
    setting = db.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else default


def _set_setting(db: Session, key: str, value: str):
    setting = db.query(Setting).filter(Setting.key == key).first()
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        db.add(setting)


def _persist_last_sync_result(db: Session, result: "SyncResult"):
    """Record the outcome of a sync run (success or failure) as a setting."""
    counts = {
        "vehicles_synced": result.vehicles_synced,
        "flights_new": result.flights_new,
        "flights_skipped": result.flights_skipped,
        "batteries_synced": result.batteries_synced,
        "controllers_synced": result.controllers_synced,
        "docks_synced": result.docks_synced,
        "sensors_synced": result.sensors_synced,
        "attachments_synced": result.attachments_synced,
        "media_synced": result.media_synced,
        "users_synced": result.users_synced,
    }
    if not result.errors:
        status = "success"
    elif any(v > 0 for v in counts.values()):
        status = "partial"
    else:
        status = "failure"
    payload = {
        **counts,
        "errors": list(result.errors),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
    }
    _set_setting(db, "last_sync_result", json.dumps(payload))


def _build_creds(db: Session, provider_name: str) -> ProviderCredentials:
    """Build credentials from the settings table."""
    api_token = _get_setting(db, f"{provider_name}_api_token")
    token_id = _get_setting(db, f"{provider_name}_token_id")
    return ProviderCredentials(api_token=api_token, token_id=token_id)


# Shortest serial tail accepted as a short-form match (e.g. "-0061" is too
# ambiguous; "-00061" can match). Uniqueness is still required on top.
MIN_SERIAL_SUFFIX = 4


def _find_equipment_by_serial(db: Session, model_class, serial: str):
    """Resolve a serial string to an existing equipment record.

    Matches exactly (case-insensitive) first. Failing that, treats the value
    as a short form — flight data sometimes reports only the tail of the full
    serial, dash-prefixed (e.g. "-231117-1-00061" for "k01-231117-1-00061") —
    and matches when exactly ONE record's serial ends with it. Ambiguous
    suffixes match nothing rather than guessing.
    """
    rows = db.query(model_class).all()
    lowered = serial.lower()
    for row in rows:
        if (row.serial_number or "").lower() == lowered:
            return row
    tail = lowered.lstrip("-").strip()
    if len(tail) < MIN_SERIAL_SUFFIX:
        return None
    matches = [r for r in rows if (r.serial_number or "").lower().endswith(tail)]
    return matches[0] if len(matches) == 1 else None


def _ensure_simple_equipment(db: Session, serial_raw: str | None, model_class, label: str) -> str | None:
    """Auto-create a simple equipment record (Battery or SensorPackage) if it doesn't exist.

    Returns the canonical serial of the matched or created record (None when
    the input is empty/placeholder), so callers can normalize the string they
    store on the flight.
    """
    if not serial_raw:
        return None
    serial = serial_raw.strip()
    if not serial or serial.upper() in ("N/A", "NONE", "NA", "-", "--"):
        return None
    existing = _find_equipment_by_serial(db, model_class, serial)
    if existing:
        return existing.serial_number
    # Leading dashes are provider artifacts; create under the clean form so
    # the fleet list shows canonical serials.
    serial = serial.lstrip("-").strip()
    if not serial:
        return None
    db.add(model_class(serial_number=serial, status="active"))
    db.flush()
    logger.info("Auto-created %s record: %s", label, serial)
    return serial


def _ensure_attachment_record(db: Session, val: str):
    """Auto-create an Attachment record from a flight equipment string."""
    serial = val.strip()
    if not serial or serial.upper() in ("N/A", "NONE", "NA", "-", "--"):
        return
    if db.query(Attachment).filter(Attachment.serial_number == serial).first():
        return
    if "(" in serial and serial.endswith(")"):
        parts = serial.rsplit("(", 1)
        name = parts[0].strip()
        serial_inner = parts[1].rstrip(")")
        if not db.query(Attachment).filter(Attachment.serial_number == serial_inner).first():
            db.add(Attachment(serial_number=serial_inner, name=name, status="active"))
            db.flush()
            logger.info("Auto-created attachment record: %s (%s)", name, serial_inner)
    else:
        db.add(Attachment(serial_number=serial, status="active"))
        db.flush()
        logger.info("Auto-created attachment record: %s", serial)


def _ensure_equipment_records(db: Session, flight: Flight):
    """Auto-create Fleet records (Battery, SensorPackage, Attachment) from flight equipment strings.

    If a flight references equipment by serial number that doesn't exist in the Fleet,
    create a minimal record so it appears in dropdown lists for future use.
    Short-form serials that resolve to an existing record are normalized to
    the canonical serial on the flight itself.
    """
    battery_serial = _ensure_simple_equipment(db, flight.battery_serial, Battery, "battery")
    if battery_serial and battery_serial != flight.battery_serial:
        flight.battery_serial = battery_serial
    sensor_serial = _ensure_simple_equipment(db, flight.sensor_package, SensorPackage, "sensor package")
    if sensor_serial and sensor_serial != flight.sensor_package:
        flight.sensor_package = sensor_serial

    for field_name in ("attachment_top", "attachment_bottom", "attachment_left", "attachment_right"):
        val = getattr(flight, field_name, None)
        if val:
            _ensure_attachment_record(db, val)


def _merge_existing_flight(existing: Flight, f_data: dict, db: Session):
    """Merge API data into an existing flight — fill empty fields, don't overwrite."""
    if not existing.vehicle_id and f_data.get("vehicle_serial"):
        v = db.query(Vehicle).filter(
            Vehicle.provider_serial == f_data["vehicle_serial"]
        ).first()
        if v:
            existing.vehicle_id = v.id
    for api_key, db_field in [
        ("takeoff_lat", "takeoff_lat"), ("takeoff_lon", "takeoff_lon"),
        ("landing_lat", "landing_lat"), ("landing_lon", "landing_lon"),
        ("battery_serial", "battery_serial"), ("sensor_package", "sensor_package"),
        ("carrier", "carrier"), ("attachment_top", "attachment_top"),
        ("attachment_bottom", "attachment_bottom"), ("attachment_left", "attachment_left"),
        ("attachment_right", "attachment_right"),
    ]:
        new_val = f_data.get(api_key)
        if new_val and not getattr(existing, db_field, None):
            setattr(existing, db_field, new_val)
    if not existing.duration_seconds and f_data.get("duration_seconds"):
        existing.duration_seconds = f_data["duration_seconds"]


def _resolve_vehicle_id(db: Session, vehicle_serial: str | None) -> int | None:
    """Try to match a vehicle serial to a local vehicle ID."""
    if not vehicle_serial:
        return None
    vehicle = db.query(Vehicle).filter(
        Vehicle.provider_serial == vehicle_serial
    ).first()
    return vehicle.id if vehicle else None


def _parse_flight_date(date_val) -> date | None:
    """Parse a date value from API data into a date object."""
    if not date_val:
        return None
    if isinstance(date_val, str):
        try:
            return date.fromisoformat(date_val)
        except ValueError:
            return None
    if isinstance(date_val, date):
        return date_val
    return None


def _upsert_flights(flights_data: list[dict], skydio_users: list[dict], db: Session, result: SyncResult):
    """Shared flight upsert logic used by both sync_all and sync_all_deep."""
    for f_data in flights_data:
        ext_id = str(f_data.get("external_id", "")).upper().replace("-", "")
        if not ext_id:
            continue

        existing = db.query(Flight).filter(
            func.replace(func.upper(Flight.external_id), "-", "") == ext_id,
        ).first()

        if existing:
            _merge_existing_flight(existing, f_data, db)
            result.flights_skipped += 1
            continue

        vehicle_id = _resolve_vehicle_id(db, f_data.get("vehicle_serial"))

        pilot_id = None
        pilot_name = f_data.get("pilot_name")
        if pilot_name and skydio_users:
            pilot_id = _match_pilot(db, pilot_name)

        flight_date = _parse_flight_date(f_data.get("date"))

        flight = Flight(
            external_id=ext_id,
            api_provider="skydio",
            pilot_id=pilot_id,
            vehicle_id=vehicle_id,
            date=flight_date,
            takeoff_time=f_data.get("takeoff_time"),
            landing_time=f_data.get("landing_time"),
            duration_seconds=f_data.get("duration_seconds"),
            takeoff_lat=f_data.get("takeoff_lat"),
            takeoff_lon=f_data.get("takeoff_lon"),
            landing_lat=f_data.get("landing_lat"),
            landing_lon=f_data.get("landing_lon"),
            takeoff_address=f_data.get("takeoff_address"),
            max_altitude_m=f_data.get("max_altitude_m"),
            max_speed_mps=f_data.get("max_speed_mps"),
            distance_m=f_data.get("distance_m"),
            battery_serial=f_data.get("battery_serial"),
            sensor_package=f_data.get("sensor_package"),
            attachment_top=f_data.get("attachment_top"),
            attachment_bottom=f_data.get("attachment_bottom"),
            attachment_left=f_data.get("attachment_left"),
            attachment_right=f_data.get("attachment_right"),
            carrier=f_data.get("carrier"),
            review_status="needs_review",
            pilot_confirmed=False,
            data_source="skydio_api",
        )
        db.add(flight)
        result.flights_new += 1

        try:
            _ensure_equipment_records(db, flight)
        except Exception as e:
            logger.warning("Equipment auto-create failed for flight %s: %s", ext_id, e)

    db.flush()


def _match_pilot_emails(skydio_users: list[dict], db: Session) -> int:
    """Match Skydio users to local pilots and populate emails. Returns count matched."""
    logger.info("Matching %d Skydio users to %d pilots",
                len(skydio_users), db.query(Pilot).filter(Pilot.status == "active").count())
    matched = 0
    for su in skydio_users:
        su_name = su.get("name", "").strip()
        su_email = su.get("email", "")
        if not su_email:
            continue
        logger.info("  Skydio user: name='%s' email='%s'", su_name, su_email)

        pilot = _find_pilot_by_name(db, su_name)
        if not pilot:
            pilot = db.query(Pilot).filter(Pilot.email.ilike(su_email)).first()
        if not pilot and su_email:
            pilot = _find_pilot_by_email_pattern(db, su_email)

        if pilot:
            if not pilot.email:
                pilot.email = su_email
                matched += 1
                logger.info("    -> Matched to pilot: %s %s", pilot.first_name, pilot.last_name)
            else:
                logger.info("    -> Pilot %s already has email: %s", pilot.first_name, pilot.email)
        else:
            logger.info("    -> No pilot match found")

    db.flush()
    logger.info("Populated emails for %d pilots", matched)
    return matched


def _find_pilot_by_name(db: Session, su_name: str) -> Pilot | None:
    """Try exact first+last name match for a Skydio user."""
    if not su_name:
        return None
    parts = su_name.split()
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        return db.query(Pilot).filter(
            Pilot.first_name.ilike(first),
            Pilot.last_name.ilike(last),
            Pilot.status == "active",
        ).first()
    return None


def _find_pilot_by_email_pattern(db: Session, su_email: str) -> Pilot | None:
    """Match email username patterns to pilots (firstinitial+lastname, etc.)."""
    username = su_email.split("@")[0].lower()
    all_pilots = db.query(Pilot).filter(Pilot.status == "active").all()
    for p in all_pilots:
        last_lower = (p.last_name or "").lower()
        first_lower = (p.first_name or "").lower()
        if not last_lower or not first_lower:
            continue
        p1 = first_lower[0] + last_lower
        p2 = last_lower[:3] + first_lower
        if username in (p1, p2, last_lower + first_lower, first_lower + last_lower):
            logger.info("    -> Pattern match: '%s' matched pilot %s %s", username, p.first_name, p.last_name)
            return p
        if len(last_lower) >= 4 and last_lower in username:
            logger.info("    -> Substring match: '%s' contains '%s' -> %s %s", username, last_lower, p.first_name, p.last_name)
            return p
    return None


def _find_vehicle_for_sync(db: Session, serial: str) -> Vehicle | None:
    """Match a provider vehicle to a local record.

    Providers identify aircraft by a short name (e.g. "SkydioX2-7646")
    while agencies often register the full airframe serial, so an exact
    serial match can miss. Fall back to a case-insensitive nickname match,
    but only when exactly one vehicle carries that nickname."""
    existing = db.query(Vehicle).filter(
        (Vehicle.provider_serial == serial) |
        (Vehicle.serial_number == serial)
    ).first()
    if existing:
        return existing
    by_nickname = db.query(Vehicle).filter(func.lower(Vehicle.nickname) == serial.lower()).all()
    return by_nickname[0] if len(by_nickname) == 1 else None


def _sync_vehicles(provider, creds, db: Session, result: SyncResult):
    """Sync vehicles from provider into the local database."""
    vehicles_data = provider.sync_vehicles(creds)
    for v_data in vehicles_data:
        serial = v_data.get("provider_serial") or v_data.get("serial_number", "")
        if not serial:
            continue

        existing = _find_vehicle_for_sync(db, serial)

        if existing:
            existing.manufacturer = v_data.get("manufacturer", existing.manufacturer)
            existing.model = v_data.get("model", existing.model)
            existing.api_provider = v_data.get("api_provider", "skydio")
            # Persist the provider link so future matches don't depend on
            # the nickname staying unchanged.
            if not existing.provider_serial:
                existing.provider_serial = serial
            if v_data.get("nickname") and not existing.nickname:
                existing.nickname = v_data["nickname"]
        else:
            vehicle = Vehicle(
                serial_number=v_data.get("serial_number", serial),
                manufacturer=v_data.get("manufacturer", "Skydio"),
                model=v_data.get("model", "Unknown"),
                provider_serial=serial,
                api_provider=v_data.get("api_provider", "skydio"),
                nickname=v_data.get("nickname"),
            )
            db.add(vehicle)

        result.vehicles_synced += 1

    db.flush()


def _enrich_flight_timestamps(flight: Flight, detail: dict):
    """Fill in takeoff/landing times and duration from flight detail."""
    takeoff_str = detail.get("takeoff") or detail.get("takeoff_time")
    if takeoff_str and not flight.takeoff_time:
        try:
            takeoff = datetime.fromisoformat(str(takeoff_str).replace("Z", UTC_OFFSET))
            flight.takeoff_time = takeoff
            if not flight.date:
                flight.date = takeoff.date()
        except (ValueError, AttributeError):
            pass

    landing_str = detail.get("landing") or detail.get("landing_time")
    if landing_str and not flight.landing_time:
        try:
            flight.landing_time = datetime.fromisoformat(str(landing_str).replace("Z", UTC_OFFSET))
        except (ValueError, AttributeError):
            pass

    if flight.takeoff_time and flight.landing_time and not flight.duration_seconds:
        flight.duration_seconds = int((flight.landing_time - flight.takeoff_time).total_seconds())


def _enrich_flight_equipment(flight: Flight, detail: dict):
    """Fill in attachments, sensor, battery from flight detail."""
    from app.integrations.skydio import _to_str

    attachments = detail.get("attachments")
    if isinstance(attachments, list):
        mount_map = {"TOP": "attachment_top", "BOTTOM": "attachment_bottom",
                     "LEFT": "attachment_left", "RIGHT": "attachment_right"}
        for att in attachments:
            if isinstance(att, dict):
                mount = att.get("mount_point", "").upper()
                fld = mount_map.get(mount)
                if fld:
                    setattr(flight, fld, f"{att.get('attachment_type', '')} ({att.get('attachment_serial', '')})")

    sensor = detail.get("sensor_package")
    if isinstance(sensor, dict):
        flight.sensor_package = sensor.get("sensor_package_serial") or _to_str(sensor)
    battery = detail.get("battery_serial")
    if battery:
        from app.integrations.skydio import _clean_serial
        flight.battery_serial = _clean_serial(battery)


def _enrich_flight_metrics(flight: Flight, detail: dict):
    """Fill in numeric metrics (lat, lon, altitude, speed, distance) from flight detail."""
    for api_key, fld in [("takeoff_latitude", "takeoff_lat"), ("takeoff_longitude", "takeoff_lon"),
                         ("max_altitude_m", "max_altitude_m"), ("max_altitude", "max_altitude_m"),
                         ("max_speed_mps", "max_speed_mps"), ("max_speed", "max_speed_mps"),
                         ("distance_m", "distance_m"), ("total_distance", "distance_m")]:
        val = detail.get(api_key)
        if val is not None and not getattr(flight, fld, None):
            try:
                setattr(flight, fld, float(val))
            except (ValueError, TypeError):
                pass

    addr = detail.get("takeoff_address") or detail.get("location")
    if addr and not flight.takeoff_address:
        flight.takeoff_address = str(addr)


def _reverse_geocode(lat, lon) -> str | None:
    """Reverse geocode coordinates via Nominatim. Network only, no DB access.

    Returns the display_name string, or None on any failure. Must be called
    OUTSIDE an open DB transaction so the synchronous HTTP request does not
    hold a write transaction open.
    """
    try:
        import httpx
        geo_resp = httpx.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 16},
            headers={"User-Agent": "DroneUnitManager/1.0"},
            timeout=5,
        )
        if geo_resp.status_code == 200:
            return geo_resp.json().get("display_name", "")
    except Exception:
        pass
    return None


def _enrich_flight_associations(flight: Flight, detail: dict, db: Session):
    """Match vehicle and pilot from flight detail."""
    vs = detail.get("vehicle_serial")
    if vs and not flight.vehicle_id:
        vehicle = db.query(Vehicle).filter(
            (Vehicle.provider_serial == str(vs)) | (Vehicle.serial_number == str(vs))
        ).first()
        if vehicle:
            flight.vehicle_id = vehicle.id

    ue = detail.get("user_email")
    if ue and not flight.pilot_id:
        pilot = db.query(Pilot).filter(
            Pilot.email.ilike(str(ue)),
            Pilot.status == "active",
        ).first()
        if pilot:
            flight.pilot_id = pilot.id


def _enrich_single_flight(flight: Flight, provider, creds, db: Session) -> bool:
    """Enrich a single flight with full details from the API. Returns True if enriched."""
    detail = provider.get_flight_detail(creds, flight.external_id)
    if not detail:
        return False

    _enrich_flight_timestamps(flight, detail)
    _enrich_flight_equipment(flight, detail)
    _enrich_flight_metrics(flight, detail)
    # Geocoding is deferred to after the enrichment loop's flush so the
    # synchronous Nominatim request never runs inside the open transaction.
    _enrich_flight_associations(flight, detail, db)
    return True


def _enrich_flights(provider, creds, db: Session, result: SyncResult):
    """Enrich flights with full details and clean up ghost flights."""
    from app.integrations.skydio import _to_str
    # Pass 1: All API flights missing pilot/vehicle/altitude
    urgent = db.query(Flight).filter(
        Flight.external_id.isnot(None),
        Flight.api_provider == "skydio",
        (Flight.pilot_id.is_(None)) | (Flight.vehicle_id.is_(None)) | (Flight.max_altitude_m.is_(None)),
    ).all()
    # Pass 2: Excel imports needing telemetry (cap at 100)
    urgent_ids = {f.id for f in urgent}
    remaining_slots = 100
    extra = []
    if remaining_slots > 0:
        extra = db.query(Flight).filter(
            Flight.max_altitude_m.is_(None),
            Flight.external_id.isnot(None),
            Flight.id.notin_(urgent_ids) if urgent_ids else True,
        ).limit(remaining_slots).all()
    unenriched = urgent + extra
    logger.info("Enrichment: %d urgent API flights + %d extra = %d total", len(urgent), len(extra), len(unenriched))

    enriched_count = 0
    for flight in unenriched:
        try:
            if _enrich_single_flight(flight, provider, creds, db):
                enriched_count += 1
        except Exception as exc:
            logger.warning("Failed to enrich flight %s: %s", flight.external_id, exc)

    db.flush()
    logger.info("Enriched %d flights with full details", enriched_count)

    # Reverse-geocode missing addresses AFTER the flush so the synchronous
    # Nominatim HTTP calls do not hold the write transaction open. Collect
    # candidates, geocode, then write the results back.
    geocode_targets = [
        f for f in unenriched
        if not f.takeoff_address and f.takeoff_lat and f.takeoff_lon
    ]
    geocoded_count = 0
    for flight in geocode_targets:
        address = _reverse_geocode(flight.takeoff_lat, flight.takeoff_lon)
        if address:
            flight.takeoff_address = address
            geocoded_count += 1
    if geocode_targets:
        db.flush()
        logger.info("Reverse-geocoded %d of %d flights missing an address",
                    geocoded_count, len(geocode_targets))

    # Clean up ghost flights
    ghosts = db.query(Flight).filter(
        Flight.api_provider == "skydio",
        Flight.date.is_(None),
        Flight.max_altitude_m.is_(None),
        Flight.external_id.isnot(None),
    ).all()
    ghost_count = len(ghosts)
    for ghost in ghosts:
        db.delete(ghost)
    db.flush()
    if ghost_count:
        logger.info("Deleted %d ghost flights with no data", ghost_count)
        result.errors.append(f"Auto-cleaned {ghost_count} flights with no data")


def _sync_entity_list(provider_method, creds, db: Session, model_class, serial_field: str,
                      update_fn, create_fn, result_attr: str, result: SyncResult):
    """Generic sync for simple entity types (batteries, controllers, docks, sensors, attachments)."""
    items_data = provider_method(creds)
    for item_data in items_data:
        serial = item_data.get("serial_number", "")
        if not serial:
            continue

        existing = db.query(model_class).filter(
            getattr(model_class, serial_field) == serial
        ).first()

        if existing:
            update_fn(existing, item_data)
        else:
            db.add(create_fn(item_data, serial))

        setattr(result, result_attr, getattr(result, result_attr) + 1)

    db.flush()


def _update_battery(existing: Battery, b_data: dict):
    existing.cycle_count = b_data.get("cycle_count", existing.cycle_count)
    existing.health_pct = b_data.get("health_pct", existing.health_pct)
    existing.api_provider = "skydio"


def _create_battery(b_data: dict, serial: str) -> Battery:
    return Battery(
        serial_number=serial,
        manufacturer=b_data.get("manufacturer", "Skydio"),
        model=b_data.get("model"),
        vehicle_model=b_data.get("vehicle_model"),
        cycle_count=b_data.get("cycle_count", 0),
        health_pct=b_data.get("health_pct"),
        skydio_battery_serial=b_data.get("skydio_battery_serial", serial),
        api_provider="skydio",
    )


def _update_controller(existing: Controller, c_data: dict):
    existing.api_provider = "skydio"
    if c_data.get("model"):
        existing.model = c_data["model"]


def _create_controller(c_data: dict, serial: str) -> Controller:
    return Controller(
        serial_number=serial,
        manufacturer=c_data.get("manufacturer", "Skydio"),
        model=c_data.get("model"),
        skydio_controller_serial=c_data.get("skydio_controller_serial", serial),
        api_provider="skydio",
    )


def _update_dock(existing: Dock, d_data: dict):
    existing.api_provider = "skydio"
    if d_data.get("name"):
        existing.name = d_data["name"]
    if d_data.get("lat"):
        existing.lat = d_data["lat"]
    if d_data.get("lon"):
        existing.lon = d_data["lon"]
    if d_data.get("location_name"):
        existing.location_name = d_data["location_name"]


def _create_dock(d_data: dict, serial: str) -> Dock:
    return Dock(
        serial_number=serial,
        name=d_data.get("name"),
        location_name=d_data.get("location_name"),
        lat=d_data.get("lat"),
        lon=d_data.get("lon"),
        skydio_dock_serial=d_data.get("skydio_dock_serial", serial),
        api_provider="skydio",
    )


def _update_sensor(existing: SensorPackage, s_data: dict):
    existing.api_provider = "skydio"
    if s_data.get("name"):
        existing.name = s_data["name"]
    if s_data.get("type"):
        existing.type = s_data["type"]


def _create_sensor(s_data: dict, serial: str) -> SensorPackage:
    return SensorPackage(
        serial_number=serial,
        name=s_data.get("name"),
        type=s_data.get("type"),
        manufacturer=s_data.get("manufacturer", "Skydio"),
        model=s_data.get("model"),
        skydio_serial=s_data.get("skydio_serial", serial),
        api_provider="skydio",
    )


def _update_attachment(existing: Attachment, a_data: dict):
    existing.api_provider = "skydio"
    if a_data.get("name"):
        existing.name = a_data["name"]
    if a_data.get("type"):
        existing.type = a_data["type"]


def _create_attachment(a_data: dict, serial: str) -> Attachment:
    return Attachment(
        serial_number=serial,
        name=a_data.get("name"),
        type=a_data.get("type"),
        manufacturer=a_data.get("manufacturer", "Skydio"),
        model=a_data.get("model"),
        skydio_serial=a_data.get("skydio_serial", serial),
        api_provider="skydio",
    )


def _sync_media(provider, creds, since: str | None, db: Session, result: SyncResult):
    """Sync media files from provider."""
    media_data = provider.sync_media(creds, since=since)
    for m_data in media_data:
        ext_uuid = m_data.get("external_uuid", "")
        if not ext_uuid:
            continue

        existing = db.query(MediaFile).filter(
            MediaFile.external_uuid == ext_uuid
        ).first()

        if not existing:
            media_file = MediaFile(
                external_uuid=ext_uuid,
                filename=m_data.get("filename", ""),
                kind=m_data.get("kind", "photo"),
                captured_time=m_data.get("captured_time"),
                size_bytes=m_data.get("size_bytes"),
                download_url=m_data.get("download_url"),
                api_provider="skydio",
            )
            flight_ext_id = m_data.get("flight_external_id")
            if flight_ext_id:
                flight = db.query(Flight).filter(
                    func.replace(func.upper(Flight.external_id), "-", "") == str(flight_ext_id).upper().replace("-", ""),
                    Flight.api_provider == "skydio",
                ).first()
                if flight:
                    media_file.flight_id = flight.id

            db.add(media_file)
            result.media_synced += 1

    db.flush()


def _parse_timestamp_ms(ts) -> int:
    """Parse a timestamp value (ISO string or epoch ms) to integer milliseconds."""
    if isinstance(ts, str):
        try:
            parsed = datetime.fromisoformat(ts.replace("Z", UTC_OFFSET))
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
        # Only update max values when we actually saw data - otherwise we'd
        # clobber existing values with 0 on partial-coverage syncs.
        if max_alt > 0:
            flight.max_altitude_m = max_alt
        if max_speed > 0:
            flight.max_speed_mps = max_speed
    finally:
        tdb.close()


class SyncManager:

    @staticmethod
    def test_connection(provider_name: str, db: Session) -> tuple[bool, str, dict]:
        """Test the API connection. Returns (ok, message, user_info)."""
        try:
            creds = _build_creds(db, provider_name)
            if not creds.api_token:
                return False, API_TOKEN_NOT_CONFIGURED, {}

            provider = get_provider(provider_name)
            valid = provider.validate_credentials(creds)

            if not valid:
                return False, "Invalid credentials", {}

            # Get user info if available
            user_info = {}
            if hasattr(provider, "get_user_info"):
                user_info = provider.get_user_info(creds)

            return True, "Connection successful", user_info
        except Exception as exc:
            logger.exception("Connection test failed for %s", provider_name)
            return False, f"Connection failed: {exc}", {}

    @staticmethod
    def sync_all(provider_name: str, db: Session, full_sync: bool = False) -> SyncResult:
        """Run a full sync from the given provider into the local database."""
        result = SyncResult()

        try:
            creds = _build_creds(db, provider_name)
            if not creds.api_token:
                result.errors.append(API_TOKEN_NOT_CONFIGURED)
                return result

            provider = get_provider(provider_name)
            if full_sync:
                since = None
                logger.info("Full sync requested — fetching all historical data")
            else:
                last_sync = _get_setting(db, "last_sync_timestamp")
                since = last_sync if last_sync else None

        except Exception as exc:
            result.errors.append(f"Setup error: {exc}")
            logger.exception("Sync setup error")
            return result

        # --- Sync users first (needed for pilot matching) ---
        skydio_users = []
        try:
            skydio_users = provider.sync_users(creds)
            result.users_synced = len(skydio_users)
            logger.info("Users sync: got %d users", len(skydio_users))
        except Exception as exc:
            result.errors.append(f"Users sync error: {exc}")
            logger.exception("Users sync error")

        # --- Match Skydio users to pilots and populate emails ---
        try:
            _match_pilot_emails(skydio_users, db)
        except Exception as exc:
            logger.warning("Pilot email matching error: %s", exc)

        # --- Sync vehicles (commit independently so a later step's failure
        #     can't discard vehicles already staged) ---
        try:
            _sync_vehicles(provider, creds, db, result)
            db.commit()
            logger.info("Committed %d vehicles to database", result.vehicles_synced)
        except Exception as exc:
            result.errors.append(f"Vehicles sync error: {exc}")
            logger.exception("Vehicles sync error")
            db.rollback()
            result.vehicles_synced = 0

        # --- Sync flights (commit independently) ---
        try:
            flights_data = provider.sync_flights(creds, since=since)
            _upsert_flights(flights_data, skydio_users, db, result)
            db.commit()
            logger.info("Committed %d new flights to database", result.flights_new)
        except Exception as exc:
            result.errors.append(f"Flights sync error: {exc}")
            logger.exception("Flights sync error")
            db.rollback()
            result.flights_new = 0
            result.flights_skipped = 0

        # --- Enrich flights with full details ---
        try:
            _enrich_flights(provider, creds, db, result)
            db.commit()
        except Exception as exc:
            result.errors.append(f"Flight enrichment error: {exc}")
            logger.exception("Flight enrichment error")
            db.rollback()

        # --- Sync batteries ---
        try:
            _sync_entity_list(provider.sync_batteries, creds, db, Battery, "serial_number",
                              _update_battery, _create_battery, "batteries_synced", result)
            db.commit()
        except Exception as exc:
            result.errors.append(f"Batteries sync error: {exc}")
            logger.exception("Batteries sync error")
            db.rollback()

        # --- Sync controllers ---
        try:
            _sync_entity_list(provider.sync_controllers, creds, db, Controller, "serial_number",
                              _update_controller, _create_controller, "controllers_synced", result)
            db.commit()
        except Exception as exc:
            result.errors.append(f"Controllers sync error: {exc}")
            logger.exception("Controllers sync error")
            db.rollback()

        # --- Sync docks ---
        try:
            _sync_entity_list(provider.sync_docks, creds, db, Dock, "serial_number",
                              _update_dock, _create_dock, "docks_synced", result)
            db.commit()
        except Exception as exc:
            result.errors.append(f"Docks sync error: {exc}")
            logger.exception("Docks sync error")
            db.rollback()

        # --- Sync sensor packages ---
        try:
            _sync_entity_list(provider.sync_sensor_packages, creds, db, SensorPackage, "serial_number",
                              _update_sensor, _create_sensor, "sensors_synced", result)
            db.commit()
        except Exception as exc:
            result.errors.append(f"Sensors sync error: {exc}")
            logger.exception("Sensors sync error")
            db.rollback()

        # --- Sync attachments ---
        try:
            _sync_entity_list(provider.sync_attachments, creds, db, Attachment, "serial_number",
                              _update_attachment, _create_attachment, "attachments_synced", result)
            db.commit()
        except Exception as exc:
            result.errors.append(f"Attachments sync error: {exc}")
            logger.exception("Attachments sync error")
            db.rollback()

        # --- Sync media ---
        try:
            _sync_media(provider, creds, since, db, result)
            db.commit()
        except Exception as exc:
            logger.debug("Media sync skipped: %s", exc)

        # --- Commit and update last sync timestamp ---
        # Only advance last_sync_timestamp when the run was clean. Otherwise
        # the next sync's `since=` filter would skip rows that failed this run.
        try:
            if not result.errors:
                _set_setting(db, "last_sync_timestamp", datetime.now(timezone.utc).isoformat())
            _set_setting(db, "last_sync_provider", provider_name)
            _persist_last_sync_result(db, result)
            db.commit()
        except Exception as exc:
            result.errors.append(f"Commit error: {exc}")
            logger.exception("Sync commit error")
            db.rollback()

        logger.info(
            "Sync complete: %d vehicles, %d new flights (%d skipped), %d batteries, %d errors",
            result.vehicles_synced, result.flights_new, result.flights_skipped,
            result.batteries_synced, len(result.errors),
        )

        return result

    @staticmethod
    def sync_all_deep(provider_name: str, db: Session) -> SyncResult:
        """Deep sync: fetches ALL historical flights via windowed date pagination."""
        result = SyncResult()

        try:
            creds = _build_creds(db, provider_name)
            if not creds.api_token:
                result.errors.append(API_TOKEN_NOT_CONFIGURED)
                return result
            provider = get_provider(provider_name)
        except Exception as exc:
            result.errors.append(f"Setup error: {exc}")
            return result

        # --- Sync users first (needed for pilot matching) ---
        skydio_users = []
        try:
            skydio_users = provider.sync_users(creds)
            result.users_synced = len(skydio_users)
            logger.info("Deep sync users: got %d users", len(skydio_users))
        except Exception as exc:
            result.errors.append(f"Users sync error: {exc}")
            logger.exception("Deep sync users error")

        # --- Sync vehicles (needed for flight vehicle matching) ---
        try:
            _sync_vehicles(provider, creds, db, result)
            db.commit()
        except Exception as exc:
            result.errors.append(f"Vehicles sync error: {exc}")
            logger.exception("Deep sync vehicles error")
            db.rollback()

        # --- Deep flight sync ---
        try:
            flights_data = provider.sync_flights_deep(creds)
            logger.info("Deep sync returned %d flights", len(flights_data))
            _upsert_flights(flights_data, skydio_users, db, result)
            db.commit()
            logger.info("Committed %d new flights to database", result.flights_new)
        except Exception as exc:
            result.errors.append(f"Deep flight sync error: {exc}")
            logger.exception("Deep flight sync error")
            db.rollback()

        # --- Commit and update last sync timestamp ---
        # Only advance last_sync_timestamp when the run was clean. Otherwise
        # the next sync's `since=` filter would skip rows that failed this run.
        try:
            if not result.errors:
                _set_setting(db, "last_sync_timestamp", datetime.now(timezone.utc).isoformat())
            _set_setting(db, "last_sync_provider", provider_name)
            _persist_last_sync_result(db, result)
            db.commit()
        except Exception as exc:
            result.errors.append(f"Commit error: {exc}")
            logger.exception("Deep sync commit error")
            db.rollback()

        logger.info(
            "Deep sync complete: %d vehicles, %d new flights (%d skipped), %d errors",
            result.vehicles_synced, result.flights_new, result.flights_skipped,
            len(result.errors),
        )

        return result

    @staticmethod
    def batch_sync_telemetry(db: Session, limit: int = 10) -> int:
        """Fetch telemetry for up to `limit` flights without it. Returns count synced."""
        from app.models.telemetry import TelemetryPoint
        from app.database import TelemetrySessionLocal

        creds = _build_creds(db, "skydio")
        if not creds.api_token:
            return 0

        provider = get_provider("skydio")
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

        _set_setting(db, "last_telemetry_sync_timestamp", datetime.now(timezone.utc).isoformat())
        _set_setting(db, "last_telemetry_sync_result", json.dumps({"synced": synced}))
        db.commit()
        return synced


def _match_pilot(db: Session, pilot_name: str) -> int | None:
    """Try to match a Skydio pilot name to a local pilot by first+last name."""
    if not pilot_name:
        return None

    parts = pilot_name.strip().split()
    if len(parts) < 2:
        # Try matching just first name
        pilot = db.query(Pilot).filter(
            Pilot.first_name.ilike(parts[0]),
            Pilot.status == "active",
        ).first()
        return pilot.id if pilot else None

    first_name = parts[0]
    last_name = " ".join(parts[1:])

    pilot = db.query(Pilot).filter(
        Pilot.first_name.ilike(first_name),
        Pilot.last_name.ilike(last_name),
        Pilot.status == "active",
    ).first()

    return pilot.id if pilot else None
