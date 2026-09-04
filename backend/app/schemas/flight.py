from datetime import datetime, timezone
from datetime import date as DateType
from typing import Optional

from pydantic import BaseModel, Field, field_validator, field_serializer

ALLOWED_REVIEW_STATUS = ("reviewed", "needs_review")


def _validate_review_status(value: str | None) -> str | None:
    if value is not None and value not in ALLOWED_REVIEW_STATUS:
        raise ValueError(
            f"review_status must be one of {ALLOWED_REVIEW_STATUS}"
        )
    return value


def _naive_utc(value: datetime | None) -> datetime | None:
    """Coerce a tz-aware datetime to naive UTC so it stores UTC-by-convention."""
    if value is not None and value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


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
    purpose: str | None = Field(None, max_length=255)
    case_number: str | None = Field(None, max_length=255)
    battery_serial: str | None = Field(None, max_length=255)
    sensor_package: str | None = Field(None, max_length=255)
    attachment_top: str | None = Field(None, max_length=255)
    attachment_bottom: str | None = Field(None, max_length=255)
    attachment_left: str | None = Field(None, max_length=255)
    attachment_right: str | None = Field(None, max_length=255)
    carrier: str | None = Field(None, max_length=255)
    operating_cost: float | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=5000)

    _tz_takeoff = field_validator("takeoff_time")(_naive_utc)
    _tz_landing = field_validator("landing_time")(_naive_utc)


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
    purpose: str | None = Field(None, max_length=255)
    case_number: str | None = Field(None, max_length=255)
    battery_serial: str | None = Field(None, max_length=255)
    sensor_package: str | None = Field(None, max_length=255)
    attachment_top: str | None = Field(None, max_length=255)
    attachment_bottom: str | None = Field(None, max_length=255)
    attachment_left: str | None = Field(None, max_length=255)
    attachment_right: str | None = Field(None, max_length=255)
    carrier: str | None = Field(None, max_length=255)
    operating_cost: float | None = Field(None, ge=0)
    review_status: str | None = None
    pilot_confirmed: bool | None = None
    counts_toward_totals: bool | None = None
    notes: str | None = Field(None, max_length=5000)

    _validate_review_status = field_validator("review_status")(
        _validate_review_status
    )
    _tz_takeoff = field_validator("takeoff_time")(_naive_utc)
    _tz_landing = field_validator("landing_time")(_naive_utc)


class FlightOut(BaseModel):
    id: int
    external_id: str | None = None
    api_provider: str | None = None
    data_source: str | None = None
    tags: str | None = None
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
    telemetry_synced: bool = False
    review_status: str = "needs_review"
    pilot_confirmed: bool = True
    counts_toward_totals: bool = True
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pilot_name: str | None = None
    vehicle_name: str | None = None

    model_config = {"from_attributes": True}

    @field_serializer("takeoff_time", "landing_time", "created_at", "updated_at", when_used="json")
    def _serialize_utc_z(self, value: datetime | None):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class FlightBulkUpdate(BaseModel):
    flight_ids: list[int]
    pilot_id: int | None = None
    purpose: str | None = Field(None, max_length=255)
    review_status: str | None = None
    pilot_confirmed: bool | None = None
    counts_toward_totals: bool | None = None

    _validate_review_status = field_validator("review_status")(
        _validate_review_status
    )
