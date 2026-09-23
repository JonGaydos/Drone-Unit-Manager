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
from PIL import Image as PILImage
from sqlalchemy.orm import Session

from app.config import settings
from app.constants import MIME_JPEG, PHOTO_NOT_FOUND, FLIGHT_NOT_FOUND, INCIDENT_NOT_FOUND, UTC_OFFSET
from app.database import get_db
from app.deps import AdminUser, DBSession, CurrentUser, PilotUser, SupervisorUser
from app.models.user import User
from app.models.photo import Photo, PhotoPilot, PhotoFlight, PhotoIncident
from app.models.pilot import Pilot
from app.models.flight import Flight
from app.models.incident import Incident
from app.responses import responses
from app.services import evidence
from app.services.audit import compute_changes, log_action
from app.services.file_validation import mime_for_filename, user_file_headers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/photos", tags=["photos"])

UPLOAD_DIR = str(Path(settings.UPLOAD_DIR) / "photos")
THUMB_WIDTH = 400  # Maximum thumbnail width in pixels

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}

# Cap decoded pixel count to defend against decompression-bomb images that
# would otherwise OOM the worker during thumbnail generation.
PILImage.MAX_IMAGE_PIXELS = 50_000_000

_security = HTTPBearer(auto_error=False)

# Signed image URLs replace the old ?token=<JWT> auth path. The JWT was a
# long-lived bearer credential that landed in browser history, referer
# headers, and reverse-proxy access logs. Signed URLs are short-lived,
# scoped to a single photo + action, and cannot be reused to access other
# endpoints if leaked.
SIGNED_URL_TTL_SECONDS = 600  # 10 minutes


def _sig_payload(photo_id: int, action: str, exp: int, viewer: int | None) -> bytes:
    """What a photo URL signs. The viewer, when present, is bound in so the
    view can be audited against the user it was issued to."""
    suffix = f":{viewer}" if viewer is not None else ""
    return f"{photo_id}:{action}:{exp}{suffix}".encode()


