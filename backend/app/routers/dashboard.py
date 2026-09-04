from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, extract

from app.deps import DBSession, CurrentUser
from app.responses import responses
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.services.flight_scope import counted_flight_clause
from app.models.vehicle import Vehicle
from app.models.certification import PilotCertification, CertificationType
from app.models.operating_authority import AUTHORITY_SCORE_CAP
from app.schemas.dashboard import (
    DashboardStats, FlightsByPurpose, FlightsByYear,
    FlightsByYearPurpose, FlightsByPilot, AvgDurationByYear,
    MonthlyFlights, VehicleHours, PilotHours,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


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
def activity_by_month(db: DBSession, user: CurrentUser, months: int = 12):
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
def top_pilots_30d(db: DBSession, user: CurrentUser, limit: int = 5):
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
def top_vehicles_30d(db: DBSession, user: CurrentUser, limit: int = 5):
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
    user: CurrentUser,
    date_from: date | None = None,
    date_to: date | None = None):
    q = db.query(
        func.coalesce(Flight.purpose, "Unknown").label("purpose"),
        func.count(Flight.id).label("count"),
    ).filter(counted_flight_clause())
    if date_from:
        q = q.filter(Flight.date >= date_from)
    if date_to:
        q = q.filter(Flight.date <= date_to)
    rows = q.group_by("purpose").order_by(func.count(Flight.id).desc()).all()
    return [FlightsByPurpose(purpose=r.purpose, count=r.count) for r in rows]


@router.get("/analytics/flights-by-year", response_model=list[FlightsByYear], responses=responses(401))
def flights_by_year(db: DBSession, user: CurrentUser):
    rows = db.query(
        extract("year", Flight.date).label("year"),
        func.count(Flight.id).label("count"),
    ).filter(counted_flight_clause(), Flight.date.isnot(None)).group_by("year").order_by("year").all()
    return [FlightsByYear(year=int(r.year), count=r.count) for r in rows]


@router.get("/analytics/flights-by-year-purpose", response_model=list[FlightsByYearPurpose])
def flights_by_year_purpose(
    db: DBSession,
    user: CurrentUser,
):
    rows = db.query(
        extract("year", Flight.date).label("year"),
        func.coalesce(Flight.purpose, "Unknown").label("purpose"),
        func.count(Flight.id).label("count"),
    ).filter(counted_flight_clause(), Flight.date.isnot(None)).group_by("year", "purpose").order_by("year", "purpose").all()
    return [FlightsByYearPurpose(year=int(r.year), purpose=r.purpose, count=r.count) for r in rows]


@router.get("/analytics/flights-by-pilot", response_model=list[FlightsByPilot])
def flights_by_pilot(
    db: DBSession,
    user: CurrentUser,
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
def avg_duration_by_year(db: DBSession, user: CurrentUser):
    rows = db.query(
        extract("year", Flight.date).label("year"),
        func.avg(Flight.duration_seconds).label("avg_seconds"),
    ).filter(counted_flight_clause(), Flight.date.isnot(None),
             Flight.duration_seconds.isnot(None)).group_by("year").order_by("year").all()
    return [AvgDurationByYear(year=int(r.year), avg_seconds=float(r.avg_seconds)) for r in rows]


@router.get("/analytics/monthly-flights", response_model=list[MonthlyFlights], responses=responses(401))
def monthly_flights(db: DBSession, user: CurrentUser):
    rows = db.query(
        extract("year", Flight.date).label("year"),
        extract("month", Flight.date).label("month"),
        func.count(Flight.id).label("count"),
    ).filter(counted_flight_clause(), Flight.date.isnot(None)).group_by("year", "month").order_by("year", "month").all()
    return [MonthlyFlights(year=int(r.year), month=int(r.month), count=r.count) for r in rows]


@router.get("/analytics/vehicle-hours", response_model=list[VehicleHours], responses=responses(401))
def vehicle_hours(db: DBSession, user: CurrentUser):
    rows = db.query(
        Vehicle.manufacturer,
        Vehicle.model,
        Vehicle.nickname,
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("total_seconds"),
    ).join(Vehicle, Flight.vehicle_id == Vehicle.id).filter(counted_flight_clause()).group_by(Vehicle.id).order_by(
        func.sum(Flight.duration_seconds).desc()
    ).all()
    return [
        VehicleHours(
            vehicle_name=f"{r.manufacturer} {r.model}" + (f" ({r.nickname})" if r.nickname else ""),
            hours=r.total_seconds / 3600,
        )
        for r in rows
    ]


@router.get("/analytics/pilot-hours", response_model=list[PilotHours], responses=responses(401))
def pilot_hours(db: DBSession, user: CurrentUser):
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
def pilot_performance(pilot_id: int, db: DBSession, user: CurrentUser):
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

    # Flights by purpose (NULL and "" both fold into "Unassigned")
    purpose_rows = db.query(
        func.coalesce(func.nullif(Flight.purpose, ""), "Unassigned").label("purpose"),
        func.count(Flight.id).label("count"),
    ).filter(counted_flight_clause(), Flight.pilot_id == pilot_id).group_by("purpose").order_by(
        func.count(Flight.id).desc()
    ).all()
    flights_by_purpose = [{"purpose": r.purpose, "count": r.count} for r in purpose_rows]

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
        "training_hours": round(float(training_hours), 1),
        "mission_hours": round(float(mission_hours), 1),
        "max_altitude_m": round(float(max_alt), 1) if max_alt else None,
        "max_speed_mps": round(float(max_speed), 1) if max_speed else None,
    }


