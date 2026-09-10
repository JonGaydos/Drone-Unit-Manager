"""Authentication and authorization tests.

Covers login success/failure, the unknown-user timing-equalized 401 path (a real
past incident produced a 500 here), token-protected routes, and admin role
gating on a real admin-only endpoint (GET /api/audit).
"""

import os

from tests.conftest import ADMIN_PASSWORD, PILOT_PASSWORD

from app.config import settings as app_settings
from app.models.user import User
from app.models.flight import FlightPurpose
from app.models.folder import Folder
from app.routers.backup import _install_token_path

LOGIN_URL = "/api/auth/login"
ME_URL = "/api/auth/me"
AUDIT_URL = "/api/audit"
SETUP_URL = "/api/auth/setup"
SETUP_REQUIRED_URL = "/api/auth/setup-required"
RECOVERY_PASSWORD = "Recovered1Passw0rd!"
INSTALL_TOKEN = "recovery-install-token"


def _seed_blank_hash_user(db, username, role):
    """Insert a user whose password_hash is blank, mimicking a restored backup
    (backup redacts every hash), so no one can log in."""
    db.add(User(username=username, password_hash="", display_name=username.title(),
                role=role, is_active=True))
    db.commit()


def _arm_install_token(monkeypatch, tmp_path, token=INSTALL_TOKEN):
    """Point DATA_DIR at tmp and write an install token file, so recovery
    reactivation (which the endpoint gates on that token) can succeed."""
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    with open(_install_token_path(), "w") as f:
        f.write(token)
    return {"X-Install-Token": token}


def _install_token_path_exists():
    return os.path.exists(_install_token_path())


