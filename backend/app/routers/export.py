import csv
import io
import logging
import tempfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import joinedload

from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.maintenance import MaintenanceRecord
from app.models.certification import PilotCertification, CertificationType
from app.models.training_log import TrainingLog
from app.models.training_log_pilot import TrainingLogPilot
from app.models.mission_log import MissionLog
from app.models.mission_log_pilot import MissionLogPilot
from app.models.battery import Battery
from app.models.controller import Controller
from app.models.dock import Dock
from app.models.sensor import SensorPackage
from app.models.attachment import Attachment
from app.models.other_equipment import OtherEquipment
from app.config import settings
from app.constants import APP_TITLE, FILE_TOO_LARGE
from app.deps import DBSession, CurrentUser, AdminUser
from app.responses import responses

router = APIRouter(prefix="/api/export", tags=["export"])

logger = logging.getLogger(__name__)

CSV_MEDIA_TYPE = "text/csv"

# Hard cap on rows in a single CSV export. Generous so normal exports are
# unaffected; protects against an unbounded query streaming the whole table.
MAX_EXPORT_ROWS = 50000

# Leading characters that spreadsheet apps interpret as the start of a formula.
_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value):
    """Neutralize CSV formula injection in user-controlled text fields.

    Prefixes a leading apostrophe to any string cell beginning with a
    formula trigger character (= + - @ tab CR). Non-string values pass
    through unchanged.
    """
    if isinstance(value, str) and value and value[0] in _CSV_INJECTION_PREFIXES:
        return "'" + value
    return value


def _cap_rows(rows: list, export_name: str) -> list:
    """Truncate an export result set to MAX_EXPORT_ROWS, logging a warning."""
    if len(rows) > MAX_EXPORT_ROWS:
        logger.warning(
            "%s export truncated: %d rows exceeds cap of %d",
            export_name, len(rows), MAX_EXPORT_ROWS,
        )
        return rows[:MAX_EXPORT_ROWS]
    return rows

# CSV column header constants (S1192 - duplicated strings)
COL_CASE_NUMBER = "Case Number"
COL_ENTITY_TYPE = "Entity Type"
COL_ENTITY_ID = "Entity ID"
COL_DURATION_S = "Duration (s)"
COL_TAKEOFF_LAT = "Takeoff Lat"
COL_TAKEOFF_LON = "Takeoff Lon"
COL_MAX_ALTITUDE_M = "Max Altitude (m)"
COL_MAX_SPEED_MPS = "Max Speed (m/s)"
# Skydio flight-list export / import header tokens (used for round-trip).
SKYDIO_FLIGHT_ID_COL = "Flight ID"
SKYDIO_LOCAL_TAKEOFF_COL = "Local Takeoff Time"
EXCEL_EXTENSIONS = ('.xlsx', '.xls')


def _resolve_display_tz(db):
    """The configured display timezone, falling back to TZ env then Central."""
    import os
    from zoneinfo import ZoneInfo
    from app.models.setting import Setting

    tz_row = db.query(Setting).filter(Setting.key == "display_timezone").first()
    tz_name = (tz_row.value if tz_row and tz_row.value else None) or os.environ.get("TZ", "America/Chicago")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("America/Chicago")


def _csv_fmt_utc(dt):
    """A stored (already-UTC) datetime rendered as-is, or empty."""
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def _csv_fmt_local(dt, local_tz):
    """A stored UTC datetime converted to the configured local zone, or empty."""
    if not dt:
        return ""
    from datetime import timezone
    return dt.replace(tzinfo=timezone.utc).astimezone(local_tz).strftime("%Y-%m-%d %H:%M")


def _csv_eq(v):
    """Equipment field: 'N/A' when empty (matches the Skydio export)."""
    return v if v else "N/A"


def _flight_csv_row(f, local_tz):
    """One flights-export row in the Skydio column order."""
    pilot_str = ""
    if f.pilot:
        name = f"{f.pilot.first_name or ''} {f.pilot.last_name or ''}".strip()
        pilot_str = f.pilot.email or name
    vehicle_str = f.vehicle.serial_number if f.vehicle and f.vehicle.serial_number else ""
    return [
        _csv_safe(f.external_id or ""),
        _csv_safe(vehicle_str),
        _csv_safe(pilot_str),
        _csv_fmt_local(f.takeoff_time, local_tz),
        _csv_fmt_utc(f.takeoff_time),
        _csv_safe(f.takeoff_address or ""),
        f.takeoff_lat if f.takeoff_lat is not None else "",
        f.takeoff_lon if f.takeoff_lon is not None else "",
        _csv_fmt_utc(f.landing_time),
        f.duration_seconds if f.duration_seconds is not None else "",
        _csv_safe(_csv_eq(f.battery_serial)),
        _csv_safe(_csv_eq(f.sensor_package)),
        _csv_safe(_csv_eq(f.attachment_top)),
        _csv_safe(_csv_eq(f.attachment_bottom)),
        _csv_safe(_csv_eq(f.attachment_left)),
        _csv_safe(_csv_eq(f.attachment_right)),
        _csv_safe(_csv_eq(f.carrier)),
        _csv_safe(f.purpose or ""),
    ]


