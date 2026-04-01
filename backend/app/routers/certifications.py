from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.constants import CERTIFICATION_TYPE_NOT_FOUND, PILOT_CERTIFICATION_NOT_FOUND, EQUIPMENT_QUAL_NOT_FOUND, PILOT_NOT_FOUND
from app.deps import DBSession, CurrentUser, SupervisorUser
from app.responses import responses
from app.models.certification import CertificationType, PilotCertification, PilotEquipmentQual
from app.models.pilot import Pilot
from app.schemas.certification import (
    CertificationTypeCreate, CertificationTypeUpdate, CertificationTypeOut,
    PilotCertificationCreate, PilotCertificationUpdate, PilotCertificationOut,
    PilotEquipmentQualCreate, PilotEquipmentQualUpdate, PilotEquipmentQualOut,
)


class ReorderItem(BaseModel):
    id: int
    sort_order: int


class ReorderRequest(BaseModel):
    items: list[ReorderItem]

router = APIRouter(tags=["certifications"])


@router.get("/api/certification-types", response_model=list[CertificationTypeOut])
def list_certification_types(
    db: DBSession,
    user: CurrentUser,
):
    rows = db.query(CertificationType).order_by(CertificationType.sort_order, CertificationType.name).all()
    return [CertificationTypeOut.model_validate(r) for r in rows]


@router.post("/api/certification-types", response_model=CertificationTypeOut, responses=responses(400))
def create_certification_type(
    data: CertificationTypeCreate,
    db: DBSession,
    admin: SupervisorUser,
):
    from app.services.audit import log_action
    if db.query(CertificationType).filter(CertificationType.name == data.name).first():
        raise HTTPException(status_code=400, detail="Certification type already exists")
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
    admin: SupervisorUser,
):
    for item in data.items:
        ct = db.query(CertificationType).filter(CertificationType.id == item.id).first()
        if ct:
            ct.sort_order = item.sort_order
    db.commit()
    return {"ok": True}


@router.patch("/api/certification-types/{ct_id}", response_model=CertificationTypeOut, responses=responses(404))
def update_certification_type(
    ct_id: int,
    data: CertificationTypeUpdate,
    db: DBSession,
    admin: SupervisorUser,
):
    from app.services.audit import log_action
    ct = db.query(CertificationType).filter(CertificationType.id == ct_id).first()
    if not ct:
        raise HTTPException(status_code=404, detail=CERTIFICATION_TYPE_NOT_FOUND)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(ct, key, value)
    log_action(db, admin.id, admin.display_name, "update", "certification_type", ct.id, ct.name)
    db.commit()
    db.refresh(ct)
    return CertificationTypeOut.model_validate(ct)


@router.delete("/api/certification-types/{ct_id}", responses=responses(404))
def delete_certification_type(
    ct_id: int,
    db: DBSession,
    admin: SupervisorUser,
):
    from app.services.audit import log_action
    ct = db.query(CertificationType).filter(CertificationType.id == ct_id).first()
    if not ct:
        raise HTTPException(status_code=404, detail=CERTIFICATION_TYPE_NOT_FOUND)
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
    user: CurrentUser,
    pilot_id: int | None = None,
    cert_type_id: int | None = None):
    q = db.query(PilotCertification)
    if pilot_id:
        q = q.filter(PilotCertification.pilot_id == pilot_id)
    if cert_type_id:
        q = q.filter(PilotCertification.certification_type_id == cert_type_id)
    rows = q.order_by(PilotCertification.pilot_id, PilotCertification.certification_type_id).all()
    return [_pilot_cert_to_out(r) for r in rows]


@router.post("/api/pilot-certifications", response_model=PilotCertificationOut)
def create_pilot_certification(
    data: PilotCertificationCreate,
    db: DBSession,
    admin: SupervisorUser,
):
    from app.services.audit import log_action
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


