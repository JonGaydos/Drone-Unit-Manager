from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Text, DateTime, Date, Float, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50))  # vehicle, battery, controller, dock
    entity_id: Mapped[int] = mapped_column(Integer)
    maintenance_type: Mapped[str] = mapped_column(String(50))  # scheduled, unscheduled, inspection
    description: Mapped[str] = mapped_column(Text)
    performed_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    performed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_due_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