def test_login_correct_credentials_returns_token(client, admin_user):
    resp = client.post(LOGIN_URL, json={"username": "admin", "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token"]
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "admin"


def test_login_wrong_password_returns_401(client, admin_user):
    resp = client.post(LOGIN_URL, json={"username": "admin", "password": "WrongPassw0rd!"})
    assert resp.status_code == 401, resp.text


def test_login_unknown_user_returns_401_not_500(client):
    # The missing-user branch runs a dummy bcrypt verify and writes a
    # login_failed audit row before committing. A column-default mismatch on
    # that path previously produced a 500; assert it is a clean 401.
    resp = client.post(LOGIN_URL, json={"username": "ghost", "password": "WhateverPass1"})
    assert resp.status_code == 401, resp.text
    assert resp.status_code != 500


def test_unknown_user_login_writes_failed_audit_row(client, db):
    from app.models.audit_log import AuditLog

    client.post(LOGIN_URL, json={"username": "ghost", "password": "WhateverPass1"})
    rows = db.query(AuditLog).filter(AuditLog.action == "login_failed").all()
    assert len(rows) == 1
    assert rows[0].entity_type == "auth"


def test_protected_route_requires_token(client, admin_user):
    assert client.get(ME_URL).status_code == 401


def test_protected_route_with_valid_token(client, admin_headers):
    resp = client.get(ME_URL, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["username"] == "admin"


def test_admin_endpoint_rejects_pilot(client, pilot_headers):
    resp = client.get(AUDIT_URL, headers=pilot_headers)
    assert resp.status_code == 403, resp.text


def test_admin_endpoint_allows_admin(client, admin_headers):
    resp = client.get(AUDIT_URL, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert "logs" in resp.json()


# --- setup / fresh-install restore lockout recovery -------------------------

def test_setup_required_true_on_empty_install(client, db):
    body = client.get(SETUP_REQUIRED_URL).json()
    assert body["setup_required"] is True
    assert body["recovery"] is False


def test_setup_required_false_with_active_admin(client, admin_user):
    body = client.get(SETUP_REQUIRED_URL).json()
    assert body["setup_required"] is False
    assert body["recovery"] is False


def test_setup_required_recovery_when_all_hashes_blank(client, db):
    """A restored backup leaves users with blank hashes (no usable login). Setup
    must reopen in recovery mode instead of silently locking the operator out."""
    _seed_blank_hash_user(db, "chief", "admin")
    body = client.get(SETUP_REQUIRED_URL).json()
    assert body["setup_required"] is True
    assert body["recovery"] is True


def test_initial_setup_creates_admin_and_seeds_defaults(client, db, tmp_path, monkeypatch):
    # Isolate DATA_DIR so the fresh-install token retirement stays in tmp.
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    resp = client.post(SETUP_URL, json={
        "username": "founder", "password": ADMIN_PASSWORD, "display_name": "Fleet Founder",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["role"] == "admin"
    # Fresh install seeds default folders and flight purposes.
    assert db.query(Folder).count() > 0
    assert db.query(FlightPurpose).count() > 0
    # The new admin can log in.
    assert client.post(LOGIN_URL, json={"username": "founder", "password": ADMIN_PASSWORD}).status_code == 200


def test_initial_setup_blocked_when_usable_login_exists(client, admin_user):
    resp = client.post(SETUP_URL, json={"username": "second", "password": ADMIN_PASSWORD})
    assert resp.status_code == 403, resp.text


def test_setup_reclaims_existing_admin_after_redacted_restore(client, db, tmp_path, monkeypatch):
    """The core fix: with users present but every hash blank, setup re-claims the
    named admin (sets its password), gated on the install token, rather than
    seeding a second install."""
    _seed_blank_hash_user(db, "chief", "admin")
    headers = _arm_install_token(monkeypatch, tmp_path)

    resp = client.post(SETUP_URL, headers=headers,
                       json={"username": "chief", "password": RECOVERY_PASSWORD})
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["username"] == "chief"

    # No duplicate account and no re-seeded defaults on top of restored data.
    assert db.query(User).count() == 1
    assert db.query(Folder).count() == 0
    assert db.query(FlightPurpose).count() == 0

    # The reclaimed admin logs in with the new password, and setup closes again.
    assert client.post(LOGIN_URL, json={"username": "chief", "password": RECOVERY_PASSWORD}).status_code == 200
    assert client.get(SETUP_REQUIRED_URL).json()["setup_required"] is False
    # The token is single-use: retired once a usable login exists.
    assert not _install_token_path_exists()


def test_setup_recovery_requires_install_token(client, db, tmp_path, monkeypatch):
    """Knowing an admin username is not enough; without the install token the
    reactivation is refused, closing the post-restore takeover window."""
    _seed_blank_hash_user(db, "chief", "admin")
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)  # token file absent
    resp = client.post(SETUP_URL, json={"username": "chief", "password": RECOVERY_PASSWORD})
    assert resp.status_code == 401, resp.text
    # The admin is untouched: still no usable login.
    assert client.post(LOGIN_URL, json={"username": "chief", "password": RECOVERY_PASSWORD}).status_code == 401


def test_setup_recovery_rejects_bad_install_token(client, db, tmp_path, monkeypatch):
    _seed_blank_hash_user(db, "chief", "admin")
    _arm_install_token(monkeypatch, tmp_path)
    resp = client.post(SETUP_URL, headers={"X-Install-Token": "wrong-token"},
                       json={"username": "chief", "password": RECOVERY_PASSWORD})
    assert resp.status_code == 401, resp.text


def test_setup_recovery_rejects_unknown_username(client, db, tmp_path, monkeypatch):
    _seed_blank_hash_user(db, "chief", "admin")
    headers = _arm_install_token(monkeypatch, tmp_path)
    resp = client.post(SETUP_URL, headers=headers,
                       json={"username": "nobody", "password": RECOVERY_PASSWORD})
    assert resp.status_code == 400, resp.text


def test_setup_recovery_rejects_non_admin_username(client, db, tmp_path, monkeypatch):
    """Claiming a non-admin account would leave the operator without admin
    access, so only an administrator username is accepted for recovery."""
    _seed_blank_hash_user(db, "chief", "admin")
    _seed_blank_hash_user(db, "observer", "pilot")
    headers = _arm_install_token(monkeypatch, tmp_path)
    resp = client.post(SETUP_URL, headers=headers,
                       json={"username": "observer", "password": RECOVERY_PASSWORD})
    assert resp.status_code == 400, resp.text
