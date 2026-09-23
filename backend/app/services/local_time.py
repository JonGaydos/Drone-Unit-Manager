"""The unit's local time, for turning stored UTC timestamps into calendar dates.

Takeoff times are stored as naive UTC. A flight's date is the day it happened
where the unit flies, so a 22:30 takeoff in Chicago is that day, not the next
one, even though it is already tomorrow in UTC.
"""

import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.models.setting import Setting

DEFAULT_TIMEZONE = "America/Chicago"


def display_zone(db) -> ZoneInfo:
    """The configured display timezone, falling back to TZ, then Central."""
    row = db.query(Setting).filter(Setting.key == "display_timezone").first()
    name = (row.value if row and row.value else None) or os.environ.get("TZ", DEFAULT_TIMEZONE)
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def local_flight_date(takeoff: datetime | None, zone: ZoneInfo) -> date | None:
    """The calendar date of ``takeoff`` in ``zone``. A naive value is UTC."""
    if takeoff is None:
        return None
    if takeoff.tzinfo is None:
        takeoff = takeoff.replace(tzinfo=timezone.utc)
    return takeoff.astimezone(zone).date()