@router.get("/flights/csv")
def export_flights_csv(
    db: DBSession,
    user: CurrentUser,
    date_from: date | None = None,
    date_to: date | None = None):
    """Export flights as CSV in the Skydio flight-list column order (plus Purpose).

    Columns match the Skydio Cloud export so the file round-trips through the
    Skydio importer, with Purpose appended at the end. Equipment slots use
    "N/A" when empty, matching the Skydio convention. Takeoff and Land are the
    stored UTC values; Local Takeoff Time is converted to the configured
    display timezone.
    """
    local_tz = _resolve_display_tz(db)

    q = db.query(Flight).options(joinedload(Flight.pilot), joinedload(Flight.vehicle))
    if date_from:
        q = q.filter(Flight.date >= date_from)
    if date_to:
        q = q.filter(Flight.date <= date_to)
    flights = _cap_rows(q.order_by(Flight.date.desc()).all(), "flights")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        SKYDIO_FLIGHT_ID_COL, "Vehicle", "Pilot", SKYDIO_LOCAL_TAKEOFF_COL, "Takeoff",
        "Takeoff Address", "Takeoff Latitude", "Takeoff Longitude",
        "Land", "Duration (seconds)", "Battery", "Sensor Package",
        "Attachment (TOP)", "Attachment (BOTTOM)", "Attachment (LEFT)",
        "Attachment (RIGHT)", "Carrier(s)", "Purpose",
    ])
    for f in flights:
        writer.writerow(_flight_csv_row(f, local_tz))

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=flights_export.csv"},
    )


