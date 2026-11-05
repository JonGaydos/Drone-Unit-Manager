"""Escaping, numeric feed values, credential trimming, fixed error text,
CSV guarding and fixed status choices."""

import csv
import io
import logging
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

import app.routers.adsb as adsb
from app.models import CertificationType, PilotCertification
from app.models.battery import Battery
from app.models.flight_approval import FlightPlan
from app.models.incident import Incident
from app.models.mission_log import MissionLog
from app.models.pilot import Pilot
from app.models.setting import Setting
from app.models.vehicle import Vehicle
from app.routers.currency import _reminder_html
from app.routers.export import _csv_safe
from app.services import sync_manager
from app.services.sync_manager import SyncManager

FORMULA = "=HYPERLINK(\"http://x\")"
TOKEN = "tok-SECRET-123456"
INCIDENTS_URL = "/api/incidents"
MISSIONS_URL = "/api/mission-logs"
SETTINGS_URL = "/api/settings"


def _incident_body(**over):
    body = {"date": "2026-01-02", "title": "T", "severity": "minor", "category": "other",
            "description": "d"}
    body.update(over)
    return body


def _seed(db, *rows):
    db.add_all(rows)
    db.commit()
    for r in rows:
        db.refresh(r)
    return rows


# ---- reminder email -------------------------------------------------------

def test_reminder_html_escapes_all_text():
    pilot = SimpleNamespace(first_name="<b>Al</b>", full_name="x")
    rules = [{"rule_name": "<img src=x>", "actual_hours": "<i>1</i>",
              "required_hours": "<u>2</u>", "period_days": "<s>3</s>"}]
    html = _reminder_html(pilot, rules, "<script>org</script>", "<a href=x>intro</a>")
    for raw in ("<b>Al", "<img", "<i>1", "<u>2", "<s>3", "<script>", "<a href"):
        assert raw not in html
    assert "&lt;script&gt;org" in html


# ---- ADS-B ----------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_adsb_cache():
    adsb._cache = {"data": None, "timestamp": 0, "key": ""}
    yield
    adsb._cache = {"data": None, "timestamp": 0, "key": ""}


@pytest.mark.parametrize("raw,expected", [
    ("45);evil", None), (180.5, 180.5), (None, None), (True, None), ("90", None),
])
def test_adsb_non_numeric_track_becomes_none(client, admin_headers, mock_httpx, raw, expected):
    ac = [{"hex": "abc", "lat": 30.0, "lon": -86.0, "track": raw}]
    mock_httpx(lambda request: httpx.Response(200, json={"ac": ac}))
    r = client.get("/api/adsb/nearby", params={"lat": 30, "lon": -86, "radius_nm": 50},
                   headers=admin_headers)
    assert r.json()["aircraft"][0]["track"] == expected


# ---- credentials ----------------------------------------------------------

def _stored(db, key):
    db.expire_all()
    return db.query(Setting).filter(Setting.key == key).first().value


def test_credentials_trimmed_on_save(client, db, admin_headers):
    r = client.put(SETTINGS_URL, json={"key": "skydio_api_token", "value": f"  {TOKEN}\n"},
                   headers=admin_headers)
    assert r.status_code == 200
    assert _stored(db, "skydio_api_token") == TOKEN
    r = client.put(f"{SETTINGS_URL}/bulk", headers=admin_headers, json=[
        {"key": "skydio_token_id", "value": " id-1 \n"},
        {"key": "smtp_password", "value": "\tpw "},
        {"key": "smtp_username", "value": " user "},
        {"key": "org_name", "value": " Unit "},
    ])
    assert r.status_code == 200
    assert _stored(db, "skydio_token_id") == "id-1"
    assert _stored(db, "smtp_password") == "\tpw "
    assert _stored(db, "smtp_username") == " user "
    assert _stored(db, "org_name") == " Unit "


# ---- fixed sync error text -----------------------------------------------

def test_sync_error_stores_fixed_message(db, caplog, monkeypatch):
    db.add_all([Setting(key="skydio_api_token", value=TOKEN), Setting(key="skydio_token_id", value="i")])
    db.commit()
    boom = RuntimeError(f"request failed with header X-Api-Token: {TOKEN}")
    provider = MagicMock()
    for name in ("sync_users", "sync_vehicles", "sync_flights", "sync_batteries",
                 "sync_controllers", "sync_docks", "sync_sensors", "sync_attachments"):
        getattr(provider, name).side_effect = boom
    monkeypatch.setattr(sync_manager, "get_provider", lambda name: provider)
    with caplog.at_level(logging.DEBUG):
        result = SyncManager.sync_all("skydio", db)
    assert result.errors
    assert all(e.endswith(": RuntimeError") for e in result.errors)
    stored = _stored(db, "last_sync_result")
    assert TOKEN not in stored
    assert all(TOKEN not in e for e in result.errors)
    assert TOKEN not in caplog.text


