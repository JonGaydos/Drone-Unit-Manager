from datetime import datetime
from datetime import date as DateType
from typing import Optional

from pydantic import BaseModel, Field


class FlightPurposeCreate(BaseModel):
    name: str
    is_active: bool = True
    sort_order: int = 0


class FlightPurposeOut(BaseModel):
    id: int
    name: str
    is_active: bool
    sort_order: int

    model_config = {"from_attributes": True}


class FlightCreate(BaseModel):
    pilot_id: int | None = None
    vehicle_id: int | None = None
    date: DateType | None = None
    takeoff_time: datetime | None = None
    landing_time: datetime | None = None
    duration_seconds: int | None = Field(None, ge=0)
    takeoff_lat: float | None = None
    takeoff_lon: float | None = None
    landing_lat: float | None = None
    landing_lon: float | None = None
    takeoff_address: str | None = None
    landing_address: str | None = None
    max_altitude_m: float | None = Field(None, ge=0)
    max_speed_mps: float | None = Field(None, ge=0)
    distance_m: float | None = Field(None, ge=0)
    purpose: str | None = None
    case_number: str | None = None
    battery_serial: str | None = None
    sensor_package: str | None = None
    attachment_top: str | None = None
    attachment_bottom: str | None = None
    attachment_left: str | None = None
    attachment_right: str | None = None
    carrier: str | None = None
    operating_cost: float | None = None
    notes: str | None = None


class FlightUpdate(BaseModel):
    pilot_id: int | None = None
    vehicle_id: int | None = None
    date: DateType | None = None
    takeoff_time: datetime | None = None
    landing_time: datetime | None = None
    duration_seconds: int | None = Field(None, ge=0)
    takeoff_lat: float | None = None
    takeoff_lon: float | None = None
    landing_lat: float | None = None
    landing_lon: float | None = None
    takeoff_address: str | None = None
    landing_address: str | None = None
    max_altitude_m: float | None = Field(None, ge=0)
    max_speed_mps: float | None = Field(None, ge=0)
    distance_m: float | None = Field(None, ge=0)
    purpose: str | None = None
    case_number: str | None = None
    battery_serial: str | None = None
    sensor_package: str | None = None
    attachment_top: str | None = None
    attachment_bottom: str | None = None
    attachment_left: str | None = None
    attachment_right: str | None = None
    carrier: str | None = None
    operating_cost: float | None = None
    review_status: str | None = None
    pilot_confirmed: bool | None = None
    notes: str | None = None


class FlightOut(BaseModel):
    id: int
    external_id: str | None = None
    api_provider: str | None = None
    pilot_id: int | None = None
    vehicle_id: int | None = None
    date: DateType | None = None
    takeoff_time: datetime | None = None
    landing_time: datetime | None = None
    duration_seconds: int | None = None
    takeoff_lat: float | None = None
    takeoff_lon: float | None = None
    landing_lat: float | None = None
    landing_lon: float | None = None
    takeoff_address: str | None = None
    landing_address: str | None = None
    max_altitude_m: float | None = None
    max_speed_mps: float | None = None
    distance_m: float | None = None
    purpose: str | None = None
    case_number: str | None = None
    battery_serial: str | None = None
    sensor_package: str | None = None
    attachment_top: str | None = None
    attachment_bottom: str | None = None
    attachment_left: str | None = None
    attachment_right: str | None = None
    carrier: str | None = None
    operating_cost: float | None = None
    has_telemetry: bool = False
    review_status: str = "reviewed"
    pilot_confirmed: bool = True
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pilot_name: str | None = None
    vehicle_name: str | None = None

    model_config = {"from_attributes": True}


class FlightBulkUpdate(BaseModel):
    flight_ids: list[int]
    pilot_id: int | None = None
    purpose: str | None = None
    review_status: str | None = None
    pilot_confirmed: bool | None = None
