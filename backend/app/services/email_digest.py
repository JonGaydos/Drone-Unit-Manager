"""Email digest builder, renderer, and sender.

Queries actionable items across the system (pending approvals, expiring certs,
overdue maintenance, etc.) and sends formatted HTML digest emails via SMTP.
"""

import json
import logging
import smtplib
from datetime import datetime, date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.setting import Setting
from app.models.notification_preference import NotificationPreference

logger = logging.getLogger(__name__)


def _get_setting(db: Session, key: str, default: str = "") -> str:
    """Read a setting value from the database."""
    s = db.query(Setting).filter(Setting.key == key).first()
    return s.value if s else default


def build_digest(db: Session, user: User) -> dict | None:
    """Build a digest of actionable items for a user based on their role.

    Args:
        db: Database session.
        user: The user to build the digest for.

    Returns:
        Dict of category -> list of item dicts, or None if nothing to report.
    """
    from app.models.flight_approval import FlightPlan
    from app.models.flight import Flight
    from app.models.certification import PilotCertification
    from app.models.vehicle_registration import VehicleRegistration
    from app.models.maintenance_schedule import MaintenanceSchedule
    from app.models.equipment_checkout import EquipmentCheckout
    from app.models.incident import Incident

    # Get user's notification preferences
    pref = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == user.id
    ).first()
    enabled_categories = None
    if pref and pref.categories:
        try:
            enabled_categories = json.loads(pref.categories)
        except (json.JSONDecodeError, TypeError):
            pass

    today = date.today()
    thirty_days = today + timedelta(days=30)
    sections = {}

    # Pending flight plan approvals (supervisors/admins only)
    if user.role in ("admin", "supervisor"):
        if not enabled_categories or "pending_approvals" in enabled_categories:
            pending = db.query(FlightPlan).filter(FlightPlan.status == "pending").all()
            if pending:
                sections["pending_approvals"] = [
                    {"id": p.id, "title": p.title or f"Flight Plan #{p.id}",
                     "submitted_by_id": p.submitted_by_id, "date": str(p.date_planned) if p.date_planned else "TBD"}
                    for p in pending
                ]

    # Flights needing review (supervisors/admins only)
    if user.role in ("admin", "supervisor"):
        if not enabled_categories or "needs_review" in enabled_categories:
            needs_review = db.query(Flight).filter(Flight.review_status == "needs_review").count()
            if needs_review > 0:
                sections["needs_review"] = [{"count": needs_review}]

    # Expiring certifications (within 30 days)
    if not enabled_categories or "expiring_certs" in enabled_categories:
        expiring = db.query(PilotCertification).filter(
            PilotCertification.expiration_date <= thirty_days,
            PilotCertification.expiration_date >= today,
        ).all()
        if expiring:
            sections["expiring_certs"] = [
                {"id": c.id,
                 "pilot_name": (f"{c.pilot.first_name} {c.pilot.last_name}".strip() if c.pilot else "Unknown"),
                 "cert_name": (c.certification_type.name if c.certification_type else "Certification"),
                 "expires": str(c.expiration_date)}
                for c in expiring
            ]

    # Expiring FAA registrations
    if not enabled_categories or "expiring_registrations" in enabled_categories:
        try:
            exp_regs = db.query(VehicleRegistration).filter(
                VehicleRegistration.expiry_date <= thirty_days,
                VehicleRegistration.expiry_date >= today,
                VehicleRegistration.is_current == True,
            ).all()
            if exp_regs:
                sections["expiring_registrations"] = [
                    {"id": r.id, "registration_number": r.registration_number or "N/A",
                     "expires": str(r.expiry_date)}
                    for r in exp_regs
                ]
        except Exception:
            pass  # Table may not have all expected columns

    # Overdue maintenance
    if not enabled_categories or "overdue_maintenance" in enabled_categories:
        overdue = db.query(MaintenanceSchedule).filter(
            MaintenanceSchedule.is_active == True,
            MaintenanceSchedule.next_due <= today,
        ).all()
        if overdue:
            sections["overdue_maintenance"] = [
                {"id": m.id, "name": m.name, "entity_type": m.entity_type,
                 "due": str(m.next_due)}
                for m in overdue
            ]

    # Overdue equipment checkouts
    if not enabled_categories or "overdue_checkouts" in enabled_categories:
        try:
            overdue_eq = db.query(EquipmentCheckout).filter(
                EquipmentCheckout.checked_in_at.is_(None),
                EquipmentCheckout.expected_return < datetime.now(),
            ).all()
            if overdue_eq:
                sections["overdue_checkouts"] = [
                    {"id": e.id, "equipment_type": e.entity_type or "Equipment",
                     "equipment_name": e.entity_name or "Unknown"}
                    for e in overdue_eq
                ]
        except Exception:
            pass

    # Recent incidents (last 24h for daily, 7d for weekly)
    if not enabled_categories or "recent_incidents" in enabled_categories:
        freq = pref.frequency if pref else "daily"
        lookback = timedelta(days=1) if freq == "daily" else timedelta(days=7)
        since = datetime.now() - lookback
        recent = db.query(Incident).filter(Incident.created_at >= since).all()
        if recent:
            sections["recent_incidents"] = [
                {"id": i.id, "title": i.title or f"Incident #{i.id}",
                 "severity": i.severity or "unknown",
                 "date": i.created_at.isoformat() if i.created_at else ""}
                for i in recent
            ]

    return sections if sections else None


