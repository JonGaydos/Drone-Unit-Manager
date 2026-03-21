from typing import Optional

from sqlalchemy import Integer, Float, BigInteger
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class TelemetryBase(DeclarativeBase):
    pass


class TelemetryPoint(TelemetryBase):
    __tablename__ = "telemetry_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    flight_id: Mapped[int] = mapped_column(Integer, index=True)
    timestamp_ms: Mapped[int] = mapped_column(BigInteger)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    altitude_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speed_mps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    battery_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    battery_voltage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    heading_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pitch_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    roll_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    satellites: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
