from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
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


@router.get("/analytics/pilot-performance/{pilot_id}")
def pilot_performance(pilot_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.incident import Incident
    from app.models.training_log_pilot import TrainingLogPilot
    from app.models.mission_log_pilot import MissionLogPilot

    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(404, "Pilot not found")

    flights = db.query(Flight).filter(Flight.pilot_id == pilot_id).all()
    total_flights = len(flights)
    total_hours = sum((f.duration_seconds or 0) for f in flights) / 3600
    avg_duration = (sum((f.duration_seconds or 0) for f in flights) / total_flights) if total_flights else 0

    # Flights by month (last 12 months)
    monthly = {}
    for f in flights:
        if f.date:
            key = f.date.strftime("%Y-%m") if hasattr(f.date, 'strftime') else str(f.date)[:7]
            monthly[key] = monthly.get(key, 0) + 1

    # Flights by purpose
    by_purpose = {}
    for f in flights:
        p = f.purpose or "Unassigned"
        by_purpose[p] = by_purpose.get(p, 0) + 1

    # Vehicles flown
    vehicles_flown = set()
    for f in flights:
        if f.vehicle_id:
            vehicles_flown.add(f.vehicle_id)

    # Incidents involving this pilot
    incidents = db.query(Incident).filter(Incident.pilot_id == pilot_id).count()

    # Training hours
    training_hours = db.query(func.coalesce(func.sum(TrainingLogPilot.hours), 0)).filter(
        TrainingLogPilot.pilot_id == pilot_id
    ).scalar()

    # Mission hours
    mission_hours = db.query(func.coalesce(func.sum(MissionLogPilot.hours), 0)).filter(
        MissionLogPilot.pilot_id == pilot_id
    ).scalar()

    # Max altitude and speed from telemetry
    max_alt = db.query(func.max(Flight.max_altitude_m)).filter(Flight.pilot_id == pilot_id).scalar()
    max_speed = db.query(func.max(Flight.max_speed_mps)).filter(Flight.pilot_id == pilot_id).scalar()

    return {
        "pilot_id": pilot_id,
        "pilot_name": f"{pilot.first_name} {pilot.last_name}",
        "total_flights": total_flights,
        "total_flight_hours": round(total_hours, 1),
        "avg_duration_min": round(avg_duration / 60, 1),
        "flights_by_month": [{"month": k, "count": v} for k, v in sorted(monthly.items())],
        "flights_by_purpose": [{"purpose": k, "count": v} for k, v in sorted(by_purpose.items(), key=lambda x: -x[1])],
        "vehicles_flown": len(vehicles_flown),
        "incidents": incidents,
        "training_hours": round(float(training_hours), 1),
        "mission_hours": round(float(mission_hours), 1),
        "max_altitude_m": round(float(max_alt), 1) if max_alt else None,
        "max_speed_mps": round(float(max_speed), 1) if max_speed else None,
    }


@router.get("/analytics/fleet-health")
def fleet_health(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.battery import Battery
    from app.models.maintenance_schedule import MaintenanceSchedule

    today = date.today()

    vehicles = db.query(Vehicle).filter(Vehicle.status == "active").all()
    batteries = db.query(Battery).all()

    # Vehicle utilization
    vehicle_stats = []
    for v in vehicles:
        flight_count = db.query(func.count(Flight.id)).filter(Flight.vehicle_id == v.id).scalar()
        total_hours = db.query(func.coalesce(func.sum(Flight.duration_seconds), 0)).filter(Flight.vehicle_id == v.id).scalar() / 3600
        last_flight = db.query(func.max(Flight.date)).filter(Flight.vehicle_id == v.id).scalar()
        overdue = db.query(func.count(MaintenanceSchedule.id)).filter(
            MaintenanceSchedule.entity_type == "vehicle",
            MaintenanceSchedule.entity_id == v.id,
            MaintenanceSchedule.is_active.is_(True),
            MaintenanceSchedule.next_due < today,
        ).scalar()
        vehicle_stats.append({
            "id": v.id,
            "name": v.nickname or f"{v.manufacturer} {v.model}",
            "serial": v.serial_number,
            "flights": flight_count,
            "hours": round(total_hours, 1),
            "last_flight": str(last_flight) if last_flight else None,
            "overdue_maintenance": overdue,
            "status": v.status,
        })

    # Battery health
    battery_stats = []
    for b in batteries:
        battery_stats.append({
            "id": b.id,
            "serial": b.serial_number,
            "nickname": b.nickname,
            "model": b.model,
            "cycle_count": b.cycle_count or 0,
            "health_pct": b.health_pct,
            "status": b.status,
        })

    # Overall stats
    avg_battery_health = sum(b.health_pct or 0 for b in batteries) / len(batteries) if batteries else 0
    total_overdue = sum(v["overdue_maintenance"] for v in vehicle_stats)

    return {
        "vehicles": vehicle_stats,
        "batteries": battery_stats,
        "summary": {
            "total_vehicles": len(vehicles),
            "total_batteries": len(batteries),
            "avg_battery_health": round(avg_battery_health, 1),
            "total_overdue_maintenance": total_overdue,
            "total_flight_hours": round(sum(v["hours"] for v in vehicle_stats), 1),
        }
    }


@router.get("/compliance")
def compliance_dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.vehicle_registration import VehicleRegistration
    from app.models.maintenance_schedule import MaintenanceSchedule
    from app.models.incident import Incident
    from app.models.flight_approval import FlightPlan

    today = date.today()
    soon = today + timedelta(days=90)

    # Certification compliance
    total_pilots = db.query(func.count(Pilot.id)).filter(Pilot.status == "active").scalar()

    # Count pilots with expired certs
    expired_certs = db.query(func.count(func.distinct(PilotCertification.pilot_id))).filter(
        PilotCertification.expiration_date < today,
        PilotCertification.status != "not_issued",
    ).scalar()

    # Count certs expiring within 90 days
    expiring_soon = db.query(PilotCertification).filter(
        PilotCertification.expiration_date.between(today, soon),
        PilotCertification.status != "not_issued",
    ).all()

    # FAA registration compliance
    total_vehicles = db.query(func.count(Vehicle.id)).filter(Vehicle.status == "active").scalar()
    expired_regs = db.query(func.count(func.distinct(VehicleRegistration.vehicle_id))).filter(
        VehicleRegistration.is_current.is_(True),
        VehicleRegistration.expiry_date < today,
    ).scalar()

    # Maintenance overdue
    overdue_maintenance = db.query(func.count(MaintenanceSchedule.id)).filter(
        MaintenanceSchedule.is_active.is_(True),
        MaintenanceSchedule.next_due < today,
    ).scalar()

    # Unreviewed flights
    unreviewed_flights = db.query(func.count(Flight.id)).filter(
        Flight.review_status == "needs_review"
    ).scalar()

    # Open incidents
    open_incidents = db.query(func.count(Incident.id)).filter(
        Incident.status.in_(["open", "investigating"])
    ).scalar()

    # Pending flight plans
    pending_plans = db.query(func.count(FlightPlan.id)).filter(
        FlightPlan.status == "pending"
    ).scalar()

    return {
        "total_pilots": total_pilots,
        "expired_certifications": expired_certs,
        "expiring_certifications": [{
            "pilot_id": c.pilot_id,
            "cert_type_id": c.certification_type_id,
            "expiration_date": c.expiration_date.isoformat() if c.expiration_date else None,
            "days_remaining": (c.expiration_date - today).days if c.expiration_date else None,
        } for c in expiring_soon],
        "total_vehicles": total_vehicles,
        "expired_registrations": expired_regs,
        "overdue_maintenance": overdue_maintenance,
        "unreviewed_flights": unreviewed_flights,
        "open_incidents": open_incidents,
        "pending_flight_plans": pending_plans,
        "compliance_score": _calc_compliance_score(
            total_pilots, expired_certs, total_vehicles, expired_regs, overdue_maintenance, open_incidents
        ),
    }


def _calc_compliance_score(pilots, exp_certs, vehicles, exp_regs, overdue, incidents):
    """Simple compliance score 0-100."""
    deductions = 0
    if pilots > 0:
        deductions += (exp_certs / pilots) * 30  # cert compliance worth 30 points
    if vehicles > 0:
        deductions += (exp_regs / vehicles) * 20  # reg compliance worth 20 points
    deductions += min(overdue * 5, 25)  # maintenance worth 25 points
    deductions += min(incidents * 10, 25)  # incidents worth 25 points
    return max(0, round(100 - deductions))


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
