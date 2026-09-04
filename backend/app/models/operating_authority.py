from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import String, Text, Date, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Warning window before expiry. Matches the certification window the compliance
# dashboard already uses, so "expiring" means the same thing everywhere.
AUTHORITY_EXPIRING_DAYS = 90

# Ceiling applied to the compliance score while an authority the unit depends on
# is expired. An expired COA means every flight is unauthorised, so no amount of
# other compliance should let the score read green.
AUTHORITY_SCORE_CAP = 50

AUTHORITY_TYPES = ("coa", "part_107_waiver")

# Record lifecycle, set by hand and independent of the expiry math. Only "active"
# records are scored; the other two stay on file for the reports without
# affecting compliance.
RECORD_STATUSES = ("active", "superseded", "not_applicable")

AUTHORITY_TYPE_LABELS = {"coa": "COA", "part_107_waiver": "Part 107 Waiver"}
RECORD_STATUS_LABELS = {
    "active": "Active",
    "superseded": "Superseded",
    "not_applicable": "Not Applicable",
}
DERIVED_STATUS_LABELS = {"active": "Active", "expiring": "Expiring Soon", "expired": "Expired"}


class OperatingAuthority(Base):
    """An authority the unit itself holds: a COA or a Part 107 waiver.

    Org-level, not attached to a pilot or a vehicle. Supporting documents are
    filed through the normal document storage under entity_type
    "operating_authority", so there is no upload path of its own.
    """

    __tablename__ = "operating_authorities"

    id: Mapped[int] = mapped_column(primary_key=True)
    authority_type: Mapped[str] = mapped_column(String(50))  # coa, part_107_waiver
    identifier: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    record_status: Mapped[str] = mapped_column(String(20), default="active")
    # False for an authority whose lapse restricts one kind of operation (a night
    # waiver, say) rather than grounding the unit outright.
    grounds_unit: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


def authority_status(authority: OperatingAuthority, today: Optional[date] = None) -> str:
    """Derived expiry status: active, expiring, or expired.

    Derived rather than stored so it can never go stale. A record with no expiry
    date does not expire.
    """
    today = today or date.today()
    if not authority.expiry_date:
        return "active"
    if authority.expiry_date < today:
        return "expired"
    if authority.expiry_date <= today + timedelta(days=AUTHORITY_EXPIRING_DAYS):
        return "expiring"
    return "active"
