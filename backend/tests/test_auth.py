"""Authentication and authorization tests.

Covers login success/failure, the unknown-user timing-equalized 401 path (a real
past incident produced a 500 here), token-protected routes, and admin role
gating on a real admin-only endpoint (GET /api/audit).
"""

from tests.conftest import ADMIN_PASSWORD, PILOT_PASSWORD

LOGIN_URL = "/api/auth/login"
ME_URL = "/api/auth/me"
AUDIT_URL = "/api/audit"


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
