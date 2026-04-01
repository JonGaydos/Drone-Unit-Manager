from fastapi import APIRouter, HTTPException

from app.deps import CurrentUser, DBSession
from app.models.media import MediaFile
from app.responses import responses
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/api/media", tags=["media"])


class MediaOut(BaseModel):
    id: int
    external_uuid: Optional[str] = None
    flight_id: Optional[int] = None
    filename: str
    kind: str
    captured_time: Optional[datetime] = None
    size_bytes: Optional[int] = None
    download_url: Optional[str] = None
    thumbnail_cached: bool
    api_provider: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[MediaOut])
def list_media(
    db: DBSession,
    user: CurrentUser,
    flight_id: int | None = None,
    kind: str | None = None,
    limit: int = 100,
    offset: int = 0):
    q = db.query(MediaFile)
    if flight_id:
        q = q.filter(MediaFile.flight_id == flight_id)
    if kind:
        q = q.filter(MediaFile.kind == kind)
    return [MediaOut.model_validate(m) for m in q.order_by(MediaFile.captured_time.desc()).offset(offset).limit(limit).all()]


@router.get("/count", responses=responses(401))
def count_media(db: DBSession, user: CurrentUser):
    from sqlalchemy import func
    return {"count": db.query(func.count(MediaFile.id)).scalar()}


@router.delete("/{media_id}", responses=responses(401, 404))
def delete_media(media_id: int, db: DBSession, user: CurrentUser):
    media = db.query(MediaFile).filter(MediaFile.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    db.delete(media)
    db.commit()
    return {"ok": True}
