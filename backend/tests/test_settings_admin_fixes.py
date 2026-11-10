"""Regression tests for the Area 8 staging-test fixes: settings, users, audit,
notifications and email (backlog F-* and G-* items)."""

import pytest

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


# --- G-2: test digests do not count as the day's digest ------------------------

PREFS_URL = "/api/notifications/preferences"


def _fake_digest(monkeypatch):
    from app.services import email_digest
    monkeypatch.setattr(email_digest, "build_digest", lambda db, user: {"expiring_certs": [{"id": 1}]})
    monkeypatch.setattr(email_digest, "send_email", lambda *a, **k: True)


def test_test_digest_is_logged_as_test_and_not_as_sent(client, db, pilot_user, pilot_headers, monkeypatch):
    from app.models.notification_log import NotificationLog
    pilot_user.email = "pilot@example.test"
    db.commit()
    _fake_digest(monkeypatch)
    resp = client.post("/api/notifications/send-test", headers=pilot_headers)
    assert resp.status_code == 200 and resp.json()["ok"], resp.text
    db.expire_all()
    rows = db.query(NotificationLog).filter(NotificationLog.user_id == pilot_user.id).all()
    assert [r.status for r in rows] == ["test"]


def test_test_digest_does_not_suppress_the_scheduled_one(client, db, pilot_user, pilot_headers, monkeypatch):
    from datetime import datetime
    from app.models.notification_preference import NotificationPreference
    from app.services.scheduler import _is_pref_due_now
    pilot_user.email = "pilot@example.test"
    db.commit()
    _fake_digest(monkeypatch)
    assert client.post("/api/notifications/send-test", headers=pilot_headers).status_code == 200
    db.expire_all()
    pref = db.query(NotificationPreference).filter(NotificationPreference.user_id == pilot_user.id).one()
    now = datetime.now()
    pref.send_time = now.strftime("%H") + ":00"
    db.commit()
    assert _is_pref_due_now(pref, now, now.strftime("%H"), db)


# --- G-3: preference validation -------------------------------------------------


@pytest.mark.parametrize("body", [
    {"send_time": "25:99"},
    {"send_time": "7:00"},
    {"send_time": "07:60"},
    {"send_time": "noon"},
    {"send_day": 9},
    {"send_day": -1},
    {"categories": ["bogus"]},
    {"categories": ["expiring_certs", "bogus"]},
])
def test_preferences_refuse_invalid_values(client, db, pilot_headers, body):
    before = client.get(PREFS_URL, headers=pilot_headers).json()
    resp = client.put(PREFS_URL, headers=pilot_headers, json=body)
    assert resp.status_code == 400, resp.text
    assert client.get(PREFS_URL, headers=pilot_headers).json() == before


def test_preferences_accept_valid_values(client, db, pilot_headers):
    resp = client.put(PREFS_URL, headers=pilot_headers, json={
        "frequency": "weekly", "send_time": "23:30", "send_day": 6,
        "categories": ["expiring_certs", "overdue_maintenance"],
    })
    assert resp.status_code == 200, resp.text
    got = client.get(PREFS_URL, headers=pilot_headers).json()
    assert got["send_time"] == "23:30" and got["send_day"] == 6
    assert got["categories"] == ["expiring_certs", "overdue_maintenance"]


# --- F-05: weather thresholds ---------------------------------------------------

@pytest.mark.parametrize("value", [
    "not json {",
    "[[[",
    "[]",
    '{"wind_sustained_go": 40, "wind_sustained_caution": 25}',
    '{"wind_sustained_go": 40}',
    '{"wind_gusts_go": 35}',
    '{"visibility_go": -5}',
    '{"visibility_go": 0.5}',
    '{"ceiling_caution": 900}',
    '{"temp_low_caution": 40}',
    '{"precip_caution": -1}',
    '{"wind_sustained_go": "fast"}',
    '{"wind_sustained_go": true}',
    '{"bogus_key": 1}',
])
def test_weather_thresholds_refuse_bad_values(client, db, admin_headers, value):
    resp = client.put(BULK_URL, headers=admin_headers, json=[{"key": "weather_thresholds", "value": value}])
    assert resp.status_code == 422, resp.text
    assert _stored(db, "weather_thresholds") is None


