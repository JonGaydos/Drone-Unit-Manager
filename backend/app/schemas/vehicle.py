from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel


class VehicleCreate(BaseModel):
    serial_number: str
    manufacturer: str
    model: str
    nickname: Optional[str] = None
    faa_registration: Optional[str] = None
    status: str = "active"
    acquired_date: Optional[date] = None
    notes: Optional[str] = None


class VehicleUpdate(BaseModel):
    serial_number: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    nickname: Optional[str] = None
    faa_registration: Optional[str] = None
    status: Optional[str] = None
    acquired_date: Optional[date] = None
    photo_url: Optional[str] = None
    notes: Optional[str] = None


class VehicleOut(BaseModel):
    id: int
    serial_number: str
    manufacturer: str
    model: str
    nickname: Optional[str]
    faa_registration: Optional[str]
    status: str
    total_flight_hours: float
    total_flights: int
    provider_serial: Optional[str]
    api_provider: Optional[str]
    acquired_date: Optional[date]
    photo_url: Optional[str] = None
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
