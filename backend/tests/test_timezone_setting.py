"""display_timezone setting: setup capture, public read, admin write."""
from app.models.setting import Setting
from tests.conftest import ADMIN_PASSWORD


def test_setup_persists_display_timezone(client, db):
    resp = client.post("/api/auth/setup", json={
        "username": "admin",
        "password": ADMIN_PASSWORD,
        "display_name": "Admin",
        "org_name": "Test Org",
        "timezone": "America/New_York",
    })
    assert resp.status_code == 200
    row = db.query(Setting).filter(Setting.key == "display_timezone").first()
    assert row is not None
    assert row.value == "America/New_York"


def test_pilot_can_read_display_timezone(client, db, pilot_headers):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()
    resp = client.get("/api/settings/display_timezone", headers=pilot_headers)
    assert resp.status_code == 200
    assert resp.json()["value"] == "America/Chicago"


def test_admin_can_write_display_timezone(client, db, admin_headers):
    resp = client.put("/api/settings",
                      json={"key": "display_timezone", "value": "America/Denver"},
                      headers=admin_headers)
    assert resp.status_code == 200
    assert db.query(Setting).filter(Setting.key == "display_timezone").first().value == "America/Denver"
