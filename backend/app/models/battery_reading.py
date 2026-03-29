"""Battery health reading snapshots for tracking degradation over time."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BatteryReading(Base):
    """Historical snapshot of a battery's health metrics.

    A new reading is inserted each time a battery's health_pct or cycle_count
    changes (via sync, manual edit, or import), enabling trend analysis.

    Attributes:
        battery_id: Foreign key to the batteries table.
        recorded_at: When this reading was taken.
        health_pct: Battery health percentage (0-100).
        cycle_count: Total charge/discharge cycles.
        voltage: Battery voltage reading.
        capacity_mah: Battery capacity in milliamp-hours.
        temperature_c: Battery temperature in Celsius.
        source: How this reading was captured (manual, skydio_sync, dji_import).
        notes: Optional free-text notes.
    """
    __tablename__ = "battery_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    battery_id: Mapped[int] = mapped_column(ForeignKey("batteries.id"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    health_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cycle_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    voltage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    capacity_mah: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