@router.get("/analytics/fleet-health", responses=responses(401))
def fleet_health(db: DBSession, user: CurrentUser):
    from app.models.battery import Battery
    from app.models.maintenance_schedule import MaintenanceSchedule

    today = date.today()

    vehicles = db.query(Vehicle).filter(Vehicle.status == "active").all()
    batteries = db.query(Battery).all()

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


@router.get("/compliance", responses=responses(401))
def compliance_dashboard(db: DBSession, user: CurrentUser):
    from app.models.vehicle_registration import VehicleRegistration
    from app.models.maintenance_schedule import MaintenanceSchedule
    from app.models.incident import Incident
    from app.models.flight_approval import FlightPlan
    from app.models.operating_authority import OperatingAuthority, authority_status

    today = date.today()
    soon = today + timedelta(days=90)

    # Certification compliance
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
    expiring_soon = db.query(PilotCertification).filter(
        PilotCertification.expiration_date.between(today, soon),
        PilotCertification.status.notin_(["not_issued", "renewed"]),
        PilotCertification.pilot_id.in_(active_pilot_ids),
    ).all()

    # FAA registration compliance — active fleet only, so expired registrations
    # kept on retired/sold vehicles don't count against compliance.
    total_vehicles = db.query(func.count(Vehicle.id)).filter(Vehicle.status == "active").scalar()
    active_vehicle_ids = db.query(Vehicle.id).filter(Vehicle.status == "active").subquery()
    expired_regs = db.query(func.count(func.distinct(VehicleRegistration.vehicle_id))).filter(
        VehicleRegistration.is_current.is_(True),
        VehicleRegistration.expiry_date < today,
        VehicleRegistration.vehicle_id.in_(active_vehicle_ids),
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

    # --- Pilot currency status ---
    # Reuses the per-pilot evaluator from currency.py so the rule semantics
    # (period window, hours met, expiry calc) stay identical to PilotDetailPage.
    from app.models.currency_rule import CurrencyRule
    from app.routers.currency import _pilot_currency
    currency_rules_active = (
        db.query(func.count(CurrencyRule.id))
        .filter(CurrencyRule.is_active.is_(True))
        .scalar() or 0
    )
    pilot_currency_status: list[dict] = []
    pilots_current = 0
    pilots_lapsed = 0
    if currency_rules_active > 0:
        rules = db.query(CurrencyRule).filter(CurrencyRule.is_active.is_(True)).all()
        active_pilots = db.query(Pilot).filter(Pilot.status == "active").all()
        for p in active_pilots:
            rule_results = _pilot_currency(p, rules, db)
            is_current = all(r["is_current"] for r in rule_results) if rule_results else True
            # Earliest expiry across current-passing rules; null when any rule lapsed.
            expiries = [r["expires_date"] for r in rule_results if r.get("expires_date")]
            earliest = min(expiries) if (expiries and is_current) else None
            pilot_currency_status.append({
                "pilot_id": p.id,
                "pilot_name": p.full_name,
                "email": p.email,
                "is_current": is_current,
                "earliest_expires_date": earliest,
                "rules": rule_results,
            })
            if is_current:
                pilots_current += 1
            else:
                pilots_lapsed += 1
    else:
        # No rules defined — every pilot is implicitly current.
        pilots_current = total_pilots

    # --- Operating authority (org-level COAs / Part 107 waivers) ---
    # Only records still marked active are scored. Superseded and not-applicable
    # ones stay on file for the reports without counting against the unit.
    authorities = db.query(OperatingAuthority).filter(
        OperatingAuthority.record_status == "active"
    ).all()
    expired_authorities = []
    expiring_authorities = []
    for a in authorities:
        state = authority_status(a, today)
        if state == "expired":
            expired_authorities.append(a)
        elif state == "expiring":
            expiring_authorities.append(a)
    # An expired authority the unit depends on caps the score outright; one that
    # only restricts a kind of operation takes an ordinary deduction instead.
    grounding_expired = [a for a in expired_authorities if a.grounds_unit]
    advisory_expired = [a for a in expired_authorities if not a.grounds_unit]
    score_cap_reason = None
    if grounding_expired:
        score_cap_reason = (
            f"Capped at {AUTHORITY_SCORE_CAP}: "
            f"{len(grounding_expired)} operating "
            f"{'authority' if len(grounding_expired) == 1 else 'authorities'} expired"
        )

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
        "currency_rules_active": currency_rules_active,
        "pilots_current": pilots_current,
        "pilots_lapsed": pilots_lapsed,
        "pilot_currency_status": pilot_currency_status,
        "operating_authorities_tracked": len(authorities),
        "expired_authorities": [_authority_brief(a, today) for a in expired_authorities],
        "expiring_authorities": [_authority_brief(a, today) for a in expiring_authorities],
        "score_cap_reason": score_cap_reason,
        "compliance_score": _calc_compliance_score(
            total_pilots, expired_certs, total_vehicles, expired_regs,
            overdue_maintenance, open_incidents,
            pilots_lapsed, currency_rules_active,
            len(expiring_authorities), len(advisory_expired), bool(grounding_expired),
        ),
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


def _calc_compliance_score(pilots, exp_certs, vehicles, exp_regs, overdue, incidents,
                           pilots_lapsed=0, currency_rules_active=0,
                           authorities_expiring=0, authorities_expired_advisory=0,
                           authority_cap=False):
    """Simple compliance score 0-100. Currency only contributes when at least
    one active rule exists — otherwise we have no signal to score against.

    Operating authority is the one input that can override the sum: an expired
    authority the unit depends on means every flight is unauthorised, so the
    score is capped rather than merely deducted. A unit with no authorities on
    file is unaffected, same as currency with no rules defined."""
    deductions = 0
    if pilots > 0:
        deductions += (exp_certs / pilots) * 25  # cert compliance worth 25 points
    if vehicles > 0:
        deductions += (exp_regs / vehicles) * 20  # reg compliance worth 20 points
    deductions += min(overdue * 5, 20)  # maintenance worth up to 20 points
    deductions += min(incidents * 10, 20)  # incidents worth up to 20 points
    if currency_rules_active > 0 and pilots > 0:
        deductions += (pilots_lapsed / pilots) * 15  # currency worth 15 points
    if authorities_expired_advisory > 0:
        deductions += 10  # expired, but flagged as not grounding the unit
    if authorities_expiring > 0:
        deductions += 5  # inside the warning window: a nudge before the cliff
    score = max(0, round(100 - deductions))
    if authority_cap:
        score = min(score, AUTHORITY_SCORE_CAP)
    return score


@router.get("/upcoming-expirations", responses=responses(401))
def upcoming_expirations(db: DBSession, user: CurrentUser, days: int = 90):
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
