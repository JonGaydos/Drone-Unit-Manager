from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class EquipmentCheckout(Base):
    __tablename__ = "equipment_checkouts"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50))  # vehicle, battery, controller
    entity_id: Mapped[int] = mapped_column(Integer)
    entity_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    checked_out_by_id: Mapped[int] = mapped_column(ForeignKey("pilots.id"))
    checked_out_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expected_return: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    checked_in_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    checked_in_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pilots.id"), nullable=True)
    condition_out: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # good, fair, needs_attention
    condition_in: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes_out: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes_in: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
