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
from sqlalchemy import func, inspect as sa_inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.types import Date, DateTime

from app.config import settings as app_settings
from app import database


def _telemetry_session():
    """The telemetry sessionmaker, resolved when called.

    Imported by name it binds at import time, which the test suite's
    per-test engines cannot rebind -- so the telemetry half of a backup
    could not be exercised by a test at all.
    """
    return database.TelemetrySessionLocal()
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


def _serialize_database(db: Session) -> tuple[dict, dict]:
    """Serialize every main table to ``{table_name: rows}``, redacting secrets.

    Setting rows whose key is a known secret are dropped, and user password
    hashes are blanked (the column is non-nullable, so the key stays with an
    empty string; restored accounts need a password reset). Returns
    ``(database, row_counts)``.
    """
    database = {}
    counts = {}
    for table_name, model_class in EXPORT_ORDER:
        rows = _serialize_table(db, model_class)
        if table_name == "settings":
            rows = [r for r in rows if r.get("key") not in SECRET_KEYS]
        elif table_name == "users":
            for r in rows:
                r["password_hash"] = ""
        database[table_name] = rows
        counts[table_name] = len(rows)
        logger.info("  Exported %s: %d rows", table_name, len(rows))
    return database, counts


def build_backup_archive(db: Session, include_telemetry: bool = False) -> tuple[tempfile.SpooledTemporaryFile, dict]:
    """Build a full backup ZIP into a SpooledTemporaryFile and return it
    seeked to position 0, along with the manifest.

    The ZIP contains manifest.json, database.json, optionally telemetry.json,
    and every uploaded file under 'uploads/...'. This is the reusable core
    shared by the download endpoint and the scheduled backup job.
    """
    database, table_counts = _serialize_database(db)
    manifest = {
        "app_version": APP_VERSION,
        "export_date": datetime.now().isoformat(),
        "include_telemetry": include_telemetry,
        "tables": table_counts,
    }

    # Telemetry is counted here and streamed into the archive below. It is the
    # one table big enough that holding it is the difference between a slow
    # export and an unusable host.
    telemetry_count = 0
    if include_telemetry:
        tel_db = _telemetry_session()
        try:
            telemetry_count = tel_db.query(func.count(TelemetryPoint.id)).scalar() or 0
        finally:
            tel_db.close()
        manifest["tables"]["telemetry_points"] = telemetry_count

    # Create ZIP
    spooled = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024)
    with zipfile.ZipFile(spooled, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST_FILE, json.dumps(manifest, cls=_BackupEncoder, indent=2))
        zf.writestr(DATABASE_FILE, json.dumps(database, cls=_BackupEncoder))

        if include_telemetry:
            _write_telemetry(zf, telemetry_count)

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


# Rows fetched per round trip while streaming. Large enough that the query is
# not the bottleneck, small enough that a batch is nothing to hold.
TELEMETRY_BATCH = 5000


def _write_telemetry(zf: zipfile.ZipFile, expected: int) -> int:
    """Write telemetry_points into the archive one row at a time.

    This used to load every row into memory as ORM objects, convert them into a
    list of dicts, and then build the whole JSON document as one string before
    handing it to the zip -- three copies of the table at once. On an instance
    with eight million points that is several gigabytes, and a container with no
    memory limit takes the host down with it rather than just failing.

    Streaming keeps it to one batch. The JSON array is assembled by hand because
    json.dump would need the whole list.
    """
    columns = _get_columns(TelemetryPoint)
    written = 0
    tel_db = _telemetry_session()
    try:
        # force_zip64: writing to a stream means the size is not known when the
        # entry header is written, and zipfile refuses anything past 2 GiB
        # unless told in advance. A real instance passes that: the export this
        # was found on holds 2.47 GB of telemetry. writestr did not need it
        # because it had the finished bytes to measure.
        with zf.open(TELEMETRY_FILE, "w", force_zip64=True) as handle:
            handle.write(b"[")
            query = tel_db.query(TelemetryPoint).execution_options(stream_results=True)
            for row in query.yield_per(TELEMETRY_BATCH):
                if written:
                    handle.write(b",")
                record = {col: getattr(row, col) for col in columns}
                handle.write(json.dumps(record, cls=_BackupEncoder).encode("utf-8"))
                written += 1
                # Without this the session keeps every row it has seen, which is
                # the leak this function exists to remove.
                tel_db.expunge(row)
            handle.write(b"]")
    finally:
        tel_db.close()
    logger.info("  Exported telemetry_points: %d rows", written)
    if written != expected:
        logger.warning("telemetry row count changed during export: counted %d, wrote %d",
                       expected, written)
    return written


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