def _sign_photo(photo_id: int, action: str, ttl: int = SIGNED_URL_TTL_SECONDS,
                viewer: int | None = None) -> tuple[str, int]:
    """Create (signature, expires_at_epoch) for a photo URL. Action is
    typically 'view' or 'thumbnail'."""
    exp = int(time.time()) + ttl
    payload = _sig_payload(photo_id, action, exp, viewer)
    sig = hmac.new(settings.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()
    return sig, exp


def _verify_photo_sig(photo_id: int, action: str, sig: str | None, exp: int | None,
                      viewer: int | None = None) -> bool:
    """Constant-time validation of a photo signature. Returns True iff the
    signature matches AND the URL has not yet expired."""
    if not sig or exp is None:
        return False
    if exp < int(time.time()):
        return False
    payload = _sig_payload(photo_id, action, exp, viewer)
    expected = hmac.new(settings.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def _photo_urls(photo_id: int, viewer: int | None = None) -> dict:
    """Build a fresh pair of signed URLs (view + thumbnail) for a photo.

    Returned URLs are relative to the /api base (no leading /api), so the
    frontend's API client (which prepends its own '/api' base) gets the right
    final URL. Previously the leading '/api' produced '/api/api/photos/...'
    and broke every <img> tag on MediaPage."""
    view_sig, view_exp = _sign_photo(photo_id, "view", viewer=viewer)
    thumb_sig, thumb_exp = _sign_photo(photo_id, "thumbnail")
    viewer_param = f"&u={viewer}" if viewer is not None else ""
    return {
        "view_url": f"/photos/{photo_id}/view?sig={view_sig}&exp={view_exp}{viewer_param}",
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
    viewer: int | None = None,
) -> int | None:
    """Allow either (a) a valid Bearer JWT (for API clients) or (b) a fresh
    signed URL for this photo_id+action. Raises 401 on failure.

    Returns the id of the user the request is for: the bearer's, or the one the
    signed URL was issued to (None for a URL issued without one)."""
    if _verify_photo_sig(photo_id, action, sig, exp, viewer):
        return viewer
    if credentials:
        from app.routers.auth import user_from_login_token
        return user_from_login_token(credentials.credentials, db).id  # 401 if invalid or revoked
    raise HTTPException(401, "Not authenticated")


def _live_photo(db, photo_id: int) -> Photo:
    """The photo, unless it is missing or deleted.

    Raises:
        HTTPException: 404 either way; a deleted photo is out of reach until restored.
    """
    photo = db.query(Photo).filter(Photo.id == photo_id, Photo.deleted_at.is_(None)).first()
    if not photo:
        raise HTTPException(404, PHOTO_NOT_FOUND)
    return photo


def _photo_or_404(db, photo_id: int) -> Photo:
    """The photo whether deleted or not, for the restore, hold and purge routes."""
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(404, PHOTO_NOT_FOUND)
    return photo


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


def _parse_date_taken(date_taken: Optional[str]):
    """Parse an optional ISO 8601 date_taken form value. None when not provided;
    raises 400 on a malformed value."""
    if not date_taken:
        return None
    try:
        return datetime.fromisoformat(date_taken.replace("Z", UTC_OFFSET).replace(UTC_OFFSET, ""))
    except (ValueError, AttributeError):
        raise HTTPException(400, "Invalid date format. Use ISO 8601 (e.g., 2026-04-02).")


def _stream_to_disk(file_obj, file_path: str, first_chunk: bytes, chunk_size: int, max_size: int) -> tuple[int, str]:
    """Write an already-started upload stream to disk, enforcing the size cap.
    Returns (bytes written, SHA-256 hex digest); removes the partial file and
    raises 413 on overflow."""
    total = 0
    digest = hashlib.sha256()
    with open(file_path, "wb") as f:
        chunk = first_chunk
        while chunk:
            total += len(chunk)
            if total > max_size:
                f.close()
                os.remove(file_path)
                raise HTTPException(413, f"File too large. Maximum size is {max_size // (1024*1024)}MB")
            f.write(chunk)
            digest.update(chunk)
            chunk = file_obj.read(chunk_size)
    return total, digest.hexdigest()


def _attach_photo_pilots(db, photo_id: int, pilot_ids: Optional[str]) -> None:
    """Attach comma-separated pilot IDs to a photo, ignoring non-numeric tokens."""
    if not pilot_ids:
        return
    for pid_str in pilot_ids.split(","):
        pid_str = pid_str.strip()
        if pid_str.isdigit():
            db.add(PhotoPilot(photo_id=photo_id, pilot_id=int(pid_str)))


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
    parsed_date = _parse_date_taken(date_taken)

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
        mime_type=mime_for_filename(stored_name),
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
    chunk_size = 64 * 1024
    first = file.file.read(chunk_size)
    if not is_image(first):
        raise HTTPException(400, "File content is not a recognized image")
    photo.file_size, photo.sha256 = _stream_to_disk(file.file, file_path, first, chunk_size, settings.MAX_UPLOAD_SIZE)

    # Generate thumbnail
    photo.thumbnail_path = _generate_thumbnail(file_path, photo_dir, stored_name)

    # Create pilot associations
    _attach_photo_pilots(db, photo.id, pilot_ids)

    log_action(db, user.id, user.display_name, "upload", "photo", photo.id, photo.original_filename,
               details=f"{relative_path}, {photo.file_size} bytes, sha256 {photo.sha256}")
    db.commit()
    db.refresh(photo)
    return {"id": photo.id, "message": "Photo uploaded successfully"}


def _photo_list_item(p, pilot_ids_for_photo, pilots_map, viewer: int | None = None) -> dict:
    """Serialize one photo (with its resolved pilot names/ids and signed URLs)
    for the list endpoint."""
    pilot_names = []
    pilot_ids_list = []
    for pid in pilot_ids_for_photo:
        pilot = pilots_map.get(pid)
        if pilot:
            pilot_names.append(f"{pilot.first_name} {pilot.last_name}".strip())
            pilot_ids_list.append(pilot.id)
    urls = _photo_urls(p.id, viewer)
    return {
        "id": p.id,
        "filename": p.original_filename,
        "title": p.title,
        "description": p.description,
        "date_taken": p.date_taken.isoformat() if p.date_taken else None,
        "file_size": p.file_size,
        "mime_type": p.mime_type,
        "has_thumbnail": p.thumbnail_path is not None,
        "legal_hold": p.legal_hold,
        "sha256": p.sha256,
        "pilot_names": pilot_names,
        "pilot_ids": pilot_ids_list,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        **urls,
    }


@router.get("", responses=responses(401))
def list_photos(db: DBSession, user: CurrentUser, flight_id: int | None = None, incident_id: int | None = None):
    """List photos with their tagged pilot names.

    Optionally filter to photos linked to a given flight or incident. Uses
    batch loading for pilot associations to avoid N+1 query issues.

    Returns:
        List of photo metadata dicts ordered by date taken (newest first).
    """
    photos_q = db.query(Photo).filter(Photo.deleted_at.is_(None))
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

    result = [
        _photo_list_item(p, photo_assoc.get(p.id, []), pilots_map, user.id)
        for p in photos
    ]
    return result


def _resolve_photo_path(photo) -> Optional[Path]:
    """Resolve photo file path from date-based layout."""
    file_path = os.path.join(UPLOAD_DIR, photo.filename)
    resolved = _validate_path(file_path)
    if resolved.exists():
        return resolved
    return None


def _serve_image(path: Path, mime: str | None = None) -> FileResponse:
    """Serve a stored photo. The type comes from the server-chosen file
    extension, never the stored upload type, so a record saved with a spoofed
    type is still served as an image."""
    mime = mime or mime_for_filename(str(path))
    return FileResponse(str(path), media_type=mime, headers=user_file_headers(mime))


@router.get("/{photo_id}/view", responses=responses(401, 404))
def view_photo(
    photo_id: int,
    db: DBSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_security)] = None,
    sig: Annotated[str | None, Query()] = None,
    exp: Annotated[int | None, Query()] = None,
    u: Annotated[int | None, Query()] = None,
):
    """Serve the full-resolution photo file.

    Accepts EITHER a Bearer JWT (for API clients) OR a signed URL with
    sig+exp query params (for <img src='...'> tags from the SPA). Every view
    of the full image is audited; thumbnails are not."""
    viewer_id = _authenticate_image_request(photo_id, "view", credentials, sig, exp, db, u)
    photo = _live_photo(db, photo_id)
    resolved = _resolve_photo_path(photo)
    if not resolved:
        raise HTTPException(404, "File not found on disk")
    viewer = db.get(User, viewer_id) if viewer_id is not None else None
    log_action(db, viewer_id, viewer.display_name if viewer else "Signed link", "view", "photo",
               photo.id, photo.original_filename)
    db.commit()
    return _serve_image(resolved)