def test_weather_thresholds_accept_a_sound_set(client, db, admin_headers):
    value = ('{"wind_sustained_go": 10, "wind_sustained_caution": 20, "visibility_go": 5, '
             '"visibility_caution": 2, "temp_low_go": 10, "temp_low_caution": -10}')
    resp = client.put(BULK_URL, headers=admin_headers, json=[{"key": "weather_thresholds", "value": value}])
    assert resp.status_code == 200, resp.text
    assert _stored(db, "weather_thresholds") == value


# --- F-07: organization name is required ----------------------------------------

@pytest.mark.parametrize("value", ["", "   "])
def test_org_name_refuses_blank(client, db, admin_headers, value):
    db.add(Setting(key="org_name", value="Sample Unit"))
    db.commit()
    resp = client.put(BULK_URL, headers=admin_headers, json=[{"key": "org_name", "value": value}])
    assert resp.status_code == 422, resp.text
    resp = client.put("/api/settings", headers=admin_headers, json={"key": "org_name", "value": value})
    assert resp.status_code == 422, resp.text
    assert _stored(db, "org_name") == "Sample Unit"


# --- F-09: theme ids ----------------------------------------------------------------

@pytest.mark.parametrize("theme", ["zztest-<b>bogus</b>", "", "Dark"])
def test_theme_refuses_unknown_ids(client, db, pilot_user, pilot_headers, theme):
    resp = client.patch("/api/auth/me", headers=pilot_headers, json={"theme": theme})
    assert resp.status_code == 422, resp.text
    db.refresh(pilot_user)
    assert pilot_user.theme == "dark"


@pytest.mark.parametrize("theme", ["sandstone", "high-contrast", "field-sage"])
def test_theme_accepts_known_ids(client, db, pilot_headers, theme):
    resp = client.patch("/api/auth/me", headers=pilot_headers, json={"theme": theme})
    assert resp.status_code == 200, resp.text
    assert resp.json()["theme"] == theme


# --- F-12: display names must not be blank -----------------------------------------

@pytest.mark.parametrize("name", ["", "   "])
def test_user_display_name_refuses_blank(client, db, admin_headers, pilot_user, name):
    resp = client.patch(f"/api/auth/users/{pilot_user.id}", headers=admin_headers, json={"display_name": name})
    assert resp.status_code == 422, resp.text
    resp = client.patch("/api/auth/me", headers=admin_headers, json={"display_name": name})
    assert resp.status_code == 422, resp.text
    resp = client.post("/api/auth/users", headers=admin_headers, json={
        "username": "newbie", "password": "NewbiePassw0rd!", "display_name": name, "role": "viewer"})
    assert resp.status_code == 422, resp.text
    db.refresh(pilot_user)
    assert pilot_user.display_name == "Pilot"


def test_user_display_name_is_trimmed(client, db, admin_headers, pilot_user):
    resp = client.patch(f"/api/auth/users/{pilot_user.id}", headers=admin_headers, json={"display_name": "  Robin Vale  "})
    assert resp.status_code == 200, resp.text
    assert resp.json()["display_name"] == "Robin Vale"


# --- F-17: exporting the audit log is itself audited ------------------------------

