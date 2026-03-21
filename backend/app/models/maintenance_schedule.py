from sqlalchemy import ForeignKey, String, Text, Date, Boolean, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import date, datetime
from typing import Optional
from app.database import Base


class MaintenanceSchedule(Base):
    __tablename__ = "maintenance_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    entity_type: Mapped[str] = mapped_column(String(50))  # vehicle, battery, controller, dock, organization
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # null for org-wide
    frequency: Mapped[str] = mapped_column(String(20))  # monthly, quarterly, yearly
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_to_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pilots.id"), nullable=True)
    last_completed: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_due: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    assigned_to = relationship("Pilot", foreign_keys=[assigned_to_id])
