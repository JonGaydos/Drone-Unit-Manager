"""Org-level operating authority records: COAs and Part 107 waivers.

The unit's own authority to fly, tracked the way a pilot's Part 107 certificate
already is: issue and expiry dates, a derived status, attached documents, and a
feed into the compliance score. Admin and Supervisor write; Pilot and Viewer read.
"""

import os
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func

from app.constants import OPERATING_AUTHORITY_NOT_FOUND
from app.deps import CurrentUser, DBSession, SupervisorUser
from app.models.document import Document
from app.models.operating_authority import (
    AUTHORITY_TYPES,
    RECORD_STATUSES,
    OperatingAuthority,
    authority_status,
)
from app.responses import responses
from app.services.audit import log_action

router = APIRouter(prefix="/api/operating-authorities", tags=["operating-authorities"])

DOCUMENT_ENTITY_TYPE = "operating_authority"


class AuthorityCreate(BaseModel):
    authority_type: str
    title: str
    identifier: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    record_status: str = "active"
    grounds_unit: bool = True
    notes: Optional[str] = None


class AuthorityUpdate(BaseModel):
    authority_type: Optional[str] = None
    title: Optional[str] = None
    identifier: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    record_status: Optional[str] = None
    grounds_unit: Optional[bool] = None
    notes: Optional[str] = None


def _validate(authority_type: Optional[str], record_status: Optional[str]) -> None:
    if authority_type is not None and authority_type not in AUTHORITY_TYPES:
        raise HTTPException(400, f"authority_type must be one of {sorted(AUTHORITY_TYPES)}")
    if record_status is not None and record_status not in RECORD_STATUSES:
        raise HTTPException(400, f"record_status must be one of {sorted(RECORD_STATUSES)}")


def _document_counts(db, authority_ids: list[int]) -> dict[int, int]:
    """Attached-document count per authority, in one query (avoids an N+1)."""
    if not authority_ids:
        return {}
    rows = (
        db.query(Document.entity_id, func.count(Document.id))
        .filter(
            Document.entity_type == DOCUMENT_ENTITY_TYPE,
            Document.entity_id.in_(authority_ids),
        )
        .group_by(Document.entity_id)
        .all()
    )
    return {entity_id: count for entity_id, count in rows}


def _serialize(a: OperatingAuthority, today: date, document_count: int = 0) -> dict:
    return {
        "id": a.id,
        "authority_type": a.authority_type,
        "identifier": a.identifier,
        "title": a.title,
        "issue_date": a.issue_date.isoformat() if a.issue_date else None,
        "expiry_date": a.expiry_date.isoformat() if a.expiry_date else None,
        "status": authority_status(a, today),
        "days_remaining": (a.expiry_date - today).days if a.expiry_date else None,
        "record_status": a.record_status,
        "grounds_unit": a.grounds_unit,
        "notes": a.notes,
        "document_count": document_count,
    }


@router.get("", responses=responses(401))
def list_authorities(db: DBSession, user: CurrentUser, record_status: Optional[str] = None):
    """List operating authorities, newest expiry first. Superseded and
    not-applicable records are included unless filtered out."""
    q = db.query(OperatingAuthority)
    if record_status:
        _validate(None, record_status)
        q = q.filter(OperatingAuthority.record_status == record_status)
    authorities = q.order_by(
        OperatingAuthority.record_status,
        OperatingAuthority.expiry_date.is_(None),
        OperatingAuthority.expiry_date,
    ).all()
    today = date.today()
    counts = _document_counts(db, [a.id for a in authorities])
    return [_serialize(a, today, counts.get(a.id, 0)) for a in authorities]


@router.get("/{authority_id}", responses=responses(401, 404))
def get_authority(authority_id: int, db: DBSession, user: CurrentUser):
    a = db.query(OperatingAuthority).filter(OperatingAuthority.id == authority_id).first()
    if not a:
        raise HTTPException(404, OPERATING_AUTHORITY_NOT_FOUND)
    counts = _document_counts(db, [a.id])
    return _serialize(a, date.today(), counts.get(a.id, 0))


@router.post("", status_code=201, responses=responses(400, 401))
def create_authority(data: AuthorityCreate, db: DBSession, user: SupervisorUser):
    _validate(data.authority_type, data.record_status)
    a = OperatingAuthority(**data.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    log_action(db, user.id, user.display_name, "create", "operating_authority", a.id, a.title)
    db.commit()
    return _serialize(a, date.today())


@router.patch("/{authority_id}", responses=responses(400, 401, 404))
def update_authority(authority_id: int, data: AuthorityUpdate, db: DBSession, user: SupervisorUser):
    a = db.query(OperatingAuthority).filter(OperatingAuthority.id == authority_id).first()
    if not a:
        raise HTTPException(404, OPERATING_AUTHORITY_NOT_FOUND)
    update_data = data.model_dump(exclude_unset=True)
    _validate(update_data.get("authority_type"), update_data.get("record_status"))
    for key, val in update_data.items():
        setattr(a, key, val)
    db.commit()
    db.refresh(a)
    log_action(db, user.id, user.display_name, "update", "operating_authority", a.id, a.title,
               changes={k: str(v) for k, v in update_data.items()})
    db.commit()
    counts = _document_counts(db, [a.id])
    return _serialize(a, date.today(), counts.get(a.id, 0))


@router.delete("/{authority_id}", responses=responses(401, 404))
def delete_authority(authority_id: int, db: DBSession, user: SupervisorUser):
    a = db.query(OperatingAuthority).filter(OperatingAuthority.id == authority_id).first()
    if not a:
        raise HTTPException(404, OPERATING_AUTHORITY_NOT_FOUND)

    # Documents attach by (entity_type, entity_id) rather than a foreign key, and
    # SQLite reuses row ids, so leaving them behind would hand this authority's
    # paperwork to whichever record is created next. Delete them with the record.
    docs = db.query(Document).filter(
        Document.entity_type == DOCUMENT_ENTITY_TYPE,
        Document.entity_id == authority_id,
    ).all()
    for doc in docs:
        file_path = Path(doc.file_path)
        if file_path.exists():
            os.remove(file_path)
        db.delete(doc)

    log_action(db, user.id, user.display_name, "delete", "operating_authority", a.id, a.title,
               details=f"Deleted {len(docs)} attached document(s)" if docs else None)
    db.delete(a)
    db.commit()
    return {"ok": True}
