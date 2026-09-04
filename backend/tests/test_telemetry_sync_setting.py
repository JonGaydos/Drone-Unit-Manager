"""telemetry_sync_interval: allowlist, public read, and bulk-save reschedule."""
from app.models.setting import Setting


def test_pilot_can_read_telemetry_interval(client, db, pilot_headers):
    db.add(Setting(key="telemetry_sync_interval", value="30"))
    db.commit()
    resp = client.get("/api/settings/telemetry_sync_interval", headers=pilot_headers)
    assert resp.status_code == 200
    assert resp.json()["value"] == "30"


def test_admin_can_write_telemetry_interval(client, db, admin_headers):
    resp = client.put("/api/settings",
                      json={"key": "telemetry_sync_interval", "value": "60"},
                      headers=admin_headers)
    assert resp.status_code == 200
    assert db.query(Setting).filter(Setting.key == "telemetry_sync_interval").first().value == "60"


def test_bulk_save_reschedules_telemetry(client, db, admin_headers, monkeypatch):
    calls = []
    import app.services.scheduler as sched
    monkeypatch.setattr(sched, "reschedule_telemetry_sync", lambda minutes: calls.append(minutes))

    resp = client.put("/api/settings/bulk",
                      json=[{"key": "telemetry_sync_interval", "value": "30"}],
                      headers=admin_headers)
    assert resp.status_code == 200
    assert calls == [30]
