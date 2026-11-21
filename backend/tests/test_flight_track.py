"""Flight distance and landing location worked out from GPS telemetry."""
import math
import random
from datetime import datetime

import pytest

from app.models.flight import Flight
from app.models.setting import Setting
from app.models.telemetry import TelemetryPoint
from app.services import flight_track, sync_manager
from app.services.flight_track import fill_track_fields, track_summary

DEG_M = math.pi * 6_371_008.8 / 180


def _pt(lat, lon, ts_s):
    return {"lat": lat, "lon": lon, "timestamp_ms": int(ts_s * 1000)}


def _square():
    """A 0.01 degree square flown at about 18 m/s, back to the start."""
    return [
        _pt(30.0, -86.0, 0), _pt(30.01, -86.0, 60), _pt(30.01, -85.99, 120),
        _pt(30.0, -85.99, 180), _pt(30.0, -86.0, 240),
    ]


def _square_length():
    north = 0.01 * DEG_M
    east = 0.01 * DEG_M * (math.cos(math.radians(30.01)) + math.cos(math.radians(30.0)))
    return 2 * north + east


def test_square_path_distance_within_one_percent():
    summary = track_summary(_square())
    assert summary["distance_m"] == pytest.approx(_square_length(), rel=0.01)


def test_landing_is_last_good_fix():
    summary = track_summary(_square() + [_pt(None, None, 250)])
    assert (summary["landing_lat"], summary["landing_lon"]) == (30.0, -86.0)


def test_gps_jump_is_skipped():
    points = _square()
    # One second after takeoff the fix leaps about 11 km away, then comes back.
    points.insert(1, _pt(30.1, -86.0, 1))
    summary = track_summary(points)
    assert summary["distance_m"] == pytest.approx(_square_length(), rel=0.01)


def test_bad_first_fix_is_skipped():
    points = [_pt(30.1, -86.0, -1)] + _square()
    summary = track_summary(points)
    assert summary["distance_m"] == pytest.approx(_square_length(), rel=0.01)


def test_bad_first_fix_does_not_move_landing():
    points = [_pt(30.1, -86.0, -1)] + _square()
    summary = track_summary(points)
    assert (summary["landing_lat"], summary["landing_lon"]) == (30.0, -86.0)


def _second_track():
    """North 0.01 degree in two minutes, one fix a second."""
    return [_pt(30.0 + 0.01 * i / 120, -86.0, i) for i in range(121)]


def _second_track_end():
    return pytest.approx((30.01, -86.0))


def _gap_then_outlier():
    """The 1 Hz track, a 200 s outage, one fix about 10 km off, then the real return."""
    return _second_track() + [_pt(30.1, -86.0, 320), _pt(30.0101, -86.0, 321), _pt(30.0102, -86.0, 322)]


def test_outlier_after_a_gap_is_skipped():
    summary = track_summary(_gap_then_outlier())
    assert summary["distance_m"] == pytest.approx(0.0102 * DEG_M, rel=0.01)


def test_outlier_after_a_gap_does_not_become_landing():
    summary = track_summary(_gap_then_outlier())
    assert (summary["landing_lat"], summary["landing_lon"]) == (30.0102, -86.0)


def test_bad_final_fix_after_a_gap_adds_no_distance():
    summary = track_summary(_second_track() + [_pt(30.1, -86.0, 320)])
    assert summary["distance_m"] == pytest.approx(0.01 * DEG_M, rel=0.01)


def test_bad_final_fix_after_a_gap_is_not_the_landing():
    summary = track_summary(_second_track() + [_pt(30.1, -86.0, 320)])
    assert (summary["landing_lat"], summary["landing_lon"]) == _second_track_end()


def _gap_then_real_pair():
    """The 1 Hz track, a 200 s outage, then two agreeing fixes about 4 km on."""
    return _second_track() + [_pt(30.045, -86.0, 320), _pt(30.0451, -86.0, 321)]


def test_confirmed_fix_after_a_pause_counts_the_straight_line():
    summary = track_summary(_gap_then_real_pair())
    assert summary["distance_m"] == pytest.approx(0.0451 * DEG_M, rel=0.01)


def test_outage_in_a_second_track_counts_the_straight_line():
    # Two minutes without fixes while the craft moves about 1 km north.
    after = [_pt(30.019 + 0.0001 * i, -86.0, 240 + i) for i in range(30)]
    summary = track_summary(_second_track() + after)
    assert summary["distance_m"] == pytest.approx((0.019 + 0.0029) * DEG_M, rel=0.01)


