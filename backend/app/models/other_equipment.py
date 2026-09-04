from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Text, DateTime, Date, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OtherEquipment(Base):
    """Miscellaneous fleet items (cases, tablets, bags, cables, etc.).

    Manual-only: never touched by provider sync. Serial numbers are optional
    because many of these items don't have one.
    """

    __tablename__ = "other_equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # case, tablet, bag, cable, etc.
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")  # active, retired, damaged
    acquired_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    decommissioned_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
