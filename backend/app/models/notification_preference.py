"""User notification preferences for email digest configuration."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Boolean, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NotificationPreference(Base):
    """Per-user email notification settings.

    Controls digest frequency, delivery time, and which categories
    of actionable items to include in the digest email.
    """
    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    frequency: Mapped[str] = mapped_column(String(20), default="daily")  # daily, weekly, off
    send_time: Mapped[str] = mapped_column(String(5), default="07:00")  # HH:MM 24h format
    send_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0=Mon..6=Sun (weekly only)
    categories: Mapped[str] = mapped_column(Text, default='["pending_approvals","needs_review","expiring_certs","expiring_registrations","overdue_maintenance","assigned_missions","overdue_checkouts","recent_incidents"]')
    email_override: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Override user's default email
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
