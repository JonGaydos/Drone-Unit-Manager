from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ChecklistTemplate(Base):
    __tablename__ = "checklist_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vehicle_model: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    items: Mapped[dict] = mapped_column(JSON)  # [{"label": "Check propellers", "required": true}, ...]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChecklistCompletion(Base):
    __tablename__ = "checklist_completions"
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("checklist_templates.id"))
    flight_plan_id: Mapped[Optional[int]] = mapped_column(ForeignKey("flight_plans.id"), nullable=True)
    flight_id: Mapped[Optional[int]] = mapped_column(ForeignKey("flights.id"), nullable=True)
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id"))
    vehicle_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    responses: Mapped[dict] = mapped_column(JSON)  # [{"label": "Check propellers", "checked": true, "notes": ""}, ...]
    all_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
