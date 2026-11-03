from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RolePermission(Base):
    """An admin's change to a role's permission. A missing row means the default."""

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role", "permission_key", name="uq_role_permissions_role_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(20))
    permission_key: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(String(10))
