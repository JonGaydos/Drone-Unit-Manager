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


# --- F-15: audit log user and date filters -----------------------------------

def _seed_audit(db):
    """Four entries in UTC days 1-4 March: Avery (user 1) twice, Blake once,
    the system once. Returns Blake's user id."""
    from datetime import datetime
    from app.models.audit_log import AuditLog
    from app.models.user import User
    blake = User(username="blake", password_hash="x", display_name="Blake Pilot", role="pilot")
    db.add(blake)
    db.add(Setting(key="display_timezone", value="UTC"))
    db.flush()
    rows = [
        (1, "Avery Admin", "avery", datetime(2026, 3, 1, 12, 0)),
        (blake.id, "Blake Pilot", "blake", datetime(2026, 3, 2, 12, 0)),
        (1, "Avery Admin", "avery", datetime(2026, 3, 3, 23, 59)),
        (None, "System", None, datetime(2026, 3, 4, 0, 0)),
    ]
    for uid, name, username, at in rows:
        db.add(AuditLog(user_id=uid, user_name=name, user_username=username, action="update",
                        entity_type="setting", created_at=at))
    db.commit()
    return blake.id


def test_audit_list_filters_by_date_range(client, db, admin_headers):
    _seed_audit(db)
    resp = client.get("/api/audit?date_from=2026-03-02&date_to=2026-03-03", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    names = sorted(e["user_name"] for e in resp.json()["logs"])
    assert names == ["Avery Admin", "Blake Pilot"]
    assert resp.json()["total"] == 2


def test_audit_list_filters_by_user_and_date(client, db, admin_headers):
    _seed_audit(db)
    resp = client.get("/api/audit?user_id=1&date_from=2026-03-02", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 1


def test_audit_users_lists_everyone_in_the_log(client, db, admin_headers):
    blake_id = _seed_audit(db)
    resp = client.get("/api/audit/users", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    users = resp.json()
    assert {(u["user_id"], u["user_name"]) for u in users} == {(1, "Avery Admin"), (blake_id, "Blake Pilot")}


def test_audit_users_needs_audit_view(client, db, pilot_headers):
    resp = client.get("/api/audit/users", headers=pilot_headers)
    assert resp.status_code == 403


def test_audit_csv_takes_the_page_filters(client, db, admin_headers):
    blake_id = _seed_audit(db)
    resp = client.get(f"/api/export/audit/csv?user_id={blake_id}&date_from=2026-03-01&date_to=2026-03-04",
                      headers=admin_headers)
    assert resp.status_code == 200, resp.text
    lines = [line for line in resp.text.splitlines() if line.strip()]
    data = [line for line in lines[1:] if "Blake Pilot" in line or "Avery Admin" in line]
    assert len(data) == 1 and "Blake Pilot" in data[0]
