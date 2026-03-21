from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Pilot(Base):
    __tablename__ = "pilots"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    badge_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    skydio_user_uuid: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, inactive
    photo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    flights = relationship("Flight", back_populates="pilot")
    certifications = relationship("PilotCertification", back_populates="pilot", cascade="all, delete-orphan")
    equipment_quals = relationship("PilotEquipmentQual", back_populates="pilot", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="pilot", foreign_keys="Document.pilot_id")
    user = relationship("User", back_populates="pilot", foreign_keys="User.pilot_id", uselist=False)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
