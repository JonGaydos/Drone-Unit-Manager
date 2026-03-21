from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Text, DateTime, Date, Float, Integer, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FlightPurpose(Base):
    __tablename__ = "flight_purposes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Flight(Base):
    __tablename__ = "flights"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    api_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    pilot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pilots.id"), nullable=True)
    vehicle_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    takeoff_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    landing_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    takeoff_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    takeoff_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    landing_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    landing_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    takeoff_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    landing_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    max_altitude_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_speed_mps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    distance_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    purpose: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    case_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    battery_serial: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    has_telemetry: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(20), default="reviewed")  # needs_review, reviewed
    pilot_confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    pilot = relationship("Pilot", back_populates="flights")
    vehicle = relationship("Vehicle", back_populates="flights")
