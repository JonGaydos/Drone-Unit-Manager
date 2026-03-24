from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Float, Boolean, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Geofence(Base):
    __tablename__ = "geofences"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    zone_type: Mapped[str] = mapped_column(String(50))  # no_fly, restricted, authorized, caution
    geometry_type: Mapped[str] = mapped_column(String(20))  # circle, polygon
    center_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    center_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    radius_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    polygon_points: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # [[lat, lon], ...]
    max_altitude_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # manual, faa, airmap
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
