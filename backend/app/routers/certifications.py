import calendar
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func

from app.constants import CERTIFICATION_TYPE_NOT_FOUND, PILOT_CERTIFICATION_NOT_FOUND, EQUIPMENT_QUAL_NOT_FOUND
from app.deps import DBSession
from app.models.user import User
from app.routers.auth import require_permission
from app.responses import responses
from app.models.certification import CertificationType, PilotCertification, PilotEquipmentQual
from app.models.pilot import Pilot
from app.schemas.certification import (
    CertificationTypeCreate, CertificationTypeUpdate, CertificationTypeOut,
    PilotCertificationCreate, PilotCertificationUpdate, PilotCertificationOut,
    PilotEquipmentQualCreate, PilotEquipmentQualUpdate, PilotEquipmentQualOut,
    CertRenewRequest, EXPIRY_BEFORE_ISSUE,
)


class ReorderItem(BaseModel):
    id: int
    sort_order: int


class ReorderRequest(BaseModel):
    items: list[ReorderItem]

router = APIRouter(tags=["certifications"])

ViewUser = Annotated[User, Depends(require_permission("certifications.view"))]
ManageUser = Annotated[User, Depends(require_permission("certifications.manage"))]


@router.get("/api/certification-types", response_model=list[CertificationTypeOut])
def list_certification_types(
    db: DBSession,
    user: ViewUser,
):
    rows = db.query(CertificationType).order_by(CertificationType.sort_order, CertificationType.name).all()
    return [CertificationTypeOut.model_validate(r) for r in rows]


def _check_type_name_free(db, name: str, ct_id: int | None = None) -> None:
    """Refuse a cert type name another type already has, ignoring case and
    surrounding spaces."""
    q = db.query(CertificationType).filter(func.lower(func.trim(CertificationType.name)) == name.strip().lower())
    if ct_id is not None:
        q = q.filter(CertificationType.id != ct_id)
    if q.first():
        raise HTTPException(status_code=400, detail="Certification type already exists")


@router.post("/api/certification-types", response_model=CertificationTypeOut, responses=responses(400))
def create_certification_type(
    data: CertificationTypeCreate,
    db: DBSession,
    admin: ManageUser,
):
    from app.services.audit import log_action
    _check_type_name_free(db, data.name)
    ct = CertificationType(**data.model_dump())
    db.add(ct)
    db.flush()
    log_action(db, admin.id, admin.display_name, "create", "certification_type", ct.id, ct.name)
    db.commit()
    db.refresh(ct)
    return CertificationTypeOut.model_validate(ct)


@router.patch("/api/certification-types/reorder")
def reorder_certification_types(
    data: ReorderRequest,
    db: DBSession,
    admin: ManageUser,
):
    for item in data.items:
        ct = db.query(CertificationType).filter(CertificationType.id == item.id).first()
        if ct:
            ct.sort_order = item.sort_order
    db.commit()
    return {"ok": True}


@router.patch("/api/certification-types/{ct_id}", response_model=CertificationTypeOut, responses=responses(400, 404))
def update_certification_type(
    ct_id: int,
    data: CertificationTypeUpdate,
    db: DBSession,
    admin: ManageUser,
):
    from app.services.audit import log_action
    ct = db.query(CertificationType).filter(CertificationType.id == ct_id).first()
    if not ct:
        raise HTTPException(status_code=404, detail=CERTIFICATION_TYPE_NOT_FOUND)
    update_data = data.model_dump(exclude_unset=True)
    if "name" in update_data:
        _check_type_name_free(db, update_data["name"], ct_id)
    for key, value in update_data.items():
        setattr(ct, key, value)
    log_action(db, admin.id, admin.display_name, "update", "certification_type", ct.id, ct.name)
    db.commit()
    db.refresh(ct)
    return CertificationTypeOut.model_validate(ct)


@router.delete("/api/certification-types/{ct_id}", responses=responses(404, 409))
def delete_certification_type(
    ct_id: int,
    db: DBSession,
    admin: ManageUser,
):
    from app.services.audit import log_action
    ct = db.query(CertificationType).filter(CertificationType.id == ct_id).first()
    if not ct:
        raise HTTPException(status_code=404, detail=CERTIFICATION_TYPE_NOT_FOUND)
    in_use = db.query(PilotCertification).filter(PilotCertification.certification_type_id == ct_id).count()
    if in_use:
        raise HTTPException(status_code=409, detail=(
            f"In use by {in_use} pilot certification record(s). Hide it instead to take it off the matrix "
            "and keep the records."))
    ct_name = ct.name
    log_action(db, admin.id, admin.display_name, "delete", "certification_type", ct_id, ct_name)
    db.delete(ct)
    db.commit()
    return {"ok": True}


