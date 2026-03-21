from datetime import date
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.flight import Flight, FlightPurpose
from app.models.user import User
from app.routers.auth import get_current_user, require_admin
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
    pilot_id: int | None = None,
    vehicle_id: int | None = None,
    purpose: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    review_status: str | None = None,
    page: int = 1,
    per_page: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
        Flight.date.desc(), Flight.takeoff_time.desc()
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
    review_status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(func.count(Flight.id))
    if review_status:
        q = q.filter(Flight.review_status == review_status)
    return {"count": q.scalar()}


@router.get("/review", response_model=list[FlightOut])
def list_review_queue(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    flights = db.query(Flight).options(
        joinedload(Flight.pilot), joinedload(Flight.vehicle)
    ).filter(
        Flight.review_status == "needs_review"
    ).order_by(Flight.date.desc(), Flight.takeoff_time.desc()).all()
    return [_flight_to_out(f) for f in flights]


@router.get("/{flight_id}", response_model=FlightOut)
def get_flight(flight_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    flight = db.query(Flight).options(
        joinedload(Flight.pilot), joinedload(Flight.vehicle)
    ).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    return _flight_to_out(flight)


@router.post("/{flight_id}/refresh")
def refresh_flight_from_api(flight_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Fetch fresh data from Skydio API for a single flight."""
    import logging
    from datetime import datetime
    from app.integrations.skydio import SkydioProvider, _to_str
    from app.services.sync_manager import _build_creds, _match_pilot
    from app.models.vehicle import Vehicle

    logger = logging.getLogger(__name__)

    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    if not flight.external_id:
        raise HTTPException(status_code=400, detail="Flight has no external ID to look up")

    creds = _build_creds(db, "skydio")
    if not creds.api_token:
        raise HTTPException(status_code=400, detail="Skydio API not configured")

    provider = SkydioProvider()
    detail = provider.get_flight_detail(creds, flight.external_id)

    if not detail:
        raise HTTPException(status_code=502, detail="Could not fetch flight data from Skydio")

    logger.info("Refresh flight %s: API returned keys: %s", flight.external_id, list(detail.keys()))
    logger.info("Refresh flight %s: API data sample: %s", flight.external_id,
                 {k: detail[k] for k in list(detail.keys())[:25]})

    updated_fields = []

    # Date/time
    takeoff_str = detail.get("takeoff_time") or detail.get("start_time")
    if takeoff_str:
        try:
            takeoff = datetime.fromisoformat(str(takeoff_str).replace("Z", "+00:00"))
            flight.takeoff_time = takeoff
            flight.date = takeoff.date()
            updated_fields.append("date")
        except (ValueError, AttributeError):
            pass

    landing_str = detail.get("landing_time") or detail.get("end_time")
    if landing_str:
        try:
            flight.landing_time = datetime.fromisoformat(str(landing_str).replace("Z", "+00:00"))
            updated_fields.append("landing_time")
        except (ValueError, AttributeError):
            pass

    # Duration
    duration = detail.get("duration_seconds") or detail.get("duration")
    if duration is not None:
        flight.duration_seconds = int(float(duration))
        updated_fields.append("duration")
    elif flight.takeoff_time and flight.landing_time:
        flight.duration_seconds = int((flight.landing_time - flight.takeoff_time).total_seconds())
        updated_fields.append("duration")

    # Location
    for api_key, field in [
        ("takeoff_latitude", "takeoff_lat"), ("takeoff_longitude", "takeoff_lon"),
        ("landing_latitude", "landing_lat"), ("landing_longitude", "landing_lon"),
    ]:
        val = detail.get(api_key) or detail.get(field)
        if val is not None:
            setattr(flight, field, val)
            updated_fields.append(field)

    addr = detail.get("takeoff_address") or detail.get("location") or detail.get("address")
    if addr:
        flight.takeoff_address = str(addr)
        updated_fields.append("address")

    # Speed / altitude / distance
    for api_key, field in [
        ("max_altitude_m", "max_altitude_m"), ("max_speed_mps", "max_speed_mps"),
        ("distance_m", "distance_m"),
    ]:
        val = detail.get(api_key) or detail.get(field.replace("_m", "").replace("_mps", ""))
        if val is not None:
            setattr(flight, field, val)
            updated_fields.append(field)

    # Pilot
    pilot_name = detail.get("pilot_name") or detail.get("operator_name") or detail.get("user_name")
    if pilot_name and not flight.pilot_id:
        flight.pilot_id = _match_pilot(db, pilot_name)
        if flight.pilot_id:
            updated_fields.append("pilot")

    # Vehicle
    vehicle_serial = detail.get("vehicle_serial") or detail.get("serial_number")
    if vehicle_serial and not flight.vehicle_id:
        vehicle = db.query(Vehicle).filter(
            (Vehicle.skydio_vehicle_serial == str(vehicle_serial)) |
            (Vehicle.serial_number == str(vehicle_serial))
        ).first()
        if vehicle:
            flight.vehicle_id = vehicle.id
            updated_fields.append("vehicle")

    # Equipment
    for api_key, field in [
        ("battery_serial", "battery_serial"), ("sensor_package", "sensor_package"),
        ("attachment_top", "attachment_top"), ("attachment_bottom", "attachment_bottom"),
        ("attachment_left", "attachment_left"), ("attachment_right", "attachment_right"),
        ("carrier", "carrier"),
    ]:
        val = detail.get(api_key)
        if val is not None:
            setattr(flight, field, _to_str(val))
            updated_fields.append(field)

    # Also try fetching telemetry
    telemetry_data = None
    try:
        telemetry_data = provider.get_flight_telemetry(creds, flight.external_id)
    except Exception as exc:
        logger.warning("Telemetry fetch failed for %s: %s", flight.external_id, exc)

    telemetry_points = 0
    if telemetry_data and isinstance(telemetry_data, list) and len(telemetry_data) > 0:
        from app.models.telemetry import TelemetryPoint
        from app.database import TelemetrySession

        tdb = TelemetrySession()
        try:
            # Clear existing telemetry for this flight
            tdb.query(TelemetryPoint).filter(TelemetryPoint.flight_id == flight.id).delete()
            for point in telemetry_data:
                tp = TelemetryPoint(
                    flight_id=flight.id,
                    timestamp_ms=point.get("timestamp_ms") or point.get("timestamp", 0),
                    lat=point.get("lat") or point.get("latitude"),
                    lon=point.get("lon") or point.get("longitude"),
                    altitude_m=point.get("altitude_m") or point.get("altitude"),
                    speed_mps=point.get("speed_mps") or point.get("speed"),
                    heading_deg=point.get("heading_deg") or point.get("heading"),
                    battery_pct=point.get("battery_pct") or point.get("battery_percent"),
                )
                tdb.add(tp)
            tdb.commit()
            telemetry_points = len(telemetry_data)
            updated_fields.append(f"telemetry({telemetry_points}pts)")
        except Exception as exc:
            logger.error("Telemetry save failed: %s", exc)
            tdb.rollback()
        finally:
            tdb.close()

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


@router.post("", response_model=FlightOut)
def create_flight(data: FlightCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    flight = Flight(**data.model_dump(), review_status="reviewed", pilot_confirmed=True)
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return _flight_to_out(flight)


@router.patch("/{flight_id}", response_model=FlightOut)
def update_flight(flight_id: int, data: FlightUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(flight, key, value)
    db.commit()
    db.refresh(flight)
    return _flight_to_out(flight)


@router.post("/bulk-update")
def bulk_update_flights(data: FlightBulkUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
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
    db.commit()
    return {"ok": True, "updated": len(flights)}


@router.delete("/{flight_id}")
def delete_flight(flight_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    db.delete(flight)
    db.commit()
    return {"ok": True}


@router.get("/purposes/list", response_model=list[FlightPurposeOut])
def list_purposes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [FlightPurposeOut.model_validate(p) for p in db.query(FlightPurpose).order_by(FlightPurpose.sort_order, FlightPurpose.name).all()]


@router.post("/purposes", response_model=FlightPurposeOut)
def create_purpose(data: FlightPurposeCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.query(FlightPurpose).filter(FlightPurpose.name == data.name).first():
        raise HTTPException(status_code=400, detail="Purpose already exists")
    purpose = FlightPurpose(**data.model_dump())
    db.add(purpose)
    db.commit()
    db.refresh(purpose)
    return FlightPurposeOut.model_validate(purpose)


@router.delete("/purposes/{purpose_id}")
def delete_purpose(purpose_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    purpose = db.query(FlightPurpose).filter(FlightPurpose.id == purpose_id).first()
    if not purpose:
        raise HTTPException(status_code=404, detail="Purpose not found")
    db.delete(purpose)
    db.commit()
    return {"ok": True}
