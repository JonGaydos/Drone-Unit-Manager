"""Photo gallery CRUD router."""
import os
import uuid
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from PIL import Image as PILImage

from app.config import settings
from app.database import get_db
from app.models.photo import Photo, PhotoPilot
from app.models.pilot import Pilot
from app.routers.auth import get_current_user, require_pilot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/photos", tags=["photos"])

UPLOAD_DIR = str(Path(settings.UPLOAD_DIR) / "photos")
THUMB_WIDTH = 400

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _validate_path(file_path: str) -> Path:
    """Validate that file_path is within the upload directory (path traversal prevention)."""
    resolved = Path(file_path).resolve()
    upload_root = Path(UPLOAD_DIR).resolve()
    if not str(resolved).startswith(str(upload_root)):
        raise HTTPException(status_code=403, detail="Access denied")
    return resolved


@router.post("/upload")
def upload_photo(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    date_taken: Optional[str] = Form(None),
    pilot_ids: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_pilot),
):
    # Validate file extension
    ext = os.path.splitext(file.filename or "photo.jpg")[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}")

    # Create photo record first to get ID
    parsed_date = None
    if date_taken:
        try:
            parsed_date = datetime.fromisoformat(date_taken.replace("Z", "+00:00").replace("+00:00", ""))
        except (ValueError, AttributeError):
            pass

    stored_name = f"{uuid.uuid4().hex}{ext}"

    photo = Photo(
        filename=stored_name,
        original_filename=file.filename or "photo.jpg",
        title=title,
        description=description,
        date_taken=parsed_date,
        mime_type=file.content_type or "image/jpeg",
        uploaded_by_id=user.id,
    )
    db.add(photo)
    db.flush()

    # Save file
    photo_dir = os.path.join(UPLOAD_DIR, str(photo.id))
    _ensure_dir(photo_dir)
    file_path = os.path.join(photo_dir, stored_name)

    # Validate path before writing
    _validate_path(file_path)

    content = file.file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB")
    with open(file_path, "wb") as f:
        f.write(content)

    photo.file_size = os.path.getsize(file_path)

    # Generate thumbnail
    try:
        img = PILImage.open(file_path)
        img.thumbnail((THUMB_WIDTH, THUMB_WIDTH * 10), PILImage.LANCZOS)
        thumb_name = f"thumb_{stored_name}"
        thumb_path = os.path.join(photo_dir, thumb_name)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(thumb_path, "JPEG", quality=85)
        photo.thumbnail_path = thumb_path
    except (IOError, OSError) as e:
        logger.warning("Thumbnail generation failed for photo %s: %s", photo.id, e)
        photo.thumbnail_path = None

    # Create pilot associations
    if pilot_ids:
        for pid_str in pilot_ids.split(","):
            pid_str = pid_str.strip()
            if pid_str.isdigit():
                db.add(PhotoPilot(photo_id=photo.id, pilot_id=int(pid_str)))

    db.commit()
    db.refresh(photo)
    return {"id": photo.id, "message": "Photo uploaded successfully"}


@router.get("")
def list_photos(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    photos = db.query(Photo).order_by(Photo.date_taken.desc().nullslast(), Photo.created_at.desc()).all()

    # Batch-load all pilot associations to avoid N+1 queries
    photo_ids = [p.id for p in photos]
    associations = db.query(PhotoPilot).filter(PhotoPilot.photo_id.in_(photo_ids)).all() if photo_ids else []

    pilot_ids_set = {a.pilot_id for a in associations}
    pilots_map = {}
    if pilot_ids_set:
        pilots = db.query(Pilot).filter(Pilot.id.in_(pilot_ids_set)).all()
        pilots_map = {p.id: p for p in pilots}

    # Group associations by photo
    photo_assoc = {}
    for a in associations:
        photo_assoc.setdefault(a.photo_id, []).append(a.pilot_id)

    result = []
    for p in photos:
        pilot_names = []
        pilot_ids_list = []
        for pid in photo_assoc.get(p.id, []):
            pilot = pilots_map.get(pid)
            if pilot:
                name = f"{pilot.first_name} {pilot.last_name}".strip()
                pilot_names.append(name)
                pilot_ids_list.append(pilot.id)

        result.append({
            "id": p.id,
            "filename": p.original_filename,
            "title": p.title,
            "description": p.description,
            "date_taken": p.date_taken.isoformat() if p.date_taken else None,
            "file_size": p.file_size,
            "mime_type": p.mime_type,
            "has_thumbnail": p.thumbnail_path is not None,
            "pilot_names": pilot_names,
            "pilot_ids": pilot_ids_list,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })
    return result


@router.get("/{photo_id}/view")
def view_photo(photo_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(404, "Photo not found")
    file_path = os.path.join(UPLOAD_DIR, str(photo.id), photo.filename)
    resolved = _validate_path(file_path)
    if not resolved.exists():
        raise HTTPException(404, "File not found on disk")
    return FileResponse(str(resolved), media_type=photo.mime_type or "image/jpeg")


@router.get("/{photo_id}/thumbnail")
def view_thumbnail(photo_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(404, "Photo not found")
    if photo.thumbnail_path:
        thumb_resolved = _validate_path(photo.thumbnail_path)
        if thumb_resolved.exists():
            return FileResponse(str(thumb_resolved), media_type="image/jpeg")
    # Fall back to full image
    file_path = os.path.join(UPLOAD_DIR, str(photo.id), photo.filename)
    resolved = _validate_path(file_path)
    if not resolved.exists():
        raise HTTPException(404, "File not found on disk")
    return FileResponse(str(resolved), media_type=photo.mime_type or "image/jpeg")


@router.patch("/{photo_id}")
def update_photo(
    photo_id: int,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    date_taken: Optional[str] = Form(None),
    pilot_ids: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_pilot),
):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(404, "Photo not found")

    if title is not None:
        photo.title = title
    if description is not None:
        photo.description = description
    if date_taken is not None:
        try:
            photo.date_taken = datetime.fromisoformat(date_taken.replace("Z", "+00:00").replace("+00:00", ""))
        except (ValueError, AttributeError):
            pass

    if pilot_ids is not None:
        # Replace pilot associations
        db.query(PhotoPilot).filter(PhotoPilot.photo_id == photo_id).delete()
        for pid_str in pilot_ids.split(","):
            pid_str = pid_str.strip()
            if pid_str.isdigit():
                db.add(PhotoPilot(photo_id=photo_id, pilot_id=int(pid_str)))

    db.commit()
    return {"message": "Photo updated"}


@router.delete("/{photo_id}")
def delete_photo(photo_id: int, db: Session = Depends(get_db), user=Depends(require_pilot)):
    from app.services.audit import log_action
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(404, "Photo not found")

    # Delete pilot associations
    db.query(PhotoPilot).filter(PhotoPilot.photo_id == photo_id).delete()

    # Delete files from disk
    photo_dir = os.path.join(UPLOAD_DIR, str(photo.id))
    if os.path.exists(photo_dir):
        shutil.rmtree(photo_dir)

    log_action(db, user.id, user.display_name, "delete", "photo", photo_id, photo.original_filename)
    db.delete(photo)
    db.commit()
    return {"message": "Photo deleted"}