def _pilot_cert_to_out(pc: PilotCertification) -> PilotCertificationOut:
    out = PilotCertificationOut.model_validate(pc)
    if pc.pilot:
        out.pilot_name = pc.pilot.full_name
    if pc.certification_type:
        out.cert_type_name = pc.certification_type.name
    return out


@router.get("/api/pilot-certifications", response_model=list[PilotCertificationOut])
def list_pilot_certifications(
    db: DBSession,
    user: ViewUser,
    pilot_id: int | None = None,
    cert_type_id: int | None = None):
    q = db.query(PilotCertification)
    if pilot_id:
        q = q.filter(PilotCertification.pilot_id == pilot_id)
    if cert_type_id:
        q = q.filter(PilotCertification.certification_type_id == cert_type_id)
    rows = q.order_by(PilotCertification.pilot_id, PilotCertification.certification_type_id).all()
    return [_pilot_cert_to_out(r) for r in rows]


LIVE_CERT_EXISTS = "This pilot already holds this certification; edit or renew it instead"


def _has_other_live_cert(db, pilot_id: int, cert_type_id: int, exclude_id: int | None = None) -> bool:
    """Whether the pilot holds a non-renewed certification of this type (other
    than exclude_id). One live record per pilot and type keeps the matrix and
    compliance on the same row."""
    q = db.query(PilotCertification).filter(
        PilotCertification.pilot_id == pilot_id,
        PilotCertification.certification_type_id == cert_type_id,
        PilotCertification.status != "renewed",
    )
    if exclude_id is not None:
        q = q.filter(PilotCertification.id != exclude_id)
    return db.query(q.exists()).scalar()


@router.post("/api/pilot-certifications", response_model=PilotCertificationOut, responses=responses(400))
def create_pilot_certification(
    data: PilotCertificationCreate,
    db: DBSession,
    admin: ManageUser,
):
    from app.services.audit import log_action
    if data.status != "renewed" and _has_other_live_cert(db, data.pilot_id, data.certification_type_id):
        raise HTTPException(status_code=400, detail=LIVE_CERT_EXISTS)
    pc = PilotCertification(**data.model_dump())
    db.add(pc)
    db.flush()
    pilot = db.query(Pilot).filter(Pilot.id == pc.pilot_id).first()
    ct = db.query(CertificationType).filter(CertificationType.id == pc.certification_type_id).first()
    log_action(db, admin.id, admin.display_name, "create", "pilot_certification", pc.id,
               f"{pilot.full_name if pilot else 'Unknown'} - {ct.name if ct else 'Unknown'}")
    db.commit()
    db.refresh(pc)
    return _pilot_cert_to_out(pc)


@router.patch("/api/pilot-certifications/{pc_id}", response_model=PilotCertificationOut, responses=responses(400, 404, 422))
def update_pilot_certification(
    pc_id: int,
    data: PilotCertificationUpdate,
    db: DBSession,
    admin: ManageUser,
):
    from app.services.audit import log_action
    pc = db.query(PilotCertification).filter(PilotCertification.id == pc_id).first()
    if not pc:
        raise HTTPException(status_code=404, detail=PILOT_CERTIFICATION_NOT_FOUND)
    update_data = data.model_dump(exclude_unset=True)
    issue = update_data.get("issue_date", pc.issue_date)
    expiry = update_data.get("expiration_date", pc.expiration_date)
    if issue and expiry and expiry < issue:
        raise HTTPException(status_code=422, detail=EXPIRY_BEFORE_ISSUE)
    if pc.status == "renewed" and update_data.get("status", "renewed") != "renewed"             and _has_other_live_cert(db, pc.pilot_id, pc.certification_type_id, pc.id):
        raise HTTPException(status_code=400, detail=LIVE_CERT_EXISTS)
    for key, value in update_data.items():
        setattr(pc, key, value)
    pilot = db.query(Pilot).filter(Pilot.id == pc.pilot_id).first()
    ct = db.query(CertificationType).filter(CertificationType.id == pc.certification_type_id).first()
    log_action(db, admin.id, admin.display_name, "update", "pilot_certification", pc.id,
               f"{pilot.full_name if pilot else 'Unknown'} - {ct.name if ct else 'Unknown'}")
    db.commit()
    db.refresh(pc)
    return _pilot_cert_to_out(pc)