def test_agreeing_fixes_after_a_gap_give_the_landing():
    summary = track_summary(_gap_then_real_pair())
    assert (summary["landing_lat"], summary["landing_lon"]) == (30.0451, -86.0)


def _line_every_minute(minutes, start_lat=30.0, start_s=0):
    """A flight north at 10 m/s with one fix a minute."""
    return [_pt(start_lat + i * 600 / DEG_M, -86.0, start_s + i * 60) for i in range(minutes + 1)]


def test_minute_sampling_is_measured():
    summary = track_summary(_line_every_minute(20))
    assert summary["distance_m"] == pytest.approx(12000, rel=0.01)


def test_minute_sampling_lands_at_the_last_fix():
    points = _line_every_minute(20)
    summary = track_summary(points)
    assert (summary["landing_lat"], summary["landing_lon"]) == (points[-1]["lat"], -86.0)


def test_minute_sampled_zigzag_is_measured():
    points = [_pt(30.0 + (i % 2) * 480 / DEG_M, -86.0, i * 60) for i in range(21)]
    assert track_summary(points)["distance_m"] == pytest.approx(9600, rel=0.01)


def test_outage_in_minute_sampling_counts_the_straight_line():
    first = _line_every_minute(10)
    # Ten minutes without fixes, then the flight carries on 4 km further north.
    second = _line_every_minute(10, start_lat=first[-1]["lat"] + 4000 / DEG_M, start_s=1200)
    summary = track_summary(first + second)
    assert summary["distance_m"] == pytest.approx(16000, rel=0.01)


def _mixed_rate(fast_fixes, slow_fixes):
    """North at 10 m/s: fast_fixes one a second, then slow_fixes one a minute."""
    fast = [_pt(30.0 + i * 10 / DEG_M, -86.0, i) for i in range(fast_fixes)]
    end_lat, end_s = fast[-1]["lat"], fast_fixes - 1
    slow = [_pt(end_lat + i * 600 / DEG_M, -86.0, end_s + i * 60) for i in range(1, slow_fixes + 1)]
    return fast + slow


def test_second_then_minute_sampling_is_measured():
    summary = track_summary(_mixed_rate(301, 10))
    assert summary["distance_m"] == pytest.approx(9000, rel=0.05)


def test_second_then_minute_sampling_lands_at_the_last_fix():
    points = _mixed_rate(301, 10)
    summary = track_summary(points)
    assert summary["landing_lat"] == points[-1]["lat"]


def test_hundred_fast_fixes_then_thirty_slow_ones():
    summary = track_summary(_mixed_rate(100, 30))
    assert summary["distance_m"] == pytest.approx(990 + 18000, rel=0.05)


NOISE_DEG = 3 / DEG_M


def _noisy_line(count, step_deg, interval_s):
    rng = random.Random(1)
    lon_noise = NOISE_DEG / math.cos(math.radians(30))
    return [_pt(30.0 + i * step_deg + rng.gauss(0, NOISE_DEG), -86.0 + rng.gauss(0, lon_noise), i * interval_s)
            for i in range(count)]


def test_noise_at_one_hertz_within_five_percent():
    summary = track_summary(_noisy_line(301, 0.0001, 1))
    assert summary["distance_m"] == pytest.approx(300 * 0.0001 * DEG_M, rel=0.05)


def test_noise_at_ten_hertz_within_fifteen_percent():
    summary = track_summary(_noisy_line(301, 0.00001, 0.1))
    assert summary["distance_m"] == pytest.approx(300 * 0.00001 * DEG_M, rel=0.15)


def test_noisy_hover_adds_almost_nothing():
    summary = track_summary(_noisy_line(500, 0, 0.2))
    assert summary["distance_m"] < 50


def test_fast_flight_is_measured():
    step = 550 / DEG_M
    summary = track_summary([_pt(30.0 + i * step, -86.0, i * 10) for i in range(11)])
    assert summary["distance_m"] == pytest.approx(5500, rel=0.01)


def test_bad_coordinates_are_skipped():
    points = [_pt(500, 500, 0), _pt(0, 0, 1)] + _square() + [_pt(91, 10, 300)]
    summary = track_summary(points)
    assert summary["distance_m"] == pytest.approx(_square_length(), rel=0.01)


def test_no_valid_points_gives_none():
    summary = track_summary([_pt(None, None, 0), _pt(500, 500, 1)])
    assert summary == {"distance_m": None, "landing_lat": None, "landing_lon": None}


