from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, extract, case
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.certification import PilotCertification, CertificationType
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.dashboard import (
    DashboardStats, FlightsByPurpose, FlightsByYear,
    FlightsByYearPurpose, FlightsByPilot, AvgDurationByYear,
    MonthlyFlights, VehicleHours, PilotHours,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    total_flights = db.query(func.count(Flight.id)).scalar()
    total_seconds = db.query(func.coalesce(func.sum(Flight.duration_seconds), 0)).scalar()
    active_pilots = db.query(func.count(Pilot.id)).filter(Pilot.status == "active").scalar()
    fleet_size = db.query(func.count(Vehicle.id)).filter(Vehicle.status == "active").scalar()
    needs_review = db.query(func.count(Flight.id)).filter(Flight.review_status == "needs_review").scalar()

    soon = date.today() + timedelta(days=90)
    expiring = db.query(func.count(PilotCertification.id)).filter(
        PilotCertification.expiration_date.isnot(None),
        PilotCertification.expiration_date <= soon,
        PilotCertification.status.in_(["active", "complete"]),
    ).scalar()

    return DashboardStats(
        total_flights=total_flights,
        total_flight_hours=total_seconds / 3600,
        active_pilots=active_pilots,
        fleet_size=fleet_size,
        flights_needing_review=needs_review,
        upcoming_cert_expirations=expiring,
    )


@router.get("/analytics/flights-by-purpose", response_model=list[FlightsByPurpose])
def flights_by_purpose(
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(
        func.coalesce(Flight.purpose, "Unknown").label("purpose"),
        func.count(Flight.id).label("count"),
    )
    if date_from:
        q = q.filter(Flight.date >= date_from)
    if date_to:
        q = q.filter(Flight.date <= date_to)
    rows = q.group_by("purpose").order_by(func.count(Flight.id).desc()).all()
    return [FlightsByPurpose(purpose=r.purpose, count=r.count) for r in rows]


@router.get("/analytics/flights-by-year", response_model=list[FlightsByYear])
def flights_by_year(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(
        extract("year", Flight.date).label("year"),
        func.count(Flight.id).label("count"),
    ).filter(Flight.date.isnot(None)).group_by("year").order_by("year").all()
    return [FlightsByYear(year=int(r.year), count=r.count) for r in rows]


@router.get("/analytics/flights-by-year-purpose", response_model=list[FlightsByYearPurpose])
def flights_by_year_purpose(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = db.query(
        extract("year", Flight.date).label("year"),
        func.coalesce(Flight.purpose, "Unknown").label("purpose"),
        func.count(Flight.id).label("count"),
    ).filter(Flight.date.isnot(None)).group_by("year", "purpose").order_by("year", "purpose").all()
    return [FlightsByYearPurpose(year=int(r.year), purpose=r.purpose, count=r.count) for r in rows]


@router.get("/analytics/flights-by-pilot", response_model=list[FlightsByPilot])
def flights_by_pilot(
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(
        Pilot.first_name,
        Pilot.last_name,
        func.count(Flight.id).label("count"),
    ).join(Pilot, Flight.pilot_id == Pilot.id)
    if date_from:
        q = q.filter(Flight.date >= date_from)
    if date_to:
        q = q.filter(Flight.date <= date_to)
    rows = q.group_by(Pilot.id).order_by(func.count(Flight.id).desc()).all()
    total = sum(r.count for r in rows)
    return [
        FlightsByPilot(
            pilot_name=f"{r.first_name} {r.last_name}",
            count=r.count,
            percentage=round(r.count / total * 100, 2) if total > 0 else 0,
        )
        for r in rows
    ]


@router.get("/analytics/avg-duration-by-year", response_model=list[AvgDurationByYear])
def avg_duration_by_year(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(
        extract("year", Flight.date).label("year"),
        func.avg(Flight.duration_seconds).label("avg_seconds"),
    ).filter(Flight.date.isnot(None), Flight.duration_seconds.isnot(None)).group_by("year").order_by("year").all()
    return [AvgDurationByYear(year=int(r.year), avg_seconds=float(r.avg_seconds)) for r in rows]


@router.get("/analytics/monthly-flights", response_model=list[MonthlyFlights])
def monthly_flights(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(
        extract("year", Flight.date).label("year"),
        extract("month", Flight.date).label("month"),
        func.count(Flight.id).label("count"),
    ).filter(Flight.date.isnot(None)).group_by("year", "month").order_by("year", "month").all()
    return [MonthlyFlights(year=int(r.year), month=int(r.month), count=r.count) for r in rows]


@router.get("/analytics/vehicle-hours", response_model=list[VehicleHours])
def vehicle_hours(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(
        Vehicle.manufacturer,
        Vehicle.model,
        Vehicle.nickname,
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("total_seconds"),
    ).join(Vehicle, Flight.vehicle_id == Vehicle.id).group_by(Vehicle.id).order_by(
        func.sum(Flight.duration_seconds).desc()
    ).all()
    return [
        VehicleHours(
            vehicle_name=f"{r.manufacturer} {r.model}" + (f" ({r.nickname})" if r.nickname else ""),
            hours=r.total_seconds / 3600,
        )
        for r in rows
    ]


@router.get("/analytics/pilot-hours", response_model=list[PilotHours])
def pilot_hours(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(
        Pilot.first_name,
        Pilot.last_name,
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("total_seconds"),
        func.count(Flight.id).label("flight_count"),
    ).join(Pilot, Flight.pilot_id == Pilot.id).group_by(Pilot.id).order_by(
        func.sum(Flight.duration_seconds).desc()
    ).all()
    return [
        PilotHours(
            pilot_name=f"{r.first_name} {r.last_name}",
            hours=r.total_seconds / 3600,
            flight_count=r.flight_count,
        )
        for r in rows
    ]


@router.get("/upcoming-expirations")
def upcoming_expirations(days: int = 90, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cutoff = date.today() + timedelta(days=days)
    rows = db.query(
        PilotCertification, Pilot, CertificationType,
    ).join(Pilot, PilotCertification.pilot_id == Pilot.id
    ).join(CertificationType, PilotCertification.certification_type_id == CertificationType.id
    ).filter(
        PilotCertification.expiration_date.isnot(None),
        PilotCertification.expiration_date <= cutoff,
        PilotCertification.status.in_(["active", "complete"]),
    ).order_by(PilotCertification.expiration_date).all()

    result = []
    for pc, pilot, ct in rows:
        days_remaining = (pc.expiration_date - date.today()).days
        result.append({
            "pilot_name": f"{pilot.first_name} {pilot.last_name}",
            "pilot_id": pilot.id,
            "cert_name": ct.name,
            "expiration_date": str(pc.expiration_date),
            "days_remaining": days_remaining,
            "status": pc.status,
        })
    return result
