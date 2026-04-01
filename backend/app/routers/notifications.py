"""Email notification preferences and digest preview/test endpoints."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DBSession
from app.models.notification_preference import NotificationPreference
from app.models.notification_log import NotificationLog
from app.responses import responses

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

DEFAULT_CATEGORIES = [
    "pending_approvals", "needs_review", "expiring_certs",
    "expiring_registrations", "overdue_maintenance",
    "assigned_missions", "overdue_checkouts", "recent_incidents",
]


class NotificationPrefUpdate(BaseModel):
    """Schema for updating notification preferences."""
    enabled: Optional[bool] = None
    frequency: Optional[str] = None  # daily, weekly, off
    send_time: Optional[str] = None  # HH:MM
    send_day: Optional[int] = None  # 0-6 for weekly
    categories: Optional[list[str]] = None
    email_override: Optional[str] = None


class NotificationPrefOut(BaseModel):
    """Schema for notification preference response."""
    enabled: bool
    frequency: str
    send_time: str
    send_day: Optional[int] = None
    categories: list[str]
    email_override: Optional[str] = None

    model_config = {"from_attributes": True}


def _get_or_create_pref(db: Session, user_id: int) -> NotificationPreference:
    """Get existing preferences or create defaults for a user."""
    pref = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == user_id
    ).first()
    if not pref:
        pref = NotificationPreference(user_id=user_id)
        db.add(pref)
        db.commit()
        db.refresh(pref)
    return pref


@router.get("/preferences")
def get_preferences(
    db: DBSession,
    user: CurrentUser,
):
    """Get the current user's email notification preferences."""
    pref = _get_or_create_pref(db, user.id)
    try:
        cats = json.loads(pref.categories) if pref.categories else DEFAULT_CATEGORIES
    except (json.JSONDecodeError, TypeError):
        cats = DEFAULT_CATEGORIES
    return {
        "enabled": pref.enabled,
        "frequency": pref.frequency,
        "send_time": pref.send_time,
        "send_day": pref.send_day,
        "categories": cats,
        "email_override": pref.email_override,
    }


@router.put("/preferences", responses=responses(400))
def update_preferences(
    data: NotificationPrefUpdate,
    db: DBSession,
    user: CurrentUser,
):
    """Update the current user's email notification preferences."""
    pref = _get_or_create_pref(db, user.id)
    if data.enabled is not None:
        pref.enabled = data.enabled
    if data.frequency is not None:
        if data.frequency not in ("daily", "weekly", "off"):
            raise HTTPException(400, "Frequency must be 'daily', 'weekly', or 'off'")
        pref.frequency = data.frequency
    if data.send_time is not None:
        pref.send_time = data.send_time
    if data.send_day is not None:
        pref.send_day = data.send_day
    if data.categories is not None:
        pref.categories = json.dumps(data.categories)
    if data.email_override is not None:
        pref.email_override = data.email_override if data.email_override else None
    db.commit()
    return {"ok": True, "message": "Notification preferences updated"}


@router.get("/preview")
def preview_digest(
    db: DBSession,
    user: CurrentUser,
):
    """Preview what the next digest email would contain for the current user."""
    from app.services.email_digest import build_digest
    digest = build_digest(db, user)
    if not digest:
        return {"empty": True, "message": "No actionable items to report", "sections": {}}
    return {"empty": False, "sections": digest}


@router.post("/send-test", responses=responses(400))
def send_test_digest(
    db: DBSession,
    user: CurrentUser,
):
    """Send a test digest email to the current user immediately."""
    from app.services.email_digest import build_digest, render_digest_html, send_email
    from app.models.setting import Setting

    # Resolve email: preference override → user email → linked pilot email
    pref = _get_or_create_pref(db, user.id)
    to_email = pref.email_override or user.email
    if not to_email and user.pilot_id:
        from app.models.pilot import Pilot
        pilot = db.query(Pilot).filter(Pilot.id == user.pilot_id).first()
        if pilot and pilot.email:
            to_email = pilot.email
    if not to_email:
        raise HTTPException(400, "No email address found. Add an email to your linked pilot profile or user account.")

    digest = build_digest(db, user)
    if not digest:
        return {"ok": False, "message": "No actionable items to include in the digest"}

    org_name_setting = db.query(Setting).filter(Setting.key == "org_name").first()
    org_name = org_name_setting.value if org_name_setting else "Drone Unit Manager"

    html = render_digest_html(digest, user, org_name)
    subject = f"{org_name} — Daily Digest"

    success = send_email(to_email, subject, html, db)
    if success:
        # Log the send
        log = NotificationLog(
            user_id=user.id,
            subject=subject,
            status="sent",
            categories_included=json.dumps(list(digest.keys())),
            item_count=sum(len(v) if isinstance(v, list) else 0 for v in digest.values()),
        )
        db.add(log)
        db.commit()
        return {"ok": True, "message": f"Test digest sent to {to_email}"}
    else:
        return {"ok": False, "message": "Failed to send email. Check SMTP settings in Integrations."}


@router.get("/log")
def get_notification_log(
    db: DBSession,
    user: CurrentUser,
    limit: int = 50):
    """Get notification send history for the current user."""
    q = db.query(NotificationLog)
    if user.role != "admin":
        q = q.filter(NotificationLog.user_id == user.id)
    logs = q.order_by(NotificationLog.sent_at.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "sent_at": log.sent_at.isoformat() if log.sent_at else None,
            "subject": log.subject,
            "status": log.status,
            "error_message": log.error_message,
            "item_count": log.item_count,
        }
        for log in logs
    ]