def test_connection_failure_message_is_fixed(db, caplog, monkeypatch):
    db.add(Setting(key="skydio_api_token", value=TOKEN))
    db.commit()
    provider = MagicMock()
    provider.validate_credentials.side_effect = RuntimeError(TOKEN)
    monkeypatch.setattr(sync_manager, "get_provider", lambda name: provider)
    ok, message, _ = SyncManager.test_connection("skydio", db)
    assert not ok
    assert TOKEN not in message
    assert TOKEN not in caplog.text


# ---- CSV guard -------------------------------------------------------------

def test_csv_guard_covers_leading_newline():
    assert _csv_safe("\n=1+1") == "'\n=1+1"
    assert _csv_safe("plain") == "plain"


def test_csv_guard_covers_spaced_formula():
    assert _csv_safe(" =1+1") == "' =1+1"
    assert _csv_safe("  @cmd") == "'  @cmd"
    assert _csv_safe(" hello") == " hello"
    assert _csv_safe("   ") == "   "


def test_reminder_subject_collapses_whitespace(monkeypatch):
    from app.routers.currency import _send_one_reminder
    import app.services.email_digest as ed
    sent = {}
    monkeypatch.setattr(ed, "send_email", lambda to, subj, html, db: sent.update(subject=subj) or True)
    monkeypatch.setattr("app.routers.currency._evaluate_currency", lambda rules, flights: [{
        "is_current": False, "rule_name": "r", "actual_hours": 0, "required_hours": 1, "period_days": 30}])
    pilot = SimpleNamespace(first_name="A", full_name="A B", email="a@x.org")
    assert _send_one_reminder(pilot, [], [], "Unit\r\nBcc: evil@x.org", "", None)[0] == "sent"
    assert "\n" not in sent["subject"]
    assert "\r" not in sent["subject"]
    assert sent["subject"].endswith("Unit Bcc: evil@x.org")


def test_fixed_error_adds_http_status_only():
    from app.services.sync_manager import _fixed_error
    request = httpx.Request("GET", "https://api.example.test/secret-path")
    exc = httpx.HTTPStatusError("boom token", request=request,
                                response=httpx.Response(401, text="secret body", request=request))
    out = _fixed_error("Users sync error", exc)
    assert out == "Users sync error: HTTPStatusError 401"
    assert _fixed_error("X", RuntimeError("t")) == "X: RuntimeError"


def _seed_pilot(db):
    _seed(db, Pilot(first_name=FORMULA, last_name=FORMULA, status=FORMULA, badge_number=FORMULA, notes=FORMULA))


def _seed_vehicle(db):
    _seed(db, Vehicle(serial_number=FORMULA, manufacturer=FORMULA, model=FORMULA, status=FORMULA))


def _seed_incident(db):
    _seed(db, Incident(date=date(2026, 1, 1), title=FORMULA, severity=FORMULA, category=FORMULA,
                       description=FORMULA, status=FORMULA, report_type=FORMULA))


def _seed_mission(db):
    _seed(db, MissionLog(date=date(2026, 1, 1), title=FORMULA, status=FORMULA))


def _seed_plan(db):
    pilot, = _seed(db, Pilot(first_name="a", last_name="b"))
    _seed(db, FlightPlan(title=FORMULA, date_planned=datetime(2026, 1, 1), status=FORMULA,
                         pilot_id=pilot.id, submitted_by_id=1))


def _seed_cert(db):
    pilot, ctype = _seed(db, Pilot(first_name="a", last_name="b")), _seed(db, CertificationType(name="C", category="faa"))
    _seed(db, PilotCertification(pilot_id=pilot[0].id, certification_type_id=ctype[0].id, status=FORMULA))


def _seed_battery(db):
    _seed(db, Battery(serial_number=FORMULA, status=FORMULA))


EXPORTS = [
    ("pilots", _seed_pilot), ("vehicles", _seed_vehicle), ("incidents", _seed_incident),
    ("mission-logs", _seed_mission), ("flight-plans", _seed_plan),
    ("certifications", _seed_cert), ("fleet/batteries", _seed_battery),
]


