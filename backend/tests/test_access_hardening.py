"""Authority deletion rules, token scope paths, proxy trust and digest recipients."""

import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.config import settings
from app.models import AuditLog, Document, NotificationPreference, OperatingAuthority, Setting, User
from app.routers import auth as auth_router
from app.services import scheduler

AUTHORITY_URL = "/api/operating-authorities"
AUDIT_CSV = "/api/export/audit/csv"
HASH = "ab" * 32


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _authority(db):
    a = OperatingAuthority(authority_type="coa", title="Blanket COA", record_status="active", grounds_unit=True)
    db.add(a)
    db.commit()
    return a


def _document(db, authority, tmp_path, name="coa.pdf", **kwargs):
    stored = tmp_path / name
    stored.write_bytes(b"%PDF-1.4 test")
    doc = Document(
        entity_type="operating_authority", entity_id=authority.id, document_type="faa_authorization",
        title=name, filename=name, file_path=str(stored), mime_type="application/pdf",
        file_size_bytes=stored.stat().st_size, sha256=HASH, **kwargs,
    )
    db.add(doc)
    db.commit()
    return doc


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def supervisor_headers(supervisor_user):
    from app.routers.auth import create_token
    return _bearer(create_token(supervisor_user.id))


def _make_token(client, admin_headers, **overrides):
    payload = {"name": "t", "read_only": True, **overrides}
    resp = client.post("/api/api-tokens", headers=admin_headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


# Authority deletion ----------------------------------------------------------

def test_supervisor_can_delete_authority_with_no_documents(client, db, supervisor_headers):
    a = _authority(db)

    assert client.delete(f"{AUTHORITY_URL}/{a.id}", headers=supervisor_headers).status_code == 200


@pytest.mark.parametrize("soft_deleted", [False, True])
def test_supervisor_refused_with_documents(client, db, supervisor_headers, upload_dir, soft_deleted):
    a = _authority(db)
    deleted_at = datetime.now(timezone.utc) if soft_deleted else None
    _document(db, a, upload_dir, deleted_at=deleted_at)

    resp = client.delete(f"{AUTHORITY_URL}/{a.id}", headers=supervisor_headers)

    assert resp.status_code == 403
    assert db.query(OperatingAuthority).count() == 1
    assert db.query(Document).count() == 1


def test_admin_delete_logs_each_document_with_hash(client, db, admin_headers, upload_dir):
    a = _authority(db)
    _document(db, a, upload_dir, "one.pdf")
    _document(db, a, upload_dir, "two.pdf", deleted_at=datetime.now(timezone.utc))

    assert client.delete(f"{AUTHORITY_URL}/{a.id}", headers=admin_headers).status_code == 200

    db.expire_all()
    entries = db.query(AuditLog).filter_by(entity_type="document", action="delete").all()
    assert len(entries) == 2
    for entry in entries:
        assert HASH in (entry.details or "")
    assert {e.entity_name for e in entries} == {"one.pdf", "two.pdf"}


def test_legal_hold_blocks_authority_delete_for_admin(client, db, admin_headers, upload_dir):
    a = _authority(db)
    _document(db, a, upload_dir, legal_hold=True)

    assert client.delete(f"{AUTHORITY_URL}/{a.id}", headers=admin_headers).status_code == 409
    assert db.query(OperatingAuthority).count() == 1


def test_legal_hold_blocks_supervisor_with_conflict(client, db, supervisor_headers, upload_dir):
    a = _authority(db)
    _document(db, a, upload_dir, legal_hold=True)

    assert client.delete(f"{AUTHORITY_URL}/{a.id}", headers=supervisor_headers).status_code == 409


# Token scope paths -----------------------------------------------------------

def test_scope_check_uses_routed_path(client, admin_headers):
    token = _make_token(client, admin_headers, scopes=["fleet"])

    resp = client.get("/api/settings", headers={**_bearer(token), "Host": "x/api/vehicles"})

    assert resp.status_code == 403


@pytest.mark.parametrize("scopes", [["reports"], None])
@pytest.mark.parametrize("url", [AUDIT_CSV, "/api/audit"])
def test_audit_scope_required_for_audit_routes(client, admin_headers, scopes, url):
    token = _make_token(client, admin_headers, scopes=scopes)

    assert client.get(url, headers=_bearer(token)).status_code == 403


@pytest.mark.parametrize("url", [AUDIT_CSV, "/api/audit"])
def test_audit_scoped_admin_token_reads_audit(client, admin_headers, url):
    token = _make_token(client, admin_headers, scopes=["audit"])

    assert client.get(url, headers=_bearer(token)).status_code == 200


def test_audit_scope_does_not_reach_other_areas(client, admin_headers):
    token = _make_token(client, admin_headers, scopes=["audit"])

    assert client.get("/api/vehicles", headers=_bearer(token)).status_code == 403


def test_reports_scope_keeps_other_exports(client, admin_headers):
    token = _make_token(client, admin_headers, scopes=["reports"])

    resp = client.get("/api/export/vehicles/csv", headers=_bearer(token))

    assert resp.status_code != 403


# Client address --------------------------------------------------------------

def _req(peer, headers=None):
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers={k.lower(): v for k, v in (headers or {}).items()})


