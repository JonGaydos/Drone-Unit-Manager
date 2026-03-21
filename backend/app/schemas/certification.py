from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


# --- CertificationType schemas ---

class CertificationTypeCreate(BaseModel):
    name: str
    category: str = "custom"
    has_expiration: bool = True
    renewal_period_months: Optional[int] = None
    description: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class CertificationTypeUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    has_expiration: Optional[bool] = None
    renewal_period_months: Optional[int] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CertificationTypeOut(BaseModel):
    id: int
    name: str
    category: str
    has_expiration: bool
    renewal_period_months: Optional[int]
    description: Optional[str]
    sort_order: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# --- PilotCertification schemas ---

class PilotCertificationCreate(BaseModel):
    pilot_id: int
    certification_type_id: int
    status: str = "not_started"
    issue_date: Optional[date] = None
    expiration_date: Optional[date] = None
    certificate_number: Optional[str] = None
    nist_level: Optional[int] = None
    notes: Optional[str] = None


class PilotCertificationUpdate(BaseModel):
    status: Optional[str] = None
    issue_date: Optional[date] = None
    expiration_date: Optional[date] = None
    certificate_number: Optional[str] = None
    nist_level: Optional[int] = None
    notes: Optional[str] = None


class PilotCertificationOut(BaseModel):
    id: int
    pilot_id: int
    certification_type_id: int
    status: str
    issue_date: Optional[date]
    expiration_date: Optional[date]
    certificate_number: Optional[str]
    nist_level: Optional[int]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    pilot_name: Optional[str] = None
    cert_type_name: Optional[str] = None

    model_config = {"from_attributes": True}


# --- PilotEquipmentQual schemas ---

class PilotEquipmentQualCreate(BaseModel):
    pilot_id: int
    vehicle_id: Optional[int] = None
    vehicle_model: Optional[str] = None
    qualification_date: Optional[date] = None
    status: str = "in_training"
    notes: Optional[str] = None


class PilotEquipmentQualUpdate(BaseModel):
    vehicle_id: Optional[int] = None
    vehicle_model: Optional[str] = None
    qualification_date: Optional[date] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class PilotEquipmentQualOut(BaseModel):
    id: int
    pilot_id: int
    vehicle_id: Optional[int]
    vehicle_model: Optional[str]
    qualification_date: Optional[date]
    status: str
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
