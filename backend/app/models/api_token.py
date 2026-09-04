from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ApiToken(Base):
    """Long-lived API token for external integrations (e.g. Home Assistant).

    The raw token is shown once at creation and stored only as a SHA-256
    hash. A token acts as its creating user (never exceeding that user's
    role), optionally restricted to read-only requests and to a set of API
    areas. Sensitive areas (auth, settings, users, backup, sync) are denied
    to every token regardless of scopes.
    """

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token_prefix: Mapped[str] = mapped_column(String(16))  # display hint only
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    read_only: Mapped[bool] = mapped_column(Boolean, default=True)
    scopes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list; null = all areas
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
