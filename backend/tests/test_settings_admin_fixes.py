"""Regression tests for the Area 8 staging-test fixes: settings, users, audit,
notifications and email (backlog F-* and G-* items)."""

from app.models.setting import Setting

BULK_URL = "/api/settings/bulk"


def _stored(db, key):
    db.expire_all()
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else None


# --- F-02: sidebar group headers toggle --------------------------------------

def test_sidebar_show_groups_is_saved_by_bulk(client, db, admin_headers):
    resp = client.put(BULK_URL, headers=admin_headers,
                      json=[{"key": "sidebar_show_groups", "value": "false"}])
    assert resp.status_code == 200, resp.text
    assert _stored(db, "sidebar_show_groups") == "false"


def test_sidebar_show_groups_is_saved_by_single_put(client, db, admin_headers):
    resp = client.put("/api/settings", headers=admin_headers,
                      json={"key": "sidebar_show_groups", "value": "true"})
    assert resp.status_code == 200, resp.text
    assert _stored(db, "sidebar_show_groups") == "true"


def test_sidebar_show_groups_refuses_other_values(client, db, admin_headers):
    resp = client.put(BULK_URL, headers=admin_headers,
                      json=[{"key": "sidebar_show_groups", "value": "maybe"}])
    assert resp.status_code == 422
    assert _stored(db, "sidebar_show_groups") is None
