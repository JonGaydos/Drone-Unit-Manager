from datetime import datetime, date
from typing import Annotated, Optional

from pydantic import BaseModel, StringConstraints

# Serial number, manufacturer and model are required text: trimmed, never blank.
RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


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


class VehicleOut(BaseModel):
    id: int
    serial_number: str
    manufacturer: str
    model: str
    nickname: Optional[str] = None
    faa_registration: Optional[str] = None
    status: str
    total_flight_hours: float
    total_flights: int
    provider_serial: Optional[str] = None
    api_provider: Optional[str] = None
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    photo_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VehicleLocationUpdate(BaseModel):
    pilot_id: int | None = None
    place: str | None = None