@router.get("/{photo_id}/thumbnail", responses=responses(401, 404))
def view_thumbnail(
    photo_id: int,
    db: DBSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_security)] = None,
    sig: Annotated[str | None, Query()] = None,
    exp: Annotated[int | None, Query()] = None,
):
    """Serve the photo thumbnail. Same auth options as view_photo."""
    _authenticate_image_request(photo_id, "thumbnail", credentials, sig, exp, db)
    photo = _live_photo(db, photo_id)
    if photo.thumbnail_path:
        thumb_resolved = _validate_path(photo.thumbnail_path)
        if thumb_resolved.exists():
            return _serve_image(thumb_resolved, MIME_JPEG)
    # Fall back to full image
    resolved = _resolve_photo_path(photo)
    if not resolved:
        raise HTTPException(404, "File not found on disk")
    return _serve_image(resolved)


@router.get("/{photo_id}/signed-urls", responses=responses(401, 404))
def get_signed_urls(photo_id: int, db: DBSession, user: CurrentUser):
    """Issue a fresh pair of short-lived signed URLs for one photo. Used
    when an existing URL has expired (e.g. user idle past TTL)."""
    _live_photo(db, photo_id)
    return _photo_urls(photo_id, user.id)


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
    photo = _live_photo(db, photo_id)

    updates = {k: v for k, v in (("title", title), ("description", description)) if v is not None}
    if date_taken is not None:
        try:
            updates["date_taken"] = datetime.fromisoformat(date_taken.replace("Z", UTC_OFFSET).replace(UTC_OFFSET, ""))
        except (ValueError, AttributeError):
            raise HTTPException(400, "Invalid date format. Use ISO 8601 (e.g., 2026-04-02).")
    changes = compute_changes(photo, updates, list(updates))
    for key, value in updates.items():
        setattr(photo, key, value)

    if pilot_ids is not None:
        # Replace pilot associations
        db.query(PhotoPilot).filter(PhotoPilot.photo_id == photo_id).delete()
        _attach_photo_pilots(db, photo_id, pilot_ids)

    if changes or pilot_ids is not None:
        log_action(db, user.id, user.display_name, "update", "photo", photo.id, photo.original_filename,
                   changes=changes or None,
                   details=f"Pilots set to [{pilot_ids}]" if pilot_ids is not None else None)
    db.commit()
    return {"message": "Photo updated"}


@router.post("/{photo_id}/flight/{flight_id}", responses=responses(401, 404))
def link_photo_flight(photo_id: int, flight_id: int, db: DBSession, user: SupervisorUser):
    """Link a photo to a flight (idempotent)."""
    _live_photo(db, photo_id)
    if not db.query(Flight).filter(Flight.id == flight_id).first():
        raise HTTPException(404, FLIGHT_NOT_FOUND)
    exists = db.query(PhotoFlight).filter(PhotoFlight.photo_id == photo_id, PhotoFlight.flight_id == flight_id).first()
    if not exists:
        db.add(PhotoFlight(photo_id=photo_id, flight_id=flight_id))
        log_action(db, user.id, user.display_name, "link", "photo", photo_id, details=f"Linked to flight {flight_id}")
        db.commit()
    return {"ok": True}


@router.delete("/{photo_id}/flight/{flight_id}", responses=responses(401, 404))
def unlink_photo_flight(photo_id: int, flight_id: int, db: DBSession, user: SupervisorUser):
    """Unlink a photo from a flight."""
    if db.query(PhotoFlight).filter(PhotoFlight.photo_id == photo_id, PhotoFlight.flight_id == flight_id).delete():
        log_action(db, user.id, user.display_name, "unlink", "photo", photo_id, details=f"Unlinked from flight {flight_id}")
    db.commit()
    return {"ok": True}