@router.get("/pilots/csv", responses=responses(401))
def export_pilots_csv(db: DBSession, user: CurrentUser):
    pilots = _cap_rows(db.query(Pilot).order_by(Pilot.last_name).all(), "pilots")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["First Name", "Last Name", "Email", "Phone", "Badge Number", "Status", "Notes"])
    for p in pilots:
        writer.writerow([
            _csv_safe(p.first_name), _csv_safe(p.last_name), _csv_safe(p.email or ""),
            _csv_safe(p.phone or ""), _csv_safe(p.badge_number or ""), p.status, _csv_safe(p.notes or ""),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=pilots_export.csv"},
    )


@router.get("/vehicles/csv", responses=responses(401))
def export_vehicles_csv(db: DBSession, user: CurrentUser):
    vehicles = _cap_rows(db.query(Vehicle).order_by(Vehicle.manufacturer).all(), "vehicles")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Serial", "Manufacturer", "Model", "Nickname", "FAA Reg", "Status", "Flights", "Hours"])
    for v in vehicles:
        writer.writerow([
            _csv_safe(v.serial_number), _csv_safe(v.manufacturer), _csv_safe(v.model),
            _csv_safe(v.nickname or ""), _csv_safe(v.faa_registration or ""), v.status,
            v.total_flights, round(v.total_flight_hours, 1),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=vehicles_export.csv"},
    )


# Six fleet tabs export the same shape, so they share one builder rather than
# six near-identical endpoints: the formula-injection guard and the row cap stay
# in a single place, and a new equipment type is a spec rather than a copy.
#
# Each entry is (model, order column, label, columns). The label is a literal
# rather than the URL path parameter: it feeds the log line and the download
# filename, and user-controlled data should reach neither.
EQUIPMENT_EXPORTS = {
    "batteries": (Battery, Battery.serial_number, "batteries", [
        ("Serial", "serial_number"), ("Nickname", "nickname"),
        ("Manufacturer", "manufacturer"), ("Model", "model"),
        ("Vehicle Model", "vehicle_model"), ("Cycles", "cycle_count"),
        ("Health %", "health_pct"), ("Status", "status"),
        ("Acquired", "acquired_date"), ("Decommissioned", "decommissioned_date"),
    ]),
    "controllers": (Controller, Controller.serial_number, "controllers", [
        ("Serial", "serial_number"), ("Nickname", "nickname"),
        ("Manufacturer", "manufacturer"), ("Model", "model"), ("Status", "status"),
        ("Acquired", "acquired_date"), ("Decommissioned", "decommissioned_date"),
    ]),
    "docks": (Dock, Dock.serial_number, "docks", [
        ("Serial", "serial_number"), ("Name", "name"),
        ("Location", "location_name"), ("Status", "status"),
        ("Acquired", "acquired_date"), ("Decommissioned", "decommissioned_date"),
    ]),
    "sensors": (SensorPackage, SensorPackage.serial_number, "sensors", [
        ("Serial", "serial_number"), ("Name", "name"), ("Type", "type"),
        ("Manufacturer", "manufacturer"), ("Model", "model"), ("Status", "status"),
        ("Acquired", "acquired_date"), ("Decommissioned", "decommissioned_date"),
    ]),
    "attachments": (Attachment, Attachment.serial_number, "attachments", [
        ("Serial", "serial_number"), ("Name", "name"), ("Type", "type"),
        ("Manufacturer", "manufacturer"), ("Model", "model"), ("Status", "status"),
        ("Acquired", "acquired_date"), ("Decommissioned", "decommissioned_date"),
    ]),
    "other-equipment": (OtherEquipment, OtherEquipment.name, "other_equipment", [
        ("Name", "name"), ("Category", "category"), ("Serial", "serial_number"),
        ("Status", "status"), ("Acquired", "acquired_date"),
        ("Decommissioned", "decommissioned_date"),
    ]),
}


# Namespaced under /fleet/ deliberately. A bare /{equipment_type}/csv would be a
# catch-all registered before the named CSV routes below it and would swallow
# every one of them, and any future named route added underneath.
@router.get("/fleet/{equipment_type}/csv", responses=responses(401, 404))
def export_equipment_csv(equipment_type: str, db: DBSession, user: CurrentUser):
    """Export one fleet equipment table as CSV.

    Deliberately exports the whole table rather than whatever the Fleet page is
    currently filtered to: the page's status filter is a viewing convenience,
    and an export silently missing retired kit would be a poor audit record.
    """
    spec = EQUIPMENT_EXPORTS.get(equipment_type)
    if not spec:
        raise HTTPException(404, "Unknown equipment type")
    model_class, order_col, label, columns = spec

    rows = _cap_rows(db.query(model_class).order_by(order_col).all(), label)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([header for header, _ in columns])
    for row in rows:
        writer.writerow([_csv_safe(getattr(row, attr, None) or "") for _, attr in columns])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename={label}_export.csv"},
    )


@router.get("/maintenance/csv")
def export_maintenance_csv(
    db: DBSession,
    user: CurrentUser,
    date_from: date | None = None,
    date_to: date | None = None,
    entity_type: str | None = None):
    q = db.query(MaintenanceRecord)
    if date_from:
        q = q.filter(MaintenanceRecord.performed_date >= date_from)
    if date_to:
        q = q.filter(MaintenanceRecord.performed_date <= date_to)
    if entity_type:
        q = q.filter(MaintenanceRecord.entity_type == entity_type)
    records = _cap_rows(q.order_by(MaintenanceRecord.performed_date.desc()).all(), "maintenance")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        COL_ENTITY_TYPE, COL_ENTITY_ID, "Maintenance Type", "Description",
        "Performed By", "Performed Date", "Next Due Date", "Cost", "Notes",
    ])
    for r in records:
        writer.writerow([
            _csv_safe(r.entity_type), r.entity_id, _csv_safe(r.maintenance_type), _csv_safe(r.description or ""),
            _csv_safe(r.performed_by or ""), r.performed_date or "", r.next_due_date or "",
            r.cost or "", _csv_safe(r.notes or ""),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=maintenance_export.csv"},
    )


@router.get("/checklists/csv", responses=responses(401))
def export_checklists_csv(db: DBSession, user: CurrentUser):
    from app.models.checklist import ChecklistCompletion, ChecklistTemplate
    completions = _cap_rows(
        db.query(ChecklistCompletion).order_by(ChecklistCompletion.completed_at.desc()).all(),
        "checklists",
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Pilot", "Vehicle", "Template", "Passed", "Notes"])
    for c in completions:
        pilot = db.query(Pilot).filter(Pilot.id == c.pilot_id).first()
        vehicle = db.query(Vehicle).filter(Vehicle.id == c.vehicle_id).first() if c.vehicle_id else None
        template = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == c.template_id).first()
        writer.writerow([
            c.completed_at.strftime("%Y-%m-%d %H:%M") if c.completed_at else "",
            _csv_safe(pilot.full_name) if pilot else "",
            _csv_safe(f"{vehicle.manufacturer} {vehicle.model}") if vehicle else "",
            _csv_safe(template.name) if template else "",
            "Yes" if c.all_passed else "No",
            _csv_safe(c.notes or ""),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=checklists_export.csv"},
    )


@router.get("/certifications/csv")
def export_certifications_csv(
    db: DBSession,
    user: CurrentUser,
    pilot_id: int | None = None,
    status: str | None = None):
    q = db.query(PilotCertification)
    if pilot_id:
        q = q.filter(PilotCertification.pilot_id == pilot_id)
    if status:
        q = q.filter(PilotCertification.status == status)
    certs = _cap_rows(q.all(), "certifications")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Pilot", "Certification", "Category", "Status",
        "Issue Date", "Expiration Date", "Certificate Number", "Notes",
    ])
    for c in certs:
        pilot = db.query(Pilot).filter(Pilot.id == c.pilot_id).first()
        cert_type = db.query(CertificationType).filter(CertificationType.id == c.certification_type_id).first()
        writer.writerow([
            _csv_safe(pilot.full_name) if pilot else "",
            _csv_safe(cert_type.name) if cert_type else "",
            _csv_safe(cert_type.category) if cert_type else "",
            c.status,
            c.issue_date or "", c.expiration_date or "",
            _csv_safe(c.certificate_number or ""), _csv_safe(c.notes or ""),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=certifications_export.csv"},
    )


@router.get("/training-logs/csv")
def export_training_logs_csv(
    db: DBSession,
    user: CurrentUser,
    date_from: date | None = None,
    date_to: date | None = None,
    pilot_id: int | None = None,
    training_type: str | None = None):
    q = db.query(TrainingLog)
    if date_from:
        q = q.filter(TrainingLog.date >= date_from)
    if date_to:
        q = q.filter(TrainingLog.date <= date_to)
    if pilot_id:
        q = q.join(TrainingLogPilot).filter(TrainingLogPilot.pilot_id == pilot_id)
    if training_type:
        q = q.filter(TrainingLog.training_type == training_type)
    logs = _cap_rows(q.order_by(TrainingLog.date.desc()).all(), "training_logs")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Title", "Training Type", "Instructor", "Location",
        "Man Hours", "Outcome", "Pilots", "Description", "Notes",
    ])
    for t in logs:
        pilot_names = []
        for tp in t.pilots:
            p = db.query(Pilot).filter(Pilot.id == tp.pilot_id).first()
            if p:
                pilot_names.append(p.full_name)
        writer.writerow([
            t.date, _csv_safe(t.title), _csv_safe(t.training_type), _csv_safe(t.instructor or ""),
            _csv_safe(t.location or ""), t.man_hours, _csv_safe(t.outcome),
            _csv_safe("; ".join(pilot_names)), _csv_safe(t.description or ""), _csv_safe(t.notes or ""),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=training_logs_export.csv"},
    )


@router.get("/mission-logs/csv")
def export_mission_logs_csv(
    db: DBSession,
    user: CurrentUser,
    date_from: date | None = None,
    date_to: date | None = None,
    pilot_id: int | None = None):
    q = db.query(MissionLog)
    if date_from:
        q = q.filter(MissionLog.date >= date_from)
    if date_to:
        q = q.filter(MissionLog.date <= date_to)
    if pilot_id:
        q = q.join(MissionLogPilot).filter(MissionLogPilot.pilot_id == pilot_id)
    logs = _cap_rows(q.order_by(MissionLog.date.desc()).all(), "mission_logs")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Title", "Reason", "Location", COL_CASE_NUMBER,
        "Man Hours", "Status", "Pilots", "Description", "Notes",
    ])
    for m in logs:
        pilot_names = []
        for mp in m.pilots:
            p = db.query(Pilot).filter(Pilot.id == mp.pilot_id).first()
            if p:
                pilot_names.append(p.full_name)
        writer.writerow([
            m.date, _csv_safe(m.title), _csv_safe(m.reason or ""), _csv_safe(m.location or ""),
            _csv_safe(m.case_number or ""), m.man_hours, m.status,
            _csv_safe("; ".join(pilot_names)), _csv_safe(m.description or ""), _csv_safe(m.notes or ""),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=mission_logs_export.csv"},
    )


def _incident_csv_row(inc, db):
    """One incidents-export row."""
    pilot = db.query(Pilot).filter(Pilot.id == inc.pilot_id).first() if inc.pilot_id else None
    return [
        inc.date, _csv_safe(inc.title), _csv_safe(pilot.full_name) if pilot else "",
        getattr(inc, 'report_type', 'incident') or 'incident',
        inc.severity, _csv_safe(inc.category), _csv_safe(inc.description or ""),
        _csv_safe(inc.location or ""), inc.status, _csv_safe(inc.resolution or ""),
        "Yes" if inc.equipment_grounded else "No",
        _csv_safe(inc.damage_description or ""), inc.estimated_cost or "", _csv_safe(inc.notes or ""),
    ]


@router.get("/incidents/csv")
def export_incidents_csv(
    db: DBSession,
    user: CurrentUser,
    date_from: date | None = None,
    date_to: date | None = None,
    report_type: str | None = None):
    from app.models.incident import Incident
    q = db.query(Incident)
    if date_from:
        q = q.filter(Incident.date >= date_from)
    if date_to:
        q = q.filter(Incident.date <= date_to)
    if report_type:
        q = q.filter(Incident.report_type == report_type)
    incidents = _cap_rows(q.order_by(Incident.date.desc()).all(), "incidents")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Title", "Pilot", "Report Type", "Severity", "Category", "Description",
        "Location", "Status", "Resolution", "Equipment Grounded",
        "Damage Description", "Estimated Cost", "Notes",
    ])
    for inc in incidents:
        writer.writerow(_incident_csv_row(inc, db))
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=incidents_export.csv"},
    )


