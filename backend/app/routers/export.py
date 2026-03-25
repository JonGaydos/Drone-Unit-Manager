import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.user import User
from app.models.maintenance import MaintenanceRecord
from app.models.certification import PilotCertification, CertificationType
from app.models.training_log import TrainingLog
from app.models.training_log_pilot import TrainingLogPilot
from app.models.mission_log import MissionLog
from app.models.mission_log_pilot import MissionLogPilot
from app.routers.auth import get_current_user, require_admin

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/flights/csv")
def export_flights_csv(
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
        "Distance (m)", "Case Number", "Review Status", "Notes",
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
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=flights_export.csv"},
    )


@router.get("/pilots/csv")
def export_pilots_csv(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pilots = db.query(Pilot).order_by(Pilot.last_name).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["First Name", "Last Name", "Email", "Phone", "Badge Number", "Status", "Notes"])
    for p in pilots:
        writer.writerow([p.first_name, p.last_name, p.email or "", p.phone or "", p.badge_number or "", p.status, p.notes or ""])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=pilots_export.csv"},
    )


@router.get("/vehicles/csv")
def export_vehicles_csv(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    vehicles = db.query(Vehicle).order_by(Vehicle.manufacturer).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Serial", "Manufacturer", "Model", "Nickname", "FAA Reg", "Status", "Flights", "Hours"])
    for v in vehicles:
        writer.writerow([v.serial_number, v.manufacturer, v.model, v.nickname or "", v.faa_registration or "", v.status, v.total_flights, round(v.total_flight_hours, 1)])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=vehicles_export.csv"},
    )


@router.get("/maintenance/csv")
def export_maintenance_csv(
    date_from: date | None = None,
    date_to: date | None = None,
    entity_type: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
        "Entity Type", "Entity ID", "Maintenance Type", "Description",
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
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=maintenance_export.csv"},
    )


@router.get("/checklists/csv")
def export_checklists_csv(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
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
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=checklists_export.csv"},
    )


@router.get("/certifications/csv")
def export_certifications_csv(
    pilot_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=certifications_export.csv"},
    )


@router.get("/training-logs/csv")
def export_training_logs_csv(
    date_from: date | None = None,
    date_to: date | None = None,
    pilot_id: int | None = None,
    training_type: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=training_logs_export.csv"},
    )


@router.get("/mission-logs/csv")
def export_mission_logs_csv(
    date_from: date | None = None,
    date_to: date | None = None,
    pilot_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
        "Date", "Title", "Reason", "Location", "Case Number",
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
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=mission_logs_export.csv"},
    )


@router.post("/flights/import")
async def import_flights_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if not file.filename.endswith('.csv'):
        raise HTTPException(400, "Only CSV files are supported")

    content = await file.read()
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
                case_number=row.get("Case Number") or None,
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


@router.post("/excel/import")
async def import_excel_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Only Excel files (.xlsx) are supported")
    content = await file.read()
    from app.services.excel_import import import_excel
    result = import_excel(db, content)
    return result
