import csv
import io
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
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
from app.config import settings
from app.constants import APP_TITLE
from app.deps import DBSession, CurrentUser, AdminUser
from app.responses import responses

router = APIRouter(prefix="/api/export", tags=["export"])

CSV_MEDIA_TYPE = "text/csv"

# CSV column header constants (S1192 - duplicated strings)
COL_CASE_NUMBER = COL_CASE_NUMBER
COL_ENTITY_TYPE = COL_ENTITY_TYPE
COL_ENTITY_ID = COL_ENTITY_ID


@router.get("/flights/csv")
def export_flights_csv(
    db: DBSession,
    user: CurrentUser,
    date_from: date | None = None,
    date_to: date | None = None):
    q = db.query(Flight).options(joinedload(Flight.pilot), joinedload(Flight.vehicle))
    if date_from:
        q = q.filter(Flight.date >= date_from)
    if date_to:
        q = q.filter(Flight.date <= date_to)
    flights = q.order_by(Flight.date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Pilot", "Vehicle", "Purpose", "Duration (s)", "Takeoff Address",
        "Takeoff Lat", "Takeoff Lon", "Max Altitude (m)", "Max Speed (m/s)",
        "Distance (m)", COL_CASE_NUMBER, "Review Status", "Notes",
    ])
    for f in flights:
        writer.writerow([
            f.date, f.pilot.full_name if f.pilot else "",
            f"{f.vehicle.manufacturer} {f.vehicle.model}" if f.vehicle else "",
            f.purpose or "", f.duration_seconds or "", f.takeoff_address or "",
            f.takeoff_lat or "", f.takeoff_lon or "",
            f.max_altitude_m or "", f.max_speed_mps or "",
            f.distance_m or "", f.case_number or "", f.review_status, f.notes or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=flights_export.csv"},
    )


@router.get("/pilots/csv", responses=responses(401))
def export_pilots_csv(db: DBSession, user: CurrentUser):
    pilots = db.query(Pilot).order_by(Pilot.last_name).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["First Name", "Last Name", "Email", "Phone", "Badge Number", "Status", "Notes"])
    for p in pilots:
        writer.writerow([p.first_name, p.last_name, p.email or "", p.phone or "", p.badge_number or "", p.status, p.notes or ""])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=pilots_export.csv"},
    )


