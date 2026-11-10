from datetime import date, datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

# The statuses the Certifications page offers (CERT_STATUS_COLORS in the frontend).
CertStatus = Literal[
    "not_issued", "not_eligible", "not_started", "in_progress", "pending",
    "complete", "active", "expired", "renewed",
]
NistLevel = Annotated[int, Field(ge=1, le=5)]
EquipmentQualStatus = Literal["qualified", "in_training", "expired"]
# Cert type fields: the categories the Certifications page offers, a trimmed
# non-blank name, and a renewal period of one month to fifty years.
CertCategory = Literal["faa", "nist", "equipment", "insurance", "training", "custom"]
CertTypeName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
RenewalMonths = Annotated[int, Field(ge=1, le=600)]

EXPIRY_BEFORE_ISSUE = "Expiration date cannot be before the issue date"


def check_cert_dates(issue_date, expiration_date):
    """Raise ValueError when the expiration falls before the issue date."""
    if issue_date and expiration_date and expiration_date < issue_date:
        raise ValueError(EXPIRY_BEFORE_ISSUE)


def _not_null(v):
    # Optional only so a patch can leave the field out; a sent null is refused.
    if v is None:
        raise ValueError("cannot be empty")
    return v


# --- CertificationType schemas ---

class CertificationTypeCreate(BaseModel):
    name: CertTypeName
    category: CertCategory = "custom"
    has_expiration: bool = True
    renewal_period_months: Optional[RenewalMonths] = None
    description: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class CertificationTypeUpdate(BaseModel):
    name: Optional[CertTypeName] = None
    category: Optional[CertCategory] = None
    has_expiration: Optional[bool] = None
    renewal_period_months: Optional[RenewalMonths] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

    _fields_not_null = field_validator("name", "category")(_not_null)


class CertificationTypeOut(BaseModel):
    id: int
    name: str
    category: str
    has_expiration: bool
    renewal_period_months: Optional[int] = None
    description: Optional[str] = None
    sort_order: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# --- PilotCertification schemas ---

class PilotCertificationCreate(BaseModel):
    pilot_id: int
    certification_type_id: int
    status: CertStatus = "not_started"
    issue_date: Optional[date] = None
    expiration_date: Optional[date] = None
    certificate_number: Optional[str] = None
    nist_level: Optional[NistLevel] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _dates(self):
        check_cert_dates(self.issue_date, self.expiration_date)
        return self


class PilotCertificationUpdate(BaseModel):
    status: Optional[CertStatus] = None
    issue_date: Optional[date] = None
    expiration_date: Optional[date] = None
    certificate_number: Optional[str] = None
    nist_level: Optional[NistLevel] = None
    notes: Optional[str] = None

    _status_not_null = field_validator("status")(_not_null)


class PilotCertificationOut(BaseModel):
    id: int
    pilot_id: int
    certification_type_id: int
    status: str
    issue_date: Optional[date] = None
    expiration_date: Optional[date] = None
    certificate_number: Optional[str] = None
    nist_level: Optional[int] = None
    notes: Optional[str] = None
    renewed_from_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    pilot_name: Optional[str] = None
    cert_type_name: Optional[str] = None

    model_config = {"from_attributes": True}


class CertRenewRequest(BaseModel):
    issue_date: date
    expiration_date: Optional[date] = None
    certificate_number: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _dates(self):
        check_cert_dates(self.issue_date, self.expiration_date)
        return self


# --- PilotEquipmentQual schemas ---

class PilotEquipmentQualCreate(BaseModel):
    pilot_id: int
    vehicle_id: Optional[int] = None
    vehicle_model: Optional[str] = None
    qualification_date: Optional[date] = None
    status: EquipmentQualStatus = "in_training"
    notes: Optional[str] = None


class PilotEquipmentQualUpdate(BaseModel):
    vehicle_id: Optional[int] = None
    vehicle_model: Optional[str] = None
    qualification_date: Optional[date] = None
    status: Optional[EquipmentQualStatus] = None
    notes: Optional[str] = None

    _status_not_null = field_validator("status")(_not_null)


class PilotEquipmentQualOut(BaseModel):
    id: int
    pilot_id: int
    vehicle_id: Optional[int] = None
    vehicle_model: Optional[str] = None
    qualification_date: Optional[date] = None
    status: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
