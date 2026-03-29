from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # "admin", "supervisor", "pilot", or "viewer"
    is_active: Mapped[bool] = mapped_column(default=True)
    theme: Mapped[str] = mapped_column(String(30), default="dark")
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pilot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pilots.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    pilot = relationship("Pilot", back_populates="user", foreign_keys=[pilot_id])
