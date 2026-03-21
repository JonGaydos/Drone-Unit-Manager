from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Text, DateTime, Date, Integer, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CertificationType(Base):
    __tablename__ = "certification_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    category: Mapped[str] = mapped_column(String(50))  # faa, nist, equipment, insurance, training, custom
    has_expiration: Mapped[bool] = mapped_column(Boolean, default=True)
    renewal_period_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    pilot_certifications = relationship("PilotCertification", back_populates="certification_type")


class PilotCertification(Base):
    __tablename__ = "pilot_certifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id"))
    certification_type_id: Mapped[int] = mapped_column(ForeignKey("certification_types.id"))
    status: Mapped[str] = mapped_column(String(30), default="not_started")
    # Statuses: not_issued, not_eligible, not_started, in_progress, pending, complete, active, expired
    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiration_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    certificate_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    nist_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5 for NIST certs
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    pilot = relationship("Pilot", back_populates="certifications")
    certification_type = relationship("CertificationType", back_populates="pilot_certifications")
    documents = relationship("Document", back_populates="certification", foreign_keys="Document.certification_id")


class PilotEquipmentQual(Base):
    __tablename__ = "pilot_equipment_quals"

    id: Mapped[int] = mapped_column(primary_key=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id"))
    vehicle_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    vehicle_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    qualification_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="in_training")  # qualified, in_training, expired
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    pilot = relationship("Pilot", back_populates="equipment_quals")
