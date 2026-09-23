from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, String, Text, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

# Repeated across the three tables that hang off a photo.
PHOTOS_ID = "photos.id"

class Photo(Base):
    __tablename__ = "photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(500))
    title: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date_taken: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    uploaded_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Evidence handling: a delete only sets deleted_at (the file stays until an
    # admin purges it), a legal hold blocks delete and purge, and sha256 is the
    # digest taken at upload.
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

class PhotoPilot(Base):
    __tablename__ = "photo_pilots"
    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey(PHOTOS_ID, ondelete="CASCADE"))
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id"))


class PhotoFlight(Base):
    __tablename__ = "photo_flights"
    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey(PHOTOS_ID, ondelete="CASCADE"))
    flight_id: Mapped[int] = mapped_column(ForeignKey("flights.id", ondelete="CASCADE"))


class PhotoIncident(Base):
    __tablename__ = "photo_incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey(PHOTOS_ID, ondelete="CASCADE"))
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"))
