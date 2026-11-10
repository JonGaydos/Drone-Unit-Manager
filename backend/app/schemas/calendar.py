from datetime import date as DateType, datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator, model_validator

ALLOWED_CATEGORIES = ("event", "leave")
END_BEFORE_START = "End date cannot be before the start date"

EventTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class CalendarEventCreate(BaseModel):
    title: EventTitle
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

    @model_validator(mode="after")
    def _dates(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError(END_BEFORE_START)
        return self


class CalendarEventUpdate(BaseModel):
    title: EventTitle | None = None
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

    @field_validator("title", "start_date", "category", "all_day")
    @classmethod
    def _not_null(cls, v):
        # Optional only so a patch can leave them out; a sent null is refused.
        if v is None:
            raise ValueError("cannot be empty")
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
