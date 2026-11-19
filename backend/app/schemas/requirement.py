"""Request and response models for the flight requirements API."""

from datetime import date, datetime, time
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.services.fleet_models import normalize_model

PeriodType = Literal[
    "calendar_month", "calendar_quarter", "calendar_year", "fiscal_quarter", "fiscal_year",
    "monthly_window", "span", "custom", "every_n_months",
]
ModelMode = Literal["all", "combined", "each", "each_all_active"]
TimeMode = Literal["any", "clock", "night"]
SpanUnit = Literal["days", "weeks", "months"]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ModelName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
PurposeName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
WindowDay = Annotated[int, Field(ge=1, le=31)]
SpanLength = Annotated[int, Field(ge=1, le=365)]
EveryMonths = Annotated[int, Field(ge=1, le=24)]
TargetMinutes = Annotated[int, Field(ge=1, le=100000)]
TargetFlights = Annotated[int, Field(ge=1, le=10000)]
ReminderDays = Annotated[int, Field(ge=0, le=60)]
GraceDays = Annotated[int, Field(ge=0, le=60)]
Month = Annotated[int, Field(ge=1, le=12)]
MAX_ITEMS = 50

# The period fields each period type needs; every other period field is cleared.
PERIOD_FIELDS = {
    "monthly_window": ("window_start_day", "window_end_day"),
    "span": ("span_length", "span_unit"),
    "every_n_months": ("every_months",),
}
ALL_PERIOD_FIELDS = ("window_start_day", "window_end_day", "span_length", "span_unit", "every_months")
# Fewest models each mode takes. A single model is stored as combined, since the
# Combined or Each separately choice only appears with two or more.
MIN_MODELS = {"combined": 1, "each": 2}


def _dedupe(names: list[str], key) -> list[str]:
    """Drop names whose key repeats, keeping the first spelling."""
    seen: dict[str, str] = {}
    for name in names:
        seen.setdefault(key(name), name)
    return list(seen.values())


class RequirementDefinition(BaseModel):
    """Every requirement setting except its dates and pilots: what a template holds."""

    name: Name
    description: Optional[str] = Field(None, max_length=1000)
    period_type: PeriodType
    recurring: bool = True
    window_start_day: Optional[WindowDay] = None
    window_end_day: Optional[WindowDay] = None
    span_length: Optional[SpanLength] = None
    span_unit: Optional[SpanUnit] = None
    every_months: Optional[EveryMonths] = None
    target_minutes: Optional[TargetMinutes] = None
    target_flights: Optional[TargetFlights] = None
    model_mode: ModelMode = "all"
    models: list[ModelName] = Field([], max_length=MAX_ITEMS)
    time_mode: TimeMode = "any"
    window_start_time: Optional[time] = None
    window_end_time: Optional[time] = None
    purposes: list[PurposeName] = Field([], max_length=MAX_ITEMS)
    reminder_days: ReminderDays = 7
    is_active: bool = True

    @field_validator("models")
    @classmethod
    def _dedupe_models(cls, v):
        return _dedupe(v, normalize_model)

    @field_validator("purposes")
    @classmethod
    def _dedupe_purposes(cls, v):
        return _dedupe(v, str.casefold)

    @model_validator(mode="after")
    def _check(self):
        if self.target_minutes is None and self.target_flights is None:
            raise ValueError("Set a target in minutes, flights or both")
        self._check_period_fields()
        self._check_time_window()
        self._check_models()
        return self

    def _check_period_fields(self) -> None:
        needed = PERIOD_FIELDS.get(self.period_type, ())
        missing = [name for name in needed if getattr(self, name) is None]
        if missing:
            raise ValueError(f"A {self.period_type} period needs {', '.join(missing)}")
        for name in ALL_PERIOD_FIELDS:
            if name not in needed:
                setattr(self, name, None)

    def _check_time_window(self) -> None:
        if self.time_mode != "clock":
            self.window_start_time = self.window_end_time = None
        elif self.window_start_time is None or self.window_end_time is None:
            raise ValueError("A clock window needs a start and an end time")

    def _check_models(self) -> None:
        fewest = MIN_MODELS.get(self.model_mode)
        if fewest is None:
            self.models = []
        elif len(self.models) < fewest:
            raise ValueError(f"Select at least {fewest} model{'s' if fewest > 1 else ''} for {self.model_mode}")


