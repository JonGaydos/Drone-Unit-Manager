"""Full backup export and import for Drone Unit Manager.

Export creates a ZIP with manifest, JSON database dump, and uploaded files.
Import requires a fresh install (no users) and restores everything.
"""

import io
import json
import logging
import os
import tempfile
import zipfile
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.types import Date, DateTime

from app.config import settings as app_settings
from app.database import SessionLocal, TelemetrySessionLocal
from app.deps import DBSession, AdminUser
from app.models.user import User
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.flight import Flight, FlightPurpose
from app.models.battery import Battery
from app.models.battery_reading import BatteryReading
from app.models.controller import Controller
from app.models.sensor import SensorPackage
from app.models.attachment import Attachment
from app.models.dock import Dock
from app.models.certification import CertificationType, PilotCertification, PilotEquipmentQual
from app.models.maintenance import MaintenanceRecord
from app.models.maintenance_schedule import MaintenanceSchedule
from app.models.document import Document
from app.models.media import MediaFile
from app.models.alert import Alert
from app.models.report import SavedReport
from app.models.setting import Setting
from app.models.mission_log import MissionLog
from app.models.mission_log_pilot import MissionLogPilot
from app.models.training_log import TrainingLog
from app.models.training_log_pilot import TrainingLogPilot
from app.models.vehicle_registration import VehicleRegistration
from app.models.photo import Photo, PhotoPilot
from app.models.folder import Folder
from app.models.audit_log import AuditLog
from app.models.incident import Incident
from app.models.flight_approval import FlightPlan
from app.models.currency_rule import CurrencyRule
from app.models.equipment_checkout import EquipmentCheckout
from app.models.checklist import ChecklistTemplate, ChecklistCompletion
from app.models.component import Component
from app.models.geofence import Geofence
from app.models.notification_preference import NotificationPreference
from app.models.notification_log import NotificationLog
from app.models.telemetry import TelemetryPoint
from app.responses import responses

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backup", tags=["backup"])

APP_VERSION = "2.2.0"

# Tables in FK-dependency order (parents before children)
EXPORT_ORDER = [
    # Tier 1: No foreign keys
    ("settings", Setting),
    ("folders", Folder),
    ("flight_purposes", FlightPurpose),
    ("certification_types", CertificationType),
    ("currency_rules", CurrencyRule),
    ("geofences", Geofence),
    # Tier 2: Base entities
    ("pilots", Pilot),
    ("users", User),
    ("vehicles", Vehicle),
    ("batteries", Battery),
    ("controllers", Controller),
    ("sensor_packages", SensorPackage),
    ("attachments", Attachment),
    ("docks", Dock),
    # Tier 3: FK to base entities
    ("pilot_certifications", PilotCertification),
    ("pilot_equipment_quals", PilotEquipmentQual),
    ("vehicle_registrations", VehicleRegistration),
    ("components", Component),
    # Tier 4: FK to pilots/vehicles
    ("flights", Flight),
    ("flight_plans", FlightPlan),
    ("mission_logs", MissionLog),
    ("training_logs", TrainingLog),
    # Tier 5: FK to flights/logs
    ("checklist_templates", ChecklistTemplate),
    ("checklist_completions", ChecklistCompletion),
    ("documents", Document),
    ("photos", Photo),
    ("photo_pilots", PhotoPilot),
    ("media_files", MediaFile),
    # Tier 6: FK to entities/flights
    ("maintenance_records", MaintenanceRecord),
    ("maintenance_schedules", MaintenanceSchedule),
    ("incidents", Incident),
    ("alerts", Alert),
    ("equipment_checkouts", EquipmentCheckout),
    # Tier 7: FK to logs
    ("mission_log_pilots", MissionLogPilot),
    ("training_log_pilots", TrainingLogPilot),
    # Tier 8: FK to users/batteries
    ("notification_preferences", NotificationPreference),
    ("notification_logs", NotificationLog),
    ("audit_logs", AuditLog),
    ("saved_reports", SavedReport),
    ("battery_readings", BatteryReading),
]


class _BackupEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime and date objects."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


def _get_columns(model_class):
    """Get column attribute names for a model."""
    return [c.key for c in sa_inspect(model_class).mapper.column_attrs]


def _serialize_table(db: Session, model_class) -> list[dict]:
    """Serialize all rows of a table to a list of dicts."""
    columns = _get_columns(model_class)
    rows = db.query(model_class).all()
    result = []
    for row in rows:
        row_dict = {}
        for col in columns:
            val = getattr(row, col)
            if isinstance(val, (datetime, date)):
                val = val.isoformat()
            row_dict[col] = val
        result.append(row_dict)
    return result


def _get_column_types(model_class) -> dict:
    """Get a mapping of column name -> SQLAlchemy type for datetime parsing."""
    mapper = sa_inspect(model_class)
    types = {}
    for col_attr in mapper.mapper.column_attrs:
        col = col_attr.columns[0]
        if isinstance(col.type, DateTime):
            types[col_attr.key] = "datetime"
        elif isinstance(col.type, Date):
            types[col_attr.key] = "date"
    return types


def _parse_rows(rows: list[dict], model_class) -> list[dict]:
    """Parse ISO datetime strings back to Python datetime/date objects."""
    col_types = _get_column_types(model_class)
    parsed = []
    for row in rows:
        parsed_row = {}
        for key, val in row.items():
            if val is not None and key in col_types:
                try:
                    if col_types[key] == "datetime":
                        parsed_row[key] = datetime.fromisoformat(val)
                    elif col_types[key] == "date":
                        parsed_row[key] = date.fromisoformat(val)
                except (ValueError, TypeError):
                    parsed_row[key] = val
            else:
                parsed_row[key] = val
        parsed.append(parsed_row)
    return parsed


