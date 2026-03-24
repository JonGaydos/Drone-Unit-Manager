from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Text, Integer, Float, ForeignKey, DateTime, Date, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Component(Base):
    __tablename__ = "components"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    component_type: Mapped[str] = mapped_column(String(100))  # gimbal, propeller, camera, motor, esc, frame, landing_gear
    serial_number: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    vehicle_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")  # active, needs_replacement, replaced, retired
    install_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    flight_hours: Mapped[float] = mapped_column(Float, default=0.0)
    max_flight_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    warranty_expiry: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    replacement_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
