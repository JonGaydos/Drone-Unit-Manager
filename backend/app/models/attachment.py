from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    serial_number: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # speaker, spotlight, etc.
    manufacturer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    skydio_serial: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    api_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
