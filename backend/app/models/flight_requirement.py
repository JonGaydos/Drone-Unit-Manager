from datetime import date, datetime, time
from typing import Optional
from sqlalchemy import (
    JSON, Boolean, Date, ForeignKey, Integer, String, Time, UniqueConstraint, func, inspect,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from app.database import Base
from app.models.types import UTCDateTime
from app.services.requirement_periods import PeriodSpec


class FlightRequirement(Base):
    __tablename__ = "flight_requirements"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    period_type: Mapped[str] = mapped_column(String(30))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    recurring: Mapped[bool] = mapped_column(Boolean)
    window_start_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    window_end_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    span_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    span_unit: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    every_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_flights: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model_mode: Mapped[str] = mapped_column(String(20))  # all, combined, each, each_all_active
    time_mode: Mapped[str] = mapped_column(String(10))  # any, clock, night
    window_start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    window_end_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    reminder_days: Mapped[int] = mapped_column(Integer, default=7)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # When is_active last changed on a saved row; NULL if never switched.
    active_changed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    # The end of the latest period closed, with or without pilots to save; NULL if none.
    closed_through: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    modified_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    models: Mapped[list["FlightRequirementModel"]] = relationship(
        back_populates="requirement", cascade="all, delete-orphan", lazy="selectin")
    pilots: Mapped[list["FlightRequirementPilot"]] = relationship(
        back_populates="requirement", cascade="all, delete-orphan", lazy="selectin")
    purposes: Mapped[list["FlightRequirementPurpose"]] = relationship(
        back_populates="requirement", cascade="all, delete-orphan", lazy="selectin")

    @validates("is_active")
    def _stamp_active_change(self, _key: str, value: bool) -> bool:
        """Stamp ``active_changed_at`` when a saved requirement is switched on or off."""
        if inspect(self).persistent and self.is_active is not None and bool(value) != self.is_active:
            self.active_changed_at = datetime.utcnow()
        return value

    def to_period_spec(self, fiscal_start_month: int) -> PeriodSpec:
        return PeriodSpec(
            period_type=self.period_type, start=self.start_date, end=self.end_date,
            recurring=self.recurring, window_start_day=self.window_start_day,
            window_end_day=self.window_end_day, span_length=self.span_length,
            span_unit=self.span_unit, every_months=self.every_months,
            fiscal_start_month=fiscal_start_month)


class FlightRequirementModel(Base):
    __tablename__ = "flight_requirement_models"
    __table_args__ = (UniqueConstraint("requirement_id", "model"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("flight_requirements.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(200))

    requirement: Mapped["FlightRequirement"] = relationship(back_populates="models")


class FlightRequirementPilot(Base):
    __tablename__ = "flight_requirement_pilots"
    __table_args__ = (UniqueConstraint("requirement_id", "pilot_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("flight_requirements.id", ondelete="CASCADE"), index=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id", ondelete="CASCADE"), index=True)
    added_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    requirement: Mapped["FlightRequirement"] = relationship(back_populates="pilots")


class FlightRequirementPurpose(Base):
    __tablename__ = "flight_requirement_purposes"
    __table_args__ = (UniqueConstraint("requirement_id", "purpose"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("flight_requirements.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(100))

    requirement: Mapped["FlightRequirement"] = relationship(back_populates="purposes")


class FlightRequirementResult(Base):
    __tablename__ = "flight_requirement_results"
    __table_args__ = (UniqueConstraint("requirement_id", "pilot_id", "period_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("flight_requirements.id", ondelete="CASCADE"), index=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id", ondelete="CASCADE"), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    totals: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {"<model or *>": {"minutes": int, "flights": int}}
    target_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    excused: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)  # NULL = no override
    excused_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    excused_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    saved_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)  # NULL = open-period override only


class FlightRequirementTemplate(Base):
    __tablename__ = "flight_requirement_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    settings: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    modified_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class FlightRequirementNotice(Base):
    __tablename__ = "flight_requirement_notices"
    __table_args__ = (UniqueConstraint("requirement_id", "pilot_id", "period_start", "kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("flight_requirements.id", ondelete="CASCADE"), index=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id", ondelete="CASCADE"), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20))  # assigned, reminder, missed
    sent_at: Mapped[datetime] = mapped_column(UTCDateTime)