def _flight_plan_csv_row(p, db):
    """One flight-plans-export row."""
    pilot = db.query(Pilot).filter(Pilot.id == p.pilot_id).first() if p.pilot_id else None
    vehicle = db.query(Vehicle).filter(Vehicle.id == p.vehicle_id).first() if p.vehicle_id else None
    return [
        _csv_safe(p.title), p.date_planned,
        _csv_safe(pilot.full_name) if pilot else "",
        _csv_safe(f"{vehicle.manufacturer} {vehicle.model}") if vehicle else "",
        _csv_safe(p.location or ""), _csv_safe(p.purpose or ""), _csv_safe(p.case_number or ""),
        p.status, p.max_altitude_planned or "", p.estimated_duration_min or "",
        _csv_safe(p.notes or ""),
    ]


@router.get("/flight-plans/csv")
def export_flight_plans_csv(
    db: DBSession,
    user: CurrentUser,
    date_from: date | None = None,
    date_to: date | None = None):
    from app.models.flight_approval import FlightPlan
    from sqlalchemy import func as sqlfunc
    q = db.query(FlightPlan)
    if date_from:
        q = q.filter(sqlfunc.date(FlightPlan.date_planned) >= date_from)
    if date_to:
        q = q.filter(sqlfunc.date(FlightPlan.date_planned) <= date_to)
    plans = _cap_rows(q.order_by(FlightPlan.date_planned.desc()).all(), "flight_plans")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Title", "Date Planned", "Pilot", "Vehicle", "Location", "Purpose",
        COL_CASE_NUMBER, "Status", "Max Altitude", "Est Duration (min)", "Notes",
    ])
    for p in plans:
        writer.writerow(_flight_plan_csv_row(p, db))
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=flight_plans_export.csv"},
    )


