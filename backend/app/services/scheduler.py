"""Background sync scheduler using APScheduler."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.database import SessionLocal
from app.models.setting import Setting
from app.services.sync_manager import SyncManager

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
SYNC_JOB_ID = "skydio_sync"


def _run_scheduled_sync():
    """Execute a sync inside a fresh DB session (called by APScheduler)."""
    db = SessionLocal()
    try:
        # Check if sync is configured
        token_setting = db.query(Setting).filter(Setting.key == "skydio_api_token").first()
        if not token_setting or not token_setting.value:
            logger.debug("Scheduled sync skipped: no API token configured")
            return

        logger.info("Starting scheduled Skydio sync")
        result = SyncManager.sync_all("skydio", db)
        logger.info(
            "Scheduled sync complete: %d vehicles, %d new flights, %d errors",
            result.vehicles_synced, result.flights_new, len(result.errors),
        )
        if result.errors:
            for err in result.errors:
                logger.warning("Sync error: %s", err)
    except Exception as exc:
        logger.error("Scheduled sync failed: %s", exc)
    finally:
        db.close()


def _get_sync_interval_minutes() -> int | None:
    """Read the sync interval from the database settings."""
    db = SessionLocal()
    try:
        setting = db.query(Setting).filter(Setting.key == "sync_interval").first()
        if setting and setting.value:
            try:
                minutes = int(setting.value)
                if minutes > 0:
                    return minutes
            except ValueError:
                logger.warning("Invalid sync_interval setting: %s", setting.value)
        return None
    except Exception:
        return None
    finally:
        db.close()


def start_scheduler():
    """Start the background scheduler if a sync interval is configured."""
    global _scheduler

    if _scheduler is not None:
        logger.debug("Scheduler already running")
        return

    # Import skydio provider to ensure it's registered
    try:
        import app.integrations.skydio  # noqa: F401
    except ImportError:
        logger.warning("Skydio integration not available")

    interval_minutes = _get_sync_interval_minutes()

    _scheduler = BackgroundScheduler()
    _scheduler.start()

    if interval_minutes:
        _scheduler.add_job(
            _run_scheduled_sync,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=SYNC_JOB_ID,
            replace_existing=True,
            max_instances=1,
        )
        logger.info("Sync scheduler started with %d minute interval", interval_minutes)
    else:
        logger.info("Sync scheduler started (no interval configured, waiting for manual trigger)")


def stop_scheduler():
    """Shut down the background scheduler."""
    global _scheduler

    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Sync scheduler stopped")


def reschedule_sync(interval_minutes: int | None):
    """Update the sync schedule (call after settings change)."""
    global _scheduler

    if _scheduler is None:
        return

    # Remove existing job if present
    try:
        _scheduler.remove_job(SYNC_JOB_ID)
    except Exception:
        pass

    if interval_minutes and interval_minutes > 0:
        _scheduler.add_job(
            _run_scheduled_sync,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=SYNC_JOB_ID,
            replace_existing=True,
            max_instances=1,
        )
        logger.info("Sync rescheduled to every %d minutes", interval_minutes)
    else:
        logger.info("Sync schedule removed (no interval)")
