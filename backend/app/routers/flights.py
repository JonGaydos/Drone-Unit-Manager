from datetime import date
from math import ceil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.constants import FLIGHT_NOT_FOUND, UTC_OFFSET
from app.models.flight import Flight, FlightPurpose
from app.deps import DBSession, CurrentUser, AdminUser, PilotUser, SupervisorUser
from app.responses import responses
from app.schemas.flight import (
    FlightCreate, FlightUpdate, FlightOut,
    FlightPurposeCreate, FlightPurposeOut,
    FlightBulkUpdate,
)

router = APIRouter(prefix="/api/flights", tags=["flights"])


def _flight_to_out(flight: Flight) -> FlightOut:
    pilot_name = None
    if flight.pilot:
        pilot_name = f"{flight.pilot.first_name} {flight.pilot.last_name}".strip()
    vehicle_name = None
    if flight.vehicle:
        vehicle_name = flight.vehicle.nickname or f"{flight.vehicle.manufacturer} {flight.vehicle.model}"
    return FlightOut.model_validate({**flight.__dict__, "pilot_name": pilot_name, "vehicle_name": vehicle_name})


@router.get("")
def list_flights(
    db: DBSession,
    user: CurrentUser,
    pilot_id: int | None = None,
    vehicle_id: int | None = None,
    purpose: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    review_status: str | None = None,
    page: int = 1,
    per_page: int = 100):
    filters = []
    if pilot_id:
        filters.append(Flight.pilot_id == pilot_id)
    if vehicle_id:
        filters.append(Flight.vehicle_id == vehicle_id)
    if purpose:
        filters.append(Flight.purpose == purpose)
    if date_from:
        filters.append(Flight.date >= date_from)
    if date_to:
        filters.append(Flight.date <= date_to)
    if review_status:
        filters.append(Flight.review_status == review_status)
    total = db.query(func.count(Flight.id)).filter(*filters).scalar()
    offset = (page - 1) * per_page
    flights = db.query(Flight).options(
        joinedload(Flight.pilot), joinedload(Flight.vehicle)
    ).filter(*filters).order_by(
        Flight.date.desc().nulls_first(), Flight.takeoff_time.desc().nulls_first()
    ).offset(offset).limit(per_page).all()
    return {
        "flights": [_flight_to_out(f) for f in flights],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ceil(total / per_page) if per_page > 0 else 1,
    }


@router.get("/count")
def count_flights(
    db: DBSession,
    user: CurrentUser,
    review_status: str | None = None):
    q = db.query(func.count(Flight.id))
    if review_status:
        q = q.filter(Flight.review_status == review_status)
    return {"count": q.scalar()}


@router.get("/review", response_model=list[FlightOut])
def list_review_queue(
    db: DBSession,
    user: CurrentUser,
):
    flights = db.query(Flight).options(
        joinedload(Flight.pilot), joinedload(Flight.vehicle)
    ).filter(
        Flight.review_status == "needs_review"
    ).order_by(Flight.date.desc(), Flight.takeoff_time.desc()).all()
    return [_flight_to_out(f) for f in flights]


@router.get("/purposes/list", response_model=list[FlightPurposeOut], responses=responses(401))
def list_purposes(db: DBSession, user: CurrentUser):
    return [FlightPurposeOut.model_validate(p) for p in db.query(FlightPurpose).order_by(FlightPurpose.sort_order, FlightPurpose.name).all()]


@router.get("/{flight_id}", response_model=FlightOut, responses=responses(401, 404))
def get_flight(flight_id: int, db: DBSession, user: CurrentUser):
    flight = db.query(Flight).options(
        joinedload(Flight.pilot), joinedload(Flight.vehicle)
    ).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail=FLIGHT_NOT_FOUND)
    return _flight_to_out(flight)


def _refresh_timestamps(flight: Flight, detail: dict, updated_fields: list):
    """Apply timestamp fields from API detail to flight."""
    from datetime import datetime

    takeoff_str = detail.get("takeoff_time") or detail.get("start_time")
    if takeoff_str:
        try:
            takeoff = datetime.fromisoformat(str(takeoff_str).replace("Z", UTC_OFFSET))
            flight.takeoff_time = takeoff
            flight.date = takeoff.date()
            updated_fields.append("date")
        except (ValueError, AttributeError):
            pass

    landing_str = detail.get("landing_time") or detail.get("end_time")
    if landing_str:
        try:
            flight.landing_time = datetime.fromisoformat(str(landing_str).replace("Z", UTC_OFFSET))
            updated_fields.append("landing_time")
        except (ValueError, AttributeError):
            pass

    duration = detail.get("duration_seconds") or detail.get("duration")
    if duration is not None:
        flight.duration_seconds = int(float(duration))
        updated_fields.append("duration")
    elif flight.takeoff_time and flight.landing_time:
        flight.duration_seconds = int((flight.landing_time - flight.takeoff_time).total_seconds())
        updated_fields.append("duration")


