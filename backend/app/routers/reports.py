"""Report generation endpoints."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.user import User
from app.models.certification import CertificationType, PilotCertification
from app.models.battery import Battery
from app.models.maintenance import MaintenanceRecord
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportConfig(BaseModel):
    report_type: str  # flight_summary, pilot_hours, equipment_utilization, pilot_certifications, battery_status, maintenance_history
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    pilot_ids: list[int] = []
    vehicle_ids: list[int] = []


class ReportRow(BaseModel):
    label: str
    values: dict


@router.post("/generate")
def generate_report(config: ReportConfig, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if config.report_type == "flight_summary":
        return _flight_summary(config, db)
    elif config.report_type == "pilot_hours":
        return _pilot_hours(config, db)
    elif config.report_type == "equipment_utilization":
        return _equipment_utilization(config, db)
    elif config.report_type == "pilot_certifications":
        return _pilot_certifications(config, db)
    elif config.report_type == "battery_status":
        return _battery_status(config, db)
    elif config.report_type == "maintenance_history":
        return _maintenance_history(config, db)
    return {"error": "Unknown report type"}


def _flight_summary(config: ReportConfig, db: Session):
    q = db.query(Flight)
    if config.date_from:
        q = q.filter(Flight.date >= config.date_from)
    if config.date_to:
        q = q.filter(Flight.date <= config.date_to)
    if config.pilot_ids:
        q = q.filter(Flight.pilot_id.in_(config.pilot_ids))
    if config.vehicle_ids:
        q = q.filter(Flight.vehicle_id.in_(config.vehicle_ids))

    flights = q.order_by(Flight.date.desc()).all()
    total_seconds = sum(f.duration_seconds or 0 for f in flights)

    rows = []
    for f in flights:
        pilot = db.query(Pilot).filter(Pilot.id == f.pilot_id).first() if f.pilot_id else None
        vehicle = db.query(Vehicle).filter(Vehicle.id == f.vehicle_id).first() if f.vehicle_id else None
        rows.append({
            "date": str(f.date) if f.date else "",
            "pilot": pilot.full_name if pilot else "Unassigned",
            "vehicle": f"{vehicle.manufacturer} {vehicle.model}" if vehicle else "—",
            "purpose": f.purpose or "—",
            "duration_min": round((f.duration_seconds or 0) / 60, 1),
            "location": f.takeoff_address or "—",
        })

    return {
        "report_type": "flight_summary",
        "title": "Flight Summary Report",
        "summary": {
            "total_flights": len(flights),
            "total_hours": round(total_seconds / 3600, 1),
            "date_range": f"{config.date_from or 'All'} to {config.date_to or 'Present'}",
        },
        "columns": ["Date", "Pilot", "Vehicle", "Purpose", "Duration (min)", "Location"],
        "rows": rows,
    }


def _pilot_hours(config: ReportConfig, db: Session):
    q = db.query(
        Pilot.first_name, Pilot.last_name,
        func.count(Flight.id).label("flights"),
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("seconds"),
    ).join(Pilot, Flight.pilot_id == Pilot.id)
    if config.date_from:
        q = q.filter(Flight.date >= config.date_from)
    if config.date_to:
        q = q.filter(Flight.date <= config.date_to)
    if config.pilot_ids:
        q = q.filter(Flight.pilot_id.in_(config.pilot_ids))

    rows = []
    for r in q.group_by(Pilot.id).order_by(func.sum(Flight.duration_seconds).desc()).all():
        rows.append({
            "pilot": f"{r.first_name} {r.last_name}",
            "flights": r.flights,
            "hours": round(r.seconds / 3600, 1),
            "avg_min": round(r.seconds / max(r.flights, 1) / 60, 1),
        })

    return {
        "report_type": "pilot_hours",
        "title": "Pilot Hours Report",
        "summary": {
            "total_pilots": len(rows),
            "total_hours": round(sum(r["hours"] for r in rows), 1),
            "date_range": f"{config.date_from or 'All'} to {config.date_to or 'Present'}",
        },
        "columns": ["Pilot", "Flights", "Hours", "Avg Duration (min)"],
        "rows": rows,
    }


def _equipment_utilization(config: ReportConfig, db: Session):
    q = db.query(
        Vehicle.manufacturer, Vehicle.model, Vehicle.nickname, Vehicle.serial_number,
        func.count(Flight.id).label("flights"),
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("seconds"),
    ).join(Vehicle, Flight.vehicle_id == Vehicle.id)
    if config.date_from:
        q = q.filter(Flight.date >= config.date_from)
    if config.date_to:
        q = q.filter(Flight.date <= config.date_to)

    rows = []
    for r in q.group_by(Vehicle.id).order_by(func.sum(Flight.duration_seconds).desc()).all():
        name = f"{r.manufacturer} {r.model}"
        if r.nickname:
            name += f" ({r.nickname})"
        rows.append({
            "vehicle": name,
            "serial": r.serial_number,
            "flights": r.flights,
            "hours": round(r.seconds / 3600, 1),
        })

    return {
        "report_type": "equipment_utilization",
        "title": "Equipment Utilization Report",
        "summary": {
            "total_vehicles": len(rows),
            "total_hours": round(sum(r["hours"] for r in rows), 1),
            "date_range": f"{config.date_from or 'All'} to {config.date_to or 'Present'}",
        },
        "columns": ["Vehicle", "Serial", "Flights", "Hours"],
        "rows": rows,
    }


def _pilot_certifications(config: ReportConfig, db: Session):
    q = db.query(PilotCertification).join(Pilot, PilotCertification.pilot_id == Pilot.id).join(
        CertificationType, PilotCertification.certification_type_id == CertificationType.id
    )
    if config.pilot_ids:
        q = q.filter(PilotCertification.pilot_id.in_(config.pilot_ids))

    records = q.order_by(Pilot.last_name, Pilot.first_name, CertificationType.sort_order).all()

    total_active = 0
    total_expired = 0
    total_pending = 0
    rows = []
    today = date.today()

    for pc in records:
        pilot = pc.pilot
        ct = pc.certification_type
        days_until = None
        if pc.expiration_date:
            days_until = (pc.expiration_date - today).days

        if pc.status in ("active", "complete"):
            total_active += 1
        elif pc.status == "expired":
            total_expired += 1
        elif pc.status == "pending":
            total_pending += 1

        rows.append({
            "pilot": pilot.full_name if pilot else "Unknown",
            "cert_name": ct.name if ct else "Unknown",
            "status": pc.status.replace("_", " "),
            "issue_date": str(pc.issue_date) if pc.issue_date else "—",
            "expiration_date": str(pc.expiration_date) if pc.expiration_date else "—",
            "days_until_expiry": days_until if days_until is not None else "N/A",
        })

    pilot_ids_seen = set(pc.pilot_id for pc in records)

    return {
        "report_type": "pilot_certifications",
        "title": "Pilot Certifications Report",
        "summary": {
            "total_pilots": len(pilot_ids_seen),
            "total_active": total_active,
            "total_expired": total_expired,
            "total_pending": total_pending,
        },
        "columns": ["Pilot", "Cert Name", "Status", "Issue Date", "Expiration Date", "Days Until Expiry"],
        "rows": rows,
    }


def _battery_status(config: ReportConfig, db: Session):
    batteries = db.query(Battery).order_by(Battery.serial_number).all()

    rows = []
    active_count = 0
    healths = []
    cycles = []

    for b in batteries:
        if b.status == "active":
            active_count += 1
        if b.health_pct is not None:
            healths.append(b.health_pct)
        cycles.append(b.cycle_count or 0)

        rows.append({
            "serial": b.serial_number,
            "manufacturer": b.manufacturer or "—",
            "model": b.model or "—",
            "vehicle_model": b.vehicle_model or "—",
            "cycles": b.cycle_count or 0,
            "health_pct": round(b.health_pct, 1) if b.health_pct is not None else "—",
            "status": b.status.replace("_", " "),
        })

    avg_health = round(sum(healths) / len(healths), 1) if healths else 0
    avg_cycles = round(sum(cycles) / len(cycles), 1) if cycles else 0

    return {
        "report_type": "battery_status",
        "title": "Battery Status Report",
        "summary": {
            "total_batteries": len(batteries),
            "active": active_count,
            "avg_health_pct": avg_health,
            "avg_cycles": avg_cycles,
        },
        "columns": ["Serial", "Manufacturer", "Model", "Vehicle Model", "Cycles", "Health %", "Status"],
        "rows": rows,
    }


def _maintenance_history(config: ReportConfig, db: Session):
    q = db.query(MaintenanceRecord)
    if config.date_from:
        q = q.filter(MaintenanceRecord.performed_date >= config.date_from)
    if config.date_to:
        q = q.filter(MaintenanceRecord.performed_date <= config.date_to)

    records = q.order_by(MaintenanceRecord.performed_date.desc()).all()

    total_cost = 0.0
    type_counts = {}
    rows = []

    for r in records:
        cost = r.cost or 0
        total_cost += cost
        mtype = r.maintenance_type or "other"
        type_counts[mtype] = type_counts.get(mtype, 0) + 1

        rows.append({
            "date": str(r.performed_date) if r.performed_date else "—",
            "entity_type": r.entity_type or "—",
            "description": (r.description[:80] + "...") if r.description and len(r.description) > 80 else (r.description or "—"),
            "type": mtype.replace("_", " "),
            "performed_by": r.performed_by or "—",
            "cost": f"${cost:,.2f}" if cost else "—",
        })

    # Build records-by-type summary string
    by_type_str = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in sorted(type_counts.items()))

    return {
        "report_type": "maintenance_history",
        "title": "Maintenance History Report",
        "summary": {
            "total_records": len(records),
            "total_cost": f"${total_cost:,.2f}",
            "records_by_type": by_type_str or "None",
            "date_range": f"{config.date_from or 'All'} to {config.date_to or 'Present'}",
        },
        "columns": ["Date", "Entity Type", "Description", "Type", "Performed By", "Cost"],
        "rows": rows,
    }
