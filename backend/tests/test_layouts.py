"""Dashboard and analytics layouts: each user's own arrangement on their
account (PATCH /api/auth/me) and the admin-set unit defaults (settings)."""

import json

import pytest

from app.models.setting import Setting
from app.models.user import User

ME_URL = "/api/auth/me"
SETTINGS_URL = "/api/settings"
BULK_URL = "/api/settings/bulk"

LAYOUT = {"order": ["recent-flights", "this-period", "locations"], "hidden": ["locations"]}


def _stored_layout(db, username, field):
    db.expire_all()
    return getattr(db.query(User).filter(User.username == username).first(), field)


def _stored_setting(db, key):
    db.expire_all()
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else None


@pytest.mark.parametrize("field", ["dashboard_layout", "analytics_layout"])
def test_user_saves_own_layout(client, db, pilot_user, pilot_headers, field):
    resp = client.patch(ME_URL, headers=pilot_headers, json={field: LAYOUT})
    assert resp.status_code == 200, resp.text
    assert resp.json()[field] == LAYOUT
    assert _stored_layout(db, pilot_user.username, field) == LAYOUT


def test_me_returns_saved_layout(client, pilot_headers):
    client.patch(ME_URL, headers=pilot_headers, json={"analytics_layout": LAYOUT})
    assert client.get(ME_URL, headers=pilot_headers).json()["analytics_layout"] == LAYOUT


def test_null_clears_layout(client, db, pilot_user, pilot_headers):
    client.patch(ME_URL, headers=pilot_headers, json={"dashboard_layout": LAYOUT})
    resp = client.patch(ME_URL, headers=pilot_headers, json={"dashboard_layout": None})
    assert resp.status_code == 200, resp.text
    assert _stored_layout(db, pilot_user.username, "dashboard_layout") is None


def test_omitted_layout_is_kept(client, db, pilot_user, pilot_headers):
    client.patch(ME_URL, headers=pilot_headers, json={"dashboard_layout": LAYOUT})
    client.patch(ME_URL, headers=pilot_headers, json={"theme": "light"})
    assert _stored_layout(db, pilot_user.username, "dashboard_layout") == LAYOUT


BAD_LAYOUTS = [
    {"order": ["Recent Flights"], "hidden": []},
    {"order": ["a" * 51], "hidden": []},
    {"order": [""], "hidden": []},
    {"order": ["kpi", "kpi"], "hidden": []},
    {"order": [], "hidden": ["kpi", "kpi"]},
    {"order": [f"tile-{i}" for i in range(51)], "hidden": []},
    {"order": [], "hidden": [f"tile-{i}" for i in range(51)]},
    {"order": "recent-flights", "hidden": []},
    {"order": [1], "hidden": []},
    {"order": [], "hidden": [], "extra": []},
    ["recent-flights"],
]


@pytest.mark.parametrize("layout", BAD_LAYOUTS)
def test_invalid_layout_rejected(client, db, pilot_user, pilot_headers, layout):
    resp = client.patch(ME_URL, headers=pilot_headers, json={"dashboard_layout": layout})
    assert resp.status_code == 422, resp.text
    assert _stored_layout(db, pilot_user.username, "dashboard_layout") is None


def test_fifty_ids_accepted(client, pilot_headers):
    ids = [f"tile-{i}" for i in range(50)]
    resp = client.patch(ME_URL, headers=pilot_headers, json={"dashboard_layout": {"order": ids, "hidden": ids}})
    assert resp.status_code == 200, resp.text


def test_admin_cannot_set_another_users_layout(client, db, admin_headers, pilot_user):
    resp = client.patch(f"/api/auth/users/{pilot_user.id}", headers=admin_headers,
                        json={"dashboard_layout": LAYOUT, "analytics_layout": LAYOUT})
    assert resp.status_code == 200, resp.text
    assert _stored_layout(db, pilot_user.username, "dashboard_layout") is None


def test_admin_update_leaves_users_layout_alone(client, db, admin_headers, pilot_user, pilot_headers):
    client.patch(ME_URL, headers=pilot_headers, json={"analytics_layout": LAYOUT})
    resp = client.patch(f"/api/auth/users/{pilot_user.id}", headers=admin_headers,
                        json={"analytics_layout": None})
    assert resp.status_code == 200, resp.text
    assert _stored_layout(db, pilot_user.username, "analytics_layout") == LAYOUT


@pytest.mark.parametrize("key", ["default_dashboard_layout", "default_analytics_layout"])
def test_admin_saves_unit_default(client, db, admin_headers, key):
    resp = client.put(SETTINGS_URL, headers=admin_headers, json={"key": key, "value": json.dumps(LAYOUT)})
    assert resp.status_code == 200, resp.text
    assert json.loads(_stored_setting(db, key)) == LAYOUT


@pytest.mark.parametrize("key", ["default_dashboard_layout", "default_analytics_layout"])
def test_unit_default_is_public(client, db, admin_headers, pilot_headers, key):
    client.put(SETTINGS_URL, headers=admin_headers, json={"key": key, "value": json.dumps(LAYOUT)})
    resp = client.get(f"{SETTINGS_URL}/{key}", headers=pilot_headers)
    assert resp.status_code == 200, resp.text
    assert json.loads(resp.json()["value"]) == LAYOUT


def test_pilot_cannot_save_unit_default(client, db, pilot_headers):
    resp = client.put(SETTINGS_URL, headers=pilot_headers,
                      json={"key": "default_dashboard_layout", "value": json.dumps(LAYOUT)})
    assert resp.status_code == 403, resp.text
    assert _stored_setting(db, "default_dashboard_layout") is None


@pytest.mark.parametrize("value", ["not json", json.dumps(["kpi"]), json.dumps({"order": ["kpi", "kpi"], "hidden": []}),
                                   json.dumps({"order": ["Bad Id"], "hidden": []})])
def test_invalid_unit_default_rejected(client, db, admin_headers, value):
    resp = client.put(SETTINGS_URL, headers=admin_headers, json={"key": "default_dashboard_layout", "value": value})
    assert resp.status_code == 422, resp.text
    assert _stored_setting(db, "default_dashboard_layout") is None


def test_invalid_unit_default_rejected_in_bulk(client, db, admin_headers):
    resp = client.put(BULK_URL, headers=admin_headers,
                      json=[{"key": "default_analytics_layout", "value": json.dumps({"order": "x"})}])
    assert resp.status_code == 422, resp.text
    assert _stored_setting(db, "default_analytics_layout") is None


def test_empty_unit_default_clears(client, db, admin_headers):
    client.put(SETTINGS_URL, headers=admin_headers,
               json={"key": "default_dashboard_layout", "value": json.dumps(LAYOUT)})
    resp = client.put(SETTINGS_URL, headers=admin_headers, json={"key": "default_dashboard_layout", "value": ""})
    assert resp.status_code == 200, resp.text
    assert _stored_setting(db, "default_dashboard_layout") == ""
