import logging
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def log_action(
    db: Session,
    user_id: int | None,
    user_name: str | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    entity_name: str | None = None,
    changes: dict | None = None,
    ip_address: str | None = None,
    details: str | None = None,
):
    entry = AuditLog(
        user_id=user_id,
        user_name=user_name or "System",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        changes=changes,
        ip_address=ip_address,
        details=details,
    )
    db.add(entry)
    # Don't commit here — let the caller's transaction handle it


def compute_changes(old_obj, update_data: dict, fields: list[str]) -> dict:
    """Compare old object values with new update data, return changed fields."""
    changes = {}
    for field in fields:
        if field not in update_data:
            continue
        old_val = getattr(old_obj, field, None)
        new_val = update_data[field]
        if old_val != new_val:
            changes[field] = {
                "old": str(old_val) if old_val is not None else None,
                "new": str(new_val) if new_val is not None else None,
            }
    return changes
