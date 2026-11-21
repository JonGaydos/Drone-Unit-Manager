from datetime import date, timedelta

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, extract
from sqlalchemy.orm import joinedload

from app.deps import DBSession, CurrentUser
from app.responses import responses
from app.routers.auth import require_permission
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.user import User
from app.services.flight_scope import counted_flight_clause
from app.services.local_time import local_today
from app.services.permissions import can
from app.services.requirement_results import requirements_score
from app.services.requirement_standing import pilots_not_in_standing, refresh_requirements
from app.models.vehicle import Vehicle
from app.models.certification import PilotCertification, CertificationType
from app.models.maintenance import MaintenanceRecord
from app.models.maintenance_schedule import MaintenanceSchedule
from app.models.operating_authority import AUTHORITY_SCORE_CAP
from app.schemas.dashboard import (
    DashboardStats, FlightsByPurpose, FlightsByYear,
    FlightsByYearPurpose, FlightsByPilot, AvgDurationByYear,
    MonthlyFlights, VehicleHours, PilotHours, ScorePart,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

FlightsUser = Annotated[User, Depends(require_permission("flights.view"))]
FleetUser = Annotated[User, Depends(require_permission("fleet.view"))]
MaintenanceUser = Annotated[User, Depends(require_permission("maintenance.view"))]
CertificationsUser = Annotated[User, Depends(require_permission("certifications.view"))]


# What the dashboard tile shows at once. Five is enough to cover everything
# overdue on a unit this size without the tile becoming the page.
MAINTENANCE_DUE_LIMIT = 5

# Points each part of the compliance score is worth.
CERTIFICATION_POINTS = 25
REGISTRATION_POINTS = 20
REQUIREMENT_POINTS = 15


def _due_items(db):
    """Everything with a due date, from both places maintenance is tracked.

    Schedules are the recurring plan; records are the log of work performed,
    each carrying its own next-due date. Both matter: a schedule nobody has
    completed yet has no record behind it (which is how an overdue task went
    missing from this tile), and an ad-hoc record with a due date has no
    schedule.

    Completing a schedule auto-creates a record carrying the schedule's new due
    date, so every recurring task that has been done once appears in both. There
    is no foreign key between the tables, so they are matched on the equipment
    and the date, and the schedule wins: it is the thing that recurs, and it
    carries the name a person recognises.
    """
    items = []
    seen = set()
    schedules = db.query(MaintenanceSchedule).filter(
        MaintenanceSchedule.is_active.is_(True),
        MaintenanceSchedule.next_due.isnot(None)).all()
    for s in schedules:
        seen.add((s.entity_type, s.entity_id, s.next_due))
        items.append({
            "source": "schedule",
            "id": s.id,
            "name": s.name,
            "entity_type": s.entity_type,
            "entity_id": s.entity_id,
            "due_date": s.next_due,
        })

    from app.services.maintenance_due import superseded_record_ids
    superseded = superseded_record_ids(db)
    records = db.query(MaintenanceRecord).filter(
        MaintenanceRecord.next_due_date.isnot(None)).all()
    for r in records:
        if r.id in superseded or (r.entity_type, r.entity_id, r.next_due_date) in seen:
            continue
        items.append({
            "source": "record",
            "id": r.id,
            "name": r.description or r.maintenance_type,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "due_date": r.next_due_date,
        })
    return items


@router.get("/maintenance-due", responses=responses(401))
def maintenance_due(db: DBSession, user: MaintenanceUser, limit: int = MAINTENANCE_DUE_LIMIT):
    """Maintenance needing attention, most overdue first.

    Sorted by days remaining ascending, so a negative number (overdue) sorts
    above anything still in the future. The tile that shows this used to list
    records only, which meant a schedule nobody had completed yet -- the case
    most likely to be overdue -- never appeared on it.
    """
    today = date.today()
    items = _due_items(db)
    for item in items:
        item["days_remaining"] = (item["due_date"] - today).days
        item["due_date"] = item["due_date"].isoformat()
    items.sort(key=lambda i: (i["days_remaining"], i["name"] or ""))
    return items[:max(limit, 0)]


@router.get("/stats", response_model=DashboardStats, responses=responses(401))
def get_stats(db: DBSession, user: CurrentUser):
    total_flights = db.query(func.count(Flight.id)).filter(counted_flight_clause()).scalar()
    total_seconds = db.query(func.coalesce(func.sum(Flight.duration_seconds), 0)).filter(counted_flight_clause()).scalar()
    active_pilots = db.query(func.count(Pilot.id)).filter(Pilot.status == "active").scalar()
    fleet_size = db.query(func.count(Vehicle.id)).filter(Vehicle.status == "active").scalar()
    needs_review = db.query(func.count(Flight.id)).filter(
        counted_flight_clause(), Flight.review_status == "needs_review").scalar()

    today_date = date.today()
    soon = today_date + timedelta(days=90)
    active_pids = db.query(Pilot.id).filter(Pilot.status == "active").subquery()
    expiring = db.query(func.count(PilotCertification.id)).filter(
        PilotCertification.expiration_date.isnot(None),
        PilotCertification.expiration_date.between(today_date, soon),
        PilotCertification.status.notin_(["not_issued", "renewed"]),
        PilotCertification.pilot_id.in_(active_pids),
    ).scalar()

    return DashboardStats(
        total_flights=total_flights,
        total_flight_hours=total_seconds / 3600,
        active_pilots=active_pilots,
        fleet_size=fleet_size,
        flights_needing_review=needs_review,
        upcoming_cert_expirations=expiring,
    )


@router.get("/trends", responses=responses(401))
def get_trends(db: DBSession, user: CurrentUser):
    """Period-over-period deltas for the bento dashboard hero stats.
    Compares the last 30 days against the prior 30 days."""
    today_date = date.today()
    last_30_start = today_date - timedelta(days=30)
    prior_30_start = today_date - timedelta(days=60)

    def _period(start, end):
        flights_q = db.query(
            func.count(Flight.id),
            func.coalesce(func.sum(Flight.duration_seconds), 0),
        ).filter(counted_flight_clause(), Flight.date >= start, Flight.date < end)
        f_count, f_secs = flights_q.one()
        unique_pilots = db.query(func.count(func.distinct(Flight.pilot_id))).filter(
            counted_flight_clause(), Flight.date >= start, Flight.date < end,
        ).scalar() or 0
        unique_vehicles = db.query(func.count(func.distinct(Flight.vehicle_id))).filter(
            counted_flight_clause(), Flight.date >= start, Flight.date < end,
        ).scalar() or 0
        return {
            "flights": f_count or 0,
            "hours": round((f_secs or 0) / 3600, 1),
            "active_pilots": unique_pilots,
            "active_vehicles": unique_vehicles,
        }

    current = _period(last_30_start, today_date + timedelta(days=1))
    prior = _period(prior_30_start, last_30_start)

    def _delta(a, b):
        if b == 0:
            return None  # avoid divide-by-zero / infinity arrows
        return round(((a - b) / b) * 100, 1)

    return {
        "range_days": 30,
        "current": current,
        "prior": prior,
        "deltas_pct": {
            k: _delta(current[k], prior[k]) for k in current
        },
    }


@router.get("/activity-by-month", responses=responses(401))
def activity_by_month(db: DBSession, user: FlightsUser, months: int = 12):
    """Flight count + hours grouped by month for the activity chart on the
    bento dashboard. Default last 12 months."""
    today_date = date.today()
    # Approximate month-window — uses date math, not calendar months, but
    # we group by extract(year/month) so calendar bins still come out right.
    start = today_date - timedelta(days=months * 31)
    rows = db.query(
        extract("year", Flight.date).label("y"),
        extract("month", Flight.date).label("m"),
        func.count(Flight.id).label("flights"),
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("secs"),
    ).filter(counted_flight_clause(), Flight.date >= start).group_by("y", "m").order_by("y", "m").all()
    return [
        {
            "year": int(r.y),
            "month": int(r.m),
            "label": f"{int(r.y)}-{int(r.m):02d}",
            "flights": r.flights or 0,
            "hours": round((r.secs or 0) / 3600, 1),
        }
        for r in rows
    ]


@router.get("/top-pilots-30d", responses=responses(401))
def top_pilots_30d(db: DBSession, user: FlightsUser, limit: int = 5):
    """Top N pilots by flight hours in the last 30 days. For the bento
    leaderboard tile."""
    cutoff = date.today() - timedelta(days=30)
    rows = db.query(
        Pilot.id, Pilot.first_name, Pilot.last_name,
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("secs"),
        func.count(Flight.id).label("flights"),
    ).join(Flight, Flight.pilot_id == Pilot.id).filter(
        counted_flight_clause(), Flight.date >= cutoff, Pilot.status == "active",
    ).group_by(Pilot.id, Pilot.first_name, Pilot.last_name
    ).order_by(func.sum(Flight.duration_seconds).desc()).limit(limit).all()
    return [
        {
            "pilot_id": r.id,
            "pilot_name": f"{r.first_name or ''} {r.last_name or ''}".strip(),
            "hours": round((r.secs or 0) / 3600, 1),
            "flights": r.flights or 0,
        }
        for r in rows
    ]


@router.get("/top-vehicles-30d", responses=responses(401))
def top_vehicles_30d(db: DBSession, user: FleetUser, limit: int = 5):
    """Top N vehicles by flight hours in the last 30 days."""
    cutoff = date.today() - timedelta(days=30)
    rows = db.query(
        Vehicle.id, Vehicle.manufacturer, Vehicle.model, Vehicle.nickname, Vehicle.serial_number,
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("secs"),
        func.count(Flight.id).label("flights"),
    ).join(Flight, Flight.vehicle_id == Vehicle.id).filter(
        counted_flight_clause(), Flight.date >= cutoff,
    ).group_by(Vehicle.id, Vehicle.manufacturer, Vehicle.model, Vehicle.nickname, Vehicle.serial_number
    ).order_by(func.sum(Flight.duration_seconds).desc()).limit(limit).all()
    return [
        {
            "vehicle_id": r.id,
            "label": (r.nickname or f"{r.manufacturer or ''} {r.model or ''}".strip() or r.serial_number),
            "hours": round((r.secs or 0) / 3600, 1),
            "flights": r.flights or 0,
        }
        for r in rows
    ]


@router.get("/analytics/flights-by-purpose", response_model=list[FlightsByPurpose])
def flights_by_purpose(
    db: DBSession,
    user: FlightsUser,
    date_from: date | None = None,
    date_to: date | None = None):
    # Group by the expression, not by the string "purpose": grouping by the
    # name resolves to the raw column, so NULL and "" would split into two
    # rows that both read "Unspecified".
    purpose = func.coalesce(func.nullif(Flight.purpose, ""), "Unspecified")
    q = db.query(purpose.label("purpose"), func.count(Flight.id).label("count")
                 ).filter(counted_flight_clause())
    if date_from:
        q = q.filter(Flight.date >= date_from)
    if date_to:
        q = q.filter(Flight.date <= date_to)
    rows = q.group_by(purpose).order_by(func.count(Flight.id).desc()).all()
    return [FlightsByPurpose(purpose=r.purpose, count=r.count) for r in rows]


@router.get("/analytics/flights-by-year", response_model=list[FlightsByYear], responses=responses(401))
def flights_by_year(db: DBSession, user: FlightsUser):
    rows = db.query(
        extract("year", Flight.date).label("year"),
        func.count(Flight.id).label("count"),
    ).filter(counted_flight_clause(), Flight.date.isnot(None)).group_by("year").order_by("year").all()
    return [FlightsByYear(year=int(r.year), count=r.count) for r in rows]


@router.get("/analytics/flights-by-year-purpose", response_model=list[FlightsByYearPurpose])
def flights_by_year_purpose(
    db: DBSession,
    user: FlightsUser,
):
    purpose = func.coalesce(func.nullif(Flight.purpose, ""), "Unspecified")
    year = extract("year", Flight.date)
    rows = db.query(
        year.label("year"), purpose.label("purpose"), func.count(Flight.id).label("count"),
    ).filter(counted_flight_clause(), Flight.date.isnot(None)).group_by(year, purpose).order_by(year, purpose).all()
    return [FlightsByYearPurpose(year=int(r.year), purpose=r.purpose, count=r.count) for r in rows]


@router.get("/analytics/flights-by-pilot", response_model=list[FlightsByPilot])
def flights_by_pilot(
    db: DBSession,
    user: FlightsUser,
    date_from: date | None = None,
    date_to: date | None = None):
    q = db.query(
        Pilot.id,
        Pilot.first_name,
        Pilot.last_name,
        func.count(Flight.id).label("count"),
    ).join(Pilot, Flight.pilot_id == Pilot.id).filter(counted_flight_clause())
    if date_from:
        q = q.filter(Flight.date >= date_from)
    if date_to:
        q = q.filter(Flight.date <= date_to)
    rows = q.group_by(Pilot.id).order_by(func.count(Flight.id).desc()).all()
    total = sum(r.count for r in rows)
    return [
        FlightsByPilot(
            pilot_id=r.id,
            pilot_name=f"{r.first_name} {r.last_name}",
            count=r.count,
            percentage=round(r.count / total * 100, 2) if total > 0 else 0,
        )
        for r in rows
    ]


@router.get("/analytics/avg-duration-by-year", response_model=list[AvgDurationByYear], responses=responses(401))
def avg_duration_by_year(db: DBSession, user: FlightsUser):
    rows = db.query(
        extract("year", Flight.date).label("year"),
        func.avg(Flight.duration_seconds).label("avg_seconds"),
    ).filter(counted_flight_clause(), Flight.date.isnot(None),
             Flight.duration_seconds.isnot(None)).group_by("year").order_by("year").all()
    return [AvgDurationByYear(year=int(r.year), avg_seconds=float(r.avg_seconds)) for r in rows]


@router.get("/analytics/monthly-flights", response_model=list[MonthlyFlights], responses=responses(401))
def monthly_flights(db: DBSession, user: FlightsUser):
    rows = db.query(
        extract("year", Flight.date).label("year"),
        extract("month", Flight.date).label("month"),
        func.count(Flight.id).label("count"),
    ).filter(counted_flight_clause(), Flight.date.isnot(None)).group_by("year", "month").order_by("year", "month").all()
    return [MonthlyFlights(year=int(r.year), month=int(r.month), count=r.count) for r in rows]


@router.get("/analytics/vehicle-hours", response_model=list[VehicleHours], responses=responses(401))
def vehicle_hours(db: DBSession, user: FleetUser):
    rows = db.query(
        Vehicle.id,
        Vehicle.manufacturer,
        Vehicle.model,
        Vehicle.nickname,
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("total_seconds"),
    ).join(Vehicle, Flight.vehicle_id == Vehicle.id).filter(counted_flight_clause()).group_by(Vehicle.id).order_by(
        func.sum(Flight.duration_seconds).desc()
    ).all()
    return [
        VehicleHours(
            vehicle_id=r.id,
            vehicle_name=f"{r.manufacturer} {r.model}" + (f" ({r.nickname})" if r.nickname else ""),
            hours=r.total_seconds / 3600,
        )
        for r in rows
    ]


@router.get("/analytics/pilot-hours", response_model=list[PilotHours], responses=responses(401))
def pilot_hours(db: DBSession, user: FlightsUser):
    rows = db.query(
        Pilot.id,
        Pilot.first_name,
        Pilot.last_name,
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("total_seconds"),
        func.count(Flight.id).label("flight_count"),
    ).join(Pilot, Flight.pilot_id == Pilot.id).filter(counted_flight_clause()).group_by(Pilot.id).order_by(
        func.sum(Flight.duration_seconds).desc()
    ).all()
    return [
        PilotHours(
            pilot_id=r.id,
            pilot_name=f"{r.first_name} {r.last_name}",
            hours=r.total_seconds / 3600,
            flight_count=r.flight_count,
        )
        for r in rows
    ]


@router.get("/analytics/pilot-performance/{pilot_id}", responses=responses(401, 404))
def pilot_performance(pilot_id: int, db: DBSession, user: FlightsUser):
    from app.models.incident import Incident
    from app.models.training_log_pilot import TrainingLogPilot
    from app.models.mission_log_pilot import MissionLogPilot

    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(404, "Pilot not found")

    # Aggregate in SQL rather than materializing every flight row in Python.
    totals = db.query(
        func.count(Flight.id),
        func.coalesce(func.sum(Flight.duration_seconds), 0),
        func.count(Flight.vehicle_id.distinct()),
    ).filter(counted_flight_clause(), Flight.pilot_id == pilot_id).one()
    total_flights = totals[0] or 0
    total_seconds = totals[1] or 0
    vehicles_flown = totals[2] or 0
    total_hours = total_seconds / 3600
    avg_duration = (total_seconds / total_flights) if total_flights else 0

    # Flights by month
    month_rows = db.query(
        extract("year", Flight.date).label("year"),
        extract("month", Flight.date).label("month"),
        func.count(Flight.id).label("count"),
    ).filter(counted_flight_clause(), Flight.pilot_id == pilot_id,
             Flight.date.isnot(None)).group_by(
        "year", "month"
    ).order_by("year", "month").all()
    flights_by_month = [
        {"month": f"{int(r.year):04d}-{int(r.month):02d}", "count": r.count}
        for r in month_rows
    ]

    # Flights by purpose (NULL and "" both fold into "Unspecified",
    # kept distinct from the real, selectable "Unknown" purpose)
    purpose = func.coalesce(func.nullif(Flight.purpose, ""), "Unspecified")
    purpose_rows = db.query(
        purpose.label("purpose"), func.count(Flight.id).label("count"),
    ).filter(counted_flight_clause(), Flight.pilot_id == pilot_id).group_by(purpose).order_by(
        func.count(Flight.id).desc()
    ).all()
    flights_by_purpose = [{"purpose": r.purpose, "count": r.count} for r in purpose_rows]

    # Incidents involving this pilot, for users who may view incidents
    incidents = None
    if can(db, user, "incidents.view"):
        incidents = db.query(Incident).filter(Incident.pilot_id == pilot_id).count()

    # Training and mission hours, for users who may view the logs
    training_hours = mission_hours = None
    if can(db, user, "logs.view"):
        training_hours = round(float(db.query(func.coalesce(func.sum(TrainingLogPilot.hours), 0)).filter(
            TrainingLogPilot.pilot_id == pilot_id
        ).scalar()), 1)
        mission_hours = round(float(db.query(func.coalesce(func.sum(MissionLogPilot.hours), 0)).filter(
            MissionLogPilot.pilot_id == pilot_id
        ).scalar()), 1)

    # Max altitude and speed from telemetry
    max_alt = db.query(func.max(Flight.max_altitude_m)).filter(
        counted_flight_clause(), Flight.pilot_id == pilot_id).scalar()
    max_speed = db.query(func.max(Flight.max_speed_mps)).filter(
        counted_flight_clause(), Flight.pilot_id == pilot_id).scalar()

    return {
        "pilot_id": pilot_id,
        "pilot_name": f"{pilot.first_name} {pilot.last_name}",
        "total_flights": total_flights,
        "total_flight_hours": round(total_hours, 1),
        "avg_duration_min": round(avg_duration / 60, 1),
        "flights_by_month": flights_by_month,
        "flights_by_purpose": flights_by_purpose,
        "vehicles_flown": vehicles_flown,
        "incidents": incidents,
        "training_hours": training_hours,
        "mission_hours": mission_hours,
        "max_altitude_m": round(float(max_alt), 1) if max_alt else None,
        "max_speed_mps": round(float(max_speed), 1) if max_speed else None,
    }


@router.get("/analytics/fleet-health", responses=responses(401))
def fleet_health(db: DBSession, user: FleetUser):
    from app.models.battery import Battery
    from app.models.maintenance_schedule import MaintenanceSchedule
    from app.services.equipment_lifecycle import DECOMMISSIONED_STATUSES

    today = date.today()

    # In service = not retired or damaged: a vehicle grounded for maintenance
    # still belongs to the fleet, as on the Fleet page.
    vehicles = db.query(Vehicle).filter(Vehicle.status.notin_(DECOMMISSIONED_STATUSES)).all()
    batteries = db.query(Battery).filter(Battery.status.notin_(DECOMMISSIONED_STATUSES)).all()

    # Pre-aggregate per-vehicle flight stats and overdue maintenance in two
    # grouped queries, instead of 4 queries per vehicle.
    flight_rows = db.query(
        Flight.vehicle_id.label("vid"),
        func.count(Flight.id).label("flights"),
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("secs"),
        func.max(Flight.date).label("last_flight"),
    ).filter(counted_flight_clause(), Flight.vehicle_id.isnot(None)).group_by(Flight.vehicle_id).all()
    flight_by_vehicle = {r.vid: r for r in flight_rows}

    overdue_rows = db.query(
        MaintenanceSchedule.entity_id.label("vid"),
        func.count(MaintenanceSchedule.id).label("overdue"),
    ).filter(
        MaintenanceSchedule.entity_type == "vehicle",
        MaintenanceSchedule.is_active.is_(True),
        MaintenanceSchedule.next_due < today,
    ).group_by(MaintenanceSchedule.entity_id).all()
    overdue_by_vehicle = {r.vid: r.overdue for r in overdue_rows}

    # Vehicle utilization
    vehicle_stats = []
    for v in vehicles:
        fr = flight_by_vehicle.get(v.id)
        total_hours = (fr.secs if fr else 0) / 3600
        vehicle_stats.append({
            "id": v.id,
            "name": v.nickname or f"{v.manufacturer} {v.model}",
            "serial": v.serial_number,
            "flights": fr.flights if fr else 0,
            "hours": round(total_hours, 1),
            "last_flight": str(fr.last_flight) if fr and fr.last_flight else None,
            "overdue_maintenance": overdue_by_vehicle.get(v.id, 0),
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
    # Only batteries with a reading: one never measured is unknown, not 0%.
    readings = [b.health_pct for b in batteries if b.health_pct is not None]
    avg_battery_health = round(sum(readings) / len(readings), 1) if readings else None
    # Every overdue schedule, not only vehicle ones: an overdue battery or dock
    # task is fleet maintenance too (the compliance dashboard counts the same).
    total_overdue = db.query(func.count(MaintenanceSchedule.id)).filter(
        MaintenanceSchedule.is_active.is_(True),
        MaintenanceSchedule.next_due < today,
    ).scalar()

    # The unit total stays; the count against a named vehicle follows maintenance.view.
    if not can(db, user, "maintenance.view"):
        vehicle_stats = [{**v, "overdue_maintenance": None} for v in vehicle_stats]

    return {
        "vehicles": vehicle_stats,
        "batteries": battery_stats,
        "summary": {
            "total_vehicles": len(vehicles),
            "total_batteries": len(batteries),
            "avg_battery_health": avg_battery_health,
            "total_overdue_maintenance": total_overdue,
            "total_flight_hours": round(sum(v["hours"] for v in vehicle_stats), 1),
        }
    }


def _authority_summary(db, today):
    """Score the org's active operating authorities. Returns (authorities,
    expired, expiring, grounding_expired, advisory_expired, score_cap_reason).
    Superseded and not-applicable records stay on file but are not scored."""
    from app.models.operating_authority import OperatingAuthority, authority_status
    authorities = db.query(OperatingAuthority).filter(
        OperatingAuthority.record_status == "active"
    ).all()
    expired = []
    expiring = []
    for a in authorities:
        state = authority_status(a, today)
        if state == "expired":
            expired.append(a)
        elif state == "expiring":
            expiring.append(a)
    # An expired authority the unit depends on caps the score outright; one that
    # only restricts a kind of operation takes an ordinary deduction instead.
    grounding_expired = [a for a in expired if a.grounds_unit]
    advisory_expired = [a for a in expired if not a.grounds_unit]
    score_cap_reason = None
    if grounding_expired:
        score_cap_reason = (
            f"Capped at {AUTHORITY_SCORE_CAP}: "
            f"{len(grounding_expired)} operating "
            f"{'authority' if len(grounding_expired) == 1 else 'authorities'} expired"
        )
    return authorities, expired, expiring, grounding_expired, advisory_expired, score_cap_reason


def _certification_counts(db, today, soon):
    """(Active pilots, those with an expired certification, certifications
    expiring within 90 days), renewed certifications and inactive pilots aside."""
    total_pilots = db.query(func.count(Pilot.id)).filter(Pilot.status == "active").scalar()

    # IDs of active pilots only
    active_pilot_ids = db.query(Pilot.id).filter(Pilot.status == "active").subquery()

    # Count pilots with expired certs (exclude renewed and inactive pilots)
    expired_certs = db.query(func.count(func.distinct(PilotCertification.pilot_id))).filter(
        PilotCertification.expiration_date < today,
        PilotCertification.status.notin_(["not_issued", "renewed"]),
        PilotCertification.pilot_id.in_(active_pilot_ids),
    ).scalar()

    # Count certs expiring within 90 days (exclude renewed and inactive pilots)
    expiring_soon = db.query(PilotCertification).options(
        joinedload(PilotCertification.pilot), joinedload(PilotCertification.certification_type),
    ).filter(
        PilotCertification.expiration_date.between(today, soon),
        PilotCertification.status.notin_(["not_issued", "renewed"]),
        PilotCertification.pilot_id.in_(active_pilot_ids),
    ).all()
    return total_pilots, expired_certs, expiring_soon


def _registration_counts(db, today):
    """(Active vehicles, those with an expired current registration)."""
    from app.models.vehicle_registration import VehicleRegistration

    # FAA registration compliance: active fleet only, so expired registrations
    # kept on retired/sold vehicles don't count against compliance.
    total_vehicles = db.query(func.count(Vehicle.id)).filter(Vehicle.status == "active").scalar()
    active_vehicle_ids = db.query(Vehicle.id).filter(Vehicle.status == "active").subquery()
    expired_regs = db.query(func.count(func.distinct(VehicleRegistration.vehicle_id))).filter(
        VehicleRegistration.is_current.is_(True),
        VehicleRegistration.expiry_date < today,
        VehicleRegistration.vehicle_id.in_(active_vehicle_ids),
    ).scalar()
    return total_vehicles, expired_regs


def _open_item_counts(db, today) -> dict:
    """Overdue maintenance, unreviewed flights, open incidents and pending flight plans."""
    from app.models.maintenance_schedule import MaintenanceSchedule
    from app.models.incident import Incident
    from app.models.flight_approval import FlightPlan

    return {
        "overdue_maintenance": db.query(func.count(MaintenanceSchedule.id)).filter(
            MaintenanceSchedule.is_active.is_(True),
            MaintenanceSchedule.next_due < today,
        ).scalar(),
        "unreviewed_flights": db.query(func.count(Flight.id)).filter(
            Flight.review_status == "needs_review"
        ).scalar(),
        "open_incidents": db.query(func.count(Incident.id)).filter(
            Incident.status.in_(["open", "investigating"])
        ).scalar(),
        "pending_flight_plans": db.query(func.count(FlightPlan.id)).filter(
            FlightPlan.status == "pending"
        ).scalar(),
    }


@router.get("/compliance", responses=responses(401))
def compliance_dashboard(db: DBSession, user: CurrentUser):
    # First, as saving due periods and lapses commits (or rolls back a race).
    out_of_standing, requirements_active, requirements_figure = _requirement_standing(db)

    today = date.today()
    soon = today + timedelta(days=90)

    total_pilots, expired_certs, expiring_soon = _certification_counts(db, today, soon)
    total_vehicles, expired_regs = _registration_counts(db, today)
    open_items = _open_item_counts(db, today)

    # Operating authority (org-level COAs / Part 107 waivers).
    authorities, expired_authorities, expiring_authorities, _, advisory_expired, score_cap_reason = _authority_summary(db, today)

    # The score and counts are unit-wide. The lists name records, so they follow
    # their features' view permissions.
    visible_certifications = []
    if can(db, user, "certifications.view"):
        visible_certifications = [_certification_brief(c, today) for c in expiring_soon]
    visible_expired_authorities = []
    visible_expiring_authorities = []
    if can(db, user, "authority.view"):
        visible_expired_authorities = [_authority_brief(a, today) for a in expired_authorities]
        visible_expiring_authorities = [_authority_brief(a, today) for a in expiring_authorities]

    return {
        "total_pilots": total_pilots,
        "expired_certifications": expired_certs,
        "expiring_certifications": visible_certifications,
        "total_vehicles": total_vehicles,
        "expired_registrations": expired_regs,
        **open_items,
        "operating_authorities_tracked": len(authorities),
        "expired_authorities": visible_expired_authorities,
        "expiring_authorities": visible_expiring_authorities,
        "score_cap_reason": score_cap_reason,
        "pilots_out_of_standing": out_of_standing,
        "requirements_active": requirements_active,
        "requirements_score": requirements_figure,
        **_score_payload({
            "pilots": total_pilots, "exp_certs": expired_certs, "vehicles": total_vehicles,
            "exp_regs": expired_regs, "overdue": open_items["overdue_maintenance"],
            "incidents": open_items["open_incidents"],
            "pilots_out_of_standing": out_of_standing, "requirements_active": requirements_active,
            "authorities_expiring": len(expiring_authorities),
            "authorities_expired_advisory": len(advisory_expired),
        }, score_cap_reason),
    }


def _requirement_standing(db) -> tuple[int, int, float | None]:
    """(Active pilots out of standing on flight requirements, active
    requirements, the 12-month requirements score), after saving due periods
    and recording lapses so a page load sees today's standing."""
    today = local_today(db)
    refresh_requirements(db, today)
    out_of_standing, requirements_active = pilots_not_in_standing(db, today)
    return len(out_of_standing), requirements_active, requirements_score(db, today)


def _certification_brief(c, today) -> dict:
    """Compact expiring-certification payload for the compliance dashboard."""
    return {
        "pilot_id": c.pilot_id,
        "pilot_name": c.pilot.full_name if c.pilot else None,
        "cert_type_id": c.certification_type_id,
        "cert_type_name": c.certification_type.name if c.certification_type else None,
        "expiration_date": c.expiration_date.isoformat() if c.expiration_date else None,
        "days_remaining": (c.expiration_date - today).days if c.expiration_date else None,
    }


def _authority_brief(a, today) -> dict:
    """Compact operating-authority payload for the compliance dashboard."""
    return {
        "id": a.id,
        "authority_type": a.authority_type,
        "identifier": a.identifier,
        "title": a.title,
        "expiry_date": a.expiry_date.isoformat() if a.expiry_date else None,
        "days_remaining": (a.expiry_date - today).days if a.expiry_date else None,
        "grounds_unit": a.grounds_unit,
    }


def _counted(count: int, noun: str) -> str:
    """``count`` and ``noun``, made plural with an s unless there is one."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _share(count: int, total: int, points: int) -> float:
    """``points`` scaled by the share ``count / total``; nothing without a total."""
    return (count / total) * points if total > 0 else 0


def _part(area: str, points_lost: float, detail: str) -> dict:
    return ScorePart(area=area, points_lost=points_lost, detail=detail).model_dump()


def _requirements_part(pilots: int, out_of_standing: int, requirements_active: int) -> dict:
    """Flight requirements only score while at least one is active; otherwise
    there is no signal to score against."""
    if requirements_active == 0:
        return _part("Flight requirements", 0, "No active flight requirements")
    return _part("Flight requirements", _share(out_of_standing, pilots, REQUIREMENT_POINTS),
                 f"{out_of_standing} of {_counted(pilots, 'active pilot')} missed or lapsed on a flight requirement")


def _authority_part(expiring: int, expired_advisory: int) -> dict:
    """An expired authority flagged as not grounding the unit costs 10; one
    inside the warning window costs 5, a nudge before the cliff. A grounding
    expiry caps the score instead (see ``_score_payload``)."""
    points = (10 if expired_advisory > 0 else 0) + (5 if expiring > 0 else 0)
    return _part("Operating authority", points,
                 f"{expired_advisory} expired (not grounding), {expiring} expiring")


def _score_breakdown(pilots, exp_certs, vehicles, exp_regs, overdue, incidents,
                     pilots_out_of_standing=0, requirements_active=0,
                     authorities_expiring=0, authorities_expired_advisory=0) -> list[dict]:
    """What each part of the compliance score takes off 100, unrounded."""
    return [
        _part("Certifications", _share(exp_certs, pilots, CERTIFICATION_POINTS),
              f"{exp_certs} of {_counted(pilots, 'active pilot')} with an expired certification"),
        _part("Registrations", _share(exp_regs, vehicles, REGISTRATION_POINTS),
              f"{exp_regs} of {_counted(vehicles, 'active vehicle')} with an expired registration"),
        _part("Maintenance", min(overdue * 5, 20), _counted(overdue, "overdue maintenance task")),
        _part("Incidents", min(incidents * 10, 20), _counted(incidents, "open incident")),
        _requirements_part(pilots, pilots_out_of_standing, requirements_active),
        _authority_part(authorities_expiring, authorities_expired_advisory),
    ]


def _calc_compliance_score(pilots, exp_certs, vehicles, exp_regs, overdue, incidents,
                           pilots_out_of_standing=0, requirements_active=0,
                           authorities_expiring=0, authorities_expired_advisory=0,
                           authority_cap=False):
    """Simple compliance score 0-100: 100 less every part of ``_score_breakdown``.

    Operating authority is the one input that can override the sum: an expired
    authority the unit depends on means every flight is unauthorised, so the
    score is capped rather than merely deducted. A unit with no authorities on
    file is unaffected, same as flight requirements with none active."""
    deductions = sum(part["points_lost"] for part in _score_breakdown(
        pilots, exp_certs, vehicles, exp_regs, overdue, incidents,
        pilots_out_of_standing, requirements_active, authorities_expiring, authorities_expired_advisory))
    score = max(0, round(100 - deductions))
    if authority_cap:
        score = min(score, AUTHORITY_SCORE_CAP)
    return score


def _score_payload(inputs: dict, cap_reason: str | None) -> dict:
    """The score and its breakdown, points rounded to one decimal. A grounding
    authority cap (``cap_reason``) adds its own line: the points it took on top."""
    uncapped = _calc_compliance_score(**inputs)
    score = _calc_compliance_score(**inputs, authority_cap=cap_reason is not None)
    breakdown = [{**part, "points_lost": round(part["points_lost"], 1)} for part in _score_breakdown(**inputs)]
    if cap_reason is not None:
        breakdown.append(_part("Operating authority cap", uncapped - score, cap_reason))
    return {"compliance_score": score, "score_breakdown": breakdown}


@router.get("/upcoming-expirations", responses=responses(401))
def upcoming_expirations(db: DBSession, user: CertificationsUser, days: int = 90):
    """Certifications of active pilots expiring from today through `days` ahead.
    Ones already expired are not upcoming (the compliance dashboard counts them)."""
    today = date.today()
    cutoff = today + timedelta(days=days)
    rows = db.query(
        PilotCertification, Pilot, CertificationType,
    ).join(Pilot, PilotCertification.pilot_id == Pilot.id
    ).join(CertificationType, PilotCertification.certification_type_id == CertificationType.id
    ).filter(
        Pilot.status == "active",
        PilotCertification.expiration_date.between(today, cutoff),
        PilotCertification.status.in_(["active", "complete"]),
    ).order_by(PilotCertification.expiration_date).all()

    result = []
    for pc, pilot, ct in rows:
        days_remaining = (pc.expiration_date - today).days
        result.append({
            "pilot_name": f"{pilot.first_name} {pilot.last_name}",
            "pilot_id": pilot.id,
            "cert_name": ct.name,
            "expiration_date": str(pc.expiration_date),
            "days_remaining": days_remaining,
            "status": pc.status,
        })
    return result