def test_accepts_telemetry_rows():
    rows = [TelemetryPoint(flight_id=1, lat=p["lat"], lon=p["lon"], timestamp_ms=p["timestamp_ms"])
            for p in _square()]
    assert track_summary(rows)["distance_m"] == pytest.approx(_square_length(), rel=0.01)


def _flight_with_track(db, telemetry_db, points=None, **fields):
    flight = Flight(has_telemetry=True, telemetry_synced=True, **fields)
    db.add(flight)
    db.commit()
    for p in points if points is not None else _square():
        telemetry_db.add(TelemetryPoint(flight_id=flight.id, **p))
    telemetry_db.commit()
    return flight


def test_fill_sets_empty_fields(db, telemetry_db):
    flight = _flight_with_track(db, telemetry_db)
    assert fill_track_fields(db, flight) is True
    assert flight.distance_m == pytest.approx(_square_length(), rel=0.01)
    assert (flight.landing_lat, flight.landing_lon) == (30.0, -86.0)


def test_fill_keeps_typed_values(db, telemetry_db):
    flight = _flight_with_track(db, telemetry_db, distance_m=1234.0, landing_lat=31.5,
                                landing_lon=-87.5, landing_time=datetime(2026, 1, 1, 10, 30))
    flight.takeoff_time = datetime(2026, 1, 1, 10, 0)
    flight.duration_seconds = 600
    assert fill_track_fields(db, flight) is False
    assert flight.distance_m == 1234.0
    assert (flight.landing_lat, flight.landing_lon) == (31.5, -87.5)
    assert flight.landing_time == datetime(2026, 1, 1, 10, 30)


def test_fill_keeps_typed_landing_address(db, telemetry_db, geocoder):
    flight = _flight_with_track(db, telemetry_db, landing_address="Typed address")
    flight_track.fill_missing()
    db.expire_all()
    assert db.get(Flight, flight.id).landing_address == "Typed address"


def test_track_without_gps_fix_stays_blank(db, telemetry_db):
    flight = _flight_with_track(db, telemetry_db, points=[_pt(None, None, 0), _pt(500, 500, 1)])
    assert fill_track_fields(db, flight) is False
    assert (flight.distance_m, flight.landing_lat, flight.landing_lon) == (None, None, None)


def test_fill_landing_time_from_takeoff_and_duration(db):
    flight = Flight(takeoff_time=datetime(2026, 1, 1, 10, 0), duration_seconds=900)
    db.add(flight)
    db.commit()
    assert fill_track_fields(db, flight) is True
    assert flight.landing_time == datetime(2026, 1, 1, 10, 15)


@pytest.fixture
def geocoder(monkeypatch):
    calls = []

    def fake(lat, lon):
        calls.append((lat, lon))
        return f"Somewhere near {lat:.2f}, {lon:.2f}"

    monkeypatch.setattr(sync_manager, "_reverse_geocode", fake)
    monkeypatch.setattr(flight_track, "GEOCODE_INTERVAL_S", 0)
    return calls


def test_backfill_fills_and_is_idempotent(db, telemetry_db, geocoder):
    ids = [_flight_with_track(db, telemetry_db).id for _ in range(3)]
    first = flight_track.fill_missing(batch_size=2)
    assert first["filled"] == 3
    assert len(geocoder) == 3

    second = flight_track.fill_missing(batch_size=2)
    assert second["filled"] == 0
    assert len(geocoder) == 3
    db.expire_all()
    flights = db.query(Flight).filter(Flight.id.in_(ids)).all()
    assert all(f.landing_address == "Somewhere near 30.00, -86.00" for f in flights)
    marker = db.query(Setting).filter(Setting.key == flight_track.BACKFILL_DONE_KEY).first()
    assert marker is not None


def test_backfill_resumes_after_interruption(db, telemetry_db, monkeypatch):
    older = _flight_with_track(db, telemetry_db)
    newer = _flight_with_track(db, telemetry_db)
    monkeypatch.setattr(flight_track, "GEOCODE_INTERVAL_S", 0)
    calls = []

    def flaky(lat, lon):
        calls.append(lat)
        if len(calls) == 2:
            raise RuntimeError("stopped")
        return "Landing spot"

    monkeypatch.setattr(sync_manager, "_reverse_geocode", flaky)
    with pytest.raises(RuntimeError):
        flight_track.fill_missing(batch_size=1)
    db.expire_all()
    assert db.get(Flight, newer.id).landing_address == "Landing spot"
    assert db.query(Setting).filter(Setting.key == flight_track.BACKFILL_DONE_KEY).first() is None

    result = flight_track.fill_missing(batch_size=1)
    db.expire_all()
    assert result["geocoded"] == 1
    assert db.get(Flight, older.id).landing_address == "Landing spot"


