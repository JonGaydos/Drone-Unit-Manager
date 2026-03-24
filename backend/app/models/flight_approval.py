from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, Date, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class FlightPlan(Base):
    __tablename__ = "flight_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    date_planned: Mapped[datetime] = mapped_column(DateTime)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id"))
    vehicle_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    purpose: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    case_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    max_altitude_planned: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_duration_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checklist_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    weather_briefing_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending, approved, denied, cancelled, completed
    submitted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    denial_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    linked_flight_id: Mapped[Optional[int]] = mapped_column(ForeignKey("flights.id"), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