@router.get("/export")
def export_backup(
    db: DBSession,
    admin: AdminUser,
    include_telemetry: bool = False,
):
    """Export a full backup as a ZIP file."""
    logger.info("Backup export started by user %s (include_telemetry=%s)", admin.display_name, include_telemetry)

    # Build manifest
    manifest = {
        "app_version": APP_VERSION,
        "export_date": datetime.now().isoformat(),
        "include_telemetry": include_telemetry,
        "tables": {},
    }

    # Serialize all main DB tables
    database = {}
    for table_name, model_class in EXPORT_ORDER:
        rows = _serialize_table(db, model_class)
        database[table_name] = rows
        manifest["tables"][table_name] = len(rows)
        logger.info("  Exported %s: %d rows", table_name, len(rows))

    # Serialize telemetry if requested
    telemetry_data = None
    if include_telemetry:
        tel_db = TelemetrySessionLocal()
        try:
            telemetry_data = _serialize_table(tel_db, TelemetryPoint)
            manifest["tables"]["telemetry_points"] = len(telemetry_data)
            logger.info("  Exported telemetry_points: %d rows", len(telemetry_data))
        finally:
            tel_db.close()

    # Create ZIP
    spooled = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024)
    with zipfile.ZipFile(spooled, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, cls=_BackupEncoder, indent=2))
        zf.writestr("database.json", json.dumps(database, cls=_BackupEncoder))

        if telemetry_data is not None:
            zf.writestr("telemetry.json", json.dumps(telemetry_data, cls=_BackupEncoder))

        # Add uploaded files
        upload_dir = str(app_settings.UPLOAD_DIR)
        if os.path.exists(upload_dir):
            for dirpath, _, filenames in os.walk(upload_dir):
                for fname in filenames:
                    full_path = os.path.join(dirpath, fname)
                    arc_name = "uploads/" + os.path.relpath(full_path, upload_dir).replace("\\", "/")
                    zf.write(full_path, arc_name)

    spooled.seek(0)

    today = date.today().isoformat()
    filename = f"drone_unit_manager_backup_{today}.zip"
    logger.info("Backup export complete: %s", filename)

    return StreamingResponse(
        spooled,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", responses=responses(400, 403))
async def import_backup(
    file: UploadFile = File(...),
):
    """Import a full backup from a ZIP file. Only works on fresh install (no users)."""
    db = SessionLocal()
    try:
        # Verify fresh install
        if db.query(User).count() > 0:
            raise HTTPException(403, "Import only available on fresh install (no existing users)")

        content = await file.read()
        if len(content) > 500 * 1024 * 1024:
            raise HTTPException(413, "Backup file too large (max 500MB)")

        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile:
            raise HTTPException(400, "Invalid ZIP file")

        if "manifest.json" not in zf.namelist():
            raise HTTPException(400, "Invalid backup: missing manifest.json")
        if "database.json" not in zf.namelist():
            raise HTTPException(400, "Invalid backup: missing database.json")

        manifest = json.loads(zf.read("manifest.json"))
        logger.info("Importing backup from %s (version %s)", manifest.get("export_date"), manifest.get("app_version"))

        database = json.loads(zf.read("database.json"))

        # Disable FK constraints for bulk import
        conn = db.connection()
        conn.execute(text("PRAGMA foreign_keys=OFF"))

        tables_imported = 0
        rows_imported = 0

        for table_name, model_class in EXPORT_ORDER:
            table_rows = database.get(table_name, [])
            if not table_rows:
                continue
            parsed = _parse_rows(table_rows, model_class)
            try:
                db.execute(model_class.__table__.insert(), parsed)
                tables_imported += 1
                rows_imported += len(parsed)
                logger.info("  Imported %s: %d rows", table_name, len(parsed))
            except Exception as e:
                logger.warning("  Failed to import %s: %s", table_name, e)

        conn.execute(text("PRAGMA foreign_keys=ON"))
        db.commit()

        # Import telemetry if present
        telemetry_imported = False
        if "telemetry.json" in zf.namelist():
            tel_db = TelemetrySessionLocal()
            try:
                tel_data = json.loads(zf.read("telemetry.json"))
                if tel_data:
                    parsed_tel = _parse_rows(tel_data, TelemetryPoint)
                    # Insert in chunks of 5000
                    chunk_size = 5000
                    for i in range(0, len(parsed_tel), chunk_size):
                        chunk = parsed_tel[i:i + chunk_size]
                        tel_db.execute(TelemetryPoint.__table__.insert(), chunk)
                    tel_db.commit()
                    telemetry_imported = True
                    rows_imported += len(parsed_tel)
                    logger.info("  Imported telemetry: %d points", len(parsed_tel))
            except Exception as e:
                logger.warning("  Failed to import telemetry: %s", e)
            finally:
                tel_db.close()

        # Extract uploaded files
        files_restored = 0
        upload_prefix = "uploads/"
        for name in zf.namelist():
            if name.startswith(upload_prefix) and not name.endswith("/"):
                relative = name[len(upload_prefix):]
                dest = os.path.join(str(app_settings.UPLOAD_DIR), relative)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(zf.read(name))
                files_restored += 1

        logger.info("Backup import complete: %d tables, %d rows, %d files", tables_imported, rows_imported, files_restored)

        return {
            "ok": True,
            "tables_imported": tables_imported,
            "rows_imported": rows_imported,
            "telemetry_imported": telemetry_imported,
            "files_restored": files_restored,
        }

    finally:
        db.close()
