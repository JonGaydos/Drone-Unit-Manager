from datetime import date as DateType, datetime
from pydantic import BaseModel, field_validator

ALLOWED_CATEGORIES = ("event", "leave")


class CalendarEventCreate(BaseModel):
    title: str
    category: str = "event"
    start_date: DateType
    end_date: DateType | None = None
    all_day: bool = True
    pilot_id: int | None = None
    notes: str | None = None

    @field_validator("category")
    @classmethod
    def _check_category(cls, v):
        if v not in ALLOWED_CATEGORIES:
            raise ValueError("category must be 'event' or 'leave'")
        return v


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    start_date: DateType | None = None
    end_date: DateType | None = None
    all_day: bool | None = None
    pilot_id: int | None = None
    notes: str | None = None

    @field_validator("category")
    @classmethod
    def _check_category(cls, v):
        if v is not None and v not in ALLOWED_CATEGORIES:
            raise ValueError("category must be 'event' or 'leave'")
        return v


class CalendarEventOut(BaseModel):
    id: int
    title: str
    category: str
    start_date: DateType
    end_date: DateType | None = None
    all_day: bool = True
    pilot_id: int | None = None
    notes: str | None = None
    created_by_id: int | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
