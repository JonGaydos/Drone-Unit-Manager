"""Batch 2 session and auth hardening: token revocation, token lifetime,
disabled-account logins, password length, restore hygiene, API token expiry and
the install token log."""

import logging
from datetime import datetime, timedelta

import pytest
from jose import jwt

from app.config import settings
from app.models.api_token import ApiToken
from app.models.audit_log import AuditLog
from app.models.user import User
from app.routers import backup as backup_router
from app.routers.auth import ALGORITHM, create_token
from app.services.api_tokens import generate_token, hash_token
from tests.conftest import _seed_user, ADMIN_PASSWORD, PILOT_PASSWORD

ME = "/api/auth/me"
NEW_PASSWORD = "BrandNewPassw0rd!"


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


# 1. Tokens are revoked when the account changes ------------------------------

def test_password_change_revokes_old_token_and_issues_a_working_one(client, pilot_user):
    old = _login(client, "pilot", PILOT_PASSWORD).json()["token"]
    resp = client.post("/api/auth/change-password", headers=_bearer(old),
                       json={"current_password": PILOT_PASSWORD, "new_password": NEW_PASSWORD})
    assert resp.status_code == 200
    assert client.get(ME, headers=_bearer(old)).status_code == 401
    assert client.get(ME, headers=_bearer(resp.json()["token"])).status_code == 200


def test_admin_password_reset_revokes_the_users_tokens(client, pilot_user, admin_headers):
    old = _login(client, "pilot", PILOT_PASSWORD).json()["token"]
    client.post(f"/api/auth/users/{pilot_user.id}/reset-password", headers=admin_headers,
                json={"new_password": NEW_PASSWORD})
    assert client.get(ME, headers=_bearer(old)).status_code == 401


def test_role_change_revokes_the_users_tokens(client, pilot_user, admin_headers):
    old = _login(client, "pilot", PILOT_PASSWORD).json()["token"]
    client.patch(f"/api/auth/users/{pilot_user.id}", headers=admin_headers, json={"role": "viewer"})
    assert client.get(ME, headers=_bearer(old)).status_code == 401


def test_unrelated_profile_edit_keeps_the_session(client, pilot_user, admin_headers):
    old = _login(client, "pilot", PILOT_PASSWORD).json()["token"]
    client.patch(f"/api/auth/users/{pilot_user.id}", headers=admin_headers, json={"display_name": "Renamed"})
    assert client.get(ME, headers=_bearer(old)).status_code == 200


def test_logout_revokes_the_token(client, pilot_user):
    token = _login(client, "pilot", PILOT_PASSWORD).json()["token"]
    assert client.post("/api/auth/logout", headers=_bearer(token)).status_code == 200
    assert client.get(ME, headers=_bearer(token)).status_code == 401