def _parse_row(row: dict, col_types: dict, renames: dict) -> dict:
    """Parse one exported row for insert: apply any legacy column renames and
    revive ISO datetime/date strings. A malformed temporal value falls back to
    the raw string so one bad cell cannot abort a whole restore.

    Takes col_types and renames precomputed so a streaming caller resolves them
    once per table rather than per row.
    """
    if renames:
        row = {renames.get(k, k): v for k, v in row.items()}
    parsed = {}
    for key, val in row.items():
        kind = col_types.get(key)
        if val is None or kind is None:
            parsed[key] = val
            continue
        try:
            parsed[key] = datetime.fromisoformat(val) if kind == "datetime" else date.fromisoformat(val)
        except (ValueError, TypeError):
            parsed[key] = val
    return parsed


def _parse_rows(rows: list[dict], model_class) -> list[dict]:
    """Parse a batch of exported rows for model_class (see _parse_row)."""
    col_types = _get_column_types(model_class)
    renames = LEGACY_COLUMN_RENAMES.get(model_class.__tablename__, {})
    return [_parse_row(row, col_types, renames) for row in rows]


def _install_token_path() -> str:
    """Filesystem path of the install token used to gate backup import on a
    fresh install (when no admin user exists yet). Plain `.txt` extension so
    operators can open it in Notepad / TextEdit / cat without ceremony."""
    return os.path.join(str(app_settings.DATA_DIR), "install_token.txt")


def _legacy_install_token_path() -> str:
    """Pre-existing dot-prefixed name. Migrated to install_token.txt on init."""
    return os.path.join(str(app_settings.DATA_DIR), ".install_token")


def init_install_token() -> str | None:
    """Generate or surface the install token whenever the install has no usable
    login, logging it so an operator can read it from container logs.

    "No usable login" covers a genuine fresh install (no users) and a database
    restored from a backup (users exist but every password hash was redacted, so
    nobody can sign in). Both need the token: the first to import a backup, the
    second to reactivate an admin. Returns None (and issues nothing) once a real
    login exists. Called at startup and again after an import, since a restore
    blanks the hashes and re-opens the no-usable-login state."""
    from app.routers.auth import _has_usable_login
    db = database.SessionLocal()   # call-time resolution, see import_backup
    try:
        if _has_usable_login(db):
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


def verify_install_token(provided: str) -> bool:
    """Constant-time check of a provided install token against the token file.

    False when the file is missing, empty, or the value does not match, so the
    caller can fail closed. Used to gate both backup import and, after a redacted
    restore, admin reactivation on the setup screen."""
    provided = (provided or "").strip()
    if not provided:
        return False
    path = _install_token_path()
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            stored = f.read().strip()
    except OSError:
        return False
    return bool(stored) and secrets.compare_digest(provided, stored)


def retire_install_token() -> None:
    """Delete the install token file if present (idempotent). Called once a
    usable login exists, so the fresh-install/recovery back door is closed."""
    path = _install_token_path()
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info("Install token retired")
    except OSError as exc:
        logger.warning("Could not delete install token file: %s", exc)


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


def _restore_main_tables(db: Session, db_tables: dict) -> tuple[int, int]:
    """Replace every main-DB table from the backup, in one atomic transaction.

    A restore makes the database match the backup, so each table is wiped and
    reloaded rather than appended to (appending would collide on the backup's
    explicit ids). PRAGMA defer_foreign_keys holds every FK check until COMMIT
    and, unlike PRAGMA foreign_keys, is honored inside a transaction -- so the
    wipe-and-reload is all-or-nothing, needs no per-row ordering, and never
    leaves a pooled connection with enforcement disabled (the pragma clears
    itself at commit/rollback). Returns (tables_imported, rows_imported).
    """
    db.execute(text("PRAGMA defer_foreign_keys=ON"))
    tables_imported = 0
    rows_imported = 0
    try:
        # Clear children-first, reload parents-first. Ordering is not required
        # for correctness here (checks are deferred to commit), only tidy.
        for _name, model in reversed(EXPORT_ORDER):
            db.execute(model.__table__.delete())
        for name, model in EXPORT_ORDER:
            rows = _parse_rows(db_tables.get(name, []), model)
            if not rows:
                continue
            db.execute(model.__table__.insert(), rows)
            tables_imported += 1
            rows_imported += len(rows)
            logger.info("  Imported %s: %d rows", name, len(rows))
        db.commit()  # FK consistency is verified here
    except Exception:
        db.rollback()
        raise
    return tables_imported, rows_imported


