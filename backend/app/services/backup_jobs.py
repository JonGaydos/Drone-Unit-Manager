"""Scheduled full-backup job and settings helpers.

Writes a full backup ZIP (DB + uploads) to DATA_DIR/backups/app/ on a daily
cron, rotates old files keeping the newest `backup_retention`, and records the
last-run time and result as Settings rows. Exceptions are caught and logged so
a failed backup never crashes the scheduler.
"""

import glob
import logging
import os
from datetime import datetime, timezone

from app.config import settings as app_settings
from app.database import SessionLocal
from app.models.setting import Setting
from app.routers.backup import build_backup_archive

logger = logging.getLogger(__name__)

# Defaults applied when the corresponding Settings row is absent.
DEFAULT_BACKUP_ENABLED = "true"
DEFAULT_BACKUP_RETENTION = 7
DEFAULT_BACKUP_HOUR = 3

BACKUP_FILE_PREFIX = "dum-backup-"
BACKUP_FILE_GLOB = BACKUP_FILE_PREFIX + "*.zip"


def backup_dir() -> str:
    """Absolute path to the app-backup directory under DATA_DIR."""
    return os.path.join(str(app_settings.DATA_DIR), "backups", "app")


def _get_setting(db, key: str) -> str | None:
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else None


def get_backup_enabled(db) -> bool:
    val = _get_setting(db, "backup_enabled")
    if val is None:
        return DEFAULT_BACKUP_ENABLED != "false"
    return val != "false"


def get_backup_retention(db) -> int:
    val = _get_setting(db, "backup_retention")
    if val:
        try:
            n = int(val)
            if n > 0:
                return n
        except ValueError:
            logger.warning("Invalid backup_retention setting: %s", val)
    return DEFAULT_BACKUP_RETENTION


def get_backup_hour(db) -> int:
    val = _get_setting(db, "backup_hour")
    if val is not None and val != "":
        try:
            h = int(val)
            if 0 <= h <= 23:
                return h
        except ValueError:
            logger.warning("Invalid backup_hour setting: %s", val)
    return DEFAULT_BACKUP_HOUR


def _set_setting(db, key: str, value: str) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


def _rotate(directory: str, retention: int) -> None:
    """Keep the newest `retention` backup files, delete older ones."""
    files = sorted(
        glob.glob(os.path.join(directory, BACKUP_FILE_GLOB)),
        key=os.path.getmtime,
        reverse=True,
    )
    for old in files[retention:]:
        try:
            os.remove(old)
            logger.info("Rotated out old backup: %s", os.path.basename(old))
        except OSError as exc:
            logger.warning("Could not delete old backup %s: %s", old, exc)


def run_scheduled_backup() -> None:
    """Build a full backup, write it to disk, rotate, and record the result.

    Any failure is caught and logged, and a failure result is still recorded so
    the scheduler never crashes on a bad backup run.
    """
    import json

    db = SessionLocal()
    try:
        directory = backup_dir()
        os.makedirs(directory, exist_ok=True)
        retention = get_backup_retention(db)

        ts = datetime.now()
        filename = f"{BACKUP_FILE_PREFIX}{ts.strftime('%Y%m%d-%H%M%S')}.zip"
        path = os.path.join(directory, filename)

        spooled, _ = build_backup_archive(db, include_telemetry=False)
        try:
            size = 0
            with open(path, "wb") as out:
                while True:
                    chunk = spooled.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    size += len(chunk)
        finally:
            spooled.close()

        _rotate(directory, retention)

        now_iso = datetime.now(timezone.utc).isoformat()
        result = {"at": now_iso, "file": filename, "bytes": size, "ok": True}
        _set_setting(db, "last_backup_at", now_iso)
        _set_setting(db, "last_backup_result", json.dumps(result))
        db.commit()
        logger.info("Scheduled backup complete: %s (%d bytes)", filename, size)
    except Exception as exc:
        logger.exception("Scheduled backup failed")
        try:
            db.rollback()
            now_iso = datetime.now(timezone.utc).isoformat()
            result = {"at": now_iso, "ok": False, "error": str(exc)}
            _set_setting(db, "last_backup_at", now_iso)
            _set_setting(db, "last_backup_result", json.dumps(result))
            db.commit()
        except Exception:
            logger.exception("Could not record backup failure result")
    finally:
        db.close()
