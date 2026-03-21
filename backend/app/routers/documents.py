import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.user import User
from app.routers.auth import get_current_user, require_admin
from app.schemas.document import DocumentOut

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _doc_to_out(doc: Document) -> DocumentOut:
    out = DocumentOut.model_validate(doc)
    out.view_url = f"/api/documents/{doc.id}/view"
    return out


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    entity_type: str = Form(...),
    entity_id: int = Form(...),
    document_type: str = Form(...),
    title: str = Form(...),
    notes: str | None = Form(default=None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    upload_dir = Path(settings.UPLOAD_DIR) / "documents" / entity_type / str(entity_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "upload"
    dest = upload_dir / filename
    counter = 1
    while dest.exists():
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        dest = upload_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    contents = await file.read()
    dest.write_bytes(contents)

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
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _doc_to_out(doc)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    entity_type: str | None = None,
    entity_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Document)
    if entity_type:
        q = q.filter(Document.entity_type == entity_type)
    if entity_id:
        q = q.filter(Document.entity_id == entity_id)
    rows = q.order_by(Document.uploaded_at.desc()).all()
    return [_doc_to_out(r) for r in rows]


@router.get("/{doc_id}/view")
def view_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Path traversal prevention
    resolved = Path(doc.file_path).resolve()
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    if not str(resolved).startswith(str(upload_root)):
        raise HTTPException(status_code=403, detail="Access denied")

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


@router.patch("/{doc_id}", response_model=DocumentOut)
def update_document(
    doc_id: int,
    title: str = None,
    document_type: str = None,
    notes: str = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if title is not None:
        doc.title = title
    if document_type is not None:
        doc.document_type = document_type
    if notes is not None:
        doc.notes = notes
    db.commit()
    db.refresh(doc)
    return _doc_to_out(doc)


@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = Path(doc.file_path)
    if file_path.exists():
        os.remove(file_path)

    db.delete(doc)
    db.commit()
    return {"ok": True}