@router.get("/vehicles/csv", responses=responses(401))
def export_vehicles_csv(db: DBSession, user: CurrentUser):
    vehicles = db.query(Vehicle).order_by(Vehicle.manufacturer).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Serial", "Manufacturer", "Model", "Nickname", "FAA Reg", "Status", "Flights", "Hours"])
    for v in vehicles:
        writer.writerow([v.serial_number, v.manufacturer, v.model, v.nickname or "", v.faa_registration or "", v.status, v.total_flights, round(v.total_flight_hours, 1)])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=vehicles_export.csv"},
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
    records = q.order_by(MaintenanceRecord.performed_date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        COL_ENTITY_TYPE, COL_ENTITY_ID, "Maintenance Type", "Description",
        "Performed By", "Performed Date", "Next Due Date", "Cost", "Notes",
    ])
    for r in records:
        writer.writerow([
            r.entity_type, r.entity_id, r.maintenance_type, r.description or "",
            r.performed_by or "", r.performed_date or "", r.next_due_date or "",
            r.cost or "", r.notes or "",
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
    completions = db.query(ChecklistCompletion).order_by(ChecklistCompletion.completed_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Pilot", "Vehicle", "Template", "Passed", "Notes"])
    for c in completions:
        pilot = db.query(Pilot).filter(Pilot.id == c.pilot_id).first()
        vehicle = db.query(Vehicle).filter(Vehicle.id == c.vehicle_id).first() if c.vehicle_id else None
        template = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == c.template_id).first()
        writer.writerow([
            c.completed_at.strftime("%Y-%m-%d %H:%M") if c.completed_at else "",
            pilot.full_name if pilot else "",
            f"{vehicle.manufacturer} {vehicle.model}" if vehicle else "",
            template.name if template else "",
            "Yes" if c.all_passed else "No",
            c.notes or "",
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
    certs = q.all()

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
            pilot.full_name if pilot else "",
            cert_type.name if cert_type else "",
            cert_type.category if cert_type else "",
            c.status,
            c.issue_date or "", c.expiration_date or "",
            c.certificate_number or "", c.notes or "",
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
    logs = q.order_by(TrainingLog.date.desc()).all()

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
            t.date, t.title, t.training_type, t.instructor or "",
            t.location or "", t.man_hours, t.outcome,
            "; ".join(pilot_names), t.description or "", t.notes or "",
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
    logs = q.order_by(MissionLog.date.desc()).all()

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
            m.date, m.title, m.reason or "", m.location or "",
            m.case_number or "", m.man_hours, m.status,
            "; ".join(pilot_names), m.description or "", m.notes or "",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=mission_logs_export.csv"},
    )


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
    incidents = q.order_by(Incident.date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Title", "Pilot", "Report Type", "Severity", "Category", "Description",
        "Location", "Status", "Resolution", "Equipment Grounded",
        "Damage Description", "Estimated Cost", "Notes",
    ])
    for inc in incidents:
        pilot = db.query(Pilot).filter(Pilot.id == inc.pilot_id).first() if inc.pilot_id else None
        writer.writerow([
            inc.date, inc.title, pilot.full_name if pilot else "",
            getattr(inc, 'report_type', 'incident') or 'incident',
            inc.severity, inc.category, inc.description or "",
            inc.location or "", inc.status, inc.resolution or "",
            "Yes" if inc.equipment_grounded else "No",
            inc.damage_description or "", inc.estimated_cost or "", inc.notes or "",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=incidents_export.csv"},
    )


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
    plans = q.order_by(FlightPlan.date_planned.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Title", "Date Planned", "Pilot", "Vehicle", "Location", "Purpose",
        COL_CASE_NUMBER, "Status", "Max Altitude", "Est Duration (min)", "Notes",
    ])
    for p in plans:
        pilot = db.query(Pilot).filter(Pilot.id == p.pilot_id).first() if p.pilot_id else None
        vehicle = db.query(Vehicle).filter(Vehicle.id == p.vehicle_id).first() if p.vehicle_id else None
        writer.writerow([
            p.title, p.date_planned,
            pilot.full_name if pilot else "",
            f"{vehicle.manufacturer} {vehicle.model}" if vehicle else "",
            p.location or "", p.purpose or "", p.case_number or "",
            p.status, p.max_altitude_planned or "", p.estimated_duration_min or "",
            p.notes or "",
        ])
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
            log.user_name or "", log.action, log.entity_type,
            log.entity_id or "", log.entity_name or "",
            log.details or "", log.ip_address or "",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=audit_log_export.csv"},
    )


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
    checkouts = q.order_by(EquipmentCheckout.checked_out_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        COL_ENTITY_TYPE, "Entity Name", "Checked Out By", "Checked Out At",
        "Expected Return", "Checked In At", "Condition Out", "Condition In",
        "Notes Out", "Notes In",
    ])
    for c in checkouts:
        pilot_out = db.query(Pilot).filter(Pilot.id == c.checked_out_by_id).first() if c.checked_out_by_id else None
        writer.writerow([
            c.entity_type, c.entity_name or "",
            pilot_out.full_name if pilot_out else "",
            c.checked_out_at.strftime("%Y-%m-%d %H:%M") if c.checked_out_at else "",
            c.expected_return.strftime("%Y-%m-%d %H:%M") if c.expected_return else "",
            c.checked_in_at.strftime("%Y-%m-%d %H:%M") if c.checked_in_at else "",
            c.condition_out or "", c.condition_in or "",
            c.notes_out or "", c.notes_in or "",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=equipment_checkouts_export.csv"},
    )


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

    imported = 0
    errors = []
    for i, row in enumerate(reader):
        try:
            flight = Flight(
                date=row.get("Date") or None,
                purpose=row.get("Purpose") or None,
                duration_seconds=int(row["Duration (s)"]) if row.get("Duration (s)") else None,
                takeoff_address=row.get("Takeoff Address") or None,
                takeoff_lat=float(row["Takeoff Lat"]) if row.get("Takeoff Lat") else None,
                takeoff_lon=float(row["Takeoff Lon"]) if row.get("Takeoff Lon") else None,
                max_altitude_m=float(row["Max Altitude (m)"]) if row.get("Max Altitude (m)") else None,
                max_speed_mps=float(row["Max Speed (m/s)"]) if row.get("Max Speed (m/s)") else None,
                case_number=row.get(COL_CASE_NUMBER) or None,
                notes=row.get("Notes") or None,
                review_status="reviewed",
                pilot_confirmed=True,
            )
            pilot_name = row.get("Pilot", "").strip()
            if pilot_name:
                parts = pilot_name.split(" ", 1)
                if len(parts) == 2:
                    pilot = db.query(Pilot).filter(
                        Pilot.first_name == parts[0], Pilot.last_name == parts[1]
                    ).first()
                    if pilot:
                        flight.pilot_id = pilot.id

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
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Only Excel files (.xlsx) are supported")
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB")
    from app.services.excel_import import import_excel
    result = import_excel(db, content)
    return result


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
    if not file.filename.endswith(('.txt', '.csv', '.json', '.zip')):
        raise HTTPException(400, "Only .txt, .csv, .json, and .zip files are supported")

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB")

    from app.services.dji_import import import_flight_log as do_import
    from app.database import get_telemetry_db

    # Handle ZIP files (bulk import)
    if file.filename.endswith('.zip'):
        import zipfile

        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            json_files = [n for n in zf.namelist() if n.endswith('.json') and not n.startswith('__')]
            results = {"total": len(json_files), "imported": 0, "skipped": 0, "errors": []}

            for fname in json_files:
                try:
                    file_content = zf.read(fname)
                    telemetry_db = next(get_telemetry_db())
                    try:
                        result = do_import(file_content, db, telemetry_db, format_hint="airdata_json", user_id=admin.id)
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