def _do_renew(db, old, issue_date, expiration_date=None, certificate_number=None, notes=None):
    """Create a renewed PilotCertification from `old`: auto-calculate the
    expiration from the cert type's renewal_period_months when not given, mark
    the old one as renewed, and link the new one back. Caller commits."""
    expiry = expiration_date
    if not expiry:
        ct = db.query(CertificationType).filter(CertificationType.id == old.certification_type_id).first()
        if ct and ct.renewal_period_months:
            m = issue_date.month + ct.renewal_period_months
            y = issue_date.year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            last_day = calendar.monthrange(y, m)[1]
            expiry = issue_date.replace(year=y, month=m, day=min(issue_date.day, last_day))
    old.status = "renewed"
    new_cert = PilotCertification(
        pilot_id=old.pilot_id,
        certification_type_id=old.certification_type_id,
        status="complete",
        issue_date=issue_date,
        expiration_date=expiry,
        certificate_number=certificate_number or old.certificate_number,
        nist_level=old.nist_level,
        notes=notes,
        renewed_from_id=old.id,
    )
    db.add(new_cert)
    db.flush()
    return new_cert


@router.post("/api/pilot-certifications/{pc_id}/renew", response_model=PilotCertificationOut, responses=responses(400, 404))
def renew_pilot_certification(
    pc_id: int,
    data: CertRenewRequest,
    db: DBSession,
    admin: ManageUser,
):
    """Renew a certification: mark old as renewed, create new with history link."""
    from app.services.audit import log_action

    old = db.query(PilotCertification).filter(PilotCertification.id == pc_id).first()
    if not old:
        raise HTTPException(status_code=404, detail=PILOT_CERTIFICATION_NOT_FOUND)
    if old.status == "renewed":
        raise HTTPException(status_code=400, detail="This certification is already renewed; renew its current record instead")

    new_cert = _do_renew(db, old, data.issue_date, data.expiration_date,
                         data.certificate_number, data.notes)

    pilot = db.query(Pilot).filter(Pilot.id == old.pilot_id).first()
    ct = db.query(CertificationType).filter(CertificationType.id == old.certification_type_id).first()
    log_action(db, admin.id, admin.display_name, "create", "pilot_certification", new_cert.id,
               f"Renewed: {pilot.full_name if pilot else 'Unknown'} - {ct.name if ct else 'Unknown'}")

    db.commit()
    db.refresh(new_cert)
    return _pilot_cert_to_out(new_cert)


class CertBulkRenewRequest(BaseModel):
    pilot_certification_ids: list[int]
    issue_date: date
    notes: Optional[str] = None


@router.post("/api/pilot-certifications/bulk-renew", responses=responses(400))
def bulk_renew_pilot_certifications(data: CertBulkRenewRequest, db: DBSession, admin: ManageUser):
    """Renew many certifications at once (e.g. a training day): each selected
    cert is renewed with the same issue date, expiration auto-calculated per
    cert type. Already-renewed certs are skipped. Needs the certifications.manage permission."""
    from app.services.audit import log_action
    if not data.pilot_certification_ids:
        raise HTTPException(400, "No certifications selected")
    olds = db.query(PilotCertification).filter(
        PilotCertification.id.in_(data.pilot_certification_ids),
        PilotCertification.status != "renewed",
    ).all()
    for old in olds:
        _do_renew(db, old, data.issue_date, None, None, data.notes)
    log_action(db, admin.id, admin.display_name, "update", "pilot_certification", None,
               f"Bulk renewed {len(olds)} certification(s)")
    db.commit()
    return {"ok": True, "renewed": len(olds)}


@router.get("/api/pilot-certifications/{pc_id}/history", responses=responses(404))
def get_certification_history(
    pc_id: int,
    db: DBSession,
    user: ViewUser,
):
    """Get renewal history chain for a certification."""
    cert = db.query(PilotCertification).filter(PilotCertification.id == pc_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail=PILOT_CERTIFICATION_NOT_FOUND)

    # Walk backwards through renewed_from_id chain
    history = []
    current = cert
    while current.renewed_from_id:
        prev = db.query(PilotCertification).filter(PilotCertification.id == current.renewed_from_id).first()
        if not prev:
            break
        history.append(_pilot_cert_to_out(prev))
        current = prev
        if len(history) > 50:
            break

    return history


@router.delete("/api/pilot-certifications/{pc_id}", responses=responses(404, 409))
def delete_pilot_certification(
    pc_id: int,
    db: DBSession,
    admin: ManageUser,
):
    """Delete a certification with its renewal history (the records it was
    renewed from). A record that was itself renewed is removed through the
    current one. Attached documents are kept and released from the record."""
    from app.services.audit import log_action
    pc = db.query(PilotCertification).filter(PilotCertification.id == pc_id).first()
    if not pc:
        raise HTTPException(status_code=404, detail=PILOT_CERTIFICATION_NOT_FOUND)
    if db.query(PilotCertification).filter(PilotCertification.renewed_from_id == pc_id).first():
        raise HTTPException(status_code=409, detail=(
            "This record was renewed into a newer one. Remove the current certification "
            "to remove it with its renewal history."))
    chain = [pc]
    while chain[-1].renewed_from_id and len(chain) <= 50:
        prev = db.query(PilotCertification).filter(PilotCertification.id == chain[-1].renewed_from_id).first()
        if not prev or prev in chain:
            break
        chain.append(prev)
    # Newest first, so no remaining row points at a deleted one.
    for cert in chain:
        log_action(db, admin.id, admin.display_name, "delete", "pilot_certification", cert.id)
        db.delete(cert)
        db.flush()
    db.commit()
    return {"ok": True, "deleted": len(chain)}


