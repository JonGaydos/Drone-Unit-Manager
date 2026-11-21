"""Flight distance and landing location worked out from GPS telemetry."""
import math
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
