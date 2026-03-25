from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PilotCreate(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    phone_type: Optional[str] = None
    phone_work: Optional[str] = None
    badge_number: Optional[str] = None
    skydio_user_uuid: Optional[str] = None
    status: str = "active"
    notes: Optional[str] = None


class PilotUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    phone_type: Optional[str] = None
    phone_work: Optional[str] = None
    badge_number: Optional[str] = None
    skydio_user_uuid: Optional[str] = None
    status: Optional[str] = None
    photo_url: Optional[str] = None
    notes: Optional[str] = None


class PilotOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    full_name: str
    email: Optional[str]
    phone: Optional[str]
    phone_type: Optional[str] = None
    phone_work: Optional[str] = None
    badge_number: Optional[str]
    skydio_user_uuid: Optional[str]
    status: str
    photo_url: Optional[str] = None
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PilotStats(BaseModel):
    total_flights: int = 0
    total_flight_hours: float = 0.0
    avg_flight_duration_seconds: float = 0.0
