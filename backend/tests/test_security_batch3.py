"""Batch 3 hardening: request body limits, markup injection in reports and the
digest email, SMTP transport, audit coverage, the pilot export, test-send
limits, and the Skydio client's handling of page links and Retry-After."""

import io
import ssl
from typing import ClassVar

import httpx
import pytest
from PIL import Image

from app.config import settings
from app.integrations.base import ProviderCredentials
from app.integrations.skydio import SkydioProvider
from app.models.audit_log import AuditLog
from app.models.setting import Setting
from app.models.user import User
from app.routers.auth import create_token
from app.services import email_digest
from tests.conftest import _seed_user

SUPERVISOR_PASSWORD = "SupervisorPassw0rd!"


def _bearer(user):
    return {"Authorization": f"Bearer {create_token(user.id, user.token_version)}"}


def _audit(db, entity_type, action=None):
    q = db.query(AuditLog).filter(AuditLog.entity_type == entity_type)
    if action:
        q = q.filter(AuditLog.action == action)
    return q.order_by(AuditLog.id).all()


@pytest.fixture
def supervisor_user(db):
    return _seed_user(db, username="sup", role="supervisor", password=SUPERVISOR_PASSWORD)


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr("app.routers.photos.UPLOAD_DIR", str(tmp_path / "photos"))
    return tmp_path


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="PNG")
    return buf.getvalue()


# 1. Request bodies are capped before anything reads them --------------------

def test_declared_oversize_body_is_refused_with_413(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 10)
    resp = client.post("/api/auth/login", content=b"x" * (2 * 1024 * 1024),
                       headers={"content-type": "application/json"})
    assert resp.status_code == 413
    assert resp.headers.get("x-request-id")


def test_streamed_oversize_body_is_cut_off_with_413(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 10)

    def chunks():
        for _ in range(40):
            yield b"y" * 65536

    resp = client.post("/api/auth/login", content=chunks(), headers={"content-type": "application/json"})
    assert resp.status_code == 413


def test_ordinary_request_is_untouched(client, admin_user):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-Passw0rd"})
    assert resp.status_code == 401


def test_backup_import_refuses_an_anonymous_caller_before_parsing_the_body(client, admin_user):
    """A declared File() parameter made FastAPI read the whole upload first, so a
    malformed body got a 422 from the parser before the caller was checked."""
    resp = client.post("/api/backup/import", data={"not_file": "x"})
    assert resp.status_code == 401


def test_backup_import_without_a_file_is_a_400_for_an_admin(client, admin_user):
    resp = client.post("/api/backup/import", headers=_bearer(admin_user), data={"not_file": "x"})
    assert resp.status_code == 400


# 2. Report PDFs treat data as text ---------------------------------------------

def test_report_pdf_renders_values_that_look_like_markup():
    from app.routers.reports import ReportConfig, _render_report_pdf
    data = {
        "title": "Flights <b>& more",
        "summary": {"top_pilot": "O'Neil <Sons> & Co"},
        "columns": ["Pilot <x>"],
        "rows": [{"pilot": "<font name='x'>unclosed"}],
    }
    pdf = _render_report_pdf(data, ReportConfig(report_type="flight_summary"), "Unit <i>", None)
    assert pdf.getvalue().startswith(b"%PDF")


def test_report_images_cannot_come_from_the_network():
    from reportlab import rl_config
    import app.routers.reports  # noqa: F401 - applies the setting
    assert rl_config.trustedHosts
    assert not {"http", "https", "ftp"} & set(rl_config.trustedSchemes)


# 3. Digest email escapes and verifies the server -----------------------------

def test_digest_html_escapes_names_and_item_values():
    user = User(username="u", display_name="<script>alert(1)</script>", role="pilot")
    sections = {"expiring_certs": [{"id": 1, "pilot": "<img src=x onerror=alert(1)>"}]}
    html = email_digest.render_digest_html(sections, user, "<b>Unit</b>")
    assert "<script>" not in html
    assert "<img" not in html
    assert "<b>Unit</b>" not in html
    assert "&lt;script&gt;" in html


class _FakeSMTP:
    instances: ClassVar[list] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.timeout, self.context, self.tls_context = timeout, context, None
        _FakeSMTP.instances.append(self)

    def starttls(self, context=None):
        self.tls_context = context

    def login(self, *_):
        pass

    def sendmail(self, *_):
        pass

    def quit(self):
        pass


