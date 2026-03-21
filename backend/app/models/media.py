from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_uuid: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    flight_id: Mapped[Optional[int]] = mapped_column(ForeignKey("flights.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(20))  # photo, video
    captured_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    download_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    thumbnail_cached: Mapped[bool] = mapped_column(Boolean, default=False)
    api_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