@pytest.mark.parametrize("name,seed", EXPORTS)
def test_every_text_column_guarded(client, db, admin_headers, name, seed):
    seed(db)
    resp = client.get(f"/api/export/{name}/csv", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    rows = list(csv.reader(io.StringIO(resp.text)))[1:]
    assert rows
    cells = [c for row in rows for c in row]
    assert FORMULA in "".join(c.lstrip("'") for c in cells)
    assert not [c for c in cells if c.startswith(("=", "+", "-", "@", "\t", "\r", "\n"))]


# ---- fixed choices ---------------------------------------------------------

@pytest.mark.parametrize("field,bad", [
    ("severity", "low"), ("report_type", "other"),
])
def test_status_choices_enforced_on_write_incident_create(client, admin_headers, field, bad):
    r = client.post(INCIDENTS_URL, json=_incident_body(**{field: bad}), headers=admin_headers)
    assert r.status_code == 422


@pytest.mark.parametrize("field,bad", [
    ("severity", "low"), ("status", "pending"), ("report_type", "other"),
])
def test_status_choices_enforced_on_write_incident_update(client, admin_headers, field, bad):
    created = client.post(INCIDENTS_URL, json=_incident_body(), headers=admin_headers).json()
    r = client.patch(f"{INCIDENTS_URL}/{created['id']}", json={field: bad}, headers=admin_headers)
    assert r.status_code == 422
    ok = {"severity": "critical", "status": "closed", "report_type": "success"}[field]
    assert client.patch(f"{INCIDENTS_URL}/{created['id']}", json={field: ok},
                        headers=admin_headers).status_code == 200


def test_status_choices_enforced_on_write_mission(client, admin_headers):
    body = {"date": "2026-01-02", "title": "M"}
    assert client.post(MISSIONS_URL, json={**body, "status": "bogus"}, headers=admin_headers).status_code == 422
    made = client.post(MISSIONS_URL, json={**body, "status": "planned"}, headers=admin_headers)
    assert made.status_code == 200
    url = f"{MISSIONS_URL}/{made.json()['id']}"
    assert client.patch(url, json={"status": "bogus"}, headers=admin_headers).status_code == 422
    assert client.patch(url, json={"status": "cancelled"}, headers=admin_headers).status_code == 200


def test_legacy_value_displays_and_exports(client, db, admin_headers):
    _seed(db, Incident(date=date(2026, 1, 1), title="Old", severity="low", category="other",
                       description="d", status="pending", report_type="incident"),
          MissionLog(date=date(2026, 1, 1), title="Old", status="active"))
    inc = client.get(INCIDENTS_URL, headers=admin_headers).json()
    items = inc["items"] if isinstance(inc, dict) else inc
    assert items[0]["severity"] == "low"
    assert client.get(MISSIONS_URL, headers=admin_headers).json()[0]["status"] == "active"
    text = client.get("/api/export/incidents/csv", headers=admin_headers).text
    assert "low" in text
    assert "pending" in text


def test_edit_leaving_legacy_value_saves(client, db, admin_headers):
    inc, mission = _seed(
        db,
        Incident(date=date(2026, 1, 1), title="Old", severity="low", category="other",
                 description="d", status="pending", report_type="incident"),
        MissionLog(date=date(2026, 1, 1), title="Old", status="active"))
    r = client.patch(f"{INCIDENTS_URL}/{inc.id}", headers=admin_headers,
                     json={"severity": "low", "status": "pending", "title": "New"})
    assert r.status_code == 200
    assert r.json()["title"] == "New"
    assert r.json()["severity"] == "low"
    r = client.patch(f"{MISSIONS_URL}/{mission.id}", json={"status": "active", "title": "New"},
                     headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "active"
    assert client.patch(f"{INCIDENTS_URL}/{inc.id}", json={"severity": "bogus"},
                        headers=admin_headers).status_code == 422


def test_incident_create_refuses_an_unknown_status(client, admin_headers):
    body = {"date": "2026-01-02", "title": "zz", "severity": "minor", "category": "other",
            "description": "zz", "status": "not-a-status"}
    resp = client.post("/api/incidents", headers=admin_headers, json=body)
    assert resp.status_code == 422
    assert "status must be one of" in resp.json()["detail"]


def test_incident_create_still_starts_open(client, admin_headers):
    body = {"date": "2026-01-02", "title": "zz", "severity": "minor", "category": "other",
            "description": "zz", "status": "resolved"}
    resp = client.post("/api/incidents", headers=admin_headers, json=body)
    assert resp.status_code == 200
    assert resp.json()["status"] == "open"
