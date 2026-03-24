from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    user_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    action: Mapped[str] = mapped_column(String(50))  # create, update, delete, login, sync, approve, deny
    entity_type: Mapped[str] = mapped_column(String(50))  # flight, pilot, vehicle, certification, etc.
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    entity_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    changes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {"field": {"old": x, "new": y}}
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
