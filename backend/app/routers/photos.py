"""Photo gallery CRUD router for uploading, browsing, and managing drone photos.

Handles image uploads with automatic thumbnail generation, pilot tagging,
and secure file serving with path-traversal prevention.
"""

import hashlib
import hmac
import os
import time
import uuid
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from PIL import Image as PILImage
from sqlalchemy.orm import Session

from app.config import settings
from app.constants import MIME_JPEG, PHOTO_NOT_FOUND, FLIGHT_NOT_FOUND, INCIDENT_NOT_FOUND, UTC_OFFSET
from app.database import get_db
from app.deps import DBSession, CurrentUser, PilotUser, SupervisorUser
from app.models.user import User
from app.models.photo import Photo, PhotoPilot, PhotoFlight, PhotoIncident
from app.models.pilot import Pilot
from app.models.flight import Flight
from app.models.incident import Incident
from app.responses import responses

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/photos", tags=["photos"])

UPLOAD_DIR = str(Path(settings.UPLOAD_DIR) / "photos")
THUMB_WIDTH = 400  # Maximum thumbnail width in pixels

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}

# Cap decoded pixel count to defend against decompression-bomb images that
# would otherwise OOM the worker during thumbnail generation.
PILImage.MAX_IMAGE_PIXELS = 50_000_000

_security = HTTPBearer(auto_error=False)
_ALGORITHM = "HS256"

# Signed image URLs replace the old ?token=<JWT> auth path. The JWT was a
# long-lived bearer credential that landed in browser history, referer
# headers, and reverse-proxy access logs. Signed URLs are short-lived,
# scoped to a single photo + action, and cannot be reused to access other
# endpoints if leaked.
SIGNED_URL_TTL_SECONDS = 600  # 10 minutes