@router.post("/{photo_id}/incident/{incident_id}", responses=responses(401, 404))
def link_photo_incident(photo_id: int, incident_id: int, db: DBSession, user: SupervisorUser):
    """Link a photo to an incident (idempotent)."""
    _live_photo(db, photo_id)
    if not db.query(Incident).filter(Incident.id == incident_id).first():
        raise HTTPException(404, INCIDENT_NOT_FOUND)
    exists = db.query(PhotoIncident).filter(PhotoIncident.photo_id == photo_id, PhotoIncident.incident_id == incident_id).first()
    if not exists:
        db.add(PhotoIncident(photo_id=photo_id, incident_id=incident_id))
        log_action(db, user.id, user.display_name, "link", "photo", photo_id, details=f"Linked to incident {incident_id}")
        db.commit()
    return {"ok": True}


@router.delete("/{photo_id}/incident/{incident_id}", responses=responses(401, 404))
def unlink_photo_incident(photo_id: int, incident_id: int, db: DBSession, user: SupervisorUser):
    """Unlink a photo from an incident."""
    if db.query(PhotoIncident).filter(PhotoIncident.photo_id == photo_id, PhotoIncident.incident_id == incident_id).delete():
        log_action(db, user.id, user.display_name, "unlink", "photo", photo_id, details=f"Unlinked from incident {incident_id}")
    db.commit()
    return {"ok": True}


@router.delete("/{photo_id}", responses=responses(401, 404, 409))
def delete_photo(photo_id: int, db: DBSession, user: PilotUser):
    """Move a photo to Recently deleted. The file and its links stay, so a
    supervisor can restore it; only an admin purge removes it for good."""
    photo = _live_photo(db, photo_id)
    evidence.soft_delete(photo, user)
    log_action(db, user.id, user.display_name, "delete", "photo", photo_id, photo.original_filename)
    db.commit()
    return {"message": "Photo deleted"}


@router.get("/deleted", responses=responses(401, 403))
def list_deleted_photos(db: DBSession, _user: SupervisorUser):
    """Deleted photos, newest deletion first."""
    photos = (db.query(Photo).filter(Photo.deleted_at.is_not(None))
              .order_by(Photo.deleted_at.desc()).all())
    user_ids = {p.deleted_by_id for p in photos if p.deleted_by_id}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return [evidence.deleted_row(p, p.title or p.original_filename, users) for p in photos]


@router.post("/{photo_id}/restore", responses=responses(401, 403, 404, 409))
def restore_photo(photo_id: int, db: DBSession, user: SupervisorUser):
    """Bring a deleted photo back, with the links it had."""
    photo = _photo_or_404(db, photo_id)
    evidence.restore(photo)
    log_action(db, user.id, user.display_name, "restore", "photo", photo_id, photo.original_filename)
    db.commit()
    return {"ok": True}


@router.put("/{photo_id}/hold", responses=responses(401, 403, 404))
def set_photo_hold(photo_id: int, data: evidence.HoldUpdate, db: DBSession, user: SupervisorUser):
    """Place or release a legal hold. A held photo cannot be deleted or purged."""
    photo = _photo_or_404(db, photo_id)
    if photo.legal_hold != data.legal_hold:
        photo.legal_hold = data.legal_hold
        log_action(db, user.id, user.display_name, "hold" if data.legal_hold else "release_hold",
                   "photo", photo_id, photo.original_filename)
        db.commit()
    return {"ok": True, "legal_hold": photo.legal_hold}


@router.delete("/{photo_id}/purge", responses=responses(401, 403, 404, 409))
def purge_photo(photo_id: int, db: DBSession, admin: AdminUser):
    """Remove a deleted photo for good: its links, its files, and its record.
    Refused unless the photo is already deleted and not on legal hold."""
    photo = _photo_or_404(db, photo_id)
    evidence.check_purgeable(photo)

    db.query(PhotoPilot).filter(PhotoPilot.photo_id == photo_id).delete()
    db.query(PhotoFlight).filter(PhotoFlight.photo_id == photo_id).delete()
    db.query(PhotoIncident).filter(PhotoIncident.photo_id == photo_id).delete()
    files = [os.path.join(UPLOAD_DIR, photo.filename), photo.thumbnail_path]
    log_action(db, admin.id, admin.display_name, "purge", "photo", photo_id, photo.original_filename,
               details=f"sha256 {photo.sha256 or 'not recorded'}")
    db.delete(photo)
    db.commit()
    # Files go only once the record is gone, so a failed commit leaves both.
    for path in files:
        evidence.remove_file(path, UPLOAD_DIR)
    return {"ok": True}
