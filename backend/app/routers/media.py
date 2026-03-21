from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.media import MediaFile
from app.models.user import User
from app.routers.auth import get_current_user
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/api/media", tags=["media"])


class MediaOut(BaseModel):
    id: int
    external_uuid: Optional[str]
    flight_id: Optional[int]
    filename: str
    kind: str
    captured_time: Optional[datetime]
    size_bytes: Optional[int]
    download_url: Optional[str]
    thumbnail_cached: bool
    api_provider: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[MediaOut])
def list_media(
    flight_id: int | None = None,
    kind: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(MediaFile)
    if flight_id:
        q = q.filter(MediaFile.flight_id == flight_id)
    if kind:
        q = q.filter(MediaFile.kind == kind)
    return [MediaOut.model_validate(m) for m in q.order_by(MediaFile.captured_time.desc()).offset(offset).limit(limit).all()]


@router.get("/count")
def count_media(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from sqlalchemy import func
    return {"count": db.query(func.count(MediaFile.id)).scalar()}


@router.delete("/{media_id}")
def delete_media(media_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    media = db.query(MediaFile).filter(MediaFile.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    db.delete(media)
    db.commit()
    return {"ok": True}
