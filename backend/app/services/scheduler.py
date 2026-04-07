"""Background sync scheduler using APScheduler."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.constants import APP_TITLE
from app.database import SessionLocal
from app.models.setting import Setting
from app.services.sync_manager import SyncManager

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
SYNC_JOB_ID = "skydio_sync"
DIGEST_JOB_ID = "email_digest"


def check_maintenance_schedules(db):
    """Create alerts for overdue maintenance schedules."""
    from datetime import date as date_type
    from app.models.maintenance_schedule import MaintenanceSchedule
    from app.models.alert import Alert

    today = date_type.today()
    overdue = db.query(MaintenanceSchedule).filter(
        MaintenanceSchedule.is_active == True,
        MaintenanceSchedule.next_due <= today,
    ).all()

    for schedule in overdue:
        # Check if an alert already exists for this schedule today
        existing = db.query(Alert).filter(
            Alert.type == "maintenance_due",
            Alert.title == f"Maintenance Due: {schedule.name}",
            Alert.is_dismissed == False,
        ).first()
        if existing:
            continue

        entity_info = f"{schedule.entity_type}"
        if schedule.entity_id:
            entity_info += f" #{schedule.entity_id}"

        alert = Alert(
            type="maintenance_due",
            severity="warning",
            title=f"Maintenance Due: {schedule.name}",
            message=f"Scheduled {schedule.frequency} maintenance for {entity_info} is overdue (due {schedule.next_due.isoformat()}).",
            entity_type=schedule.entity_type,
            entity_id=schedule.entity_id,
        )
        db.add(alert)

    db.commit()
    logger.info("Maintenance schedule check complete: %d overdue schedules found", len(overdue))


def _run_scheduled_sync():
    """Execute a sync inside a fresh DB session (called by APScheduler)."""
    db = SessionLocal()
    try:
        # Check maintenance schedules for overdue items
        check_maintenance_schedules(db)

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


def _is_pref_due_now(pref, now, current_hour, db, NotificationLog) -> bool:
    """Check if a notification preference is due to send right now."""
    from datetime import datetime, date as date_type

    pref_hour = pref.send_time.split(":")[0] if pref.send_time else "07"
    if pref_hour != current_hour:
        return False

    today_start = datetime.combine(date_type.today(), datetime.min.time())
    already_sent = db.query(NotificationLog).filter(
        NotificationLog.user_id == pref.user_id,
        NotificationLog.sent_at >= today_start,
        NotificationLog.status == "sent",
    ).first()
    if already_sent:
        return False

    if pref.frequency == "weekly" and pref.send_day is not None:
        if now.weekday() != pref.send_day:
            return False

    return True


def _send_user_digest(pref, db, NotificationLog):
    """Build and send a digest email for a single user preference."""
    import json
    from app.models.user import User
    from app.services.email_digest import build_digest, render_digest_html, send_email

    user = db.query(User).filter(User.id == pref.user_id).first()
    if not user:
        return

    to_email = pref.email_override or user.email
    if not to_email:
        return

    digest = build_digest(db, user)
    if not digest:
        db.add(NotificationLog(
            user_id=user.id, subject="Daily Digest", status="skipped",
            error_message="No actionable items", item_count=0,
        ))
        db.commit()
        return

    org_setting = db.query(Setting).filter(Setting.key == "org_name").first()
    org_name = org_setting.value if org_setting else APP_TITLE
    html = render_digest_html(digest, user, org_name)
    subject = f"{org_name} — Daily Digest"

    success = send_email(to_email, subject, html, db)
    item_count = sum(len(v) if isinstance(v, list) else 0 for v in digest.values())

    db.add(NotificationLog(
        user_id=user.id, subject=subject,
        status="sent" if success else "failed",
        error_message=None if success else "SMTP send failed",
        categories_included=json.dumps(list(digest.keys())),
        item_count=item_count,
    ))
    db.commit()
    logger.info("Digest %s for user %s (%s)", "sent" if success else "failed", user.display_name, to_email)


def _run_digest_job():
    """Check for users due for a digest email and send them."""
    from datetime import datetime
    from app.models.notification_preference import NotificationPreference
    from app.models.notification_log import NotificationLog

    db = SessionLocal()
    try:
        smtp_enabled = db.query(Setting).filter(Setting.key == "smtp_enabled").first()
        if not smtp_enabled or smtp_enabled.value != "true":
            return

        now = datetime.now()
        current_hour = now.strftime("%H")

        prefs = db.query(NotificationPreference).filter(
            NotificationPreference.enabled == True,
            NotificationPreference.frequency != "off",
        ).all()

        for pref in prefs:
            if not _is_pref_due_now(pref, now, current_hour, db, NotificationLog):
                continue
            _send_user_digest(pref, db, NotificationLog)

    except Exception as exc:
        logger.error("Digest job failed: %s", exc)
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
        # Calculate how long since last sync to determine first run time
        from datetime import datetime, timezone, timedelta
        next_run = None
        try:
            db = SessionLocal()
            last_ts = db.query(Setting).filter(Setting.key == "last_sync_timestamp").first()
            if last_ts and last_ts.value:
                last_sync = datetime.fromisoformat(last_ts.value)
                due_at = last_sync + timedelta(minutes=interval_minutes)
                now = datetime.now(timezone.utc)
                if due_at <= now:
                    # Overdue — run in 2 minutes to let the app finish starting
                    next_run = now + timedelta(minutes=2)
                    logger.info("Sync is overdue (last: %s), scheduling first run in 2 minutes", last_ts.value)
                else:
                    next_run = due_at
                    logger.info("Next sync due at %s (%d minutes from now)", due_at.isoformat(), (due_at - now).total_seconds() / 60)
            db.close()
        except Exception:
            pass

        _scheduler.add_job(
            _run_scheduled_sync,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=SYNC_JOB_ID,
            replace_existing=True,
            max_instances=1,
            next_run_time=next_run,
        )
        logger.info("Sync scheduler started with %d minute interval", interval_minutes)
    else:
        logger.info("Sync scheduler started (no interval configured, waiting for manual trigger)")

    # Always run digest check every 30 minutes
    _scheduler.add_job(
        _run_digest_job,
        trigger=IntervalTrigger(minutes=10),
        id=DIGEST_JOB_ID,
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Email digest scheduler started (checks every 10 minutes)")


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