def _refresh_location_and_metrics(flight: Flight, detail: dict, updated_fields: list):
    """Apply location, speed, altitude, distance from API detail to flight."""
    for api_key, fld in [
        ("takeoff_latitude", "takeoff_lat"), ("takeoff_longitude", "takeoff_lon"),
        ("landing_latitude", "landing_lat"), ("landing_longitude", "landing_lon"),
    ]:
        val = detail.get(api_key) or detail.get(fld)
        if val is not None:
            setattr(flight, fld, val)
            updated_fields.append(fld)

    addr = detail.get("takeoff_address") or detail.get("location") or detail.get("address")
    if addr:
        flight.takeoff_address = str(addr)
        updated_fields.append("address")

    for api_key, fld in [
        ("max_altitude_m", "max_altitude_m"), ("max_speed_mps", "max_speed_mps"),
        ("distance_m", "distance_m"),
    ]:
        val = detail.get(api_key) or detail.get(fld.replace("_m", "").replace("_mps", ""))
        if val is not None:
            setattr(flight, fld, val)
            updated_fields.append(fld)


def _refresh_pilot(flight: Flight, detail: dict, db, updated_fields: list):
    """Match pilot by email or name from API detail."""
    from app.models.pilot import Pilot
    from app.services.sync_manager import _match_pilot

    if flight.pilot_id:
        return
    user_email = detail.get("user_email")
    if user_email:
        pilot = db.query(Pilot).filter(
            Pilot.email.ilike(str(user_email)),
            Pilot.status == "active",
        ).first()
        if pilot:
            flight.pilot_id = pilot.id
            updated_fields.append("pilot")
    if not flight.pilot_id:
        pilot_name = detail.get("pilot_name") or detail.get("operator_name") or detail.get("user_name")
        if pilot_name:
            flight.pilot_id = _match_pilot(db, pilot_name)
            if flight.pilot_id:
                updated_fields.append("pilot")


def _refresh_equipment(flight: Flight, detail: dict, updated_fields: list):
    """Apply equipment fields (battery, sensor, attachments, carrier) from API detail."""
    from app.integrations.skydio import _to_str

    for api_key, fld in [
        ("battery_serial", "battery_serial"), ("sensor_package", "sensor_package"),
        ("carrier", "carrier"),
    ]:
        val = detail.get(api_key)
        if val is not None:
            setattr(flight, fld, _to_str(val))
            updated_fields.append(fld)

    attachments = detail.get("attachments")
    if isinstance(attachments, list):
        mount_map = {"TOP": "attachment_top", "BOTTOM": "attachment_bottom",
                     "LEFT": "attachment_left", "RIGHT": "attachment_right"}
        for att in attachments:
            if not isinstance(att, dict):
                continue
            mount = att.get("mount_point", "").upper()
            fld = mount_map.get(mount)
            if fld:
                label = f"{att.get('attachment_type', '')} ({att.get('attachment_serial', '')})"
                setattr(flight, fld, label.strip())
                updated_fields.append(fld)

    battery = detail.get("battery")
    if isinstance(battery, dict) and not flight.battery_serial:
        flight.battery_serial = battery.get("battery_serial") or battery.get("serial_number") or _to_str(battery)
        updated_fields.append("battery_serial")
    elif isinstance(battery, str) and not flight.battery_serial:
        flight.battery_serial = battery
        updated_fields.append("battery_serial")

    sensor = detail.get("sensor_package")
    if isinstance(sensor, dict) and not flight.sensor_package:
        flight.sensor_package = sensor.get("sensor_package_serial") or sensor.get("serial_number") or _to_str(sensor)
        updated_fields.append("sensor_package")


def _refresh_vehicle(flight: Flight, detail: dict, db, updated_fields: list):
    """Match vehicle from API detail."""
    from app.models.vehicle import Vehicle

    vehicle_data = detail.get("vehicle")
    vs = detail.get("vehicle_serial") or (vehicle_data.get("serial_number") if isinstance(vehicle_data, dict) else None)
    if vs and not flight.vehicle_id:
        vehicle = db.query(Vehicle).filter(
            (Vehicle.provider_serial == str(vs)) |
            (Vehicle.serial_number == str(vs))
        ).first()
        if vehicle:
            flight.vehicle_id = vehicle.id
            updated_fields.append("vehicle")