def _smtp_settings(db, port):
    for key, value in (("smtp_host", "mail.example.org"), ("smtp_port", str(port)),
                       ("smtp_from_address", "unit@example.org"), ("smtp_tls", "true")):
        db.add(Setting(key=key, value=value))
    db.commit()


@pytest.mark.parametrize("port,attr", [(587, "tls_context"), (465, "context")])
def test_smtp_verifies_the_certificate_and_times_out(db, monkeypatch, port, attr):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(email_digest.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(email_digest.smtplib, "SMTP_SSL", _FakeSMTP)
    _smtp_settings(db, port)
    assert email_digest.send_email("a@example.org", "s", "<p>x</p>", db)
    server = _FakeSMTP.instances[-1]
    assert server.timeout == 30
    context = getattr(server, attr)
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname


# 4. Changes leave a trail ------------------------------------------------------

def test_bulk_settings_audit_names_keys_but_never_values(client, db, admin_user):
    resp = client.put("/api/settings/bulk", headers=_bearer(admin_user), json=[
        {"key": "smtp_password", "value": "hunter2-secret"},
        {"key": "org_name", "value": "Test Unit"},
    ])
    assert resp.status_code == 200
    entries = _audit(db, "setting", "update")
    assert len(entries) == 1
    assert "smtp_password" in entries[0].details
    assert "org_name" in entries[0].details
    assert "hunter2-secret" not in entries[0].details


def test_logo_upload_is_audited(client, db, admin_user, upload_dir):
    resp = client.post("/api/settings/logo", headers=_bearer(admin_user),
                       files={"file": ("logo.png", _png_bytes(), "image/png")})
    assert resp.status_code == 200
    assert _audit(db, "setting", "update")


def test_document_upload_and_edit_are_audited(client, db, pilot_user, upload_dir):
    resp = client.post("/api/documents/upload", headers=_bearer(pilot_user),
                       data={"entity_type": "general", "document_type": "other", "title": "Warrant"},
                       files={"file": ("w.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert resp.status_code == 200
    doc_id = resp.json()["id"]
    assert [e.entity_id for e in _audit(db, "document", "upload")] == [doc_id]

    client.patch(f"/api/documents/{doc_id}", headers=_bearer(pilot_user), json={"title": "Warrant v2"})
    change = _audit(db, "document", "update")[0].changes
    assert change["title"] == {"old": "Warrant", "new": "Warrant v2"}


def test_photo_upload_edit_and_links_are_audited(client, db, pilot_user, supervisor_user, upload_dir):
    from datetime import date
    from app.models.flight import Flight
    resp = client.post("/api/photos/upload", headers=_bearer(pilot_user),
                       files={"file": ("scene.png", _png_bytes(), "image/png")})
    assert resp.status_code == 200
    photo_id = resp.json()["id"]
    assert _audit(db, "photo", "upload")

    client.patch(f"/api/photos/{photo_id}", headers=_bearer(pilot_user), data={"title": "Scene A"})
    assert _audit(db, "photo", "update")[0].changes["title"]["new"] == "Scene A"

    flight = Flight(date=date(2026, 9, 1))
    db.add(flight)
    db.commit()
    client.post(f"/api/photos/{photo_id}/flight/{flight.id}", headers=_bearer(supervisor_user))
    client.delete(f"/api/photos/{photo_id}/flight/{flight.id}", headers=_bearer(supervisor_user))
    assert [e.action for e in _audit(db, "photo") if e.action in ("link", "unlink")] == ["link", "unlink"]


def test_folder_changes_are_audited(client, db, pilot_user):
    folder_id = client.post("/api/folders", headers=_bearer(pilot_user), json={"name": "Case 12"}).json()["id"]
    client.patch(f"/api/folders/{folder_id}", headers=_bearer(pilot_user), json={"name": "Case 12A"})
    client.delete(f"/api/folders/{folder_id}", headers=_bearer(pilot_user))
    assert [e.action for e in _audit(db, "folder")] == ["create", "update", "delete"]


def test_maintenance_schedule_changes_are_audited(client, db, pilot_user):
    url = "/api/maintenance/schedules"
    sid = client.post(url, headers=_bearer(pilot_user), json={
        "name": "Annual audit", "entity_type": "organization", "entity_id": None, "frequency": "yearly",
    }).json()["id"]
    client.patch(f"{url}/{sid}", headers=_bearer(pilot_user), json={"name": "Annual review"})
    client.post(f"{url}/{sid}/complete", headers=_bearer(pilot_user))
    client.delete(f"{url}/{sid}", headers=_bearer(pilot_user))
    assert [e.action for e in _audit(db, "maintenance_schedule")] == ["create", "update", "complete", "delete"]


def test_own_profile_edit_is_audited_but_theme_is_not(client, db, pilot_user):
    client.patch("/api/auth/me", headers=_bearer(pilot_user), json={"theme": "dark"})
    assert not _audit(db, "user", "update")
    client.patch("/api/auth/me", headers=_bearer(pilot_user), json={"display_name": "Pilot One"})
    assert _audit(db, "user", "update")[0].changes["display_name"]["new"] == "Pilot One"


def test_initial_setup_is_audited(client, db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    from app.routers.backup import _install_token_path
    with open(_install_token_path(), "w") as f:
        f.write("setup-token")
    resp = client.post("/api/auth/setup", headers={"X-Install-Token": "setup-token"},
                       json={"username": "founder", "password": "FounderPassw0rd!"})
    assert resp.status_code == 200
    assert _audit(db, "user", "setup")


# 5. Bulk personal data and outbound mail ---------------------------------------

def test_pilot_roster_export_is_supervisor_only_and_audited(client, db, pilot_user, supervisor_user):
    assert client.get("/api/export/pilots/csv", headers=_bearer(pilot_user)).status_code == 403
    assert client.get("/api/export/pilots/csv", headers=_bearer(supervisor_user)).status_code == 200
    assert _audit(db, "pilot", "export")


def test_test_digest_sends_are_rate_limited(client, db, pilot_user, monkeypatch):
    pilot_user.email = "pilot@example.org"
    db.commit()
    monkeypatch.setattr(email_digest, "build_digest", lambda db, user: {"expiring_certs": [{"id": 1, "x": "y"}]})
    monkeypatch.setattr(email_digest, "send_email", lambda *a, **k: True)
    codes = [client.post("/api/notifications/send-test", headers=_bearer(pilot_user)).status_code
             for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    assert len(_audit(db, "notification", "send_test")) == 3


def test_digest_redirect_address_is_audited(client, db, pilot_user):
    client.put("/api/notifications/preferences", headers=_bearer(pilot_user),
               json={"email_override": "someone@elsewhere.example"})
    entries = _audit(db, "notification_preference", "update")
    assert entries
    assert "someone@elsewhere.example" in entries[0].details


# 6. Skydio client ---------------------------------------------------------------

CREDS = ProviderCredentials(api_token="t", token_id="id")


class _Resp:
    def __init__(self, body):
        self._body, self.status_code = body, 200

    def json(self):
        return self._body


@pytest.mark.parametrize("link", [
    "https://collector.example/steal?page=2",
    "http://api.skydio.com/api/v0/flights?page=2",
    "https://api.skydio.com.evil.example/api/v0/flights",
])
def test_pagination_does_not_follow_links_off_the_skydio_api(link):
    provider = SkydioProvider()
    urls = []

    def fake_request(method, url, creds, params=None, timeout=30.0):
        urls.append(url)
        return _Resp({"data": [{"id": len(urls)}], "next": link})

    provider._request = fake_request
    assert provider._paginate("https://api.skydio.com/api/v0/flights", CREDS) == [{"id": 1}]
    assert urls == ["https://api.skydio.com/api/v0/flights"]


def test_pagination_still_follows_skydio_links():
    provider = SkydioProvider()
    pages = iter([
        _Resp({"data": [{"id": 1}], "next": "https://api.skydio.com/api/v0/flights?cursor=2"}),
        _Resp({"data": [{"id": 2}]}),
    ])
    provider._request = lambda method, url, creds, params=None, timeout=30.0: next(pages)
    assert provider._paginate("https://api.skydio.com/api/v0/flights", CREDS) == [{"id": 1}, {"id": 2}]


@pytest.mark.parametrize("header,expected", [
    ("86400", 60.0),
    ("Wed, 21 Oct 2026 07:28:00 GMT", 5.0),
    ("2", 2.0),
])
def test_retry_after_is_bounded(monkeypatch, header, expected):
    responses = iter([
        httpx.Response(429, headers={"Retry-After": header}),
        httpx.Response(200, json={"ok": True}),
    ])
    transport = httpx.MockTransport(lambda request: next(responses))
    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=transport, **kw))
    sleeps = []
    monkeypatch.setattr("app.integrations.skydio.time.sleep", sleeps.append)

    resp = SkydioProvider()._request("GET", "https://api.skydio.com/api/v0/whoami", CREDS)
    assert resp.status_code == 200
    assert sleeps == [expected]
