from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func

from app.constants import ALERT_NOT_FOUND
from app.deps import DBSession
from app.models.user import User
from app.routers.auth import require_permission
from app.models.alert import Alert
from app.responses import responses
from app.services.audit import compute_changes, log_action
from app.services.audit_capture import update_recorded
from pydantic import BaseModel
from datetime import datetime
from typing import Annotated, Optional

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

ViewUser = Annotated[User, Depends(require_permission("alerts.view"))]
DismissUser = Annotated[User, Depends(require_permission("alerts.dismiss"))]


class AlertOut(BaseModel):
    id: int
    type: str
    severity: str
    title: str
    message: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    is_read: bool
    is_dismissed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AlertOut])
def list_alerts(
    db: DBSession,
    user: ViewUser,
    is_read: bool | None = None,
    severity: str | None = None,
    limit: int = 100):
    q = db.query(Alert).filter(Alert.is_dismissed.is_(False))
    if is_read is not None:
        q = q.filter(Alert.is_read == is_read)
    if severity:
        q = q.filter(Alert.severity == severity)
    return [AlertOut.model_validate(a) for a in q.order_by(Alert.created_at.desc()).limit(limit).all()]


@router.get("/count", responses=responses(401))
def count_alerts(db: DBSession, user: ViewUser):
    return {
        "total": db.query(func.count(Alert.id)).filter(Alert.is_dismissed.is_(False)).scalar(),
        "unread": db.query(func.count(Alert.id)).filter(Alert.is_dismissed.is_(False), Alert.is_read.is_(False)).scalar(),
    }


@router.patch("/{alert_id}/read", responses=responses(401, 404))
def mark_read(alert_id: int, db: DBSession, user: DismissUser):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    changes = compute_changes(alert, {"is_read": True}, ["is_read"])
    if changes:
        alert.is_read = True
        log_action(db, user.id, user.display_name, "read", "alert", alert.id, alert.title, changes=changes)
    db.commit()
    return {"ok": True}


@router.patch("/{alert_id}/dismiss", responses=responses(401, 404))
def dismiss_alert(alert_id: int, db: DBSession, user: DismissUser):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    changes = compute_changes(alert, {"is_dismissed": True}, ["is_dismissed"])
    if changes:
        alert.is_dismissed = True
        log_action(db, user.id, user.display_name, "dismiss", "alert", alert.id, alert.title, changes=changes)
    db.commit()
    return {"ok": True}


@router.post("/dismiss-all", responses=responses(401))
def dismiss_all(db: DBSession, user: DismissUser):
    update_recorded(db, db.query(Alert).filter(Alert.is_dismissed.is_(False)),
                    {Alert.is_dismissed: (False, True)}, action="dismiss_all")
    db.commit()
    return {"ok": True}
