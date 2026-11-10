from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, StringConstraints, field_validator

# First and last name are required: trimmed, never blank.
PilotName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class PilotCreate(BaseModel):
    first_name: PilotName
    last_name: PilotName
    email: Optional[str] = None
    phone: Optional[str] = None
    phone_type: Optional[str] = None
    phone_work: Optional[str] = None
    badge_number: Optional[str] = None
    skydio_user_uuid: Optional[str] = None
    status: str = "active"
    counts_toward_totals: bool = True
    notes: Optional[str] = None


class PilotUpdate(BaseModel):
    first_name: Optional[PilotName] = None
    last_name: Optional[PilotName] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    phone_type: Optional[str] = None
    phone_work: Optional[str] = None
    badge_number: Optional[str] = None
    skydio_user_uuid: Optional[str] = None
    status: Optional[str] = None
    counts_toward_totals: Optional[bool] = None
    photo_url: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("first_name", "last_name")
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