def test_revoked_token_cannot_fetch_photos_or_import_backups(client, db, admin_user, tmp_path, monkeypatch):
    """Image serving and backup import decode tokens on their own paths; a
    revoked token must be refused there too, not only by the main dependency."""
    from app.models.photo import Photo
    monkeypatch.setattr("app.routers.photos.UPLOAD_DIR", str(tmp_path))
    (tmp_path / "p.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    photo = Photo(filename="p.png", original_filename="p.png", mime_type="image/png")
    db.add(photo)
    db.commit()
    token = create_token(admin_user.id, admin_user.token_version)
    assert client.get(f"/api/photos/{photo.id}/view", headers=_bearer(token)).status_code == 200

    client.post("/api/auth/logout", headers=_bearer(token))
    assert client.get(f"/api/photos/{photo.id}/view", headers=_bearer(token)).status_code == 401
    resp = client.post("/api/backup/import", headers=_bearer(token),
                       files={"file": ("b.zip", b"PK\x05\x06" + b"\x00" * 18, "application/zip")})
    assert resp.status_code == 401


def test_token_from_before_versioning_still_works(client, pilot_user):
    """Upgrading must not sign everyone out: a token with no version claim is
    read as version 0, which is where every existing user starts."""
    now = datetime.utcnow()
    legacy = jwt.encode({"sub": str(pilot_user.id), "iat": now, "exp": now + timedelta(hours=1)},
                        settings.SECRET_KEY, algorithm=ALGORITHM)
    assert client.get(ME, headers=_bearer(legacy)).status_code == 200


def test_login_token_lasts_twelve_hours():
    claims = jwt.get_unverified_claims(create_token(1))
    assert claims["exp"] - claims["iat"] == 12 * 3600


# 2. Login and password rules ---------------------------------------------------

def test_disabled_account_gets_the_same_answer_as_a_wrong_password(client, db, pilot_user):
    pilot_user.is_active = False
    db.commit()
    resp = _login(client, "pilot", PILOT_PASSWORD)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"
    blocked = db.query(AuditLog).filter(AuditLog.action == "login_blocked").count()
    assert blocked == 1


def test_password_over_72_bytes_is_refused(client, pilot_user, pilot_headers):
    too_long = "Aa1" + "x" * 70
    resp = client.post("/api/auth/change-password", headers=pilot_headers,
                       json={"current_password": PILOT_PASSWORD, "new_password": too_long})
    assert resp.status_code == 400


# 3. A restore cannot grant access or rewrite history ---------------------------

def test_restore_blanks_hashes_drops_tokens_and_keeps_the_audit_trail(db, admin_user):
    raw = generate_token()
    db.add(ApiToken(name="local", token_hash=hash_token(raw), token_prefix=raw[:12], user_id=admin_user.id))
    db.add(AuditLog(user_id=admin_user.id, user_name="Local Admin", action="login", entity_type="auth",
                    created_at=datetime(2026, 9, 1, 8, 0)))
    db.commit()

    doctored = {
        "users": [{"id": 1, "username": "planted", "password_hash": "$2b$12$knownhashknownhashknownhashknownhashknownhashkn",
                   "display_name": "Planted", "role": "admin", "is_active": True}],
        "api_tokens": [{"id": 1, "name": "planted", "token_hash": hash_token("dum_planted"),
                        "token_prefix": "dum_planted", "user_id": 1, "read_only": False}],
        "audit_logs": [
            {"id": 1, "user_id": 1, "user_name": "Planted", "action": "update", "entity_type": "flight",
             "created_at": "2026-01-01T00:00:00"},
            # The same event this install already holds: skipped, not duplicated.
            {"id": 2, "user_id": None, "user_name": "Local Admin", "action": "login", "entity_type": "auth",
             "created_at": "2026-09-01T08:00:00"},
        ],
    }
    backup_router._restore_main_tables(db, doctored)
    db.expire_all()

    assert db.query(User).one().password_hash == ""
    assert db.query(ApiToken).count() == 0
    entries = db.query(AuditLog).order_by(AuditLog.created_at).all()
    assert [(e.user_name, e.action) for e in entries] == [("Planted", "update"), ("Local Admin", "login")]
    local = entries[1]
    assert local.user_id is None  # detached from the replaced user id, name kept


def test_login_token_from_before_a_restore_stops_working(client, db, admin_user):
    """Users come back by id, so without a fresh version a pre-restore token
    for id N would sign in as whoever is id N in the backup."""
    old = create_token(admin_user.id, admin_user.token_version)
    backup_router._restore_main_tables(db, {"users": [
        {"id": admin_user.id, "username": "someone_else", "password_hash": "", "display_name": "Else",
         "role": "admin", "is_active": True},
    ]})
    assert client.get(ME, headers=_bearer(old)).status_code == 401


# 4. API tokens can expire -------------------------------------------------------

def test_api_token_with_expiry_is_refused_after_it_lapses(client, db, admin_user, admin_headers):
    created = client.post("/api/api-tokens", headers=admin_headers,
                          json={"name": "short", "expires_in_days": 30}).json()
    assert created["expires_at"] is not None
    assert client.get("/api/flights", headers=_bearer(created["token"])).status_code == 200

    token = db.get(ApiToken, created["id"])
    token.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    assert client.get("/api/flights", headers=_bearer(created["token"])).status_code == 401


def test_api_token_without_expiry_never_lapses(client, admin_headers):
    created = client.post("/api/api-tokens", headers=admin_headers, json={"name": "forever"}).json()
    assert created["expires_at"] is None


# 5. The install token is printed once, not on every boot ------------------------

def test_install_token_value_is_logged_only_when_generated(db, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(backup_router.database, "SessionLocal", lambda: db)
    with caplog.at_level(logging.INFO, logger="app.routers.backup"):
        token = backup_router.init_install_token()
        first_boot = caplog.text
        caplog.clear()
        assert backup_router.init_install_token() == token
        second_boot = caplog.text
    assert token in first_boot
    assert token not in second_boot
    assert "install_token.txt" in second_boot
