"""Folder management router for document storage."""
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.folder import Folder
from app.models.document import Document
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/folders", tags=["folders"])


class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
    description: Optional[str] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


@router.get("")
def list_folders(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    folders = db.query(Folder).order_by(Folder.name).all()
    result = []
    for f in folders:
        doc_count = db.query(func.count(Document.id)).filter(Document.folder_id == f.id).scalar() or 0
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


@router.get("/{folder_id}/documents")
def get_folder_documents(folder_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(404, "Folder not found")
    docs = db.query(Document).filter(Document.folder_id == folder_id).order_by(Document.uploaded_at.desc()).all()
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
    } for d in docs]


@router.post("")
def create_folder(data: FolderCreate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    folder = Folder(
        name=data.name,
        parent_id=data.parent_id,
        description=data.description,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return {"id": folder.id, "name": folder.name, "message": "Folder created"}


@router.patch("/{folder_id}")
def update_folder(folder_id: int, data: FolderUpdate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(404, "Folder not found")
    if folder.is_system:
        raise HTTPException(400, "Cannot rename system folders")
    if data.name is not None:
        folder.name = data.name
    if data.description is not None:
        folder.description = data.description
    db.commit()
    return {"message": "Folder updated"}


@router.delete("/{folder_id}")
def delete_folder(folder_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(404, "Folder not found")
    if folder.is_system:
        raise HTTPException(400, "Cannot delete system folders")

    # Move documents to no folder
    db.query(Document).filter(Document.folder_id == folder_id).update({"folder_id": None})

    # Move child folders to parent
    db.query(Folder).filter(Folder.parent_id == folder_id).update({"parent_id": folder.parent_id})

    db.delete(folder)
    db.commit()
    return {"message": "Folder deleted"}
