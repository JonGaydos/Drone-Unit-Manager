from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.schemas.user import _validate_optional_email

# First and last name are required: trimmed, never blank.
PilotName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
PilotStatus = Literal["active", "inactive"]


def _text(max_length: int):
    """Optional text capped at its column size."""
    return Annotated[Optional[str], Field(max_length=max_length)]


class _PilotFields(BaseModel):
    """Contact and record fields shared by create and update, capped at their
    column sizes (notes at 10,000 characters)."""
    email: _text(200) = None
    phone: _text(50) = None
    phone_type: _text(20) = None
    phone_work: _text(50) = None
    badge_number: _text(50) = None
    skydio_user_uuid: _text(100) = None
    notes: _text(10000) = None

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return _validate_optional_email(v)


class PilotCreate(_PilotFields):
    first_name: PilotName
    last_name: PilotName
    status: PilotStatus = "active"
    counts_toward_totals: bool = True


class PilotUpdate(_PilotFields):
    first_name: Optional[PilotName] = None
    last_name: Optional[PilotName] = None
    status: Optional[PilotStatus] = None
    counts_toward_totals: Optional[bool] = None
    photo_url: _text(500) = None

    @field_validator("first_name", "last_name", "status")
    @classmethod
    def _not_null(cls, v):
        # Optional only so a patch can leave them out; a sent null is refused.
        if v is None:
            raise ValueError("cannot be empty")
        return v


class PilotOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    phone_type: Optional[str] = None
    phone_work: Optional[str] = None
    badge_number: Optional[str] = None
    skydio_user_uuid: Optional[str] = None
    status: str
    counts_toward_totals: bool = True
    photo_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PilotStats(BaseModel):
    total_flights: int = 0
    total_flight_hours: float = 0.0
    avg_flight_duration_seconds: float = 0.0
