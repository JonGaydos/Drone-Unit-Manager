from collections import Counter
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
from app.services.audit import log_action
from app.schemas.flight import (
    FlightCreate, FlightUpdate, FlightOut,
    FlightPurposeCreate, FlightPurposeOut,
    FlightBulkUpdate,
)

router = APIRouter(prefix="/api/flights", tags=["flights"])


def _refresh_capable_providers() -> set[str]:
    """Registered providers that can look up a single flight's live detail.

    A provider is refresh-capable only if it implements get_flight_detail; the
    abstract base does not, so a sync-only provider is excluded automatically.
    """
    from app.integrations import registry
    capable = set()
    for name in registry.list_providers():
        if hasattr(registry.get_provider(name), "get_flight_detail"):
            capable.add(name)
    return capable


def _refresh_provider_name(flight: Flight) -> str | None:
    """The provider that can refresh this flight, following the drone.

    The drone's own provider wins over the flight's import source, so a Skydio
    vehicle whose flights arrived through Airdata or Excel still refreshes,
    while a BRINC flight (no live API) does not. Falls back to the vehicle
    manufacturer, then the flight's recorded provider.
    """
    capable = _refresh_capable_providers()
    candidates = []
    if flight.vehicle:
        if flight.vehicle.api_provider:
            candidates.append(flight.vehicle.api_provider)
        if flight.vehicle.manufacturer:
            candidates.append(flight.vehicle.manufacturer)
    if flight.api_provider:
        candidates.append(flight.api_provider)
    for candidate in candidates:
        name = candidate.strip().lower()
        if name in capable:
            return name
    return None


def _flight_to_out(flight: Flight) -> FlightOut:
    pilot_name = None
    if flight.pilot:
        pilot_name = f"{flight.pilot.first_name} {flight.pilot.last_name}".strip()
    vehicle_name = None
    if flight.vehicle:
        vehicle_name = flight.vehicle.nickname or f"{flight.vehicle.manufacturer} {flight.vehicle.model}"
    can_refresh = bool(flight.external_id) and _refresh_provider_name(flight) is not None
    return FlightOut.model_validate({
        **flight.__dict__,
        "pilot_name": pilot_name,
        "vehicle_name": vehicle_name,
        "can_refresh": can_refresh,
    })


def _purge_flight_references(db, ids: list[int]) -> None:
    if not ids: return
    from app.models.incident import Incident
    from app.models.checklist import ChecklistCompletion
    from app.models.flight_approval import FlightPlan
    from app.models.media import MediaFile
    from app.models.photo import PhotoFlight
    db.query(Incident).filter(Incident.flight_id.in_(ids)).update({Incident.flight_id: None}, synchronize_session=False)
    db.query(ChecklistCompletion).filter(ChecklistCompletion.flight_id.in_(ids)).update({ChecklistCompletion.flight_id: None}, synchronize_session=False)
    db.query(FlightPlan).filter(FlightPlan.linked_flight_id.in_(ids)).update({FlightPlan.linked_flight_id: None}, synchronize_session=False)
    db.query(MediaFile).filter(MediaFile.flight_id.in_(ids)).delete(synchronize_session=False)
    db.query(PhotoFlight).filter(PhotoFlight.flight_id.in_(ids)).delete(synchronize_session=False)


def _purge_flight_telemetry(ids: list[int]) -> None:   # call AFTER main commit
    if not ids: return
    from app.models.telemetry import TelemetryPoint
    from app.database import TelemetrySessionLocal
    tdb = TelemetrySessionLocal()
    try:
        tdb.query(TelemetryPoint).filter(TelemetryPoint.flight_id.in_(ids)).delete(synchronize_session=False)
        tdb.commit()
    finally:
        tdb.close()


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
    if purpose == "__none__":
        filters.append((Flight.purpose.is_(None)) | (Flight.purpose == ""))
    elif purpose:
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