@router.get("/audit/csv")
def export_audit_csv(
    db: DBSession,
    user: AdminUser,
    date_from: date | None = None,
    date_to: date | None = None):
    from app.models.audit_log import AuditLog
    from sqlalchemy import func as sqlfunc
    q = db.query(AuditLog)
    if date_from:
        q = q.filter(sqlfunc.date(AuditLog.created_at) >= date_from)
    if date_to:
        q = q.filter(sqlfunc.date(AuditLog.created_at) <= date_to)
    logs = q.order_by(AuditLog.created_at.desc()).limit(5000).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Timestamp", "User", "Action", COL_ENTITY_TYPE, COL_ENTITY_ID,
        "Entity Name", "Details", "IP Address",
    ])
    for log in logs:
        writer.writerow([
            log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "",
            _csv_safe(log.user_name or ""), _csv_safe(log.action), _csv_safe(log.entity_type),
            log.entity_id or "", _csv_safe(log.entity_name or ""),
            _csv_safe(log.details or ""), _csv_safe(log.ip_address or ""),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=audit_log_export.csv"},
    )


def _equipment_checkout_csv_row(c, db):
    """One equipment-checkouts-export row."""
    pilot_out = db.query(Pilot).filter(Pilot.id == c.checked_out_by_id).first() if c.checked_out_by_id else None
    return [
        _csv_safe(c.entity_type), _csv_safe(c.entity_name or ""),
        _csv_safe(pilot_out.full_name) if pilot_out else "",
        c.checked_out_at.strftime("%Y-%m-%d %H:%M") if c.checked_out_at else "",
        c.expected_return.strftime("%Y-%m-%d %H:%M") if c.expected_return else "",
        c.checked_in_at.strftime("%Y-%m-%d %H:%M") if c.checked_in_at else "",
        _csv_safe(c.condition_out or ""), _csv_safe(c.condition_in or ""),
        _csv_safe(c.notes_out or ""), _csv_safe(c.notes_in or ""),
    ]


@router.get("/equipment-checkouts/csv")
def export_equipment_checkouts_csv(
    db: DBSession,
    user: CurrentUser,
    date_from: date | None = None,
    date_to: date | None = None):
    from app.models.equipment_checkout import EquipmentCheckout
    from sqlalchemy import func as sqlfunc
    q = db.query(EquipmentCheckout)
    if date_from:
        q = q.filter(sqlfunc.date(EquipmentCheckout.checked_out_at) >= date_from)
    if date_to:
        q = q.filter(sqlfunc.date(EquipmentCheckout.checked_out_at) <= date_to)
    checkouts = _cap_rows(q.order_by(EquipmentCheckout.checked_out_at.desc()).all(), "equipment_checkouts")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        COL_ENTITY_TYPE, "Entity Name", "Checked Out By", "Checked Out At",
        "Expected Return", "Checked In At", "Condition Out", "Condition In",
        "Notes Out", "Notes In",
    ])
    for c in checkouts:
        writer.writerow(_equipment_checkout_csv_row(c, db))
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=equipment_checkouts_export.csv"},
    )


def _lookup_pilot_by_name(db, full_name: str) -> int | None:
    """Look up a pilot ID by 'First Last' name string."""
    parts = full_name.split(" ", 1)
    if len(parts) != 2:
        return None
    pilot = db.query(Pilot).filter(
        Pilot.first_name == parts[0], Pilot.last_name == parts[1]
    ).first()
    return pilot.id if pilot else None