def render_digest_html(sections: dict, user: User, org_name: str) -> str:
    """Render digest data as a responsive HTML email.

    Args:
        sections: Dict of category -> list of items from build_digest().
        user: The recipient user.
        org_name: Organization name for the email header.

    Returns:
        HTML string for the email body.
    """
    category_labels = {
        "pending_approvals": "Pending Flight Plan Approvals",
        "needs_review": "Flights Needing Review",
        "expiring_certs": "Expiring Certifications",
        "expiring_registrations": "Expiring FAA Registrations",
        "overdue_maintenance": "Overdue Maintenance",
        "assigned_missions": "Assigned Missions",
        "overdue_checkouts": "Overdue Equipment Checkouts",
        "recent_incidents": "Recent Incidents",
    }

    sections_html = ""
    for cat_key, items in sections.items():
        label = category_labels.get(cat_key, cat_key.replace("_", " ").title())
        count = items[0].get("count", len(items)) if items else 0

        items_html = ""
        if cat_key == "needs_review":
            items_html = f'<p style="margin:4px 0;color:#666;">{count} flight(s) awaiting review</p>'
        else:
            for item in items:
                detail_parts = []
                for k, v in item.items():
                    if k == "id":
                        continue
                    detail_parts.append(f"{k.replace('_', ' ').title()}: {v}")
                items_html += f'<p style="margin:4px 0;padding:4px 8px;background:#f5f5f5;border-radius:4px;font-size:13px;">{" | ".join(detail_parts)}</p>'

        sections_html += f"""
        <div style="margin-bottom:20px;">
            <h3 style="margin:0 0 8px;font-size:15px;color:#333;border-bottom:1px solid #eee;padding-bottom:4px;">
                {label} ({count if cat_key == 'needs_review' else len(items)})
            </h3>
            {items_html}
        </div>
        """

    today_str = date.today().strftime("%B %d, %Y")

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333;">
    <div style="background:#1a1a2e;color:white;padding:20px;border-radius:8px 8px 0 0;text-align:center;">
        <h1 style="margin:0;font-size:20px;">{org_name}</h1>
        <p style="margin:4px 0 0;opacity:0.8;font-size:13px;">Daily Digest — {today_str}</p>
    </div>
    <div style="border:1px solid #e0e0e0;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
        <p style="margin:0 0 16px;">Hi {user.display_name},</p>
        <p style="margin:0 0 20px;color:#666;">Here's your summary of items that need attention:</p>
        {sections_html}
        <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
        <p style="font-size:12px;color:#999;text-align:center;">
            You can manage your notification preferences in Settings.<br>
            Sent by Drone Unit Manager
        </p>
    </div>
</body>
</html>"""
    return html


def send_email(to_address: str, subject: str, html_body: str, db: Session) -> bool:
    """Send an HTML email via the configured SMTP server.

    Args:
        to_address: Recipient email address.
        subject: Email subject line.
        html_body: HTML content of the email.
        db: Database session for reading SMTP settings.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    smtp_host = _get_setting(db, "smtp_host")
    smtp_port = int(_get_setting(db, "smtp_port", "587"))
    smtp_user = _get_setting(db, "smtp_username")
    smtp_pass = _get_setting(db, "smtp_password")
    smtp_from = _get_setting(db, "smtp_from_address")
    smtp_from_name = _get_setting(db, "smtp_from_name", "Drone Unit Manager")
    smtp_tls = _get_setting(db, "smtp_tls", "true").lower() == "true"

    if not smtp_host or not smtp_from:
        logger.warning("SMTP not configured — cannot send email")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{smtp_from_name} <{smtp_from}>"
    msg["To"] = to_address

    # Plain text fallback
    plain = f"Daily Digest for Drone Unit Manager. View the full digest in the app."
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if smtp_tls:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)

        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)

        server.sendmail(smtp_from, to_address, msg.as_string())
        server.quit()
        logger.info("Digest email sent to %s", to_address)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_address, e)
        return False
