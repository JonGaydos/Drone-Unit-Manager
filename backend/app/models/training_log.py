from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Text, DateTime, Date, Float, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TrainingLog(Base):
    __tablename__ = "training_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    title: Mapped[str] = mapped_column(String(300))
    training_type: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    man_hours: Mapped[float] = mapped_column(Float, default=0.0)
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    vehicle_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    instructor: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    objectives: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String(30), default="completed")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    vehicle = relationship("Vehicle")
    pilots = relationship("TrainingLogPilot", back_populates="training_log", cascade="all, delete-orphan")
