from datetime import date
from typing import Optional

from sqlalchemy import ForeignKey, String, Date, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class VehicleRegistration(Base):
    __tablename__ = "vehicle_registrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    registration_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    registration_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    vehicle = relationship("Vehicle", back_populates="registrations")
