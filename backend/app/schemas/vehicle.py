from datetime import datetime, date
from typing import Annotated, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator

# Required text (serial number, manufacturer, model, location place): trimmed,
# never blank, at most the 100 characters their columns hold.
RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
# Hourly operating cost: optional, 0 to 100000.
HourlyRate = Annotated[Optional[float], Field(ge=0, le=100000)]


class VehicleCreate(BaseModel):
    serial_number: RequiredText
    manufacturer: RequiredText
    model: RequiredText
    nickname: Optional[str] = None
    provider_serial: Optional[str] = None
    faa_registration: Optional[str] = None
    status: str = "active"
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None
    hourly_operating_cost: HourlyRate = None


class VehicleUpdate(BaseModel):
    serial_number: Optional[RequiredText] = None
    manufacturer: Optional[RequiredText] = None
    model: Optional[RequiredText] = None
    nickname: Optional[str] = None
    provider_serial: Optional[str] = None
    faa_registration: Optional[str] = None
    status: Optional[str] = None
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    photo_url: Optional[str] = None
    notes: Optional[str] = None
    hourly_operating_cost: HourlyRate = None

    @field_validator("serial_number", "manufacturer", "model", "status")
    @classmethod
    def _not_null(cls, v):
        # Optional only so a patch can leave them out; a sent null is refused.
        if v is None:
            raise ValueError("cannot be empty")
        return v


class VehicleOut(BaseModel):
    id: int
    serial_number: str
    manufacturer: str
    model: str
    nickname: Optional[str] = None
    faa_registration: Optional[str] = None
    status: str
    # Counted flights only; None when the caller lacks flights.view.
    total_flight_hours: Optional[float] = None
    total_flights: Optional[int] = None
    provider_serial: Optional[str] = None
    api_provider: Optional[str] = None
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    photo_url: Optional[str] = None
    notes: Optional[str] = None
    hourly_operating_cost: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VehicleLocationUpdate(BaseModel):
    pilot_id: int | None = None
    place: RequiredText | None = None