def test_audit_csv_export_is_audited(client, db, admin_user, admin_headers):
    from app.models.audit_log import AuditLog
    resp = client.get("/api/export/audit/csv?date_from=2026-03-01&action=update", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    db.expire_all()
    entries = db.query(AuditLog).filter(AuditLog.action == "export", AuditLog.entity_type == "audit_log").all()
    assert len(entries) == 1
    assert entries[0].user_id == admin_user.id
    assert "date_from=2026-03-01" in entries[0].details and "action=update" in entries[0].details


# --- F-18: unmatched /api paths ------------------------------------------------------

@pytest.fixture
def spa_dir(tmp_path, monkeypatch):
    import app.main
    (tmp_path / "index.html").write_text("<div id=root></div>")
    monkeypatch.setattr(app.main, "_static_dir", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("path", ["/api/weather/current", "/api/reports/templates", "/api", "/api/"])
def test_unmatched_api_paths_are_404_json(client, spa_dir, path):
    resp = client.get(path)
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"detail": "Not Found"}


@pytest.mark.parametrize("path", ["/flights/12", "/apiary", "/settings"])
def test_app_paths_still_get_the_spa(client, spa_dir, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert "root" in resp.text


# --- G-4: explicit null clears a preference ------------------------------------------

def test_preferences_null_clears_or_resets(client, db, supervisor_headers):
    client.put(PREFS_URL, headers=supervisor_headers, json={
        "frequency": "weekly", "send_day": 3, "send_time": "18:00",
        "categories": ["expiring_certs"], "email_override": "desk@example.test"})
    resp = client.put(PREFS_URL, headers=supervisor_headers, json={
        "send_day": None, "send_time": None, "categories": None, "email_override": None})
    assert resp.status_code == 200, resp.text
    got = client.get(PREFS_URL, headers=supervisor_headers).json()
    assert got["send_day"] is None
    assert got["send_time"] == "07:00"
    assert got["email_override"] is None
    assert len(got["categories"]) == 8
    assert got["frequency"] == "weekly"


def test_preferences_leave_out_keeps(client, db, pilot_headers):
    client.put(PREFS_URL, headers=pilot_headers, json={"frequency": "weekly", "send_day": 3})
    client.put(PREFS_URL, headers=pilot_headers, json={"send_time": "08:00"})
    assert client.get(PREFS_URL, headers=pilot_headers).json()["send_day"] == 3


@pytest.mark.parametrize("field", ["enabled", "frequency"])
def test_preferences_refuse_null_on_required_fields(client, db, pilot_headers, field):
    resp = client.put(PREFS_URL, headers=pilot_headers, json={field: None})
    assert resp.status_code == 400, resp.text


# --- G-5: reminders to unknown or inactive pilots -----------------------------------

REMINDERS_URL = "/api/currency/send-reminders"


@pytest.fixture
def reminder_setup(db):
    """SMTP on, one active rule, an active lapsed pilot and an inactive one."""
    from app.models.currency_rule import CurrencyRule
    from app.models.pilot import Pilot
    db.add(Setting(key="smtp_enabled", value="true"))
    db.add(CurrencyRule(name="Monthly hour", required_hours=1, period_days=30, is_active=True))
    active = Pilot(first_name="Robin", last_name="Vale", status="active", email="robin@example.test")
    gone = Pilot(first_name="Sam", last_name="Reed", status="inactive", email="sam@example.test")
    db.add_all([active, gone])
    db.commit()
    return active, gone


def test_reminders_count_unknown_and_inactive_pilots(client, db, admin_headers, reminder_setup, monkeypatch):
    from app.services import email_digest
    active, gone = reminder_setup
    monkeypatch.setattr(email_digest, "send_email", lambda *a, **k: True)
    resp = client.post(REMINDERS_URL, headers=admin_headers,
                       json={"pilot_ids": [active.id, gone.id, 99999]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sent"] == 1
    assert body["skipped_inactive"] == 1
    assert body["not_found"] == 1


def test_reminders_to_all_report_no_unknown_or_inactive(client, db, admin_headers, reminder_setup, monkeypatch):
    from app.services import email_digest
    monkeypatch.setattr(email_digest, "send_email", lambda *a, **k: True)
    body = client.post(REMINDERS_URL, headers=admin_headers, json={}).json()
    assert body["sent"] == 1 and body["skipped_inactive"] == 0 and body["not_found"] == 0


# --- G-7: SMTP test emails are rate-limited like test digests ---------------------

def test_smtp_test_is_rate_limited(client, db, admin_user, admin_headers, monkeypatch):
    from app.services import email_digest
    admin_user.email = "admin@example.test"
    db.commit()
    monkeypatch.setattr(email_digest, "send_email", lambda *a, **k: True)
    codes = [client.post("/api/settings/smtp/test", headers=admin_headers).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
