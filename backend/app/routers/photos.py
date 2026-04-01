"""Photo gallery CRUD router for uploading, browsing, and managing drone photos.

Handles image uploads with automatic thumbnail generation, pilot tagging,
and secure file serving with path-traversal prevention.
"""

import os
import uuid
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from PIL import Image as PILImage

from app.config import settings
from app.constants import MIME_JPEG, PHOTO_NOT_FOUND, UTC_OFFSET
from app.deps import DBSession, CurrentUser, PilotUser
from app.models.photo import Photo, PhotoPilot
from app.models.pilot import Pilot
from app.responses import responses

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/photos", tags=["photos"])

UPLOAD_DIR = str(Path(settings.UPLOAD_DIR) / "photos")
THUMB_WIDTH = 400  # Maximum thumbnail width in pixels

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


def _ensure_dir(path: str):
    """Create the directory (and parents) if it does not already exist."""
    os.makedirs(path, exist_ok=True)


def _validate_path(file_path: str) -> Path:
    """Validate that file_path is within the upload directory (path traversal prevention)."""
    resolved = Path(file_path).resolve()
    upload_root = Path(UPLOAD_DIR).resolve()
    if not str(resolved).startswith(str(upload_root)):
        raise HTTPException(status_code=403, detail="Access denied")
    return resolved


@router.post("/upload", responses=responses(400, 413))
def upload_photo(

    db: DBSession,

    user: PilotUser,

    file: Annotated[UploadFile, File()],

    title: Annotated[Optional[str], Form()] = None,

    description: Annotated[Optional[str], Form()] = None,

    date_taken: Annotated[Optional[str], Form()] = None,

    pilot_ids: Annotated[Optional[str], Form()] = None,
):
    """Upload a photo with optional metadata and pilot associations.

    Generates a JPEG thumbnail automatically. Files are stored in
    per-photo subdirectories with UUID-based filenames.

    Args:
        file: The image file to upload.
        title: Optional display title.
        description: Optional description text.
        date_taken: ISO 8601 date string for when the photo was taken.
        pilot_ids: Comma-separated pilot IDs to tag in the photo.
        db: Database session.
        user: Authenticated user (pilot role or higher).

    Returns:
        Dict with the new photo ID and success message.
    """
    # Validate file extension
    ext = os.path.splitext(file.filename or "photo.jpg")[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}")

    # Create photo record first to get ID
    parsed_date = None
    if date_taken:
        try:
            parsed_date = datetime.fromisoformat(date_taken.replace("Z", UTC_OFFSET).replace(UTC_OFFSET, ""))
        except (ValueError, AttributeError):
            pass

    stored_name = f"{uuid.uuid4().hex}{ext}"

    photo = Photo(
        filename=stored_name,
        original_filename=file.filename or "photo.jpg",
        title=title,
        description=description,
        date_taken=parsed_date,
        mime_type=file.content_type or MIME_JPEG,
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


@router.get("", responses=responses(401))
def list_photos(db: DBSession, _user: CurrentUser):
    """List all photos with their tagged pilot names.

    Uses batch loading for pilot associations to avoid N+1 query issues.

    Returns:
        List of photo metadata dicts ordered by date taken (newest first).
    """
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


@router.get("/{photo_id}/view", responses=responses(401, 404))
def view_photo(photo_id: int, db: DBSession, _user: CurrentUser):
    """Serve the full-resolution photo file."""
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(404, PHOTO_NOT_FOUND)
    file_path = os.path.join(UPLOAD_DIR, str(photo.id), photo.filename)
    resolved = _validate_path(file_path)
    if not resolved.exists():
        raise HTTPException(404, "File not found on disk")
    return FileResponse(str(resolved), media_type=photo.mime_type or MIME_JPEG)


@router.get("/{photo_id}/thumbnail", responses=responses(401, 404))
def view_thumbnail(photo_id: int, db: DBSession, _user: CurrentUser):
    """Serve the photo thumbnail, falling back to the full image if unavailable."""
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(404, PHOTO_NOT_FOUND)
    if photo.thumbnail_path:
        thumb_resolved = _validate_path(photo.thumbnail_path)
        if thumb_resolved.exists():
            return FileResponse(str(thumb_resolved), media_type=MIME_JPEG)
    # Fall back to full image
    file_path = os.path.join(UPLOAD_DIR, str(photo.id), photo.filename)
    resolved = _validate_path(file_path)
    if not resolved.exists():
        raise HTTPException(404, "File not found on disk")
    return FileResponse(str(resolved), media_type=photo.mime_type or MIME_JPEG)


@router.patch("/{photo_id}", responses=responses(404))
def update_photo(

    photo_id: int,

    db: DBSession,

    user: PilotUser,

    title: Annotated[Optional[str], Form()] = None,

    description: Annotated[Optional[str], Form()] = None,

    date_taken: Annotated[Optional[str], Form()] = None,

    pilot_ids: Annotated[Optional[str], Form()] = None,
):
    """Update photo metadata and/or replace pilot associations.

    Args:
        photo_id: The photo record ID.
        title: New title (or None to keep existing).
        description: New description (or None to keep existing).
        date_taken: New date-taken ISO string (or None to keep existing).
        pilot_ids: Comma-separated pilot IDs (replaces all existing associations).

    Returns:
        Success message dict.
    """
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(404, PHOTO_NOT_FOUND)

    if title is not None:
        photo.title = title
    if description is not None:
        photo.description = description
    if date_taken is not None:
        try:
            photo.date_taken = datetime.fromisoformat(date_taken.replace("Z", UTC_OFFSET).replace(UTC_OFFSET, ""))
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


@router.delete("/{photo_id}", responses=responses(401, 404))
def delete_photo(photo_id: int, db: DBSession, user: PilotUser):
    """Delete a photo, its thumbnail, pilot associations, and on-disk files."""
    from app.services.audit import log_action
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(404, PHOTO_NOT_FOUND)

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
