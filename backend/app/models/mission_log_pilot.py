from typing import Optional

from sqlalchemy import String, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MissionLogPilot(Base):
    __tablename__ = "mission_log_pilots"

    id: Mapped[int] = mapped_column(primary_key=True)
    mission_log_id: Mapped[int] = mapped_column(ForeignKey("mission_logs.id", ondelete="CASCADE"))
    pilot_id: Mapped[int] = mapped_column(ForeignKey("pilots.id"))
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    hours: Mapped[float] = mapped_column(Float, default=0.0)

    mission_log = relationship("MissionLog", back_populates="pilots")
    pilot = relationship("Pilot")
