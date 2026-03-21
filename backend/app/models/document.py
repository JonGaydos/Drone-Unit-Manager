from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    pilot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pilots.id"), nullable=True)
    vehicle_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    certification_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pilot_certifications.id"), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(50))  # pilot, vehicle, certification, general
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    document_type: Mapped[str] = mapped_column(String(50))  # part_107, faa_registration, insurance, nist_cert, etc.
    title: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(300))
    file_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    pilot = relationship("Pilot", back_populates="documents", foreign_keys=[pilot_id])
    vehicle = relationship("Vehicle", back_populates="documents", foreign_keys=[vehicle_id])
    certification = relationship("PilotCertification", back_populates="documents", foreign_keys=[certification_id])