def test_backfill_skips_flights_without_telemetry(db, geocoder):
    db.add(Flight(has_telemetry=False))
    db.commit()
    result = flight_track.fill_missing()
    assert result["checked"] == 0


def test_log_import_fills_distance_and_landing(db, telemetry_db):
    from app.services.flight_log_import import import_flight_log
    log = chr(10).join(chr(9).join(str(c) for c in row) for row in [
        ["CUSTOM.date", "OSD.latitude", "OSD.longitude", "OSD.altitude [m]"],
        ["2026-05-01 10:00:00", 28.5, -81.4, 10.0],
        ["2026-05-01 10:00:30", 28.501, -81.4, 20.0],
        ["2026-05-01 10:01:00", 28.502, -81.4, 5.0],
    ])
    result = import_flight_log(log.encode(), db, telemetry_db)
    flight = db.get(Flight, result["flight_id"])
    assert flight.distance_m == pytest.approx(0.002 * DEG_M, rel=0.01)
    assert (flight.landing_lat, flight.landing_lon) == (28.502, -81.4)


def test_telemetry_sync_fills_distance_and_landing(db, mock_httpx):
    import httpx
    from app.services.sync_manager import SyncManager

    def handler(request):
        if "/telemetry" in str(request.url):
            return httpx.Response(200, json={"data": {"flight_telemetry": [
                {"timestamp_ms": 1000, "gps_latitude": 30.72, "gps_longitude": -86.10},
                {"timestamp_ms": 61000, "gps_latitude": 30.721, "gps_longitude": -86.10},
            ]}})
        return httpx.Response(200, json={})

    db.add_all([Setting(key="skydio_api_token", value="t"), Setting(key="skydio_token_id", value="i")])
    flight = Flight(external_id="FLIGHT-1", api_provider="skydio", telemetry_synced=False)
    db.add(flight)
    db.commit()
    mock_httpx(handler)
    SyncManager.batch_sync_telemetry(db, limit=10)
    db.expire_all()
    flight = db.get(Flight, flight.id)
    assert flight.distance_m == pytest.approx(0.001 * DEG_M, rel=0.01)
    assert (flight.landing_lat, flight.landing_lon) == (30.721, -86.10)


@pytest.fixture
def scheduler_db(_engines, monkeypatch):
    import app.services.scheduler as sched
    monkeypatch.setattr(sched, "SessionLocal", _engines[0])
    monkeypatch.setattr(sched, "_scheduler", None)
    return sched


def test_scheduler_runs_fill_soon_after_boot_until_done(scheduler_db):
    sched = scheduler_db
    sched.start_scheduler()
    try:
        job = sched._scheduler.get_job(sched.TRACK_FILL_JOB_ID)
        assert job.next_run_time.timestamp() - datetime.now().timestamp() < 300
    finally:
        sched.stop_scheduler()


def test_scheduler_waits_for_daily_run_after_backfill(db, scheduler_db):
    sched = scheduler_db
    db.add(Setting(key=flight_track.BACKFILL_DONE_KEY, value="2026-11-20T00:00:00+00:00"))
    db.commit()
    sched.start_scheduler()
    try:
        job = sched._scheduler.get_job(sched.TRACK_FILL_JOB_ID)
        assert job.next_run_time.timestamp() - datetime.now().timestamp() > 300
    finally:
        sched.stop_scheduler()


def test_geocoding_stops_after_repeated_failures(db, telemetry_db, monkeypatch):
    for _ in range(8):
        _flight_with_track(db, telemetry_db)
    monkeypatch.setattr(flight_track, "GEOCODE_INTERVAL_S", 0)
    calls = []
    monkeypatch.setattr(sync_manager, "_reverse_geocode", lambda lat, lon: calls.append(lat))
    result = flight_track.fill_missing(batch_size=3)
    assert len(calls) == flight_track.GEOCODE_FAILURE_LIMIT
    assert result["filled"] == 8
    assert db.query(Setting).filter(Setting.key == flight_track.BACKFILL_DONE_KEY).first() is None


def test_backfill_check_failure_skips_the_early_run(scheduler_db, monkeypatch):
    sched = scheduler_db

    def broken():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(sched, "SessionLocal", broken)
    assert sched._track_fill_job_kwargs() == {}
