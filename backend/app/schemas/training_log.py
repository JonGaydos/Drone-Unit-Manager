from datetime import datetime
from datetime import date as DateType
from typing import Annotated, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator

LogTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class TrainingLogPilotIn(BaseModel):
    pilot_id: int
    role: str | None = None
    hours: float = Field(default=0.0, ge=0)


def _pilots_once(pilots):
    """A pilot is listed once; a second row would double their hours."""
    if pilots is not None and len({p.pilot_id for p in pilots}) != len(pilots):
        raise ValueError("each pilot can be listed only once")
    return pilots


class TrainingLogPilotOut(BaseModel):
    id: int
    pilot_id: int
    pilot_name: str | None = None
    role: str | None = None
    hours: float = 0.0

    model_config = {"from_attributes": True}


class TrainingLogCreate(BaseModel):
    date: DateType
    title: LogTitle
    training_type: str
    description: str | None = None
    location: str | None = None
    man_hours: float = Field(default=0.0, ge=0)
    start_time: datetime | None = None
    end_time: datetime | None = None
    vehicle_id: int | None = None
    instructor: str | None = None
    objectives: str | None = None
    outcome: str = "completed"
    total_cost: float | None = Field(None, ge=0)
    notes: str | None = None
    pilots: list[TrainingLogPilotIn] = []

    _unique_pilots = field_validator("pilots")(_pilots_once)


class TrainingLogUpdate(BaseModel):
    date: DateType | None = None
    title: LogTitle | None = None
    training_type: str | None = None
    description: str | None = None
    location: str | None = None
    man_hours: float | None = Field(None, ge=0)
    start_time: datetime | None = None
    end_time: datetime | None = None
    vehicle_id: int | None = None
    instructor: str | None = None
    objectives: str | None = None
    outcome: str | None = None
    total_cost: float | None = Field(None, ge=0)
    notes: str | None = None
    pilots: list[TrainingLogPilotIn] | None = None

    _unique_pilots = field_validator("pilots")(_pilots_once)

    @field_validator("date", "title", "man_hours", "training_type", "outcome")
    @classmethod
    def _not_null(cls, v):
        # Optional only so a patch can leave them out; a sent null is refused.
        if v is None:
            raise ValueError("cannot be empty")
        return v


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
    total_cost: float | None = None
    notes: str | None = None
    created_by_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pilots: list[TrainingLogPilotOut] = []

    model_config = {"from_attributes": True}