def _parse_csv_flight_row(row: dict, db) -> Flight:
    """Parse a single CSV row into a Flight object with pilot lookup."""
    flight = Flight(
        date=row.get("Date") or None,
        purpose=row.get("Purpose") or None,
        duration_seconds=int(row[COL_DURATION_S]) if row.get(COL_DURATION_S) else None,
        takeoff_address=row.get("Takeoff Address") or None,
        takeoff_lat=float(row[COL_TAKEOFF_LAT]) if row.get(COL_TAKEOFF_LAT) else None,
        takeoff_lon=float(row[COL_TAKEOFF_LON]) if row.get(COL_TAKEOFF_LON) else None,
        max_altitude_m=float(row[COL_MAX_ALTITUDE_M]) if row.get(COL_MAX_ALTITUDE_M) else None,
        max_speed_mps=float(row[COL_MAX_SPEED_MPS]) if row.get(COL_MAX_SPEED_MPS) else None,
        case_number=row.get(COL_CASE_NUMBER) or None,
        notes=row.get("Notes") or None,
        review_status="needs_review",
        pilot_confirmed=True,
    )
    pilot_name = row.get("Pilot", "").strip()
    if pilot_name:
        flight.pilot_id = _lookup_pilot_by_name(db, pilot_name)
    return flight


@router.post("/flights/import", responses=responses(400, 413))
async def import_flights_csv(
    db: DBSession,
    admin: AdminUser,
    file: Annotated[UploadFile, File()],
):
    if not file.filename.endswith('.csv'):
        raise HTTPException(400, "Only CSV files are supported")

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB")
    text = content.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    headers = set(reader.fieldnames or [])

    # A Skydio flight-list export → full importer that creates pilots, vehicles,
    # and equipment. The app's own exported flights CSV uses different columns
    # (Date, Case Number, ...) and falls through to the round-trip path below.
    if {SKYDIO_FLIGHT_ID_COL, "Vehicle", "Pilot"} <= headers and (
        SKYDIO_LOCAL_TAKEOFF_COL in headers or "Takeoff" in headers
    ):
        from app.services.excel_import import import_skydio_csv
        return import_skydio_csv(db, content)

    imported = 0
    errors = []
    for i, row in enumerate(reader):
        try:
            flight = _parse_csv_flight_row(row, db)
            db.add(flight)
            imported += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")

    db.commit()
    return {"imported": imported, "errors": errors}


@router.post("/excel/import", responses=responses(400, 413))
async def import_excel_file(
    db: DBSession,
    admin: AdminUser,
    file: Annotated[UploadFile, File()],
):
    """Import a Skydio export and create fleet, pilots, accessories, and flights.

    Accepts the same export as either an Excel workbook (.xlsx, multi-sheet:
    flights + pilot certifications) or a flight-list CSV. Both run the full
    Skydio importer so equipment and pilots are created, not just flights.
    """
    if not file.filename.endswith(EXCEL_EXTENSIONS + ('.csv',)):
        raise HTTPException(400, "Only Skydio .xlsx, .xls, or .csv files are supported")
    spooled = await _spool_upload(file, settings.MAX_UPLOAD_SIZE)
    try:
        content = spooled.read()
    finally:
        spooled.close()
    from app.services.excel_import import import_excel, import_skydio_csv
    if file.filename.endswith('.csv'):
        return import_skydio_csv(db, content)
    return import_excel(db, content)


# Below this the upload stays in memory; above it, the spool writes to disk.
SPOOL_TO_DISK_ABOVE = 8 * 1024 * 1024


