"""SyncManager.batch_sync_telemetry: fetch + store telemetry for unsynced flights."""
import httpx

from app.models.flight import Flight
from app.models.setting import Setting
from app.models.telemetry import TelemetryPoint
from app.services.sync_manager import SyncManager


def _seed_setting(db, key, value):
    db.add(Setting(key=key, value=value))
    db.commit()


def _telemetry_handler(request):
    if "/telemetry" in str(request.url):
        return httpx.Response(200, json={"data": {"flight_telemetry": [
            {"timestamp_ms": 1000, "gps_latitude": 30.72, "gps_longitude": -86.10,
             "height_above_takeoff": 50.0, "battery_percentage": 90},
            {"timestamp_ms": 2000, "gps_latitude": 30.73, "gps_longitude": -86.11,
             "height_above_takeoff": 55.0, "battery_percentage": 88},
        ]}})
    return httpx.Response(200, json={})


def test_batch_sync_fetches_and_marks_flight(db, telemetry_db, mock_httpx):
    _seed_setting(db, "skydio_api_token", "test-token")
    _seed_setting(db, "skydio_token_id", "test-token-id")
    f = Flight(external_id="FLIGHT-1", api_provider="skydio", telemetry_synced=False)
    db.add(f)
    db.commit()
    db.refresh(f)

    mock_httpx(_telemetry_handler)
    synced = SyncManager.batch_sync_telemetry(db, limit=10)

    assert synced == 1
    db.expire_all()
    updated = db.query(Flight).filter(Flight.id == f.id).first()
    assert updated.telemetry_synced is True
    assert updated.has_telemetry is True
    points = telemetry_db.query(TelemetryPoint).filter(TelemetryPoint.flight_id == f.id).count()
    assert points == 2


def test_batch_sync_returns_zero_without_credentials(db, mock_httpx):
    f = Flight(external_id="FLIGHT-2", api_provider="skydio", telemetry_synced=False)
    db.add(f)
    db.commit()
    # No token seeded -> batch must no-op.
    assert SyncManager.batch_sync_telemetry(db, limit=10) == 0
