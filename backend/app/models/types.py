"""Column types shared by the models."""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """A moment the server stamped (created, updated, uploaded, sent...).

    Stored as naive UTC, the way these columns always have been, so nothing on
    disk changes. Read back as UTC-aware, so every response carries the zone
    and a browser shows it in local time. Unmarked, the browser took the UTC
    clock time for local time and showed an 8:27 PM action at 1:27 AM the next
    day. Times a person types in (a planned flight, a mission start) stay plain
    DateTime: they are local wall-clock times, not UTC.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if isinstance(value, datetime) and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if isinstance(value, datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
