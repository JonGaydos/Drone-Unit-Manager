from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.routers.auth import get_current_user, require_admin

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit_logs(
    entity_type: str | None = None,
    entity_id: int | None = None,
    user_id: int | None = None,
    action: str | None = None,
    page: int = 1,
    per_page: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    q = db.query(AuditLog)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if action:
        q = q.filter(AuditLog.action == action)
    total = q.count()
    logs = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "logs": [
            {
                "id": entry.id,
                "user_id": entry.user_id,
                "user_name": entry.user_name,
                "action": entry.action,
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
                "entity_name": entry.entity_name,
                "changes": entry.changes,
                "details": entry.details,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            }
            for entry in logs
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }
