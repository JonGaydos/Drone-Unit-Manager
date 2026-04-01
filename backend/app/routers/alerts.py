from fastapi import APIRouter, HTTPException
from sqlalchemy import func

from app.constants import ALERT_NOT_FOUND
from app.deps import DBSession, CurrentUser
from app.models.alert import Alert
from app.responses import responses
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


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
    user: CurrentUser,
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
def count_alerts(db: DBSession, user: CurrentUser):
    return {
        "total": db.query(func.count(Alert.id)).filter(Alert.is_dismissed.is_(False)).scalar(),
        "unread": db.query(func.count(Alert.id)).filter(Alert.is_dismissed.is_(False), Alert.is_read.is_(False)).scalar(),
    }


@router.patch("/{alert_id}/read", responses=responses(401, 404))
def mark_read(alert_id: int, db: DBSession, user: CurrentUser):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_read = True
    db.commit()
    return {"ok": True}


@router.patch("/{alert_id}/dismiss", responses=responses(401, 404))
def dismiss_alert(alert_id: int, db: DBSession, user: CurrentUser):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_dismissed = True
    db.commit()
    return {"ok": True}


@router.post("/dismiss-all", responses=responses(401))
def dismiss_all(db: DBSession, user: CurrentUser):
    db.query(Alert).filter(Alert.is_dismissed.is_(False)).update({Alert.is_dismissed: True})
    db.commit()
    return {"ok": True}