@router.get("/api/pilot-equipment-quals", response_model=list[PilotEquipmentQualOut])
def list_pilot_equipment_quals(
    db: DBSession,
    user: ViewUser,
    pilot_id: int | None = None):
    q = db.query(PilotEquipmentQual)
    if pilot_id:
        q = q.filter(PilotEquipmentQual.pilot_id == pilot_id)
    rows = q.order_by(PilotEquipmentQual.pilot_id).all()
    return [PilotEquipmentQualOut.model_validate(r) for r in rows]


@router.post("/api/pilot-equipment-quals", response_model=PilotEquipmentQualOut)
def create_pilot_equipment_qual(
    data: PilotEquipmentQualCreate,
    db: DBSession,
    admin: ManageUser,
):
    peq = PilotEquipmentQual(**data.model_dump())
    db.add(peq)
    db.commit()
    db.refresh(peq)
    return PilotEquipmentQualOut.model_validate(peq)


@router.patch("/api/pilot-equipment-quals/{peq_id}", response_model=PilotEquipmentQualOut, responses=responses(404))
def update_pilot_equipment_qual(
    peq_id: int,
    data: PilotEquipmentQualUpdate,
    db: DBSession,
    admin: ManageUser,
):
    peq = db.query(PilotEquipmentQual).filter(PilotEquipmentQual.id == peq_id).first()
    if not peq:
        raise HTTPException(status_code=404, detail=EQUIPMENT_QUAL_NOT_FOUND)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(peq, key, value)
    db.commit()
    db.refresh(peq)
    return PilotEquipmentQualOut.model_validate(peq)


@router.delete("/api/pilot-equipment-quals/{peq_id}", responses=responses(404))
def delete_pilot_equipment_qual(
    peq_id: int,
    db: DBSession,
    admin: ManageUser,
):
    peq = db.query(PilotEquipmentQual).filter(PilotEquipmentQual.id == peq_id).first()
    if not peq:
        raise HTTPException(status_code=404, detail=EQUIPMENT_QUAL_NOT_FOUND)
    db.delete(peq)
    db.commit()
    return {"ok": True}


def _cert_cell(pc) -> dict:
    """Build one certification-matrix cell for a pilot/cert-type pair. A missing
    cert renders as a 'not_started' placeholder."""
    if not pc:
        return {
            "id": None,
            "status": "not_started",
            "issue_date": None,
            "expiration_date": None,
            "certificate_number": None,
            "nist_level": None,
        }
    return {
        "id": pc.id,
        "status": pc.status,
        "issue_date": pc.issue_date.isoformat() if pc.issue_date else None,
        "expiration_date": pc.expiration_date.isoformat() if pc.expiration_date else None,
        "certificate_number": pc.certificate_number,
        "nist_level": pc.nist_level,
    }


@router.get("/api/certifications/matrix")
def certification_matrix(
    db: DBSession,
    user: ViewUser,
):
    pilots = db.query(Pilot).filter(Pilot.status == "active").order_by(Pilot.last_name, Pilot.first_name).all()
    cert_types = db.query(CertificationType).filter(CertificationType.is_active.is_(True)).order_by(
        CertificationType.sort_order, CertificationType.name
    ).all()

    # Pre-load all pilot certifications for active pilots in one query
    pilot_ids = [p.id for p in pilots]
    all_certs = db.query(PilotCertification).filter(
        PilotCertification.pilot_id.in_(pilot_ids),
    ).order_by(PilotCertification.id).all()

    # Index by (pilot_id, cert_type_id): the latest live cert wins. A renewed
    # record shows only when no live one exists (its renewal was removed), so
    # it can still be opened and removed.
    cert_map: dict[tuple[int, int], PilotCertification] = {}
    for pc in all_certs:
        key = (pc.pilot_id, pc.certification_type_id)
        held = cert_map.get(key)
        if held is None or pc.status != "renewed" or held.status == "renewed":
            cert_map[key] = pc

    matrix = []
    for pilot in pilots:
        certs = {ct.id: _cert_cell(cert_map.get((pilot.id, ct.id))) for ct in cert_types}
        matrix.append({
            "pilot_id": pilot.id,
            "pilot_name": pilot.full_name,
            "certs": certs,
        })

    return {
        "cert_types": [CertificationTypeOut.model_validate(ct).model_dump() for ct in cert_types],
        "matrix": matrix,
    }
