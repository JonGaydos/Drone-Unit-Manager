from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Text, DateTime, Date, Float, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    serial_number: Mapped[str] = mapped_column(String(100), unique=True)
    manufacturer: Mapped[str] = mapped_column(String(100))  # "Skydio", "BRINC", "DJI", etc.
    model: Mapped[str] = mapped_column(String(100))  # "X2E", "X10", "LEMUR 2"
    nickname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    faa_registration: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")  # active, maintenance, retired
    total_flight_hours: Mapped[float] = mapped_column(Float, default=0.0)
    total_flights: Mapped[int] = mapped_column(Integer, default=0)
    provider_serial: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    api_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    acquired_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    photo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    modified_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    flights = relationship("Flight", back_populates="vehicle")
    documents = relationship("Document", back_populates="vehicle", foreign_keys="Document.vehicle_id")
    registrations = relationship("VehicleRegistration", back_populates="vehicle", order_by="VehicleRegistration.registration_date.desc()")
