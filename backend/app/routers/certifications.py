from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.certification import CertificationType, PilotCertification, PilotEquipmentQual
from app.models.pilot import Pilot
from app.models.user import User
from app.routers.auth import get_current_user, require_admin
from app.schemas.certification import (
    CertificationTypeCreate, CertificationTypeUpdate, CertificationTypeOut,
    PilotCertificationCreate, PilotCertificationUpdate, PilotCertificationOut,
    PilotEquipmentQualCreate, PilotEquipmentQualUpdate, PilotEquipmentQualOut,
)

router = APIRouter(tags=["certifications"])


# ---------------------------------------------------------------------------
# Certification Types
# ---------------------------------------------------------------------------

@router.get("/api/certification-types", response_model=list[CertificationTypeOut])
def list_certification_types(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = db.query(CertificationType).order_by(CertificationType.sort_order, CertificationType.name).all()
    return [CertificationTypeOut.model_validate(r) for r in rows]


@router.post("/api/certification-types", response_model=CertificationTypeOut)
def create_certification_type(
    data: CertificationTypeCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if db.query(CertificationType).filter(CertificationType.name == data.name).first():
        raise HTTPException(status_code=400, detail="Certification type already exists")
    ct = CertificationType(**data.model_dump())
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return CertificationTypeOut.model_validate(ct)


@router.patch("/api/certification-types/{ct_id}", response_model=CertificationTypeOut)
def update_certification_type(
    ct_id: int,
    data: CertificationTypeUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    ct = db.query(CertificationType).filter(CertificationType.id == ct_id).first()
    if not ct:
        raise HTTPException(status_code=404, detail="Certification type not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(ct, key, value)
    db.commit()
    db.refresh(ct)
    return CertificationTypeOut.model_validate(ct)


@router.delete("/api/certification-types/{ct_id}")
def delete_certification_type(
    ct_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    ct = db.query(CertificationType).filter(CertificationType.id == ct_id).first()
    if not ct:
        raise HTTPException(status_code=404, detail="Certification type not found")
    db.delete(ct)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Pilot Certifications
# ---------------------------------------------------------------------------

def _pilot_cert_to_out(pc: PilotCertification, db: Session) -> PilotCertificationOut:
    out = PilotCertificationOut.model_validate(pc)
    if pc.pilot:
        out.pilot_name = pc.pilot.full_name
    if pc.certification_type:
        out.cert_type_name = pc.certification_type.name
    return out


@router.get("/api/pilot-certifications", response_model=list[PilotCertificationOut])
def list_pilot_certifications(
    pilot_id: int | None = None,
    cert_type_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(PilotCertification)
    if pilot_id:
        q = q.filter(PilotCertification.pilot_id == pilot_id)
    if cert_type_id:
        q = q.filter(PilotCertification.certification_type_id == cert_type_id)
    rows = q.order_by(PilotCertification.pilot_id, PilotCertification.certification_type_id).all()
    return [_pilot_cert_to_out(r, db) for r in rows]


@router.post("/api/pilot-certifications", response_model=PilotCertificationOut)
def create_pilot_certification(
    data: PilotCertificationCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    pc = PilotCertification(**data.model_dump())
    db.add(pc)
    db.commit()
    db.refresh(pc)
    return _pilot_cert_to_out(pc, db)


@router.patch("/api/pilot-certifications/{pc_id}", response_model=PilotCertificationOut)
def update_pilot_certification(
    pc_id: int,
    data: PilotCertificationUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    pc = db.query(PilotCertification).filter(PilotCertification.id == pc_id).first()
    if not pc:
        raise HTTPException(status_code=404, detail="Pilot certification not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(pc, key, value)
    db.commit()
    db.refresh(pc)
    return _pilot_cert_to_out(pc, db)


@router.delete("/api/pilot-certifications/{pc_id}")
def delete_pilot_certification(
    pc_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    pc = db.query(PilotCertification).filter(PilotCertification.id == pc_id).first()
    if not pc:
        raise HTTPException(status_code=404, detail="Pilot certification not found")
    db.delete(pc)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Pilot Equipment Qualifications
# ---------------------------------------------------------------------------

@router.get("/api/pilot-equipment-quals", response_model=list[PilotEquipmentQualOut])
def list_pilot_equipment_quals(
    pilot_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(PilotEquipmentQual)
    if pilot_id:
        q = q.filter(PilotEquipmentQual.pilot_id == pilot_id)
    rows = q.order_by(PilotEquipmentQual.pilot_id).all()
    return [PilotEquipmentQualOut.model_validate(r) for r in rows]


@router.post("/api/pilot-equipment-quals", response_model=PilotEquipmentQualOut)
def create_pilot_equipment_qual(
    data: PilotEquipmentQualCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    peq = PilotEquipmentQual(**data.model_dump())
    db.add(peq)
    db.commit()
    db.refresh(peq)
    return PilotEquipmentQualOut.model_validate(peq)


@router.patch("/api/pilot-equipment-quals/{peq_id}", response_model=PilotEquipmentQualOut)
def update_pilot_equipment_qual(
    peq_id: int,
    data: PilotEquipmentQualUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    peq = db.query(PilotEquipmentQual).filter(PilotEquipmentQual.id == peq_id).first()
    if not peq:
        raise HTTPException(status_code=404, detail="Equipment qualification not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(peq, key, value)
    db.commit()
    db.refresh(peq)
    return PilotEquipmentQualOut.model_validate(peq)


@router.delete("/api/pilot-equipment-quals/{peq_id}")
def delete_pilot_equipment_qual(
    peq_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    peq = db.query(PilotEquipmentQual).filter(PilotEquipmentQual.id == peq_id).first()
    if not peq:
        raise HTTPException(status_code=404, detail="Equipment qualification not found")
    db.delete(peq)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Certification Matrix
# ---------------------------------------------------------------------------

@router.get("/api/certifications/matrix")
def certification_matrix(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pilots = db.query(Pilot).filter(Pilot.status == "active").order_by(Pilot.last_name, Pilot.first_name).all()
    cert_types = db.query(CertificationType).filter(CertificationType.is_active == True).order_by(
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
