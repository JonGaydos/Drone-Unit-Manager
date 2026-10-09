"""The unit's local time, for turning stored UTC timestamps into calendar dates.

Takeoff times are stored as naive UTC. A flight's date is the day it happened
where the unit flies, so a 22:30 takeoff in Chicago is that day, not the next
one, even though it is already tomorrow in UTC.
"""

import os
from datetime import date, datetime, time, timedelta, timezone
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


def local_day_start(day: date, zone: ZoneInfo) -> datetime:
    """Midnight at the start of ``day`` in ``zone``, as a UTC moment.

    A server-stamped time is stored in UTC, so a filter "on or after Oct 7"
    starts at 05:00 UTC in Chicago, not at 00:00 UTC (7 PM the evening before).
    """
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc)


def stamped_on_or_after(column, day: date, zone: ZoneInfo):
    """Filter: ``column`` falls on ``day`` or later, in local days."""
    return column >= local_day_start(day, zone)


def stamped_on_or_before(column, day: date, zone: ZoneInfo):
    """Filter: ``column`` falls on ``day`` or earlier, in local days."""
    return column < local_day_start(day + timedelta(days=1), zone)