def _sign_photo(photo_id: int, action: str, ttl: int = SIGNED_URL_TTL_SECONDS) -> tuple[str, int]:
    """Create (signature, expires_at_epoch) for a photo URL. Action is
    typically 'view' or 'thumbnail'."""
    exp = int(time.time()) + ttl
    payload = f"{photo_id}:{action}:{exp}".encode()
    sig = hmac.new(settings.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()
    return sig, exp


def _verify_photo_sig(photo_id: int, action: str, sig: str | None, exp: int | None) -> bool:
    """Constant-time validation of a photo signature. Returns True iff the
    signature matches AND the URL has not yet expired."""
    if not sig or exp is None:
        return False
    if exp < int(time.time()):
        return False
    payload = f"{photo_id}:{action}:{exp}".encode()
    expected = hmac.new(settings.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def _photo_urls(photo_id: int) -> dict:
    """Build a fresh pair of signed URLs (view + thumbnail) for a photo.

    Returned URLs are relative to the /api base (no leading /api), so the
    frontend's API client (which prepends its own '/api' base) gets the right
    final URL. Previously the leading '/api' produced '/api/api/photos/...'
    and broke every <img> tag on MediaPage."""
    view_sig, view_exp = _sign_photo(photo_id, "view")
    thumb_sig, thumb_exp = _sign_photo(photo_id, "thumbnail")
    return {
        "view_url": f"/photos/{photo_id}/view?sig={view_sig}&exp={view_exp}",
        "thumbnail_url": f"/photos/{photo_id}/thumbnail?sig={thumb_sig}&exp={thumb_exp}",
        "urls_expire_at": min(view_exp, thumb_exp),
    }


def _authenticate_image_request(
    photo_id: int,
    action: str,
    credentials: HTTPAuthorizationCredentials | None,
    sig: str | None,
    exp: int | None,
    db: Session,
) -> None:
    """Allow either (a) a valid Bearer JWT (for API clients) or (b) a fresh
    signed URL for this photo_id+action. Raises 401 on failure."""
    if _verify_photo_sig(photo_id, action, sig, exp):
        return
    if credentials:
        try:
            payload = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=[_ALGORITHM])
            user_id = int(payload["sub"])
        except (JWTError, KeyError, ValueError):
            raise HTTPException(401, "Invalid token")
        user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
        if not user:
            raise HTTPException(401, "User not found or inactive")
        return
    raise HTTPException(401, "Not authenticated")


def _ensure_dir(path: str):
    """Create the directory (and parents) if it does not already exist."""
    os.makedirs(path, exist_ok=True)


def _validate_path(file_path: str) -> Path:
    """Validate that file_path is within the upload directory (path traversal prevention)."""
    resolved = Path(file_path).resolve()
    upload_root = Path(UPLOAD_DIR).resolve()
    if not resolved.is_relative_to(upload_root):
        raise HTTPException(status_code=403, detail="Access denied")
    return resolved


def _generate_thumbnail(file_path: str, photo_dir: str, stored_name: str) -> str | None:
    """Generate a JPEG thumbnail for an uploaded image. Returns thumbnail path or None."""
    try:
        img = PILImage.open(file_path)
        img.load()  # force decode now so a decompression bomb trips the guard here
        img.thumbnail((THUMB_WIDTH, THUMB_WIDTH * 10), PILImage.LANCZOS)
        thumb_name = f"thumb_{stored_name}"
        thumb_path = os.path.join(photo_dir, thumb_name)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(thumb_path, "JPEG", quality=85)
        return thumb_path
    except (IOError, OSError, ValueError, PILImage.DecompressionBombError) as e:
        logger.warning("Thumbnail generation failed: %s", e)
        return None


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
            raise HTTPException(400, "Invalid date format. Use ISO 8601 (e.g., 2026-04-02).")

    stored_name = f"{uuid.uuid4().hex}{ext}"

    # Organize by date: photos/2026-04-07/uuid.jpg
    from datetime import date as date_type
    date_folder = (parsed_date.strftime("%Y-%m-%d") if parsed_date else date_type.today().isoformat())
    relative_path = f"{date_folder}/{stored_name}"

    photo = Photo(
        filename=relative_path,
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
    photo_dir = os.path.join(UPLOAD_DIR, date_folder)
    _ensure_dir(photo_dir)
    file_path = os.path.join(UPLOAD_DIR, relative_path)

    # Validate path before writing
    _validate_path(file_path)

    from app.services.file_validation import is_image
    total = 0
    chunk_size = 64 * 1024
    first = file.file.read(chunk_size)
    if not is_image(first):
        raise HTTPException(400, "File content is not a recognized image")
    with open(file_path, "wb") as f:
        chunk = first
        while chunk:
            total += len(chunk)
            if total > settings.MAX_UPLOAD_SIZE:
                f.close()
                os.remove(file_path)
                raise HTTPException(413, f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB")
            f.write(chunk)
            chunk = file.file.read(chunk_size)

    photo.file_size = total

    # Generate thumbnail
    photo.thumbnail_path = _generate_thumbnail(file_path, photo_dir, stored_name)

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
def list_photos(db: DBSession, _user: CurrentUser, flight_id: int | None = None, incident_id: int | None = None):
    """List photos with their tagged pilot names.

    Optionally filter to photos linked to a given flight or incident. Uses
    batch loading for pilot associations to avoid N+1 query issues.

    Returns:
        List of photo metadata dicts ordered by date taken (newest first).
    """
    photos_q = db.query(Photo)
    if flight_id is not None:
        photos_q = photos_q.join(PhotoFlight, PhotoFlight.photo_id == Photo.id).filter(PhotoFlight.flight_id == flight_id)
    if incident_id is not None:
        photos_q = photos_q.join(PhotoIncident, PhotoIncident.photo_id == Photo.id).filter(PhotoIncident.incident_id == incident_id)
    if flight_id is not None or incident_id is not None:
        photos_q = photos_q.distinct()
    photos = photos_q.order_by(Photo.date_taken.desc().nullslast(), Photo.created_at.desc()).all()

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

        urls = _photo_urls(p.id)
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
            **urls,
        })
    return result


def _resolve_photo_path(photo) -> Optional[Path]:
    """Resolve photo file path from date-based layout."""
    file_path = os.path.join(UPLOAD_DIR, photo.filename)
    resolved = _validate_path(file_path)
    if resolved.exists():
        return resolved
    return None


@router.get("/{photo_id}/view", responses=responses(401, 404))
def view_photo(
    photo_id: int,
    db: DBSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_security)] = None,
    sig: str | None = Query(None),
    exp: int | None = Query(None),
):
    """Serve the full-resolution photo file.

    Accepts EITHER a Bearer JWT (for API clients) OR a signed URL with
    sig+exp query params (for <img src='...'> tags from the SPA)."""
    _authenticate_image_request(photo_id, "view", credentials, sig, exp, db)
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(404, PHOTO_NOT_FOUND)
    resolved = _resolve_photo_path(photo)
    if not resolved:
        raise HTTPException(404, "File not found on disk")
    response = FileResponse(str(resolved), media_type=photo.mime_type or MIME_JPEG)
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@router.get("/{photo_id}/thumbnail", responses=responses(401, 404))
def view_thumbnail(
    photo_id: int,
    db: DBSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_security)] = None,
    sig: str | None = Query(None),
    exp: int | None = Query(None),
):
    """Serve the photo thumbnail. Same auth options as view_photo."""
    _authenticate_image_request(photo_id, "thumbnail", credentials, sig, exp, db)
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(404, PHOTO_NOT_FOUND)
    if photo.thumbnail_path:
        thumb_resolved = _validate_path(photo.thumbnail_path)
        if thumb_resolved.exists():
            response = FileResponse(str(thumb_resolved), media_type=MIME_JPEG)
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
    # Fall back to full image
    resolved = _resolve_photo_path(photo)
    if not resolved:
        raise HTTPException(404, "File not found on disk")
    response = FileResponse(str(resolved), media_type=photo.mime_type or MIME_JPEG)
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@router.get("/{photo_id}/signed-urls", responses=responses(401, 404))
def get_signed_urls(photo_id: int, db: DBSession, _user: CurrentUser):
    """Issue a fresh pair of short-lived signed URLs for one photo. Used
    when an existing URL has expired (e.g. user idle past TTL)."""
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(404, PHOTO_NOT_FOUND)
    return _photo_urls(photo_id)


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
            raise HTTPException(400, "Invalid date format. Use ISO 8601 (e.g., 2026-04-02).")

    if pilot_ids is not None:
        # Replace pilot associations
        db.query(PhotoPilot).filter(PhotoPilot.photo_id == photo_id).delete()
        for pid_str in pilot_ids.split(","):
            pid_str = pid_str.strip()
            if pid_str.isdigit():
                db.add(PhotoPilot(photo_id=photo_id, pilot_id=int(pid_str)))

    db.commit()
    return {"message": "Photo updated"}