@router.get("/purposes/usage", responses=responses(401))
def list_purposes_with_usage(db: DBSession, user: SupervisorUser):
    """Purposes plus how many records reference each, for the Settings editor.

    Kept separate from /purposes/list, which every flight page calls on load and
    should not pay for these counts.

    Flight.purpose and MissionLog.reason hold the purpose NAME rather than a
    foreign key, so usage is a string match and deleting a purpose cannot
    cascade on its own.
    """
    from app.models.mission_log import MissionLog

    purposes = db.query(FlightPurpose).order_by(FlightPurpose.sort_order, FlightPurpose.name).all()

    flight_counts = dict(
        db.query(Flight.purpose, func.count(Flight.id))
          .filter(Flight.purpose.isnot(None)).group_by(Flight.purpose).all()
    )
    mission_counts = dict(
        db.query(MissionLog.reason, func.count(MissionLog.id))
          .filter(MissionLog.reason.isnot(None)).group_by(MissionLog.reason).all()
    )

    return [
        {
            "id": p.id,
            "name": p.name,
            "sort_order": p.sort_order,
            "flight_count": flight_counts.get(p.name, 0),
            "mission_count": mission_counts.get(p.name, 0),
        }
        for p in purposes
    ]


@router.get("/preflight-check", responses=responses(401))
def preflight_check(vehicle_id: int, db: DBSession, user: CurrentUser):
    """Non-blocking pre-flight readiness warnings for a vehicle: a non-active
    status, overdue active maintenance schedules, or an expired current FAA
    registration. Surfaced in the Add Flight form so the logger sees airframe
    issues without being blocked from recording a flight that already happened.
    """
    from app.models.vehicle import Vehicle
    from app.models.maintenance_schedule import MaintenanceSchedule
    from app.models.vehicle_registration import VehicleRegistration

    today = date.today()
    warnings = []
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        return {"warnings": warnings}

    if vehicle.status and vehicle.status != "active":
        warnings.append(f"Vehicle status is '{vehicle.status}', not active.")

    overdue = db.query(MaintenanceSchedule).filter(
        MaintenanceSchedule.entity_type == "vehicle",
        MaintenanceSchedule.entity_id == vehicle_id,
        MaintenanceSchedule.is_active.is_(True),
        MaintenanceSchedule.next_due.isnot(None),
        MaintenanceSchedule.next_due < today,
    ).all()
    for s in overdue:
        warnings.append(f"Overdue maintenance: {s.name} (due {s.next_due}).")

    current_reg = db.query(VehicleRegistration).filter(
        VehicleRegistration.vehicle_id == vehicle_id,
        VehicleRegistration.is_current.is_(True),
    ).order_by(VehicleRegistration.registration_date.desc()).first()
    if current_reg and current_reg.expiry_date and current_reg.expiry_date < today:
        warnings.append(f"FAA registration expired on {current_reg.expiry_date}.")

    return {"warnings": warnings}


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
        logger.exception("Telemetry save failed")
        tdb.rollback()
        return 0
    finally:
        tdb.close()


@router.post("/{flight_id}/refresh", responses=responses(400, 401, 404, 502))
def refresh_flight_from_api(flight_id: int, db: DBSession, admin: AdminUser):
    """Fetch fresh data from the drone's provider API for a single flight."""
    import logging
    from app.integrations import registry
    from app.services.sync_manager import _build_creds

    logger = logging.getLogger(__name__)

    flight = db.query(Flight).options(
        joinedload(Flight.vehicle)
    ).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail=FLIGHT_NOT_FOUND)
    if not flight.external_id:
        raise HTTPException(status_code=400, detail="Flight has no external ID to look up")

    provider_name = _refresh_provider_name(flight)
    if not provider_name:
        raise HTTPException(status_code=400, detail="This drone has no connected API to refresh from")

    creds = _build_creds(db, provider_name)
    if not creds.api_token:
        raise HTTPException(status_code=400, detail=f"{provider_name.title()} API not configured")

    provider = registry.get_provider(provider_name)
    detail = provider.get_flight_detail(creds, flight.external_id)

    if not detail:
        raise HTTPException(status_code=502, detail="Could not fetch flight data from the provider")

    updated_fields = []

    _refresh_timestamps(flight, detail, updated_fields)
    _refresh_location_and_metrics(flight, detail, updated_fields)
    _refresh_pilot(flight, detail, db, updated_fields)
    _refresh_equipment(flight, detail, updated_fields)
    _refresh_vehicle(flight, detail, db, updated_fields)

    telemetry_points = _refresh_telemetry(flight, provider, creds, updated_fields, logger)

    if telemetry_points > 0:
        flight.telemetry_synced = True
        flight.has_telemetry = True

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
    flight = Flight(**data.model_dump(), review_status="needs_review", pilot_confirmed=True, data_source="manual")
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


