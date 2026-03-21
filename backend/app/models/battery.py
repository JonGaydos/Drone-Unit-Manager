from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Text, DateTime, Date, Float, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Battery(Base):
    __tablename__ = "batteries"

    id: Mapped[int] = mapped_column(primary_key=True)
    serial_number: Mapped[str] = mapped_column(String(100), unique=True)
    nickname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    vehicle_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cycle_count: Mapped[int] = mapped_column(Integer, default=0)
    health_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")  # active, retired, damaged
    purchase_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    skydio_battery_serial: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    api_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