def _parse_telemetry_timestamp(ts) -> int:
    """Parse a telemetry timestamp value to milliseconds."""
    from datetime import datetime
    if isinstance(ts, str):
        try:
            parsed = datetime.fromisoformat(ts.replace("Z", UTC_OFFSET))
            return int(parsed.timestamp() * 1000)
        except (ValueError, AttributeError):
            return 0
    if isinstance(ts, (int, float)):
        return int(ts)
    return 0


def _refresh_telemetry(flight: Flight, provider, creds, updated_fields: list, logger) -> int:
    """Fetch and save telemetry data. Returns number of points saved."""
    telemetry_data = None
    try:
        telemetry_data = provider.get_flight_telemetry(creds, flight.external_id)
    except Exception as exc:
        logger.warning("Telemetry fetch failed for %s: %s", flight.external_id, exc)

    if not telemetry_data or not isinstance(telemetry_data, list) or len(telemetry_data) == 0:
        return 0

    from app.models.telemetry import TelemetryPoint
    from app.database import TelemetrySessionLocal

    tdb = TelemetrySessionLocal()
    try:
        tdb.query(TelemetryPoint).filter(TelemetryPoint.flight_id == flight.id).delete()

        max_alt = 0
        max_speed = 0

        for point in telemetry_data:
            if not isinstance(point, dict):
                continue

            timestamp_ms = _parse_telemetry_timestamp(point.get("timestamp_ms"))
            alt = point.get("altitude_m") or 0
            speed = point.get("speed_mps") or 0

            if alt > max_alt:
                max_alt = alt
            if speed > max_speed:
                max_speed = speed

            tp = TelemetryPoint(
                flight_id=flight.id,
                timestamp_ms=timestamp_ms,
                lat=point.get("lat"),
                lon=point.get("lon"),
                altitude_m=alt,
                speed_mps=speed,
                heading_deg=point.get("heading_deg"),
                battery_pct=point.get("battery_pct"),
            )
            tdb.add(tp)

        tdb.commit()
        telemetry_points = len(telemetry_data)
        updated_fields.append(f"telemetry({telemetry_points}pts)")

        if max_alt > 0:
            flight.max_altitude_m = round(max_alt, 2)
            updated_fields.append("max_altitude")
        if max_speed > 0:
            flight.max_speed_mps = round(max_speed, 2)
            updated_fields.append("max_speed")

        return telemetry_points
    except Exception as exc:
        logger.error("Telemetry save failed: %s", exc)
        tdb.rollback()
        return 0
    finally:
        tdb.close()


@router.post("/{flight_id}/refresh", responses=responses(400, 401, 404, 502))
def refresh_flight_from_api(flight_id: int, db: DBSession, admin: AdminUser):
    """Fetch fresh data from Skydio API for a single flight."""
    import logging
    from app.integrations.skydio import SkydioProvider
    from app.services.sync_manager import _build_creds

    logger = logging.getLogger(__name__)

    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail=FLIGHT_NOT_FOUND)
    if not flight.external_id:
        raise HTTPException(status_code=400, detail="Flight has no external ID to look up")

    creds = _build_creds(db, "skydio")
    if not creds.api_token:
        raise HTTPException(status_code=400, detail="Skydio API not configured")

    provider = SkydioProvider()
    detail = provider.get_flight_detail(creds, flight.external_id)

    if not detail:
        raise HTTPException(status_code=502, detail="Could not fetch flight data from Skydio")

    updated_fields = []

    _refresh_timestamps(flight, detail, updated_fields)
    _refresh_location_and_metrics(flight, detail, updated_fields)
    _refresh_pilot(flight, detail, db, updated_fields)
    _refresh_equipment(flight, detail, updated_fields)
    _refresh_vehicle(flight, detail, db, updated_fields)

    telemetry_points = _refresh_telemetry(flight, provider, creds, updated_fields, logger)

    if telemetry_points > 0:
        flight.telemetry_synced = True

    db.commit()

    logger.info("Refreshed flight %s: updated %s", flight.external_id, updated_fields)

    return {
        "ok": True,
        "flight_id": flight.id,
        "external_id": flight.external_id,
        "updated_fields": updated_fields,
        "telemetry_points": telemetry_points,
        "api_keys_returned": list(detail.keys()),
    }


