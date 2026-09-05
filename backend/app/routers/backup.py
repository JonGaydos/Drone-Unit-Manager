"""Full backup export and import for Drone Unit Manager.

Export creates a ZIP with manifest, JSON database dump, and uploaded files.
Import requires a fresh install (no users) and restores everything.
"""

import asyncio
import io
import json
import logging
import os
import secrets
import tempfile
import zipfile
from typing import Annotated
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, UploadFile, File, Request
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
from app.models.other_equipment import OtherEquipment
from app.models.api_token import ApiToken
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
from app.models.operating_authority import OperatingAuthority
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
from app.routers.settings import SECRET_KEYS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backup", tags=["backup"])

APP_VERSION = "2.2.0"

# Component filenames inside a DUM backup ZIP.
MANIFEST_FILE = "manifest.json"
DATABASE_FILE = "database.json"
TELEMETRY_FILE = "telemetry.json"

# Per-entry decompressed size cap for extracted uploads. Guards against a
# zip-bomb entry whose declared (and actual) uncompressed size is huge.
MAX_UPLOAD_ENTRY_BYTES = 200 * 1024 * 1024  # 200 MB

# Tables in FK-dependency order (parents before children)
EXPORT_ORDER = [
    # Tier 1: No foreign keys
    ("settings", Setting),
    ("folders", Folder),
    ("flight_purposes", FlightPurpose),
    ("certification_types", CertificationType),
    ("currency_rules", CurrencyRule),
    ("geofences", Geofence),
    ("operating_authorities", OperatingAuthority),
    # Tier 2: Base entities
    ("pilots", Pilot),
    ("users", User),
    ("vehicles", Vehicle),
    ("batteries", Battery),
    ("controllers", Controller),
    ("sensor_packages", SensorPackage),
    ("attachments", Attachment),
    ("docks", Dock),
    ("other_equipment", OtherEquipment),
    # Tier 3: FK to base entities
    ("api_tokens", ApiToken),
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


def build_backup_archive(db: Session, include_telemetry: bool = False) -> tuple[tempfile.SpooledTemporaryFile, dict]:
    """Build a full backup ZIP into a SpooledTemporaryFile and return it
    seeked to position 0, along with the manifest.

    The ZIP contains manifest.json, database.json, optionally telemetry.json,
    and every uploaded file under 'uploads/...'. This is the reusable core
    shared by the download endpoint and the scheduled backup job.
    """
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
        # Redact secrets on export. Drop Setting rows holding secret values and
        # blank user password hashes (the column is non-nullable, so keep the
        # key with an empty string — restored accounts need a password reset).
        if table_name == "settings":
            rows = [r for r in rows if r.get("key") not in SECRET_KEYS]
        elif table_name == "users":
            for r in rows:
                r["password_hash"] = ""
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
        zf.writestr(MANIFEST_FILE, json.dumps(manifest, cls=_BackupEncoder, indent=2))
        zf.writestr(DATABASE_FILE, json.dumps(database, cls=_BackupEncoder))

        if telemetry_data is not None:
            zf.writestr(TELEMETRY_FILE, json.dumps(telemetry_data, cls=_BackupEncoder))

        # Add uploaded files
        upload_dir = str(app_settings.UPLOAD_DIR)
        if os.path.exists(upload_dir):
            for dirpath, _, filenames in os.walk(upload_dir):
                for fname in filenames:
                    full_path = os.path.join(dirpath, fname)
                    arc_name = "uploads/" + os.path.relpath(full_path, upload_dir).replace("\\", "/")
                    zf.write(full_path, arc_name)

    spooled.seek(0)
    return spooled, manifest


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


# Columns renamed since older backups were written: table -> {old: new}.
LEGACY_COLUMN_RENAMES = {
    "batteries": {"purchase_date": "acquired_date"},
}


def _parse_rows(rows: list[dict], model_class) -> list[dict]:
    """Parse ISO datetime strings back to Python datetime/date objects."""
    col_types = _get_column_types(model_class)
    renames = LEGACY_COLUMN_RENAMES.get(model_class.__tablename__, {})
    parsed = []
    for row in rows:
        if renames:
            row = {renames.get(k, k): v for k, v in row.items()}
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


def _install_token_path() -> str:
    """Filesystem path of the install token used to gate backup import on a
    fresh install (when no admin user exists yet). Plain `.txt` extension so
    operators can open it in Notepad / TextEdit / cat without ceremony."""
    return os.path.join(str(app_settings.DATA_DIR), "install_token.txt")


def _legacy_install_token_path() -> str:
    """Pre-existing dot-prefixed name. Migrated to install_token.txt on init."""
    return os.path.join(str(app_settings.DATA_DIR), ".install_token")


def init_install_token() -> str | None:
    """Generate the install token at startup if (a) no users exist and (b) the
    file isn't already there. Returns the token (existing or new) when a fresh
    install is detected; returns None once any admin has been created. The
    token is printed to the logger so an operator can read it from container
    logs and paste it into the first-run setup screen."""
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return None
    finally:
        db.close()

    path = _install_token_path()
    legacy = _legacy_install_token_path()

    # Migrate the old hidden-dot file to install_token.txt so existing installs
    # don't regenerate their token unexpectedly.
    if os.path.exists(legacy) and not os.path.exists(path):
        try:
            os.rename(legacy, path)
            logger.info("Migrated install token file: %s -> %s", legacy, path)
        except OSError as exc:
            logger.warning("Could not migrate legacy install token file: %s", exc)

    if os.path.exists(path):
        try:
            with open(path) as f:
                token = f.read().strip()
            if token:
                banner = "=" * 72
                logger.info("\n%s\nDrone Unit Manager — install token (fresh install):\n  %s\nFile: %s\nUse the X-Install-Token header (or paste into the setup screen) to\nimport a backup before the first admin user is created.\n%s",
                            banner, token, path, banner)
                return token
        except OSError:
            pass

    token = secrets.token_hex(32)
    try:
        with open(path, "w") as f:
            f.write(token + "\n")
        try:
            os.chmod(path, 0o600)
        except OSError:
            # Some filesystems (mounted Windows volumes, certain NFS exports)
            # ignore chmod. The file is still readable to whoever has shell.
            pass
    except OSError as e:
        logger.warning("Could not write install token to %s: %s", path, e)
        return token

    banner = "=" * 72
    logger.info("\n%s\nDrone Unit Manager — install token (fresh install):\n  %s\nFile: %s\nUse the X-Install-Token header (or paste into the setup screen) to\nimport a backup before the first admin user is created.\n%s",
                banner, token, path, banner)
    return token


def _verify_admin_or_install_token(request: Request, db: Session) -> str:
    """Authorize a backup import. Returns an audit-friendly principal string.

    - If any user exists, require an Admin JWT (standard bearer auth).
    - If no users exist (fresh install), require an X-Install-Token header
      matching the token file generated at startup.
    """
    if db.query(User).count() > 0:
        from jose import jwt, JWTError
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(401, "Admin authentication required to import a backup")
        token = auth_header[len("Bearer "):]
        try:
            payload = jwt.decode(token, app_settings.SECRET_KEY, algorithms=["HS256"])
            user_id = int(payload["sub"])
        except (JWTError, KeyError, ValueError):
            raise HTTPException(401, "Invalid token")
        user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
        if not user or user.role != "admin":
            raise HTTPException(403, "Backup import requires an admin account")
        return f"admin:{user.username}"
    # Fresh install path: install-token check
    provided = request.headers.get("X-Install-Token", "").strip()
    if not provided:
        raise HTTPException(401, "Install token required. Check container logs for X-Install-Token.")
    token_path = _install_token_path()
    if not os.path.exists(token_path):
        raise HTTPException(403, "No install token file on disk. Restart the container to regenerate.")
    try:
        with open(token_path) as f:
            stored = f.read().strip()
    except OSError as e:
        raise HTTPException(500, f"Could not read install token: {e}")
    if not secrets.compare_digest(provided, stored):
        raise HTTPException(403, "Invalid install token")
    return "install_token"


def _safe_zip_member_path(upload_dir: str, relative: str) -> str:
    """Compute and validate the destination path for a backup ZIP entry.
    Raises ValueError on any traversal attempt (absolute paths, .., or
    realpath landing outside upload_dir)."""
    parts = relative.replace("\\", "/").split("/")
    if os.path.isabs(relative) or any(p in ("..", "") for p in parts if p != parts[-1] or parts[-1] == ".."):
        raise ValueError(f"unsafe path: {relative!r}")
    dest = os.path.join(upload_dir, relative)
    real_dest = os.path.realpath(dest)
    real_root = os.path.realpath(upload_dir)
    if real_dest != real_root and not real_dest.startswith(real_root + os.sep):
        raise ValueError(f"escapes upload root: {relative!r}")
    return dest


def _restore_uploads(zf: zipfile.ZipFile, upload_dir: str) -> int:
    """Extract every 'uploads/...' entry in the backup ZIP into upload_dir on
    disk. Rejects entries that try to escape upload_dir via absolute paths,
    '..' segments, or symlinks. Called from import_backup via
    asyncio.to_thread so blocking file I/O doesn't stall the event loop."""
    files_restored = 0
    files_rejected = 0
    upload_prefix = "uploads/"
    for name in zf.namelist():
        if not name.startswith(upload_prefix) or name.endswith("/"):
            continue
        relative = name[len(upload_prefix):]
        # Reject entries whose declared decompressed size exceeds the cap before
        # reading them into memory (zip-bomb guard).
        if zf.getinfo(name).file_size > MAX_UPLOAD_ENTRY_BYTES:
            logger.warning("Refused backup entry %s: decompressed size exceeds cap", name)
            files_rejected += 1
            continue
        try:
            dest = _safe_zip_member_path(upload_dir, relative)
        except ValueError as exc:
            logger.warning("Refused backup entry %s: %s", name, exc)
            files_rejected += 1
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(zf.read(name))
        files_restored += 1
    if files_rejected:
        logger.warning("Skipped %d unsafe backup entries", files_rejected)
    return files_restored


@router.get("/export")
def export_backup(
    db: DBSession,
    admin: AdminUser,
    include_telemetry: bool = False,
):
    """Export a full backup as a ZIP file."""
    from app.services.audit import log_action
    logger.info("Backup export started by user %s (include_telemetry=%s)", admin.display_name, include_telemetry)
    log_action(db, admin.id, admin.display_name, "export", "backup",
               details=f"include_telemetry={include_telemetry}")
    db.commit()

    spooled, _ = build_backup_archive(db, include_telemetry=include_telemetry)

    today = date.today().isoformat()
    filename = f"drone_unit_manager_backup_{today}.zip"
    logger.info("Backup export complete: %s", filename)

    return StreamingResponse(
        spooled,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/status")
def backup_status(db: DBSession, admin: AdminUser):
    """Return automated-backup configuration and the last run's outcome."""
    from app.services.backup_jobs import (
        backup_dir, get_backup_enabled, get_backup_hour, get_backup_retention,
        BACKUP_FILE_GLOB,
    )
    from app.models.setting import Setting

    last_at = db.query(Setting).filter(Setting.key == "last_backup_at").first()
    last_result_row = db.query(Setting).filter(Setting.key == "last_backup_result").first()
    last_result = None
    if last_result_row and last_result_row.value:
        try:
            last_result = json.loads(last_result_row.value)
        except (ValueError, TypeError):
            last_result = last_result_row.value

    directory = backup_dir()
    count = 0
    if os.path.isdir(directory):
        import glob
        count = len(glob.glob(os.path.join(directory, BACKUP_FILE_GLOB)))

    return {
        "enabled": get_backup_enabled(db),
        "retention": get_backup_retention(db),
        "hour": get_backup_hour(db),
        "last_backup_at": last_at.value if last_at else None,
        "last_backup_result": last_result,
        "count": count,
    }


@router.post("/import", responses=responses(400, 401, 403, 413))
async def import_backup(
    request: Request,
    file: Annotated[UploadFile, File()],
):
    """Import a full backup from a ZIP file.

    Authorization:
    - Existing install (any user present): requires Admin JWT.
    - Fresh install (no users): requires X-Install-Token header matching
      the token generated at startup (printed to container logs).
    """
    db = SessionLocal()
    try:
        principal = _verify_admin_or_install_token(request, db)

        content = await file.read()
        if len(content) > 500 * 1024 * 1024:
            raise HTTPException(413, "Backup file too large (max 500MB)")

        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile:
            raise HTTPException(400, "Invalid ZIP file")

        if MANIFEST_FILE not in zf.namelist():
            raise HTTPException(400, f"Invalid backup: missing {MANIFEST_FILE}")
        if DATABASE_FILE not in zf.namelist():
            raise HTTPException(400, f"Invalid backup: missing {DATABASE_FILE}")

        manifest = json.loads(zf.read(MANIFEST_FILE))
        logger.info("Importing backup from %s (version %s), principal=%s",
                    manifest.get("export_date"), manifest.get("app_version"), principal)

        database = json.loads(zf.read(DATABASE_FILE))

        # Disable FK constraints for the bulk insert phase.
        conn = db.connection()
        conn.execute(text("PRAGMA foreign_keys=OFF"))

        tables_imported = 0
        rows_imported = 0

        # First failure aborts the whole import. The previous behavior swallowed
        # per-table failures and committed whatever survived, leaving FK
        # constraints back on with referential integrity already broken.
        # The try/finally guarantees FK enforcement is re-enabled on every exit
        # path (success, HTTPException, or rollback) so a failed import can never
        # leave the connection with constraints disabled.
        try:
            try:
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
                    except Exception as exc:
                        logger.exception("Backup import aborted at table %s", table_name)
                        raise HTTPException(500, f"Backup import failed at table '{table_name}': {exc}")
            except HTTPException:
                db.rollback()
                raise
            db.commit()
        finally:
            conn.execute(text("PRAGMA foreign_keys=ON"))

        # Import telemetry if present
        telemetry_imported = False
        if TELEMETRY_FILE in zf.namelist():
            tel_db = TelemetrySessionLocal()
            try:
                tel_data = json.loads(zf.read(TELEMETRY_FILE))
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

        # Extract uploaded files on a worker thread; blocking I/O doesn't
        # belong on the event loop.
        files_restored = await asyncio.to_thread(
            _restore_uploads, zf, str(app_settings.UPLOAD_DIR)
        )

        logger.info("Backup import complete: %d tables, %d rows, %d files (principal=%s)",
                    tables_imported, rows_imported, files_restored, principal)

        # After a successful fresh-install import, retire the install token —
        # the database now contains an admin, so future import calls must use
        # admin auth. Leaving the file in place would create a back-door.
        if principal == "install_token":
            try:
                os.remove(_install_token_path())
                logger.info("Install token retired after successful import")
            except OSError as exc:
                logger.warning("Could not delete install token file: %s", exc)

        # Audit log entry (best-effort — table may not have existed pre-import).
        try:
            from app.services.audit import log_action
            log_action(db, None, principal, "import", "backup",
                       details=f"tables={tables_imported}, rows={rows_imported}, files={files_restored}")
            db.commit()
        except Exception as exc:
            logger.warning("Could not write audit log for backup import: %s", exc)

        return {
            "ok": True,
            "tables_imported": tables_imported,
            "rows_imported": rows_imported,
            "telemetry_imported": telemetry_imported,
            "files_restored": files_restored,
        }

    finally:
        db.close()