def test_default_trusts_no_proxy():
    req = _req("192.168.0.5", {"CF-Connecting-IP": "198.51.100.7"})

    assert auth_router._client_ip(req) == "192.168.0.5"


def test_named_proxy_is_trusted(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "192.168.0.5")
    req = _req("192.168.0.5", {"CF-Connecting-IP": "198.51.100.7"})

    assert auth_router._client_ip(req) == "198.51.100.7"


@pytest.mark.parametrize("header", ["CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP"])
def test_header_value_must_be_an_ip(monkeypatch, header):
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "192.168.0.5")
    req = _req("192.168.0.5", {header: "not-an-ip<script>"})

    assert auth_router._client_ip(req) == "192.168.0.5"


def test_warns_once_when_proxy_headers_arrive_untrusted(caplog, monkeypatch):
    monkeypatch.setattr(auth_router, "_warned_untrusted_proxy", False)
    req = _req("192.168.0.5", {"X-Forwarded-For": "198.51.100.7"})

    with caplog.at_level(logging.WARNING, logger=auth_router.logger.name):
        auth_router._client_ip(req)
        auth_router._client_ip(req)

    warnings = [r for r in caplog.records if "TRUSTED_PROXIES" in r.getMessage()]
    assert len(warnings) == 1


def test_no_warning_without_forwarding_headers(caplog, monkeypatch):
    monkeypatch.setattr(auth_router, "_warned_untrusted_proxy", False)

    with caplog.at_level(logging.WARNING, logger=auth_router.logger.name):
        auth_router._client_ip(_req("192.168.0.5"))

    assert not [r for r in caplog.records if "TRUSTED_PROXIES" in r.getMessage()]


# Digest recipients -----------------------------------------------------------

@pytest.fixture
def digest_recipients(_engines, monkeypatch):
    sent = []
    monkeypatch.setattr(scheduler, "SessionLocal", _engines[0])
    monkeypatch.setattr(scheduler, "_is_pref_due_now", lambda pref, now, hour, session: True)
    monkeypatch.setattr(scheduler, "_send_user_digest", lambda pref, session: sent.append(pref.user_id))
    return sent


def _digest_user(db, active):
    db.add(Setting(key="smtp_enabled", value="true"))
    user = User(username="digest", display_name="Digest", password_hash="x", email="d@example.com",
                role="viewer", is_active=active)
    db.add(user)
    db.commit()
    db.add(NotificationPreference(user_id=user.id, enabled=True, frequency="daily"))
    db.commit()
    return user


def test_digest_skips_inactive_user(db, digest_recipients):
    user = _digest_user(db, active=False)

    scheduler._run_digest_job()

    assert digest_recipients == []
    assert db.query(NotificationPreference).filter_by(user_id=user.id).count() == 1


def test_reactivated_user_gets_digest(db, digest_recipients):
    user = _digest_user(db, active=False)
    scheduler._run_digest_job()
    user.is_active = True
    db.commit()

    scheduler._run_digest_job()

    assert digest_recipients == [user.id]