@router.post("", response_model=FlightOut, responses=responses(401))
def create_flight(data: FlightCreate, db: DBSession, admin: PilotUser):
    from app.services.audit import log_action
    flight = Flight(**data.model_dump(), review_status="reviewed", pilot_confirmed=True, data_source="manual")
    db.add(flight)
    db.flush()
    # Auto-create Fleet records for any new equipment serials
    from app.services.sync_manager import _ensure_equipment_records
    try:
        _ensure_equipment_records(db, flight)
    except Exception:
        pass
    log_action(db, admin.id, admin.display_name, "create", "flight", flight.id, f"Flight {flight.external_id or flight.id}")
    db.commit()
    db.refresh(flight)
    return _flight_to_out(flight)


@router.patch("/{flight_id}", response_model=FlightOut, responses=responses(401, 404))
def update_flight(flight_id: int, data: FlightUpdate, db: DBSession, admin: PilotUser):
    from app.services.audit import log_action, compute_changes
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail=FLIGHT_NOT_FOUND)
    update_data = data.model_dump(exclude_unset=True)
    changes = compute_changes(flight, update_data, ["pilot_id", "vehicle_id", "purpose", "review_status", "date", "notes"])
    for key, value in update_data.items():
        setattr(flight, key, value)
    # Auto-create Fleet records for any new equipment serials
    from app.services.sync_manager import _ensure_equipment_records
    try:
        _ensure_equipment_records(db, flight)
    except Exception:
        pass
    if changes:
        log_action(db, admin.id, admin.display_name, "update", "flight", flight.id, f"Flight {flight.external_id or flight.id}", changes=changes)
    db.commit()
    db.refresh(flight)
    return _flight_to_out(flight)


@router.post("/bulk-update", responses=responses(401))
def bulk_update_flights(data: FlightBulkUpdate, db: DBSession, admin: SupervisorUser):
    from app.services.audit import log_action
    flights = db.query(Flight).filter(Flight.id.in_(data.flight_ids)).all()
    for flight in flights:
        if data.pilot_id is not None:
            flight.pilot_id = data.pilot_id
        if data.purpose is not None:
            flight.purpose = data.purpose
        if data.review_status is not None:
            flight.review_status = data.review_status
        if data.pilot_confirmed is not None:
            flight.pilot_confirmed = data.pilot_confirmed
    action = "bulk_approve" if data.review_status == "reviewed" else "bulk_update"
    log_action(db, admin.id, admin.display_name, action, "flight", details=f"Updated {len(flights)} flights")
    db.commit()
    return {"ok": True, "updated": len(flights)}


class TelemetryStatusUpdate(BaseModel):
    telemetry_synced: bool


@router.patch("/{flight_id}/telemetry-status", responses=responses(404))
def update_telemetry_status(
    flight_id: int,
    data: TelemetryStatusUpdate,
    db: DBSession,
    user: SupervisorUser,
):
    """Toggle the telemetry synced flag on a flight."""
    from app.services.audit import log_action
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(404, FLIGHT_NOT_FOUND)
    flight.telemetry_synced = data.telemetry_synced
    log_action(db, user.id, user.display_name, "update", "flight", flight_id,
               details=f"Telemetry synced set to {data.telemetry_synced}")
    db.commit()
    return {"ok": True, "telemetry_synced": flight.telemetry_synced}


@router.delete("/{flight_id}", responses=responses(401, 404))
def delete_flight(flight_id: int, db: DBSession, admin: PilotUser):
    from app.services.audit import log_action
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail=FLIGHT_NOT_FOUND)
    flight_name = f"Flight {flight.external_id or flight.id}"
    log_action(db, admin.id, admin.display_name, "delete", "flight", flight.id, flight_name)
    db.delete(flight)
    db.commit()
    return {"ok": True}


@router.post("/purposes", response_model=FlightPurposeOut, responses=responses(400, 401))
def create_purpose(data: FlightPurposeCreate, db: DBSession, admin: AdminUser):
    if db.query(FlightPurpose).filter(FlightPurpose.name == data.name).first():
        raise HTTPException(status_code=400, detail="Purpose already exists")
    purpose = FlightPurpose(**data.model_dump())
    db.add(purpose)
    db.commit()
    db.refresh(purpose)
    return FlightPurposeOut.model_validate(purpose)


@router.delete("/purposes/{purpose_id}", responses=responses(401, 404))
def delete_purpose(purpose_id: int, db: DBSession, admin: AdminUser):
    purpose = db.query(FlightPurpose).filter(FlightPurpose.id == purpose_id).first()
    if not purpose:
        raise HTTPException(status_code=404, detail="Purpose not found")
    db.delete(purpose)
    db.commit()
    return {"ok": True}
