from datetime import datetime
from datetime import date as DateType
from typing import Optional

from pydantic import BaseModel, Field


class MissionLogPilotIn(BaseModel):
    pilot_id: int
    role: str | None = None
    hours: float = 0.0


class MissionLogPilotOut(BaseModel):
    id: int
    pilot_id: int
    pilot_name: str | None = None
    role: str | None = None
    hours: float = 0.0

    model_config = {"from_attributes": True}


class MissionLogCreate(BaseModel):
    date: DateType
    title: str
    description: str | None = None
    reason: str | None = None
    location: str | None = None
    case_number: str | None = None
    man_hours: float = Field(default=0.0, ge=0)
    start_time: datetime | None = None
    end_time: datetime | None = None
    vehicle_id: int | None = None
    status: str = "completed"
    total_cost: float | None = None
    cost_breakdown: str | None = None
    notes: str | None = None
    pilots: list[MissionLogPilotIn] = []


class MissionLogUpdate(BaseModel):
    date: DateType | None = None
    title: str | None = None
    description: str | None = None
    reason: str | None = None
    location: str | None = None
    case_number: str | None = None
    man_hours: float | None = Field(None, ge=0)
    start_time: datetime | None = None
    end_time: datetime | None = None
    vehicle_id: int | None = None
    status: str | None = None
    total_cost: float | None = None
    cost_breakdown: str | None = None
    notes: str | None = None
    pilots: list[MissionLogPilotIn] | None = None


class MissionLogOut(BaseModel):
    id: int
    date: DateType
    title: str
    description: str | None = None
    reason: str | None = None
    location: str | None = None
    case_number: str | None = None
    man_hours: float = 0.0
    start_time: datetime | None = None
    end_time: datetime | None = None
    vehicle_id: int | None = None
    vehicle_name: str | None = None
    status: str = "completed"
    total_cost: float | None = None
    cost_breakdown: str | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pilots: list[MissionLogPilotOut] = []

    model_config = {"from_attributes": True}