@router.post("/{photo_id}/flight/{flight_id}", responses=responses(401, 404))
def link_photo_flight(photo_id: int, flight_id: int, db: DBSession, user: SupervisorUser):
    """Link a photo to a flight (idempotent)."""
    if not db.query(Photo).filter(Photo.id == photo_id).first():
        raise HTTPException(404, PHOTO_NOT_FOUND)
    if not db.query(Flight).filter(Flight.id == flight_id).first():
        raise HTTPException(404, FLIGHT_NOT_FOUND)
    exists = db.query(PhotoFlight).filter(PhotoFlight.photo_id == photo_id, PhotoFlight.flight_id == flight_id).first()
    if not exists:
        db.add(PhotoFlight(photo_id=photo_id, flight_id=flight_id))
        db.commit()
    return {"ok": True}


@router.delete("/{photo_id}/flight/{flight_id}", responses=responses(401, 404))
def unlink_photo_flight(photo_id: int, flight_id: int, db: DBSession, user: SupervisorUser):
    """Unlink a photo from a flight."""
    db.query(PhotoFlight).filter(PhotoFlight.photo_id == photo_id, PhotoFlight.flight_id == flight_id).delete()
    db.commit()
    return {"ok": True}


@router.post("/{photo_id}/incident/{incident_id}", responses=responses(401, 404))
def link_photo_incident(photo_id: int, incident_id: int, db: DBSession, user: SupervisorUser):
    """Link a photo to an incident (idempotent)."""
    if not db.query(Photo).filter(Photo.id == photo_id).first():
        raise HTTPException(404, PHOTO_NOT_FOUND)
    if not db.query(Incident).filter(Incident.id == incident_id).first():
        raise HTTPException(404, INCIDENT_NOT_FOUND)
    exists = db.query(PhotoIncident).filter(PhotoIncident.photo_id == photo_id, PhotoIncident.incident_id == incident_id).first()
    if not exists:
        db.add(PhotoIncident(photo_id=photo_id, incident_id=incident_id))
        db.commit()
    return {"ok": True}


@router.delete("/{photo_id}/incident/{incident_id}", responses=responses(401, 404))
def unlink_photo_incident(photo_id: int, incident_id: int, db: DBSession, user: SupervisorUser):
    """Unlink a photo from an incident."""
    db.query(PhotoIncident).filter(PhotoIncident.photo_id == photo_id, PhotoIncident.incident_id == incident_id).delete()
    db.commit()
    return {"ok": True}


@router.delete("/{photo_id}", responses=responses(401, 404))
def delete_photo(photo_id: int, db: DBSession, user: PilotUser):
    """Delete a photo, its thumbnail, all associations, and on-disk files."""
    from app.services.audit import log_action
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(404, PHOTO_NOT_FOUND)

    # Delete associations (pilot, flight, incident)
    db.query(PhotoPilot).filter(PhotoPilot.photo_id == photo_id).delete()
    db.query(PhotoFlight).filter(PhotoFlight.photo_id == photo_id).delete()
    db.query(PhotoIncident).filter(PhotoIncident.photo_id == photo_id).delete()

    # Delete files from disk
    photo_path = _resolve_photo_path(photo)
    if photo_path and photo_path.exists():
        photo_path.unlink()
    if photo.thumbnail_path:
        thumb = Path(photo.thumbnail_path)
        if thumb.exists():
            thumb.unlink()

    log_action(db, user.id, user.display_name, "delete", "photo", photo_id, photo.original_filename)
    db.delete(photo)
    db.commit()
    return {"message": "Photo deleted"}