# The fields one bulk edit may set. Anything else on the payload is neither
# applied nor audited.
BULK_FIELDS = ("pilot_id", "purpose", "review_status", "pilot_confirmed",
               "counts_toward_totals")

# Enough of the id list to identify what an edit touched without turning the
# audit table into a wall of digits.
MAX_ID_DETAIL_CHARS = 300

# Flight purposes are free text on import, so the distinct prior values an edit
# replaces are not bounded by the configured purpose list. Cap them.
MAX_DISTINCT_PRIOR_VALUES = 10


def _id_ranges(ids) -> str:
    """``[1, 2, 3, 7, 8]`` -> ``"1-3, 7-8"``."""
    ranges: list[list[int]] = []
    for i in sorted(set(ids)):
        if ranges and i == ranges[-1][1] + 1:
            ranges[-1][1] = i
        else:
            ranges.append([i, i])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges)


def _overwritten(flights, field, new_value) -> str:
    """The values this edit replaces, most common first: ``"Map Scan (62), Training (20)"``.

    A bulk edit sets one field on every selected row at once, so the audit entry
    is the only record of what was there before it. Without it, undoing an
    accidental edit means diffing a backup.
    """
    counts = Counter(
        "(none)" if (old := getattr(flight, field)) is None else str(old)
        for flight in flights if getattr(flight, field) != new_value)
    summary = ", ".join(f"{value} ({n})"
                        for value, n in counts.most_common(MAX_DISTINCT_PRIOR_VALUES))
    if len(counts) > MAX_DISTINCT_PRIOR_VALUES:
        summary += f", and {len(counts) - MAX_DISTINCT_PRIOR_VALUES} more"
    return summary


@router.post("/bulk-update", responses=responses(401))
def bulk_update_flights(data: FlightBulkUpdate, db: DBSession, admin: SupervisorUser):
    flights = db.query(Flight).filter(Flight.id.in_(data.flight_ids)).all()
    updates = {field: value for field in BULK_FIELDS
               if (value := getattr(data, field)) is not None}

    # Read the old values before writing over them.
    changes = {field: {"old": _overwritten(flights, field, value) or "(no change)",
                       "new": str(value)}
               for field, value in updates.items()}

    for flight in flights:
        for field, value in updates.items():
            setattr(flight, field, value)

    details = f"Updated {len(flights)} flights"
    if flights:
        touched = _id_ranges(f.id for f in flights)
        if len(touched) > MAX_ID_DETAIL_CHARS:
            # Trim back to a whole range so the tail is never a half id.
            touched = touched[:MAX_ID_DETAIL_CHARS].rsplit(", ", 1)[0] + ", ..."
        details += f" (ids {touched})"

    action = "bulk_approve" if data.review_status == "reviewed" else "bulk_update"
    log_action(db, admin.id, admin.display_name, action, "flight",
               changes=changes or None, details=details)
    db.commit()
    return {"ok": True, "updated": len(flights)}


class FlightBulkDelete(BaseModel):
    flight_ids: list[int]


@router.post("/bulk-delete", responses=responses(401))
def bulk_delete_flights(data: FlightBulkDelete, db: DBSession, admin: SupervisorUser):
    """Delete multiple flights at once. Purges their telemetry (a separate DB,
    not ORM-cascaded) in one pass and audit-logs the count. Supervisor or admin
    only; mirrors the single-flight delete."""
    from app.services.audit import log_action
    flights = db.query(Flight).filter(Flight.id.in_(data.flight_ids)).all()
    if not flights:
        return {"ok": True, "deleted": 0}
    ids = [f.id for f in flights]
    _purge_flight_references(db, ids)
    log_action(db, admin.id, admin.display_name, "bulk_delete", "flight", details=f"Deleted {len(flights)} flights")
    for flight in flights:
        db.delete(flight)
    db.commit()
    _purge_flight_telemetry(ids)
    return {"ok": True, "deleted": len(flights)}


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


