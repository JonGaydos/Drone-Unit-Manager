"""Document management endpoints for uploading, viewing, and organizing files.

Supports attaching documents to pilots, vehicles, and certifications with
file-type validation and path-traversal protection.
"""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.constants import DOCUMENT_NOT_FOUND, ACCESS_DENIED
from app.deps import DBSession, CurrentUser, PilotUser
from app.models.document import Document
from app.schemas.document import DocumentOut
from app.responses import responses

router = APIRouter(prefix="/api/documents", tags=["documents"])

# Whitelist of permitted file extensions for document uploads
ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".rtf",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif",
    ".ppt", ".pptx", ".odt", ".ods", ".odp",
}


def _doc_to_out(doc: Document) -> DocumentOut:
    """Convert a Document ORM instance to its API response schema with a view URL."""
    out = DocumentOut.model_validate(doc)
    out.view_url = f"/api/documents/{doc.id}/view"
    return out


@router.post("/upload", response_model=DocumentOut, responses=responses(400, 413))
async def upload_document(
    db: DBSession,
    admin: PilotUser,
    file: UploadFile = File(...),
    entity_type: str = Form(...),
    entity_id: int = Form(...),
    document_type: str = Form(...),
    title: str = Form(...),
    notes: str | None = Form(default=None),
    folder_id: int | None = Form(default=None),
):
    """Upload a document and attach it to a pilot, vehicle, or certification.

    Args:
        file: The uploaded file.
        entity_type: Parent entity type (pilot, vehicle, certification).
        entity_id: ID of the parent entity.
        document_type: Classification label (e.g., "insurance", "manual").
        title: Human-readable document title.
        notes: Optional free-text notes.
        folder_id: Optional folder for organization.
        db: Database session.
        admin: Authenticated user (pilot role or higher).

    Returns:
        The created document record.
    """
    filename = file.filename or "upload"

    # Validate file extension
    ext = Path(filename).suffix.lower()
    if ext and ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' not allowed.")

    upload_dir = Path(settings.UPLOAD_DIR) / "documents" / entity_type / str(entity_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest = upload_dir / filename
    # Deduplicate filenames by appending a counter suffix
    counter = 1
    while dest.exists():
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        dest = upload_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB")
    dest.write_bytes(contents)

    # Map entity_type to the appropriate foreign key column
    pilot_id = entity_id if entity_type == "pilot" else None
    vehicle_id = entity_id if entity_type == "vehicle" else None
    certification_id = entity_id if entity_type == "certification" else None

    doc = Document(
        pilot_id=pilot_id,
        vehicle_id=vehicle_id,
        certification_id=certification_id,
        entity_type=entity_type,
        entity_id=entity_id,
        document_type=document_type,
        title=title,
        filename=dest.name,
        file_path=str(dest),
        mime_type=file.content_type or "application/octet-stream",
        file_size_bytes=len(contents),
        notes=notes,
        folder_id=folder_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _doc_to_out(doc)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    db: DBSession,
    user: CurrentUser,
    entity_type: str | None = None,
    entity_id: int | None = None):
    """List documents with optional filtering by entity type and ID.

    Args:
        entity_type: Filter by parent entity type (pilot, vehicle, certification).
        entity_id: Filter by parent entity ID.

    Returns:
        List of document records, newest first.
    """
    q = db.query(Document)
    if entity_type:
        q = q.filter(Document.entity_type == entity_type)
    if entity_id:
        q = q.filter(Document.entity_id == entity_id)
    rows = q.order_by(Document.uploaded_at.desc()).all()
    return [_doc_to_out(r) for r in rows]


@router.get("/{doc_id}/view", responses=responses(403, 404))
def view_document(
    doc_id: int,
    db: DBSession,
    _user: CurrentUser,
):
    """Serve a document file for viewing or download.

    PDFs are served inline; all other types as attachments.
    Includes path-traversal prevention.

    Args:
        doc_id: The document record ID.

    Returns:
        FileResponse with the document contents.
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND)

    # Path traversal prevention
    resolved = Path(doc.file_path).resolve()
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    if not str(resolved).startswith(str(upload_root)):
        raise HTTPException(status_code=403, detail=ACCESS_DENIED)

    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Serve PDFs inline, everything else as attachment
    if doc.mime_type and doc.mime_type.startswith("application/pdf"):
        disposition = "inline"
    else:
        disposition = "attachment"

    return FileResponse(
        path=str(file_path),
        media_type=doc.mime_type,
        filename=doc.filename,
        content_disposition_type=disposition,
    )


class DocumentUpdate(BaseModel):
    """Schema for partial document metadata updates."""
    title: str | None = None
    document_type: str | None = None
    notes: str | None = None
    folder_id: int | None = None


@router.patch("/{doc_id}", response_model=DocumentOut, responses=responses(404))
def update_document(
    doc_id: int,
    data: DocumentUpdate,
    db: DBSession,
    user: PilotUser,
):
    """Update a document's metadata (title, type, notes, folder).

    Args:
        doc_id: The document record ID.
        data: Fields to update (only provided fields are changed).

    Returns:
        The updated document record.
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND)
    update_fields = data.model_dump(exclude_unset=True)
    for key, value in update_fields.items():
        setattr(doc, key, value)
    db.commit()
    db.refresh(doc)
    return _doc_to_out(doc)


@router.delete("/{doc_id}", responses=responses(404))
def delete_document(
    doc_id: int,
    db: DBSession,
    admin: PilotUser,
):
    """Delete a document record and remove the file from disk."""
    from app.services.audit import log_action
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND)

    file_path = Path(doc.file_path)
    if file_path.exists():
        os.remove(file_path)

    log_action(db, admin.id, admin.display_name, "delete", "document", doc_id, doc.title or doc.filename)
    db.delete(doc)
    db.commit()
    return {"ok": True}
