import csv
import io
import logging
from datetime import datetime, date
from typing import Optional

import openpyxl
from sqlalchemy.orm import Session

from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.flight import Flight, FlightPurpose
from app.models.certification import CertificationType, PilotCertification, PilotEquipmentQual

logger = logging.getLogger(__name__)


def _parse_date(val) -> Optional[date]:
    if val is None or val == "Pending" or val == "N/A" or val == "":
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                continue
    return None


def _parse_status(val) -> str:
    if val is None or val == "" or val == "Pending":
        return "pending"
    if isinstance(val, datetime) or isinstance(val, date):
        return "complete"
    s = str(val).strip().lower()
    status_map = {
        "complete": "complete",
        "issued": "complete",
        "active": "active",
        "in progress": "in_progress",
        "pending": "pending",
        "not started": "not_started",
        "not issued": "not_issued",
        "not eligible": "not_eligible",
        "n/a": "not_eligible",
        "exempt": "complete",
    }
    return status_map.get(s, "pending")


def _find_or_create_pilot(db: Session, identifier: str) -> tuple[Optional[Pilot], bool]:
    """Find or create a pilot from a 'First Last' name or an email address.

    Skydio exports the pilot as an email, so when the value looks like an email
    we match (and store) by email; otherwise we fall back to name matching.
    Returns (pilot, was_created).
    """
    if not identifier or identifier.strip() == "":
        return None, False
    value = identifier.strip()
    if "@" in value:
        return _find_or_create_pilot_by_email(db, value)
    parts = value.split(" ", 1)
    first = parts[0]
    last = parts[1] if len(parts) > 1 else ""
    pilot = db.query(Pilot).filter(Pilot.first_name == first, Pilot.last_name == last).first()
    if not pilot:
        pilot = Pilot(first_name=first, last_name=last, status="active")
        db.add(pilot)
        db.flush()
        return pilot, True
    return pilot, False


def _find_or_create_pilot_by_email(db: Session, email: str) -> tuple[Optional[Pilot], bool]:
    """Match a pilot by email (case-insensitive); create one if absent.

    The Skydio CSV carries no human name, so a new pilot is created with a
    placeholder name derived from the email local part for the user to edit.
    """
    pilot = db.query(Pilot).filter(Pilot.email.ilike(email)).first()
    if pilot:
        return pilot, False
    local = email.split("@", 1)[0]
    if "." in local or "_" in local:
        bits = local.replace("_", ".").split(".", 1)
        first = bits[0].capitalize()
        last = bits[1].capitalize() if len(bits) > 1 else ""
    else:
        first = local
        last = ""
    pilot = Pilot(first_name=first, last_name=last, email=email, status="active")
    db.add(pilot)
    db.flush()
    return pilot, True


def _find_or_create_vehicle(db: Session, vehicle_str: str) -> tuple[Optional[Vehicle], bool]:
    """Returns (vehicle, was_created)."""
    if not vehicle_str or vehicle_str.strip() == "":
        return None, False
    serial = vehicle_str.strip()
    vehicle = db.query(Vehicle).filter(Vehicle.serial_number == serial).first()
    if not vehicle:
        manufacturer = "Skydio"
        model = serial
        if "X10" in serial:
            model = "X10"
        elif "X2" in serial:
            model = "X2E"
        elif "BRINC" in serial or "LEMUR" in serial:
            manufacturer = "BRINC"
            model = "LEMUR 2"
        vehicle = Vehicle(
            serial_number=serial,
            manufacturer=manufacturer,
            model=model,
            status="active",
        )
        db.add(vehicle)
        db.flush()
        return vehicle, True
    return vehicle, False


def _ensure_cert_type(db: Session, name: str, category: str, has_expiration: bool = True,
                      renewal_months: Optional[int] = None) -> CertificationType:
    ct = db.query(CertificationType).filter(CertificationType.name == name).first()
    if not ct:
        ct = CertificationType(
            name=name, category=category, has_expiration=has_expiration,
            renewal_period_months=renewal_months, is_active=True,
        )
        db.add(ct)
        db.flush()
    return ct


