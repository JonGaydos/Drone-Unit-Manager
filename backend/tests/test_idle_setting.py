"""The idle lock setting: allowed values, who can read and write it, and its audit entry."""
import pytest

from app.models.audit_log import AuditLog
from app.models.setting import Setting

KEY = "idle_lock_minutes"
ALLOWED = ["30", "60", "120", "240", "360", "480", "720"]
REFUSED = ["", "0", "15", "45", "31", "721", "-30", "abc", "30.0", " 30", "1e2"]


def _stored(db):
    db.expire_all()
    row = db.query(Setting).filter(Setting.key == KEY).first()
    return row.value if row else None


@pytest.mark.parametrize("value", ALLOWED)
def test_idle_setting_accepts_allowed_values(client, db, admin_headers, value):
    single = client.put("/api/settings", headers=admin_headers, json={"key": KEY, "value": value})
    assert single.status_code == 200, single.text
    assert _stored(db) == value

    other = "60" if value == "30" else "30"
    bulk = client.put("/api/settings/bulk", headers=admin_headers, json=[{"key": KEY, "value": other}])
    assert bulk.status_code == 200, bulk.text
    assert _stored(db) == other


@pytest.mark.parametrize("value", REFUSED)
def test_idle_setting_refuses_other_values(client, db, admin_headers, value):
    single = client.put("/api/settings", headers=admin_headers, json={"key": KEY, "value": value})
    assert single.status_code == 422

    bulk = client.put("/api/settings/bulk", headers=admin_headers,
                      json=[{"key": "org_name", "value": "Kept"}, {"key": KEY, "value": value}])
    assert bulk.status_code == 422
    assert _stored(db) is None
    # A refused request changes nothing else in the same request.
    assert db.query(Setting).filter(Setting.key == "org_name").first() is None


def test_non_admin_can_read_not_write(client, db, admin_headers, pilot_headers):
    client.put("/api/settings", headers=admin_headers, json={"key": KEY, "value": "120"})

    listed = client.get("/api/settings", headers=pilot_headers)
    assert listed.status_code == 200
    assert {s["key"]: s["value"] for s in listed.json()}[KEY] == "120"
    one = client.get(f"/api/settings/{KEY}", headers=pilot_headers)
    assert one.status_code == 200
    assert one.json()["value"] == "120"

    assert client.put("/api/settings", headers=pilot_headers,
                      json={"key": KEY, "value": "60"}).status_code == 403
    assert client.put("/api/settings/bulk", headers=pilot_headers,
                      json=[{"key": KEY, "value": "60"}]).status_code == 403
    assert _stored(db) == "120"


def test_change_is_recorded_as_an_edit_by_the_admin(client, db, admin_headers):
    client.put("/api/settings", headers=admin_headers, json={"key": KEY, "value": "30"})
    client.put("/api/settings", headers=admin_headers, json={"key": KEY, "value": "240"})

    db.expire_all()
    entries = db.query(AuditLog).filter_by(entity_type="setting", entity_name=KEY).order_by(AuditLog.id).all()
    assert len(entries) == 2
    assert entries[1].action == "update"
    assert entries[1].user_username == "admin"
    assert entries[1].changes == {"value": {"old": "30", "new": "240"}}
