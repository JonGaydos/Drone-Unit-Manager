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
