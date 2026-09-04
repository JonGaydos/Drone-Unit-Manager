"""Sync endpoint tests: status surfacing and credential disconnect.

Covers the real behavior of ``app.routers.sync``:

* GET ``/api/sync/status`` parses the ``last_sync_result`` Setting row (JSON
  text) and surfaces it as a dict; returns ``None`` when the row is absent and,
  importantly, also when the stored value is unparseable JSON (it must not 500).
* POST ``/api/sync/disconnect`` clears the ``skydio_api_token`` and
  ``skydio_token_id`` secret settings, and is admin-gated (pilot gets 403 and
  nothing is cleared).

Neither endpoint makes an outbound HTTP call (status reads Setting rows;
disconnect only clears DB rows with no upstream token revoke), so no httpx
mocking is required here.

Assertions check live-app responses via ``client`` and persisted state via the
``db`` fixture (the app commits; cross-session reads see committed rows).
"""

import json

from app.models.setting import Setting

STATUS_URL = "/api/sync/status"
DISCONNECT_URL = "/api/sync/disconnect"

RESULT_KEY = "last_sync_result"


def _seed_setting(db, key, value):
    db.add(Setting(key=key, value=value))
    db.commit()


def _stored(db, key):
    """Read a setting value from a fresh query (sees app-committed rows)."""
    db.expire_all()
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else None


def test_status_surfaces_last_sync_result(client, db, admin_headers):
    result = {"vehicles_synced": 3, "flights_new": 7, "errors": []}
    _seed_setting(db, RESULT_KEY, json.dumps(result))

    resp = client.get(STATUS_URL, headers=admin_headers)
    assert resp.status_code == 200, resp.text

    assert resp.json()["last_sync_result"] == result


def test_status_last_sync_result_none_when_absent(client, db, admin_headers):
    resp = client.get(STATUS_URL, headers=admin_headers)
    assert resp.status_code == 200, resp.text

    assert resp.json()["last_sync_result"] is None


def test_status_last_sync_result_none_when_garbage(client, db, admin_headers):
    # Unparseable JSON in the stored value must be tolerated, not 500.
    _seed_setting(db, RESULT_KEY, "{not valid json")

    resp = client.get(STATUS_URL, headers=admin_headers)
    assert resp.status_code == 200, resp.text

    assert resp.json()["last_sync_result"] is None


def test_disconnect_clears_skydio_credentials(client, db, admin_headers):
    _seed_setting(db, "skydio_api_token", "real-token-abc123")
    _seed_setting(db, "skydio_token_id", "token-id-xyz")

    resp = client.post(DISCONNECT_URL, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    assert _stored(db, "skydio_api_token") == ""
    assert _stored(db, "skydio_token_id") == ""


def test_disconnect_rejects_non_admin(client, db, pilot_headers):
    _seed_setting(db, "skydio_api_token", "real-token-abc123")
    _seed_setting(db, "skydio_token_id", "token-id-xyz")

    resp = client.post(DISCONNECT_URL, headers=pilot_headers)
    assert resp.status_code == 403, resp.text

    # Nothing cleared.
    assert _stored(db, "skydio_api_token") == "real-token-abc123"
    assert _stored(db, "skydio_token_id") == "token-id-xyz"
