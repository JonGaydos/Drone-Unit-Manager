from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CurrencyRule(Base):
    __tablename__ = "currency_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    vehicle_model: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # null = applies to all
    required_hours: Mapped[float] = mapped_column(Float)  # hours required
    period_days: Mapped[int] = mapped_column(Integer)  # within this many days
    required_flights: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # min flights in period
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