def _ensure_purpose(db: Session, name: str):
    if not name or name.strip() == "":
        return
    existing = db.query(FlightPurpose).filter(FlightPurpose.name == name.strip()).first()
    if not existing:
        db.add(FlightPurpose(name=name.strip(), sort_order=100))
        db.flush()


def _parse_safe_float(val) -> Optional[float]:
    """Safely parse a float from a cell value."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


_DT_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y %I:%M %p",
)


def _parse_dt(val) -> Optional[datetime]:
    """Parse a datetime from an Excel cell (already a datetime) or a CSV string."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day)
    s = str(val).strip()
    if not s or s.upper() == "N/A":
        return None
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _clean(val) -> Optional[str]:
    """Normalize a cell to a non-empty string, treating blank / N/A as None."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.upper() in ("N/A", "NONE", "NA", "-", "--"):
        return None
    return s


def _is_duplicate_flight(db: Session, flight_id: str, pilot, vehicle, takeoff_dt) -> bool:
    """Check if a flight is a duplicate.

    Primary check: normalized external_id (case-insensitive, hyphens stripped).
    Fallback check: exact takeoff timestamp + pilot + vehicle. Distinct same-day
    flights with merely similar durations are no longer treated as duplicates.
    """
    from sqlalchemy import func as sa_func
    existing = db.query(Flight).filter(
        sa_func.replace(sa_func.upper(Flight.external_id), "-", "") == flight_id
    ).first()
    if existing:
        return True

    if takeoff_dt:
        potential = db.query(Flight).filter(
            Flight.takeoff_time == takeoff_dt,
            Flight.pilot_id == (pilot.id if pilot else None),
            Flight.vehicle_id == (vehicle.id if vehicle else None),
        ).first()
        if potential:
            logger.info(
                "excel_import: skipping flight %s as duplicate "
                "(takeoff %s, pilot_id=%s, vehicle_id=%s matches existing flight %s)",
                flight_id, takeoff_dt,
                pilot.id if pilot else None,
                vehicle.id if vehicle else None,
                potential.id,
            )
            return True

    return False


def _build_flight_from_row(row: dict, flight_id: str, pilot, vehicle, db: Session,
                           source: str = "skydio_csv") -> Optional[Flight]:
    """Build a Flight object from a Skydio row dict (xlsx cell values or CSV strings).

    Returns None if the flight is a duplicate.
    """
    takeoff_dt = _parse_dt(row.get("Takeoff") or row.get("Local Takeoff Time"))
    landing_dt = _parse_dt(row.get("Land"))
    flight_date = takeoff_dt.date() if takeoff_dt else None
    duration_f = _parse_safe_float(row.get("Duration (seconds)"))
    duration = int(duration_f) if duration_f is not None else None

    if _is_duplicate_flight(db, flight_id, pilot, vehicle, takeoff_dt):
        return None

    purpose = _clean(row.get("Purpose"))
    if purpose:
        _ensure_purpose(db, purpose)

    return Flight(
        external_id=str(flight_id),
        api_provider=source,
        pilot_id=pilot.id if pilot else None,
        vehicle_id=vehicle.id if vehicle else None,
        date=flight_date,
        takeoff_time=takeoff_dt,
        landing_time=landing_dt,
        duration_seconds=duration,
        takeoff_lat=_parse_safe_float(row.get("Takeoff Latitude")),
        takeoff_lon=_parse_safe_float(row.get("Takeoff Longitude")),
        takeoff_address=_clean(row.get("Takeoff Address")) or "",
        purpose=purpose,
        battery_serial=_clean(row.get("Battery")),
        sensor_package=_clean(row.get("Sensor Package")),
        attachment_top=_clean(row.get("Attachment (TOP)")),
        attachment_bottom=_clean(row.get("Attachment (BOTTOM)")),
        attachment_left=_clean(row.get("Attachment (LEFT)")),
        attachment_right=_clean(row.get("Attachment (RIGHT)")),
        carrier=_clean(row.get("Carrier(s)")),
        review_status="needs_review",
        pilot_confirmed=True,
        data_source=source,
    )


def _process_skydio_row(row: dict, db: Session, result: dict,
                        source: str = "skydio_csv") -> tuple[bool, bool]:
    """Process one Skydio flight row from either an xlsx sheet or a CSV.

    Finds or creates the pilot, vehicle, and equipment records, then builds and
    adds the flight (skipping duplicates). Returns (pilot_created, vehicle_created).
    """
    flight_id = row.get("Flight ID")
    if not flight_id:
        return False, False
    flight_id = str(flight_id).upper().replace("-", "")

    pilot, pilot_new = _find_or_create_pilot(db, row.get("Pilot") or "")
    vehicle, vehicle_new = _find_or_create_vehicle(db, row.get("Vehicle") or "")

    flight = _build_flight_from_row(row, flight_id, pilot, vehicle, db, source)
    if flight is None:
        result["flights_skipped"] += 1
        return pilot_new, vehicle_new

    db.add(flight)
    try:
        from app.services.sync_manager import _ensure_equipment_records
        _ensure_equipment_records(db, flight)
    except Exception:
        pass
    result["flights_imported"] += 1
    return pilot_new, vehicle_new


def _import_skydio_sheet(ws, db: Session, result: dict) -> tuple[int, int]:
    """Import flights from the Skydio sheet. Returns (pilots_created, vehicles_created)."""
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    pilots_created = 0
    vehicles_created = 0

    for r in range(2, ws.max_row + 1):
        try:
            row = {headers[c]: ws.cell(r, c + 1).value for c in range(len(headers))}
            pilot_new, vehicle_new = _process_skydio_row(row, db, result, source="excel_import")
            pilots_created += int(pilot_new)
            vehicles_created += int(vehicle_new)
        except Exception as e:
            result["errors"].append(f"Skydio row {r}: {str(e)}")

    return pilots_created, vehicles_created


def _new_import_result() -> dict:
    return {
        "pilots_created": 0,
        "vehicles_created": 0,
        "flights_imported": 0,
        "flights_skipped": 0,
        "certifications_created": 0,
        "cert_assignments": 0,
        "errors": [],
    }


def import_skydio_csv(db: Session, file_bytes: bytes) -> dict:
    """Import a Skydio flight-list CSV export.

    Creates pilots (matched by email), vehicles, batteries, sensor packages, and
    attachments that do not already exist, parses takeoff/landing times, and
    deduplicates by Flight ID.
    """
    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    result = _new_import_result()
    pilots_created = 0
    vehicles_created = 0

    for i, row in enumerate(reader, start=2):
        try:
            pilot_new, vehicle_new = _process_skydio_row(db=db, row=row, result=result, source="skydio_csv")
            pilots_created += int(pilot_new)
            vehicles_created += int(vehicle_new)
        except Exception as e:
            result["errors"].append(f"Row {i}: {str(e)}")

    result["pilots_created"] = pilots_created
    result["vehicles_created"] = vehicles_created
    result["imported"] = result["flights_imported"]
    db.commit()
    return result


# Certification definitions and column mapping for Pilot Info sheet
_CERT_DEFS = [
    ("Skydio X2E Academy", "equipment", False, None),
    ("Skydio X2E Checkoff", "equipment", False, None),
    ("Skydio X10 Academy", "equipment", False, None),
    ("Skydio X10 Checkoff", "equipment", False, None),
    ("BRINC LEMUR 2 Academy", "equipment", False, None),
    ("BRINC LEMUR 2 Checkoff", "equipment", False, None),
    ("NIST Level 1", "nist", False, None),
    ("NIST Level 2", "nist", False, None),
    ("NIST Level 3", "nist", False, None),
    ("NIST Level 4", "nist", False, None),
    ("NIST Level 5", "nist", False, None),
    ("DART Training", "training", False, None),
    ("GCSC Training", "training", False, None),
    ("Insurance 2026", "insurance", True, 12),
    ("Insurance 2027", "insurance", True, 12),
    ("FAA Part 107", "faa", True, 24),
]

_COL_MAP = {
    3: "Skydio X2E Academy", 4: "Skydio X2E Checkoff",
    5: "Skydio X10 Academy", 6: "Skydio X10 Checkoff",
    7: "BRINC LEMUR 2 Academy", 8: "BRINC LEMUR 2 Checkoff",
    9: "NIST Level 1", 10: "NIST Level 2", 11: "NIST Level 3",
    12: "NIST Level 4", 13: "NIST Level 5",
    14: "DART Training", 15: "GCSC Training",
    16: "Insurance 2026", 17: "Insurance 2027",
}


def _assign_cert_columns(db: Session, pilot: Pilot, ws, r: int, col_map: dict, cert_types: dict, result: dict):
    """Assign certifications from column-mapped cells for a single pilot row."""
    for col, cert_name in col_map.items():
        val = ws.cell(r, col).value
        ct = cert_types.get(cert_name)
        if not ct:
            continue

        existing = db.query(PilotCertification).filter(
            PilotCertification.pilot_id == pilot.id,
            PilotCertification.certification_type_id == ct.id,
        ).first()
        if existing:
            continue

        pc = PilotCertification(
            pilot_id=pilot.id,
            certification_type_id=ct.id,
            status=_parse_status(val),
            issue_date=_parse_date(val),
        )
        db.add(pc)
        result["cert_assignments"] += 1


def _assign_faa_part107(db: Session, pilot: Pilot, ws, r: int, cert_types: dict, result: dict):
    """Assign FAA Part 107 certification for a pilot row."""
    ct_faa = cert_types.get("FAA Part 107")
    if not ct_faa:
        return

    existing = db.query(PilotCertification).filter(
        PilotCertification.pilot_id == pilot.id,
        PilotCertification.certification_type_id == ct_faa.id,
    ).first()
    if existing:
        return

    part107_date = _parse_date(ws.cell(r, 19).value)
    renewal_due = _parse_date(ws.cell(r, 20).value)
    renewed_date = _parse_date(ws.cell(r, 21).value)
    renewal_due_2 = _parse_date(ws.cell(r, 22).value)

    faa_status = "active" if part107_date else "pending"
    if renewal_due and not renewed_date and renewal_due < date.today():
        faa_status = "expired"

    pc = PilotCertification(
        pilot_id=pilot.id,
        certification_type_id=ct_faa.id,
        status=faa_status,
        issue_date=renewed_date or part107_date,
        expiration_date=renewal_due_2 or renewal_due,
    )
    db.add(pc)
    result["cert_assignments"] += 1


def _import_pilot_info_sheet(ws, db: Session, result: dict) -> int:
    """Import pilot certifications from the Pilot Info sheet. Returns pilots_created count."""
    cert_types = {}
    for name, cat, has_exp, months in _CERT_DEFS:
        ct = _ensure_cert_type(db, name, cat, has_exp, months)
        cert_types[name] = ct
        result["certifications_created"] += 1

    pilots_created = 0

    for r in range(7, ws.max_row + 1):
        name = ws.cell(r, 1).value
        if not name or str(name).strip() == "" or "STATUS KEY" in str(name):
            continue

        try:
            pilot, pilot_new = _find_or_create_pilot(db, str(name))
            if pilot_new:
                pilots_created += 1
            if not pilot:
                continue

            status_val = ws.cell(r, 2).value
            if status_val:
                pilot.status = "active" if str(status_val).lower() == "active" else "inactive"

            _assign_cert_columns(db, pilot, ws, r, _COL_MAP, cert_types, result)
            _assign_faa_part107(db, pilot, ws, r, cert_types, result)

        except Exception as e:
            result["errors"].append(f"Pilot Info row {r}: {str(e)}")

    return pilots_created


def import_excel(db: Session, file_bytes: bytes) -> dict:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    pilots_created_count = 0
    vehicles_created_count = 0
    result = {
        "pilots_created": 0,
        "vehicles_created": 0,
        "flights_imported": 0,
        "flights_skipped": 0,
        "certifications_created": 0,
        "cert_assignments": 0,
        "errors": [],
    }

    if "Skydio" in wb.sheetnames:
        p_count, v_count = _import_skydio_sheet(wb["Skydio"], db, result)
        pilots_created_count += p_count
        vehicles_created_count += v_count

    if "Pilot Info" in wb.sheetnames:
        pilots_created_count += _import_pilot_info_sheet(wb["Pilot Info"], db, result)

    result["pilots_created"] = pilots_created_count
    result["vehicles_created"] = vehicles_created_count

    db.commit()
    return result
