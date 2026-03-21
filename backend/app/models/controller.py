from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Controller(Base):
    __tablename__ = "controllers"

    id: Mapped[int] = mapped_column(primary_key=True)
    serial_number: Mapped[str] = mapped_column(String(100), unique=True)
    nickname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    skydio_controller_serial: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    api_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    assigned_pilot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pilots.id"), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
