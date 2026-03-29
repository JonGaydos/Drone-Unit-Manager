"""Notification delivery log for tracking sent digest emails."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NotificationLog(Base):
    """Record of each digest email sent or attempted."""
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    subject: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(30))  # sent, failed, skipped
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    categories_included: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list
    item_count: Mapped[int] = mapped_column(Integer, default=0)