def _stream_json_array(stream, read_size: int = 1 << 20):
    """Yield each top-level element of a JSON array from a binary stream without
    holding the whole array in memory.

    The backup writes telemetry.json as one large array (see _write_telemetry),
    the one table big enough that loading it whole is the OOM risk this avoids
    on restore -- the mirror of the streaming export. Assumes a well-formed
    array of objects; tolerant of surrounding whitespace.
    """
    decoder = json.JSONDecoder()
    buf = ""
    eof = False

    def fill():
        nonlocal buf, eof
        chunk = stream.read(read_size)
        buf += chunk.decode("utf-8") if chunk else ""
        eof = eof or not chunk

    # Consume up to and including the opening '['.
    while "[" not in buf and not eof:
        fill()
    _, _, buf = buf.partition("[")

    while True:
        buf = buf.lstrip().lstrip(",").lstrip()
        # End of array, or an empty buffer at end of stream: nothing left.
        if buf.startswith("]") or (not buf and eof):
            return
        try:
            # Also the path for an empty-but-not-yet-EOF buffer: raw_decode("")
            # raises, and we top up below rather than special-casing it.
            obj, end = decoder.raw_decode(buf)
        except json.JSONDecodeError:
            if eof:
                raise
            fill()
            continue
        yield obj
        buf = buf[end:]


def _restore_telemetry(zf: zipfile.ZipFile) -> tuple[bool, int]:
    """Replace telemetry_points from the backup, streamed in chunks.

    telemetry.json is read one record at a time and inserted in batches so a
    multi-GB table never lands in memory at once. Existing telemetry is cleared
    first (replace semantics, matching the main restore). Raises on failure
    rather than swallowing it -- a telemetry restore that half-completes while
    the response says "ok" would silently misreport the flights it belongs to.
    Returns (imported, count).
    """
    if TELEMETRY_FILE not in zf.namelist():
        return False, 0
    col_types = _get_column_types(TelemetryPoint)
    renames = LEGACY_COLUMN_RENAMES.get(TelemetryPoint.__tablename__, {})
    tel_db = _telemetry_session()
    count = 0
    chunk = []
    try:
        tel_db.query(TelemetryPoint).delete()
        with zf.open(TELEMETRY_FILE) as stream:
            for record in _stream_json_array(stream):
                chunk.append(_parse_row(record, col_types, renames))
                if len(chunk) >= TELEMETRY_BATCH:
                    tel_db.execute(TelemetryPoint.__table__.insert(), chunk)
                    count += len(chunk)
                    chunk = []
            if chunk:
                tel_db.execute(TelemetryPoint.__table__.insert(), chunk)
                count += len(chunk)
        tel_db.commit()
    except Exception:
        tel_db.rollback()
        raise
    finally:
        tel_db.close()
    logger.info("  Imported telemetry: %d points", count)
    return count > 0, count


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
    # Resolved at call time (like _telemetry_session) so the test suite's
    # per-test engines are used; an imported-by-name SessionLocal binds at
    # import and would send the restore to the wrong database under test.
    db = database.SessionLocal()
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

        db_tables = json.loads(zf.read(DATABASE_FILE))
        tables_imported, rows_imported = _restore_main_tables(db, db_tables)

        # Telemetry lives in a separate database, so it cannot share the main
        # transaction. A failure is surfaced rather than swallowed: the operator
        # can retry, which is safe because the whole restore is idempotent
        # (every table is replaced, not appended).
        try:
            telemetry_imported, telemetry_count = _restore_telemetry(zf)
        except Exception as exc:
            logger.exception("Backup telemetry import failed")
            raise HTTPException(500, f"Backup telemetry import failed: {exc}")
        rows_imported += telemetry_count

        # Extract uploaded files on a worker thread; blocking I/O doesn't
        # belong on the event loop.
        files_restored = await asyncio.to_thread(
            _restore_uploads, zf, str(app_settings.UPLOAD_DIR)
        )

        logger.info("Backup import complete: %d tables, %d rows, %d files (principal=%s)",
                    tables_imported, rows_imported, files_restored, principal)

        # A restore blanks every password hash, so the install is left with no
        # usable login. Keep the SAME install token available (and logged) so the
        # operator can reactivate an admin on the setup screen; /auth/setup
        # retires it once that succeeds. init_install_token reuses the existing
        # token file untouched -- it never replaces a token -- and only mints one
        # when none is on disk (an admin restoring in-app, where no token existed
        # at boot). No-ops if a usable login somehow remains.
        init_install_token()

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
