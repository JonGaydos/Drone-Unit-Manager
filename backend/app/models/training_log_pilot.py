from typing import Optional

from sqlalchemy import String, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TrainingLogPilot(Base):
    __tablename__ = "training_log_pilots"

    id: Mapped[int] = mapped_column(primary_key=True)
    training_log_id: Mapped[int] = mapped_column(ForeignKey("training_logs.id", ondelete="CASCADE"))
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id"))
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    hours: Mapped[float] = mapped_column(Float, default=0.0)

    training_log = relationship("TrainingLog", back_populates="pilots")
    pilot = relationship("Pilot")