class ReviewStatusUpdate(BaseModel):
    review_status: str  # "reviewed" or "needs_review"


@router.patch("/{flight_id}/review-status", responses=responses(400, 404))
def update_review_status(
    flight_id: int,
    data: ReviewStatusUpdate,
    db: DBSession,
    user: SupervisorUser,
):
    """Toggle the review status flag on a flight."""
    from app.services.audit import log_action
    if data.review_status not in ("reviewed", "needs_review"):
        raise HTTPException(400, "review_status must be 'reviewed' or 'needs_review'")
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(404, FLIGHT_NOT_FOUND)
    flight.review_status = data.review_status
    action = "approve" if data.review_status == "reviewed" else "unapprove"
    log_action(db, user.id, user.display_name, action, "flight", flight_id,
               details=f"Review status set to {data.review_status}")
    db.commit()
    return {"ok": True, "review_status": flight.review_status}


@router.delete("/{flight_id}", responses=responses(401, 404))
def delete_flight(flight_id: int, db: DBSession, admin: PilotUser):
    from app.services.audit import log_action
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail=FLIGHT_NOT_FOUND)
    flight_name = f"Flight {flight.external_id or flight.id}"
    flight_id = flight.id
    # Telemetry lives in a separate DB and is not cascaded by the ORM, so purge
    # it explicitly AFTER the main commit; otherwise it orphans and can collide
    # when an id is reused.
    _purge_flight_references(db, [flight_id])
    log_action(db, admin.id, admin.display_name, "delete", "flight", flight_id, flight_name)
    db.delete(flight)
    db.commit()
    _purge_flight_telemetry([flight_id])
    return {"ok": True}


@router.post("/purposes", response_model=FlightPurposeOut, responses=responses(400, 401))
def create_purpose(data: FlightPurposeCreate, db: DBSession, admin: AdminUser):
    # Case-insensitive: the exact-match check let "CPTEd" be created alongside
    # "CPTED", leaving two options that look like one.
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Purpose name is required")
    existing = db.query(FlightPurpose).filter(func.lower(FlightPurpose.name) == name.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail=f'A purpose named "{existing.name}" already exists')

    payload = data.model_dump()
    payload["name"] = name
    purpose = FlightPurpose(**payload)
    db.add(purpose)
    db.commit()
    db.refresh(purpose)
    log_action(db, admin.id, admin.display_name, "create", "flight_purpose", purpose.id, purpose.name)
    db.commit()
    return FlightPurposeOut.model_validate(purpose)


@router.delete("/purposes/{purpose_id}", responses=responses(401, 404))
def delete_purpose(purpose_id: int, db: DBSession, admin: AdminUser):
    """Delete a purpose and clear it from every flight that used it.

    A flight stores the purpose NAME, not a foreign key, so deleting the option
    on its own left flights holding a value no longer in the list - selectable
    nowhere, removable nowhere. Those flights are set to NULL, which the flight
    pages render as an em dash.

    Mission log reasons are counted and returned but deliberately NOT cleared:
    "reason" is descriptive prose on a mission record rather than a picked
    option, and blanking it would destroy written history the caller did not ask
    to lose.
    """
    from app.models.mission_log import MissionLog

    purpose = db.query(FlightPurpose).filter(FlightPurpose.id == purpose_id).first()
    if not purpose:
        raise HTTPException(status_code=404, detail="Purpose not found")

    name = purpose.name
    flights_cleared = db.query(Flight).filter(Flight.purpose == name).update(
        {Flight.purpose: None}, synchronize_session=False
    )
    missions_untouched = db.query(func.count(MissionLog.id)).filter(MissionLog.reason == name).scalar() or 0

    log_action(db, admin.id, admin.display_name, "delete", "flight_purpose", purpose_id, name,
               details=f"Cleared from {flights_cleared} flight(s); {missions_untouched} mission reason(s) left intact")
    db.delete(purpose)
    db.commit()
    return {"ok": True, "flights_cleared": flights_cleared, "missions_untouched": missions_untouched}
