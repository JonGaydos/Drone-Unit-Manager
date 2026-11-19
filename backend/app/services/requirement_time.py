"""Time-of-day math for flight requirements.

Pure functions, no database. A flight becomes an aware interval in the display
zone; clock and night windows are aware intervals too. Overlaps are measured on
UTC instants, so a window or flight across a daylight saving change counts real
elapsed minutes, not wall-clock minutes.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo

from astral import Observer
from astral.sun import dawn, dusk

LOCAL_WALL_CLOCK_SOURCES = frozenset({"parrot_gutma"})

CIVIL_DEPRESSION = 6

Interval = tuple[datetime, datetime]


@dataclass(frozen=True)
class WindowSettings:
    """What windows_for_period needs.

    ``zone`` is the display zone. ``window_start`` and ``window_end`` are used
    for ``time_mode == "clock"``; ``lat`` and ``lon`` (the unit default
    location) for ``time_mode == "night"``.
    """

    zone: tzinfo
    window_start: time | None = None
    window_end: time | None = None
    lat: float | None = None
    lon: float | None = None


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _stored_to_zone(value: datetime, source: str | None, zone: tzinfo) -> datetime:
    """A stored naive time as an aware time in ``zone``.

    Most sources store UTC; the local wall-clock sources store time in ``zone``.
    """
    if source in LOCAL_WALL_CLOCK_SOURCES:
        return value.replace(tzinfo=zone)
    return value.replace(tzinfo=timezone.utc).astimezone(zone)


def _flight_end(flight, start: datetime, zone: tzinfo) -> datetime | None:
    if flight.duration_seconds:
        return (_utc(start) + timedelta(seconds=flight.duration_seconds)).astimezone(zone)
    if flight.landing_time is not None:
        return _stored_to_zone(flight.landing_time, flight.data_source, zone)
    return None


def flight_interval(flight, zone: tzinfo) -> Interval | None:
    """Aware (start, end) of ``flight`` in ``zone``, or None without a takeoff or a length.

    The length is ``duration_seconds``, or the landing time when there is no duration.
    """
    if flight.takeoff_time is None:
        return None
    start = _stored_to_zone(flight.takeoff_time, flight.data_source, zone)
    end = _flight_end(flight, start, zone)
    if end is None or _utc(end) <= _utc(start):
        return None
    return start, end


def clock_windows(day: date, start: time, end: time, zone: tzinfo) -> list[Interval]:
    """The clock window that starts on ``day``; when ``end <= start`` it ends the next day."""
    end_day = day + timedelta(days=1) if end <= start else day
    return [(datetime.combine(day, start, tzinfo=zone), datetime.combine(end_day, end, tzinfo=zone))]


def night_window(day: date, lat: float, lon: float, zone: tzinfo) -> Interval | None:
    """End of evening civil twilight on ``day`` to start of morning civil twilight the next day.

    None when the sun never gets 6 degrees below the horizon (astral raises).
    """
    observer = Observer(latitude=lat, longitude=lon)
    try:
        start = dusk(observer, date=day, depression=CIVIL_DEPRESSION, tzinfo=zone)
        end = dawn(observer, date=day + timedelta(days=1), depression=CIVIL_DEPRESSION, tzinfo=zone)
    except ValueError:
        return None
    return start, end


def period_bounds(period: tuple[date, date], zone: tzinfo) -> Interval:
    """Midnight at the start of the period's first day to midnight after its last day."""
    first, last = period
    return (
        datetime.combine(first, time.min, tzinfo=zone),
        datetime.combine(last + timedelta(days=1), time.min, tzinfo=zone),
    )


def _merged_utc(windows: list[Interval]) -> list[Interval]:
    """The union of ``windows`` as sorted, non-overlapping UTC intervals."""
    merged: list[Interval] = []
    for start, end in sorted((_utc(s), _utc(e)) for s, e in windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def minutes_inside(interval: Interval, windows: list[Interval], clip: Interval) -> float:
    """Elapsed minutes of ``interval`` inside the union of ``windows`` and inside ``clip``."""
    start = max(_utc(interval[0]), _utc(clip[0]))
    end = min(_utc(interval[1]), _utc(clip[1]))
    total = timedelta()
    for w_start, w_end in _merged_utc(windows):
        overlap = min(end, w_end) - max(start, w_start)
        if overlap > timedelta():
            total += overlap
    return total.total_seconds() / 60


def windows_for_period(time_mode: str, period: tuple[date, date], settings: WindowSettings) -> list[Interval]:
    """Every clock or night window from the day before the period through its last day.

    The day before is included so a window that starts the evening before the
    period and runs past midnight is found; ``minutes_inside`` clips it to the
    period. ``time_mode`` is ``"clock"`` or ``"night"``.
    """
    first, last = period
    days = [first + timedelta(days=offset) for offset in range(-1, (last - first).days + 1)]
    if time_mode == "clock":
        start, end, zone = settings.window_start, settings.window_end, settings.zone
        return [w for day in days for w in clock_windows(day, start, end, zone)]
    if time_mode == "night":
        nights = (night_window(day, settings.lat, settings.lon, settings.zone) for day in days)
        return [night for night in nights if night is not None]
    raise ValueError(f"No windows for time mode {time_mode!r}")
