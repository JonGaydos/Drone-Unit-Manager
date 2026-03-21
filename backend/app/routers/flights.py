from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.flight import Flight, FlightPurpose
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.user import User
from app.routers.auth import get_current_user, require_admin
from app.schemas.flight import (
    FlightCreate, FlightUpdate, FlightOut,
    FlightPurposeCreate, FlightPurposeOut,
    FlightBulkUpdate,
)

router = APIRouter(prefix="/api/flights", tags=["flights"])


def _flight_to_out(flight: Flight, db: Session) -> FlightOut:
    out = FlightOut.model_validate(flight)
    if flight.pilot_id:
        pilot = db.query(Pilot).filter(Pilot.id == flight.pilot_id).first()
        if pilot:
            out.pilot_name = pilot.full_name
    if flight.vehicle_id:
        vehicle = db.query(Vehicle).filter(Vehicle.id == flight.vehicle_id).first()
        if vehicle:
            out.vehicle_name = f"{vehicle.manufacturer} {vehicle.model}" + (f" ({vehicle.nickname})" if vehicle.nickname else "")
    return out


@router.get("", response_model=list[FlightOut])
def list_flights(
    pilot_id: int | None = None,
    vehicle_id: int | None = None,
    purpose: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    review_status: str | None = None,
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Flight)
    if pilot_id:
        q = q.filter(Flight.pilot_id == pilot_id)
    if vehicle_id:
        q = q.filter(Flight.vehicle_id == vehicle_id)
    if purpose:
        q = q.filter(Flight.purpose == purpose)
    if date_from:
        q = q.filter(Flight.date >= date_from)
    if date_to:
        q = q.filter(Flight.date <= date_to)
    if review_status:
        q = q.filter(Flight.review_status == review_status)
    flights = q.order_by(Flight.date.desc(), Flight.takeoff_time.desc()).offset(offset).limit(limit).all()
    return [_flight_to_out(f, db) for f in flights]


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
    flights = db.query(Flight).filter(
        Flight.review_status == "needs_review"
    ).order_by(Flight.date.desc(), Flight.takeoff_time.desc()).all()
    return [_flight_to_out(f, db) for f in flights]


@router.get("/{flight_id}", response_model=FlightOut)
def get_flight(flight_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    return _flight_to_out(flight, db)


@router.post("", response_model=FlightOut)
def create_flight(data: FlightCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    flight = Flight(**data.model_dump(), review_status="reviewed", pilot_confirmed=True)
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return _flight_to_out(flight, db)


@router.patch("/{flight_id}", response_model=FlightOut)
def update_flight(flight_id: int, data: FlightUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(flight, key, value)
    db.commit()
    db.refresh(flight)
    return _flight_to_out(flight, db)


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


# Flight purposes CRUD
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
