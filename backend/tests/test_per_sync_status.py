"""Per-sync status: batch records telemetry run; /sync/status exposes it."""
import httpx

from app.models.flight import Flight
from app.models.setting import Setting
from app.services.sync_manager import SyncManager


def _seed_setting(db, key, value):
    db.add(Setting(key=key, value=value))
    db.commit()


def _telemetry_handler(request):
    if "/telemetry" in str(request.url):
        return httpx.Response(200, json={"data": {"flight_telemetry": [
            {"timestamp_ms": 1000, "gps_latitude": 30.72, "gps_longitude": -86.10,
             "height_above_takeoff": 50.0, "battery_percentage": 90},
        ]}})
    return httpx.Response(200, json={})


def test_batch_records_last_telemetry_status(db, telemetry_db, mock_httpx):
    _seed_setting(db, "skydio_api_token", "test-token")
    _seed_setting(db, "skydio_token_id", "test-token-id")
    db.add(Flight(external_id="F1", api_provider="skydio", telemetry_synced=False))
    db.commit()

    mock_httpx(_telemetry_handler)
    SyncManager.batch_sync_telemetry(db, limit=10)

    db.expire_all()
    ts = db.query(Setting).filter(Setting.key == "last_telemetry_sync_timestamp").first()
    res = db.query(Setting).filter(Setting.key == "last_telemetry_sync_result").first()
    assert ts is not None
    assert ts.value
    assert res is not None
    assert '"synced": 1' in res.value


def test_status_returns_telemetry_fields_and_remaining(client, db, admin_headers):
    import json
    _seed_setting(db, "last_telemetry_sync_timestamp", "2026-07-11T20:00:00+00:00")
    _seed_setting(db, "telemetry_sync_interval", "30")
    _seed_setting(db, "last_telemetry_sync_result", json.dumps({"synced": 5}))
    # Two unsynced with external_id (counted) + one synced (excluded) + one without id (excluded).
    db.add(Flight(external_id="A", api_provider="skydio", telemetry_synced=False))
    db.add(Flight(external_id="B", api_provider="skydio", telemetry_synced=False))
    db.add(Flight(external_id="C", api_provider="skydio", telemetry_synced=True))
    db.add(Flight(external_id=None, api_provider="skydio", telemetry_synced=False))
    db.commit()

    resp = client.get("/api/sync/status", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_telemetry_sync"] == "2026-07-11T20:00:00+00:00"
    assert body["telemetry_sync_interval"] == "30"
    assert body["last_telemetry_sync_result"] == {"synced": 5}
    assert body["telemetry_remaining"] == 2