async def _spool_upload(file: UploadFile, limit: int):
    """Read an upload into a temp file, refusing it as soon as it passes `limit`.

    Reading it all with `await file.read()` and measuring afterwards means a
    client can make the server hold the whole thing before the check runs,
    which is the check doing nothing. Counting while reading rejects an
    oversized upload after one chunk instead of all of it.

    Returns a file object positioned at the start; the caller closes it.
    """
    spooled = tempfile.SpooledTemporaryFile(max_size=SPOOL_TO_DISK_ABOVE)
    total = 0
    try:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > limit:
                raise HTTPException(413, FILE_TOO_LARGE.format(limit // (1024 * 1024)))
            # Once the spool passes SPOOL_TO_DISK_ABOVE these writes hit the
            # disk, and a synchronous write on the event loop stalls every other
            # request behind it.
            await run_in_threadpool(spooled.write, chunk)
    except BaseException:
        spooled.close()
        raise
    await run_in_threadpool(spooled.seek, 0)
    return spooled


def _import_zip_flight_logs(archive, db, do_import, get_telemetry_db, user_id: int) -> dict:
    """Bulk import flight logs from a ZIP file containing JSON files.

    Takes a file object rather than bytes: ZipFile reads entries on demand, so
    a 200MB export costs the largest single entry rather than the whole archive.
    """
    import zipfile
    with zipfile.ZipFile(archive) as zf:
        json_files = [n for n in zf.namelist() if n.endswith('.json') and not n.startswith('__')]
        results = {"total": len(json_files), "imported": 0, "skipped": 0, "errors": []}
        for fname in json_files:
            try:
                # Refuse an entry on its declared decompressed size, before
                # reading it: an archive can be small and claim gigabytes.
                if zf.getinfo(fname).file_size > settings.MAX_ARCHIVE_ENTRY_SIZE:
                    results["errors"].append(f"{fname}: entry too large")
                    continue
                file_content = zf.read(fname)
                telemetry_db = next(get_telemetry_db())
                try:
                    result = do_import(file_content, db, telemetry_db, format_hint="airdata_json", user_id=user_id)
                finally:
                    telemetry_db.close()
                if result.get("skipped"):
                    results["skipped"] += 1
                elif result.get("error"):
                    results["errors"].append(f"{fname}: {result['error']}")
                else:
                    results["imported"] += 1
            except Exception as e:
                results["errors"].append(f"{fname}: {str(e)}")
        return results


@router.post("/flights/import/log", responses=responses(400, 413))
async def import_flight_log(
    db: DBSession,
    admin: AdminUser,
    file: Annotated[UploadFile, File()],
    format: str = "auto",
):
    """Import a flight log file (DJI .txt, Litchi CSV, Airdata CSV/JSON, or ZIP).

    Auto-detects format from file content, or use the format parameter
    to specify explicitly. Creates a Flight record and TelemetryPoints.

    Args:
        file: The flight log file (.txt, .csv, .json, or .zip).
        format: Format hint - "auto", "dji", "litchi", "airdata", or "airdata_json".

    Returns:
        Import result with flight_id, points_imported, and format_detected.
    """
    if not file.filename.endswith(('.txt', '.csv', '.json', '.zip') + EXCEL_EXTENSIONS):
        raise HTTPException(400, "Only .txt, .csv, .json, .zip, and .xlsx files are supported")

    # An archive is a bulk import and gets its own, larger cap: it is streamed
    # to disk and its entries are read one at a time, so what it costs in memory
    # is the largest entry rather than the archive.
    is_archive = file.filename.endswith('.zip')
    limit = settings.MAX_ARCHIVE_SIZE if is_archive else settings.MAX_UPLOAD_SIZE
    spooled = await _spool_upload(file, limit)

    if is_archive:
        from app.services.flight_log_import import import_flight_log as do_import
        from app.database import get_telemetry_db
        try:
            # Off the event loop: this is minutes of synchronous parsing and
            # database work for a full export, and on the loop it would freeze
            # every other request in the app for the duration.
            return await run_in_threadpool(
                _import_zip_flight_logs, spooled, db, do_import, get_telemetry_db, admin.id)
        finally:
            spooled.close()

    try:
        content = spooled.read()
    finally:
        spooled.close()

    # Handle Excel files — route to Excel import
    if file.filename.endswith(EXCEL_EXTENSIONS):
        from app.services.excel_import import import_excel
        result = import_excel(db, content)
        result["format_detected"] = "excel"
        return result

    # Skydio flight-list CSV (multi-row export) — route to the bulk Skydio
    # importer, which creates pilots/vehicles/equipment. Without this, auto-detect
    # mistakes it for single-flight Litchi telemetry.
    if file.filename.endswith('.csv'):
        try:
            first_line = content.decode('utf-8-sig').splitlines()[0]
        except (UnicodeDecodeError, IndexError):
            first_line = ""
        cols = {c.strip() for c in first_line.split(",")}

        # BRINC flight-list CSV (multi-row export, no telemetry). Same shape as
        # the Skydio list export, so it is routed to a bulk importer rather than
        # the single-flight log path.
        from app.services.brinc_import import is_brinc_csv
        if is_brinc_csv(cols):
            from app.services.brinc_import import import_brinc_csv
            result = import_brinc_csv(db, content)
            result["format_detected"] = "brinc_csv"
            return result

        if {SKYDIO_FLIGHT_ID_COL, "Vehicle", "Pilot"} <= cols and (SKYDIO_LOCAL_TAKEOFF_COL in cols or "Takeoff" in cols):
            from app.services.excel_import import import_skydio_csv
            result = import_skydio_csv(db, content)
            result["format_detected"] = "skydio_csv"
            return result

    from app.services.flight_log_import import import_flight_log as do_import
    from app.database import get_telemetry_db

    telemetry_db = next(get_telemetry_db())
    try:
        result = do_import(content, db, telemetry_db, format_hint=format, user_id=admin.id)
    finally:
        telemetry_db.close()

    if result.get("error"):
        raise HTTPException(400, result["error"])

    return result


@router.get("/flights/{flight_id}/gpx", responses=responses(404))
def export_flight_gpx(
    flight_id: int,
    db: DBSession,
    user: CurrentUser,
):
    """Export a flight's telemetry as a GPX file for Google Earth / GPS tools."""
    from app.database import get_telemetry_db
    from app.models.telemetry import TelemetryPoint

    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(404, "Flight not found")

    tel_db = next(get_telemetry_db())
    try:
        points = tel_db.query(TelemetryPoint).filter(
            TelemetryPoint.flight_id == flight_id
        ).order_by(TelemetryPoint.timestamp_ms).all()
    finally:
        tel_db.close()

    if not points:
        raise HTTPException(404, "No telemetry data for this flight")

    gpx = ET.Element("gpx", version="1.1", creator=APP_TITLE,
                     xmlns="http://www.topografix.com/GPX/1/1")

    metadata = ET.SubElement(gpx, "metadata")
    ET.SubElement(metadata, "name").text = f"Flight {flight.external_id or flight.id}"
    ET.SubElement(metadata, "time").text = (flight.takeoff_time or flight.created_at).isoformat()

    trk = ET.SubElement(gpx, "trk")
    ET.SubElement(trk, "name").text = f"Flight {flight.external_id or flight.id}"
    if flight.purpose:
        ET.SubElement(trk, "desc").text = flight.purpose

    trkseg = ET.SubElement(trk, "trkseg")
    for pt in points:
        if pt.lat is None or pt.lon is None:
            continue
        trkpt = ET.SubElement(trkseg, "trkpt", lat=str(pt.lat), lon=str(pt.lon))
        if pt.altitude_m is not None:
            ET.SubElement(trkpt, "ele").text = str(round(pt.altitude_m, 2))
        ts = datetime.fromtimestamp(pt.timestamp_ms / 1000, tz=timezone.utc)
        ET.SubElement(trkpt, "time").text = ts.isoformat()
        if pt.speed_mps is not None:
            extensions = ET.SubElement(trkpt, "extensions")
            ET.SubElement(extensions, "speed").text = str(round(pt.speed_mps, 2))

    xml_bytes = ET.tostring(gpx, encoding="unicode", xml_declaration=True)
    flight_date = flight.date.isoformat() if flight.date else "unknown"
    filename = f"flight_{flight_id}_{flight_date}.gpx"

    return StreamingResponse(
        io.BytesIO(xml_bytes.encode("utf-8")),
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/flights/{flight_id}/kml", responses=responses(404))
def export_flight_kml(
    flight_id: int,
    db: DBSession,
    user: CurrentUser,
):
    """Export a flight's telemetry as a KML file for Google Earth."""
    from app.database import get_telemetry_db
    from app.models.telemetry import TelemetryPoint

    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(404, "Flight not found")

    tel_db = next(get_telemetry_db())
    try:
        points = tel_db.query(TelemetryPoint).filter(
            TelemetryPoint.flight_id == flight_id
        ).order_by(TelemetryPoint.timestamp_ms).all()
    finally:
        tel_db.close()

    if not points:
        raise HTTPException(404, "No telemetry data for this flight")

    kml_ns = "http://www.opengis.net/kml/2.2"
    kml = ET.Element("kml", xmlns=kml_ns)
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = f"Flight {flight.external_id or flight.id}"

    desc_parts = []
    if flight.purpose:
        desc_parts.append(f"Purpose: {flight.purpose}")
    if flight.date:
        desc_parts.append(f"Date: {flight.date.isoformat()}")
    if flight.duration_seconds:
        mins = flight.duration_seconds // 60
        secs = flight.duration_seconds % 60
        desc_parts.append(f"Duration: {mins}m {secs}s")
    if desc_parts:
        ET.SubElement(doc, "description").text = "\n".join(desc_parts)

    # Style for the flight path line
    style = ET.SubElement(doc, "Style", id="flightPath")
    line_style = ET.SubElement(style, "LineStyle")
    ET.SubElement(line_style, "color").text = "ff0000ff"  # Red in ABGR
    ET.SubElement(line_style, "width").text = "3"

    placemark = ET.SubElement(doc, "Placemark")
    ET.SubElement(placemark, "name").text = "Flight Path"
    ET.SubElement(placemark, "styleUrl").text = "#flightPath"

    linestring = ET.SubElement(placemark, "LineString")
    ET.SubElement(linestring, "altitudeMode").text = "absolute"

    coords = []
    for pt in points:
        if pt.lat is None or pt.lon is None:
            continue
        alt = pt.altitude_m if pt.altitude_m is not None else 0
        coords.append(f"{pt.lon},{pt.lat},{alt}")

    ET.SubElement(linestring, "coordinates").text = "\n".join(coords)

    xml_bytes = ET.tostring(kml, encoding="unicode", xml_declaration=True)
    flight_date = flight.date.isoformat() if flight.date else "unknown"
    filename = f"flight_{flight_id}_{flight_date}.kml"

    return StreamingResponse(
        io.BytesIO(xml_bytes.encode("utf-8")),
        media_type="application/vnd.google-earth.kml+xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
