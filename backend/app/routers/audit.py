from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps import DBSession
from app.models.audit_log import AuditLog
from app.models.user import User
from app.routers.auth import require_permission
from app.services.local_time import display_zone, stamped_on_or_after, stamped_on_or_before
from app.services.pilot_contacts import hides_contacts, redact_audit_changes, redact_audit_details

router = APIRouter(prefix="/api/audit", tags=["audit"])

ViewUser = Annotated[User, Depends(require_permission("audit.view"))]


def filtered_audit_logs(db, *, entity_type: str | None = None, entity_id: int | None = None,
                        user_id: int | None = None, action: str | None = None,
                        date_from: date | None = None, date_to: date | None = None):
    """Audit entries matching the Audit Log page's filters. Dates are days in
    the display zone, both ends included. Shared with the CSV export."""
    q = db.query(AuditLog)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if action:
        q = q.filter(AuditLog.action == action)
    if date_from or date_to:
        zone = display_zone(db)
        if date_from:
            q = q.filter(stamped_on_or_after(AuditLog.created_at, date_from, zone))
        if date_to:
            q = q.filter(stamped_on_or_before(AuditLog.created_at, date_to, zone))
    return q


@router.get("/users")
def list_audit_users(db: DBSession, _user: ViewUser):
    """Each signed-in user who has an entry in the log, for the user filter.
    Names come from the entries, so deleted users still appear."""
    rows = (
        db.query(AuditLog.user_id, AuditLog.user_name, AuditLog.user_username)
        .filter(AuditLog.user_id.isnot(None))
        .distinct()
        .all()
    )
    by_id: dict[int, dict] = {}
    for user_id, name, username in rows:
        by_id.setdefault(user_id, {"user_id": user_id, "user_name": name, "user_username": username})
    return sorted(by_id.values(), key=lambda u: ((u["user_name"] or u["user_username"] or "").lower(), u["user_id"]))


@router.get("")
def list_audit_logs(
    db: DBSession,
    user: ViewUser,
    entity_type: str | None = None,
    entity_id: int | None = None,
    user_id: int | None = None,
    action: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    per_page: int = 50):
    q = filtered_audit_logs(db, entity_type=entity_type, entity_id=entity_id, user_id=user_id,
                            action=action, date_from=date_from, date_to=date_to)
    total = q.count()
    logs = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    hide = hides_contacts(db, user)
    return {
        "logs": [
            {
                "id": entry.id,
                "user_id": entry.user_id,
                "user_name": entry.user_name,
                "user_username": entry.user_username,
                "action": entry.action,
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
                "entity_name": entry.entity_name,
                "changes": redact_audit_changes(entry.changes) if hide else entry.changes,
                "details": redact_audit_details(entry.details) if hide else entry.details,
                "ip_address": entry.ip_address,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "imported": bool(entry.imported),
            }
            for entry in logs
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }
