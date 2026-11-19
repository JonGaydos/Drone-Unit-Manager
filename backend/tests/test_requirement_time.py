from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.services.requirement_time import (
    LOCAL_WALL_CLOCK_SOURCES,
    WindowSettings,
    clock_windows,
    flight_interval,
    minutes_inside,
    night_window,
    period_bounds,
    windows_for_period,
)

CHICAGO = ZoneInfo("America/Chicago")
LONDON = ZoneInfo("Europe/London")
D = date(2026, 11, 19)


def flight(takeoff, duration=None, landing=None, source="skydio_api"):
    return SimpleNamespace(
        takeoff_time=takeoff, duration_seconds=duration, landing_time=landing, data_source=source
    )


def local(*args):
    return datetime(*args, tzinfo=CHICAGO)


def test_parrot_takeoff_is_local():
    assert "parrot_gutma" in LOCAL_WALL_CLOCK_SOURCES
    parrot = flight(datetime(2026, 11, 19, 22, 0), duration=600, source="parrot_gutma")
    start, end = flight_interval(parrot, CHICAGO)
    assert start.replace(tzinfo=None) == datetime(2026, 11, 19, 22, 0)
    assert end - start == timedelta(minutes=10)

    skydio = flight(datetime(2026, 11, 20, 4, 0), duration=600)
    start, _ = flight_interval(skydio, CHICAGO)
    assert start.replace(tzinfo=None) == datetime(2026, 11, 19, 22, 0)


def test_landing_time_used_when_no_duration():
    f = flight(datetime(2026, 11, 20, 4, 0), landing=datetime(2026, 11, 20, 4, 45))
    start, end = flight_interval(f, CHICAGO)
    assert end.replace(tzinfo=None) == datetime(2026, 11, 19, 22, 45)
    assert end - start == timedelta(minutes=45)


def test_no_takeoff_gives_none():
    assert flight_interval(flight(None, duration=600), CHICAGO) is None
    assert flight_interval(flight(datetime(2026, 11, 20, 4, 0)), CHICAGO) is None


def test_partial_overlap():
    windows = clock_windows(D, time(0, 0), time(6, 0), CHICAGO)
    interval = (local(2026, 11, 19, 5, 30), local(2026, 11, 19, 6, 15))
    assert minutes_inside(interval, windows, period_bounds((D, D), CHICAGO)) == 30


def test_window_crossing_midnight():
    windows = clock_windows(D, time(18, 0), time(2, 0), CHICAGO)
    assert windows == [(local(2026, 11, 19, 18, 0), local(2026, 11, 20, 2, 0))]
    interval = (local(2026, 11, 20, 1, 0), local(2026, 11, 20, 3, 0))
    clip = period_bounds((D, D + timedelta(days=1)), CHICAGO)
    assert minutes_inside(interval, windows, clip) == 60


def test_flight_longer_than_window():
    windows = clock_windows(D, time(0, 0), time(6, 0), CHICAGO)
    interval = (local(2026, 11, 18, 23, 0), local(2026, 11, 19, 7, 0))
    assert minutes_inside(interval, windows, period_bounds((D, D), CHICAGO)) == 360


def test_flight_spanning_two_nights():
    settings = WindowSettings(zone=CHICAGO, window_start=time(22, 0), window_end=time(2, 0))
    period = (D, D + timedelta(days=1))
    windows = windows_for_period("clock", period, settings)
    interval = (local(2026, 11, 19, 23, 0), local(2026, 11, 20, 23, 0))
    assert minutes_inside(interval, windows, period_bounds(period, CHICAGO)) == 180 + 60


def test_overlapping_windows_counted_once():
    windows = [
        (local(2026, 11, 19, 0, 0), local(2026, 11, 19, 6, 0)),
        (local(2026, 11, 19, 4, 0), local(2026, 11, 19, 8, 0)),
    ]
    interval = (local(2026, 11, 19, 5, 0), local(2026, 11, 19, 7, 0))
    assert minutes_inside(interval, windows, period_bounds((D, D), CHICAGO)) == 120


def test_windows_for_period_starts_the_day_before():
    settings = WindowSettings(zone=CHICAGO, window_start=time(18, 0), window_end=time(2, 0))
    windows = windows_for_period("clock", (D, D + timedelta(days=1)), settings)
    assert [w[0].date() for w in windows] == [date(2026, 11, 18), D, date(2026, 11, 20)]
    interval = (local(2026, 11, 19, 1, 0), local(2026, 11, 19, 1, 30))
    assert minutes_inside(interval, windows, period_bounds((D, D), CHICAGO)) == 30


def test_clipped_to_period_end():
    period = (date(2026, 11, 1), date(2026, 11, 30))
    any_time = [(local(2026, 10, 1, 0, 0), local(2027, 1, 1, 0, 0))]
    interval = (local(2026, 11, 30, 23, 30), local(2026, 12, 1, 0, 30))
    assert minutes_inside(interval, any_time, period_bounds(period, CHICAGO)) == 30


def test_dst_fall_back():
    # 00:30 CDT is 05:30 UTC; three hours later the clock reads 02:30 CST.
    f = flight(datetime(2026, 11, 1, 5, 30), duration=3 * 3600)
    interval = flight_interval(f, CHICAGO)
    assert interval[0].replace(tzinfo=None) == datetime(2026, 11, 1, 0, 30)
    assert interval[1].replace(tzinfo=None) == datetime(2026, 11, 1, 2, 30)
    day = date(2026, 11, 1)
    windows = clock_windows(day, time(0, 0), time(6, 0), CHICAGO)
    assert minutes_inside(interval, windows, period_bounds((day, day), CHICAGO)) == 180


def test_night_window_matches_published():
    # US Naval Observatory, Greenwich (51.4769 N, 0.0 E), UTC+1:
    # end of civil twilight 2026-06-21 22:09, begin 2026-06-22 03:55.
    dusk, dawn = night_window(date(2026, 6, 21), 51.4769, 0.0, LONDON)
    published_dusk = datetime(2026, 6, 21, 22, 9, tzinfo=LONDON)
    published_dawn = datetime(2026, 6, 22, 3, 55, tzinfo=LONDON)
    assert abs(dusk - published_dusk) <= timedelta(minutes=2)
    assert abs(dawn - published_dawn) <= timedelta(minutes=2)
    assert dusk.hour >= 21 and dawn.hour < 4
    length = dawn.astimezone(timezone.utc) - dusk.astimezone(timezone.utc)
    assert abs(length - timedelta(hours=5, minutes=46)) <= timedelta(minutes=5)


def test_polar_day_has_no_night():
    midsummer = date(2026, 6, 21)
    assert night_window(midsummer, 78.0, 15.0, timezone.utc) is None
    settings = WindowSettings(zone=timezone.utc, lat=78.0, lon=15.0)
    assert windows_for_period("night", (midsummer, midsummer), settings) == []
