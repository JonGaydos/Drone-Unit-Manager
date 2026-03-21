from datetime import datetime
from datetime import date as DateType
from typing import Optional

from pydantic import BaseModel


class TrainingLogPilotIn(BaseModel):
    pilot_id: int
    role: str | None = None
    hours: float = 0.0


class TrainingLogPilotOut(BaseModel):
    id: int
    pilot_id: int
    pilot_name: str | None = None
    role: str | None = None
    hours: float = 0.0

    model_config = {"from_attributes": True}


class TrainingLogCreate(BaseModel):
    date: DateType
    title: str
    training_type: str
    description: str | None = None
    location: str | None = None
    man_hours: float = 0.0
    start_time: datetime | None = None
    end_time: datetime | None = None
    vehicle_id: int | None = None
    instructor: str | None = None
    objectives: str | None = None
    outcome: str = "completed"
    notes: str | None = None
    pilots: list[TrainingLogPilotIn] = []


class TrainingLogUpdate(BaseModel):
    date: DateType | None = None
    title: str | None = None
    training_type: str | None = None
    description: str | None = None
    location: str | None = None
    man_hours: float | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    vehicle_id: int | None = None
    instructor: str | None = None
    objectives: str | None = None
    outcome: str | None = None
    notes: str | None = None
    pilots: list[TrainingLogPilotIn] | None = None


class TrainingLogOut(BaseModel):
    id: int
    date: DateType
    title: str
    training_type: str
    description: str | None = None
    location: str | None = None
    man_hours: float = 0.0
    start_time: datetime | None = None
    end_time: datetime | None = None
    vehicle_id: int | None = None
    vehicle_name: str | None = None
    instructor: str | None = None
    objectives: str | None = None
    outcome: str = "completed"
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pilots: list[TrainingLogPilotOut] = []

    model_config = {"from_attributes": True}