@router.patch("/api/pilot-certifications/{pc_id}", response_model=PilotCertificationOut, responses=responses(404))
def update_pilot_certification(
    pc_id: int,
    data: PilotCertificationUpdate,
    db: DBSession,
    admin: SupervisorUser,
):
    from app.services.audit import log_action
    pc = db.query(PilotCertification).filter(PilotCertification.id == pc_id).first()
    if not pc:
        raise HTTPException(status_code=404, detail=PILOT_CERTIFICATION_NOT_FOUND)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(pc, key, value)
    pilot = db.query(Pilot).filter(Pilot.id == pc.pilot_id).first()
    ct = db.query(CertificationType).filter(CertificationType.id == pc.certification_type_id).first()
    log_action(db, admin.id, admin.display_name, "update", "pilot_certification", pc.id,
               f"{pilot.full_name if pilot else 'Unknown'} - {ct.name if ct else 'Unknown'}")
    db.commit()
    db.refresh(pc)
    return _pilot_cert_to_out(pc)


@router.delete("/api/pilot-certifications/{pc_id}", responses=responses(404))
def delete_pilot_certification(
    pc_id: int,
    db: DBSession,
    admin: SupervisorUser,
):
    from app.services.audit import log_action
    pc = db.query(PilotCertification).filter(PilotCertification.id == pc_id).first()
    if not pc:
        raise HTTPException(status_code=404, detail=PILOT_CERTIFICATION_NOT_FOUND)
    log_action(db, admin.id, admin.display_name, "delete", "pilot_certification", pc_id)
    db.delete(pc)
    db.commit()
    return {"ok": True}


@router.get("/api/pilot-equipment-quals", response_model=list[PilotEquipmentQualOut])
def list_pilot_equipment_quals(
    db: DBSession,
    user: CurrentUser,
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
    admin: SupervisorUser,
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
    admin: SupervisorUser,
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
    admin: SupervisorUser,
):
    peq = db.query(PilotEquipmentQual).filter(PilotEquipmentQual.id == peq_id).first()
    if not peq:
        raise HTTPException(status_code=404, detail=EQUIPMENT_QUAL_NOT_FOUND)
    db.delete(peq)
    db.commit()
    return {"ok": True}


@router.get("/api/certifications/matrix")
def certification_matrix(
    db: DBSession,
    user: CurrentUser,
):
    pilots = db.query(Pilot).filter(Pilot.status == "active").order_by(Pilot.last_name, Pilot.first_name).all()
    cert_types = db.query(CertificationType).filter(CertificationType.is_active.is_(True)).order_by(
        CertificationType.sort_order, CertificationType.name
    ).all()

    # Pre-load all pilot certifications for active pilots in one query
    pilot_ids = [p.id for p in pilots]
    all_certs = db.query(PilotCertification).filter(PilotCertification.pilot_id.in_(pilot_ids)).all()

    # Index by (pilot_id, cert_type_id)
    cert_map: dict[tuple[int, int], PilotCertification] = {}
    for pc in all_certs:
        cert_map[(pc.pilot_id, pc.certification_type_id)] = pc

    matrix = []
    for pilot in pilots:
        certs = {}
        for ct in cert_types:
            pc = cert_map.get((pilot.id, ct.id))
            if pc:
                certs[ct.id] = {
                    "id": pc.id,
                    "status": pc.status,
                    "issue_date": pc.issue_date.isoformat() if pc.issue_date else None,
                    "expiration_date": pc.expiration_date.isoformat() if pc.expiration_date else None,
                    "certificate_number": pc.certificate_number,
                    "nist_level": pc.nist_level,
                }
            else:
                certs[ct.id] = {
                    "id": None,
                    "status": "not_started",
                    "issue_date": None,
                    "expiration_date": None,
                    "certificate_number": None,
                    "nist_level": None,
                }
        matrix.append({
            "pilot_id": pilot.id,
            "pilot_name": pilot.full_name,
            "certs": certs,
        })

    return {
        "cert_types": [CertificationTypeOut.model_validate(ct).model_dump() for ct in cert_types],
        "matrix": matrix,
    }
