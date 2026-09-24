"""Folder management router for document storage."""
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from sqlalchemy import func

from app.constants import FOLDER_NOT_FOUND
from app.models.folder import Folder
from app.models.document import Document
from app.deps import DBSession, CurrentUser, PilotUser
from app.responses import responses
from app.services.audit import compute_changes, log_action

router = APIRouter(prefix="/api/folders", tags=["folders"])


class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
    description: Optional[str] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


def _live_folder(db, folder_id: int) -> Folder:
    """The folder, unless it is missing or deleted.

    Raises:
        HTTPException: 404 either way.
    """
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.deleted_at.is_(None)).first()
    if not folder:
        raise HTTPException(404, FOLDER_NOT_FOUND)
    return folder


@router.get("", responses=responses(401))
def list_folders(db: DBSession, _user: CurrentUser):
    folders = db.query(Folder).filter(Folder.deleted_at.is_(None)).order_by(Folder.name).all()
    result = []
    for f in folders:
        doc_count = db.query(func.count(Document.id)).filter(
            Document.folder_id == f.id, Document.deleted_at.is_(None)).scalar() or 0
        result.append({
            "id": f.id,
            "name": f.name,
            "parent_id": f.parent_id,
            "description": f.description,
            "is_system": f.is_system,
            "document_count": doc_count,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        })
    return result


@router.get("/{folder_id}/documents", responses=responses(401, 404))
def get_folder_documents(folder_id: int, db: DBSession, _user: CurrentUser):
    _live_folder(db, folder_id)
    docs = (db.query(Document)
            .filter(Document.folder_id == folder_id, Document.deleted_at.is_(None))
            .order_by(Document.uploaded_at.desc()).all())
    return [{
        "id": d.id,
        "title": d.title,
        "filename": d.filename,
        "document_type": d.document_type,
        "mime_type": d.mime_type,
        "file_size_bytes": d.file_size_bytes,
        "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        "entity_type": d.entity_type,
        "notes": d.notes,
        "folder_id": d.folder_id,
        "legal_hold": d.legal_hold,
        "sha256": d.sha256,
    } for d in docs]


@router.post("", responses=responses(401))
def create_folder(data: FolderCreate, db: DBSession, user: PilotUser):
    folder = Folder(
        name=data.name,
        parent_id=data.parent_id,
        description=data.description,
    )
    db.add(folder)
    db.flush()
    log_action(db, user.id, user.display_name, "create", "folder", folder.id, folder.name)
    db.commit()
    db.refresh(folder)
    return {"id": folder.id, "name": folder.name, "message": "Folder created"}


@router.patch("/{folder_id}", responses=responses(400, 401, 404))
def update_folder(folder_id: int, data: FolderUpdate, db: DBSession, user: PilotUser):
    folder = _live_folder(db, folder_id)
    if folder.is_system:
        raise HTTPException(400, "Cannot rename system folders")
    updates = {k: v for k, v in (("name", data.name), ("description", data.description)) if v is not None}
    changes = compute_changes(folder, updates, list(updates))
    for key, value in updates.items():
        setattr(folder, key, value)
    if changes:
        log_action(db, user.id, user.display_name, "update", "folder", folder.id, folder.name, changes=changes)
    db.commit()
    return {"message": "Folder updated"}


@router.delete("/{folder_id}", responses=responses(400, 401, 404))
def delete_folder(folder_id: int, db: DBSession, user: PilotUser):
    folder = _live_folder(db, folder_id)
    if folder.is_system:
        raise HTTPException(400, "Cannot delete system folders")

    # Move documents to no folder
    moved = db.query(Document).filter(Document.folder_id == folder_id).update({"folder_id": None})

    # Move child folders to parent
    db.query(Folder).filter(Folder.parent_id == folder_id).update({"parent_id": folder.parent_id})

    # The record stays, marked deleted, so the trail can still name it.
    folder.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    log_action(db, user.id, user.display_name, "delete", "folder", folder.id, folder.name,
               details=f"{moved} document(s) moved to Unfiled" if moved else None)
    db.commit()
    return {"message": "Folder deleted"}
