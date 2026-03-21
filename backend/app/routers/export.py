"""CSV/JSON export and Excel/CSV import endpoints."""
import csv
import io
import json
from datetime import date

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.user import User
from app.routers.auth import get_current_user, require_admin

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/flights/csv")
def export_flights_csv(
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Flight)
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
        pilot = db.query(Pilot).filter(Pilot.id == f.pilot_id).first() if f.pilot_id else None
        vehicle = db.query(Vehicle).filter(Vehicle.id == f.vehicle_id).first() if f.vehicle_id else None
        writer.writerow([
            f.date, pilot.full_name if pilot else "",
            f"{vehicle.manufacturer} {vehicle.model}" if vehicle else "",
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
            # Try to match pilot by name
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