class RequirementIn(RequirementDefinition):
    start_date: date
    end_date: Optional[date] = None
    pilot_ids: list[int] = Field([], max_length=1000)

    @field_validator("pilot_ids")
    @classmethod
    def _dedupe_pilots(cls, v):
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _check_dates(self):
        if self.period_type == "custom" and self.end_date is None:
            raise ValueError("A custom period needs an end date")
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("The end date cannot be before the start date")
        return self


class RequirementUpdate(BaseModel):
    """A partial edit. The edited requirement is validated whole as RequirementIn."""

    name: Optional[str] = None
    description: Optional[str] = None
    period_type: Optional[str] = None
    recurring: Optional[bool] = None
    window_start_day: Optional[int] = None
    window_end_day: Optional[int] = None
    span_length: Optional[int] = None
    span_unit: Optional[str] = None
    every_months: Optional[int] = None
    target_minutes: Optional[int] = None
    target_flights: Optional[int] = None
    model_mode: Optional[str] = None
    models: Optional[list[str]] = None
    time_mode: Optional[str] = None
    window_start_time: Optional[time] = None
    window_end_time: Optional[time] = None
    purposes: Optional[list[str]] = None
    reminder_days: Optional[int] = None
    is_active: Optional[bool] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    pilot_ids: Optional[list[int]] = None


class CurrentPeriod(BaseModel):
    start: date
    end: date
    days_left: int  # days from today through the period's last day, counting both


class RequirementOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    period_type: str
    start_date: date
    end_date: Optional[date] = None
    recurring: bool
    window_start_day: Optional[int] = None
    window_end_day: Optional[int] = None
    span_length: Optional[int] = None
    span_unit: Optional[str] = None
    every_months: Optional[int] = None
    target_minutes: Optional[int] = None
    target_flights: Optional[int] = None
    model_mode: str
    models: list[str]
    time_mode: str
    window_start_time: Optional[time] = None
    window_end_time: Optional[time] = None
    purposes: list[str]
    pilot_ids: list[int]
    reminder_days: int
    is_active: bool
    active_changed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    current_period: Optional[CurrentPeriod] = None


class PilotProgressOut(BaseModel):
    pilot_id: int
    pilot_name: str
    status: str
    totals: dict[str, dict]
    met_by_model: dict[str, bool]
    excluded_no_takeoff: int
    unreviewed_in_period: int
    excused: bool
    excused_reason: Optional[str] = None


class RequirementStatusOut(BaseModel):
    requirement_id: int
    name: str
    target_minutes: Optional[int] = None
    target_flights: Optional[int] = None
    model_mode: str
    period: Optional[CurrentPeriod] = None
    pilots: list[PilotProgressOut]


class StatusOut(BaseModel):
    score: Optional[float] = None
    requirements: list[RequirementStatusOut]


class PilotCurrentOut(PilotProgressOut):
    requirement_id: int
    name: str
    period: CurrentPeriod


class HistoryRowOut(BaseModel):
    result_id: int
    requirement_id: int
    name: str
    period_start: date
    period_end: date
    status: Optional[str] = None
    totals: Optional[dict] = None
    target_snapshot: Optional[dict] = None
    excused: Optional[bool] = None
    excused_by_id: Optional[int] = None  # None on an automatic excusal
    excused_reason: Optional[str] = None
    saved_at: datetime


class PilotRequirementsOut(BaseModel):
    pilot_id: int
    current: list[PilotCurrentOut]
    history: list[HistoryRowOut]


class ExcuseIn(BaseModel):
    pilot_id: int
    period_start: date
    excused: bool
    reason: Optional[str] = Field(None, max_length=500)


class RecalculateIn(BaseModel):
    period_start: date


class RecalculateOut(BaseModel):
    recalculated: int


class FlagOut(BaseModel):
    result_id: int
    requirement_id: int
    name: str
    period_start: date
    period_end: date


class RequirementSettings(BaseModel):
    grace_days: GraceDays
    fiscal_year_start_month: Month


class TemplateIn(BaseModel):
    name: Name
    settings: RequirementDefinition


class TemplateUpdate(BaseModel):
    name: Optional[Name] = None
    settings: Optional[RequirementDefinition] = None


class TemplateOut(BaseModel):
    id: int
    name: str
    settings: dict
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
