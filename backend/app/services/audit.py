"""Audit trail service for recording user actions and tracking field-level changes.

All audit entries are added to the current session without committing,
allowing the caller to include them in its own transaction.
"""

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
    """Record an audit log entry for a user action.

    The entry is added to the session but NOT committed; the caller is
    responsible for committing the transaction.

    Args:
        db: Active database session.
        user_id: ID of the user performing the action (None for system actions).
        user_name: Display name of the acting user.
        action: Action verb (e.g., "create", "update", "delete", "login").
        entity_type: Type of entity affected (e.g., "pilot", "vehicle", "user").
        entity_id: ID of the affected entity.
        entity_name: Human-readable name of the affected entity.
        changes: Dict of field-level changes from compute_changes().
        ip_address: Client IP address, if available.
        details: Free-text description of the action.
    """
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
    """Compare an ORM object's current values with incoming update data.

    Only fields present in both ``update_data`` and ``fields`` are checked.
    Unchanged fields are omitted from the result.

    Args:
        old_obj: The existing ORM model instance.
        update_data: Dict of proposed new values (from request body).
        fields: List of field names to compare.

    Returns:
        Dict mapping changed field names to {"old": ..., "new": ...} pairs.
    """
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
