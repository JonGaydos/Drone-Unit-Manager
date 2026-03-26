from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Text, Integer, Float, ForeignKey, DateTime, Date, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(300))
    severity: Mapped[str] = mapped_column(String(30))  # minor, moderate, major, critical
    category: Mapped[str] = mapped_column(String(100))  # crash, near_miss, equipment_failure, injury, airspace_violation, other
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    flight_id: Mapped[Optional[int]] = mapped_column(ForeignKey("flights.id"), nullable=True)
    pilot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pilots.id"), nullable=True)
    vehicle_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    reported_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="open")  # open, investigating, resolved, closed
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolution_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    equipment_grounded: Mapped[bool] = mapped_column(Boolean, default=False)
    damage_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrective_actions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimated_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    report_type: Mapped[str] = mapped_column(String(30), default="incident")  # "incident" or "success"
    impact_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # For successes: lives_saved, arrest, evidence, community
    outcome_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
