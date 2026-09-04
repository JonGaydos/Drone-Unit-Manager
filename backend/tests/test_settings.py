"""Settings endpoint tests: secret redaction and bulk-save guards.

Covers the real behavior of ``app.routers.settings``:

* GET ``/api/settings`` redacts SECRET_KEYS to the ``********`` marker.
* PUT ``/api/settings/bulk`` never overwrites a stored secret with an empty
  string or the redaction marker (the GET-then-save round-trip guard), but does
  persist a genuine new secret and normal allowlisted keys.
* Keys outside ALLOWED_SETTING_KEYS are silently dropped.
* Bulk save is admin-gated (pilot gets 403).

Assertions check live-app responses via ``client`` and persisted state via the
``db`` fixture (the app commits; cross-session reads see committed rows).
"""

from app.models.setting import Setting
from app.routers.settings import REDACTED_MARKER

SETTINGS_URL = "/api/settings"
BULK_URL = "/api/settings/bulk"

SECRET_KEY = "skydio_api_token"
ORIGINAL_SECRET = "real-skydio-token-abc123"


def _seed_setting(db, key, value):
    db.add(Setting(key=key, value=value))
    db.commit()


def _stored(db, key):
    """Read a setting value from a fresh query (sees app-committed rows)."""
    db.expire_all()
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else None


def test_get_redacts_secret_values(client, db, admin_headers):
    _seed_setting(db, SECRET_KEY, ORIGINAL_SECRET)

    resp = client.get(SETTINGS_URL, headers=admin_headers)
    assert resp.status_code == 200, resp.text

    by_key = {s["key"]: s["value"] for s in resp.json()}
    assert SECRET_KEY in by_key
    assert by_key[SECRET_KEY] == REDACTED_MARKER
    assert ORIGINAL_SECRET not in resp.text


def test_bulk_save_empty_string_does_not_overwrite_secret(client, db, admin_headers):
    _seed_setting(db, SECRET_KEY, ORIGINAL_SECRET)

    resp = client.put(BULK_URL, headers=admin_headers,
                      json=[{"key": SECRET_KEY, "value": ""}])
    assert resp.status_code == 200, resp.text

    assert _stored(db, SECRET_KEY) == ORIGINAL_SECRET


def test_bulk_save_redaction_marker_does_not_overwrite_secret(client, db, admin_headers):
    _seed_setting(db, SECRET_KEY, ORIGINAL_SECRET)

    resp = client.put(BULK_URL, headers=admin_headers,
                      json=[{"key": SECRET_KEY, "value": REDACTED_MARKER}])
    assert resp.status_code == 200, resp.text

    assert _stored(db, SECRET_KEY) == ORIGINAL_SECRET


def test_bulk_save_real_new_secret_is_saved(client, db, admin_headers):
    _seed_setting(db, SECRET_KEY, ORIGINAL_SECRET)
    new_secret = "brand-new-token-xyz789"

    resp = client.put(BULK_URL, headers=admin_headers,
                      json=[{"key": SECRET_KEY, "value": new_secret}])
    assert resp.status_code == 200, resp.text

    assert _stored(db, SECRET_KEY) == new_secret


def test_bulk_save_non_secret_key_persists(client, db, admin_headers):
    resp = client.put(BULK_URL, headers=admin_headers,
                      json=[{"key": "org_name", "value": "Drone Squad"}])
    assert resp.status_code == 200, resp.text

    assert _stored(db, "org_name") == "Drone Squad"


def test_bulk_save_non_allowlisted_key_is_ignored(client, db, admin_headers):
    # Not in ALLOWED_SETTING_KEYS; the endpoint silently `continue`s, returning
    # 200 but never writing the row.
    resp = client.put(BULK_URL, headers=admin_headers,
                      json=[{"key": "not_a_real_key", "value": "evil"}])
    assert resp.status_code == 200, resp.text

    assert _stored(db, "not_a_real_key") is None


def test_bulk_save_rejects_non_admin(client, db, pilot_headers):
    resp = client.put(BULK_URL, headers=pilot_headers,
                      json=[{"key": "org_name", "value": "Pilot Tried"}])
    assert resp.status_code == 403, resp.text
    assert _stored(db, "org_name") is None
