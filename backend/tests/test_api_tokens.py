"""Long-lived API tokens: creation, scoping, and request authentication.

Tokens are admin-created, shown once, stored hashed, and act as their
owning user. Enforcement layers under test: read_only blocks non-GET,
area scopes gate by route prefix, and sensitive areas (auth, settings,
the token API itself) are denied to every token.
"""

from app.models.api_token import ApiToken


def _create_token(client, admin_headers, **overrides):
    payload = {"name": "Home Assistant", "read_only": True, **overrides}
    resp = client.post("/api/api-tokens", headers=admin_headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_returns_token_once_and_lists_prefix_only(client, db, admin_headers):
    created = _create_token(client, admin_headers)
    assert created["token"].startswith("dum_")
    assert created["read_only"] is True
    assert created["scopes"] is None

    listing = client.get("/api/api-tokens", headers=admin_headers).json()
    assert len(listing) == 1
    assert "token" not in listing[0]
    assert created["token"].startswith(listing[0]["token_prefix"])
    # Only the hash is stored
    row = db.query(ApiToken).one()
    assert created["token"] not in (row.token_hash, row.token_prefix)


def test_token_reads_scoped_area(client, admin_headers):
    token = _create_token(client, admin_headers, scopes=["fleet"])["token"]

    resp = client.get("/api/vehicles", headers=_bearer(token))
    assert resp.status_code == 200, resp.text


def test_token_blocked_outside_scope(client, admin_headers):
    token = _create_token(client, admin_headers, scopes=["flights"])["token"]

    resp = client.get("/api/vehicles", headers=_bearer(token))
    assert resp.status_code == 403


def test_read_only_token_cannot_write(client, admin_headers):
    token = _create_token(client, admin_headers, scopes=["fleet"])["token"]

    resp = client.post("/api/batteries", headers=_bearer(token), json={"serial_number": "TOK-B1"})
    assert resp.status_code == 403


def test_read_write_token_can_write_in_scope(client, admin_headers):
    token = _create_token(client, admin_headers, read_only=False, scopes=["fleet"])["token"]

    resp = client.post("/api/batteries", headers=_bearer(token), json={"serial_number": "TOK-B2"})
    assert resp.status_code == 200, resp.text


def test_sensitive_areas_denied_to_all_tokens(client, admin_headers):
    token = _create_token(client, admin_headers, read_only=False)["token"]

    assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 403
    assert client.get("/api/settings/timezone", headers=_bearer(token)).status_code == 403
    assert client.get("/api/api-tokens", headers=_bearer(token)).status_code == 403
    assert client.post("/api/api-tokens", headers=_bearer(token), json={"name": "x"}).status_code == 403


def test_revoked_token_is_rejected(client, admin_headers):
    created = _create_token(client, admin_headers, scopes=["fleet"])
    assert client.get("/api/vehicles", headers=_bearer(created["token"])).status_code == 200

    assert client.delete(f"/api/api-tokens/{created['id']}", headers=admin_headers).status_code == 200
    assert client.get("/api/vehicles", headers=_bearer(created["token"])).status_code == 401


def test_unknown_scope_rejected(client, admin_headers):
    resp = client.post("/api/api-tokens", headers=admin_headers,
                       json={"name": "bad", "scopes": ["everything"]})
    assert resp.status_code == 400


def test_token_management_is_admin_only(client, pilot_headers):
    assert client.get("/api/api-tokens", headers=pilot_headers).status_code == 403
    assert client.post("/api/api-tokens", headers=pilot_headers, json={"name": "x"}).status_code == 403


def test_garbage_dum_token_is_401(client):
    assert client.get("/api/vehicles", headers=_bearer("dum_notarealtoken")).status_code == 401
