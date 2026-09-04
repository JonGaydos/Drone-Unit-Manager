"""Backup export secret-stripping and empty-hash bypass tests.

Covers the security-critical core of ``app.routers.backup`` and
``app.routers.auth.verify_password``:

* GET ``/api/backup/export`` is admin-gated (pilot gets 403) and produces a ZIP
  whose ``database.json`` blanks every user ``password_hash`` to ``""`` and drops
  Setting rows whose key is in ``SECRET_KEYS``. The raw ZIP bytes contain none of
  the seeded cleartext secrets, while non-secret data still round-trips (so the
  export is not just empty).
* ``verify_password`` fails closed on an empty stored hash: a blanked
  ``password_hash`` from a restored export can never authenticate.

Assertions check the live export via ``client`` and the real ``verify_password``
function directly.
"""

import io
import json
import zipfile

from app.models.setting import Setting
from app.models.user import User
from app.routers.auth import hash_password, verify_password
from app.routers.backup import DATABASE_FILE
from app.routers.settings import SECRET_KEYS

EXPORT_URL = "/api/backup/export"

# Known cleartext secrets seeded into secret Setting rows. The export must drop
# these rows; none of these strings may appear anywhere in the ZIP.
SKYDIO_TOKEN = "skydio-cleartext-token-abc123"
SKYDIO_TOKEN_ID = "skydio-token-id-cleartext-456"
SMTP_PASSWORD = "smtp-cleartext-password-789"

# Known plaintext password for a seeded user. Its bcrypt hash must be blanked.
USER_PASSWORD = "ExportUserP4ss!"


def _seed_secret_settings(db):
    db.add(Setting(key="skydio_api_token", value=SKYDIO_TOKEN))
    db.add(Setting(key="skydio_token_id", value=SKYDIO_TOKEN_ID))
    db.add(Setting(key="smtp_password", value=SMTP_PASSWORD))
    # A non-secret setting that SHOULD survive the export.
    db.add(Setting(key="org_name", value="Drone Squad"))
    db.commit()


def _read_database_blob(resp):
    """Return the decompressed database.json from an export ZIP as (bytes, dict).

    The ZIP entries are DEFLATE-compressed, so the cleartext-absence check must
    run against the DECOMPRESSED member bytes, not the raw ZIP container.
    """
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    raw = zf.read(DATABASE_FILE)
    return raw, json.loads(raw)


def test_export_requires_admin(client, db, pilot_user, pilot_headers):
    resp = client.get(EXPORT_URL, headers=pilot_headers)
    assert resp.status_code == 403, resp.text


def test_export_strips_secrets_and_password_hashes(client, db, admin_user, admin_headers):
    # Seed a known-password user (its hash must be blanked) and secret settings.
    extra = User(
        username="exportuser",
        password_hash=hash_password(USER_PASSWORD),
        display_name="Export User",
        role="pilot",
        is_active=True,
    )
    db.add(extra)
    db.commit()
    db.refresh(extra)
    real_hash = extra.password_hash
    assert real_hash, "precondition: seeded user has a real bcrypt hash"

    _seed_secret_settings(db)

    resp = client.get(EXPORT_URL, headers=admin_headers)
    assert resp.status_code == 200, resp.text

    blob, database = _read_database_blob(resp)

    # --- Password hashes: blanked to "" on export ---
    users = database["users"]
    assert len(users) >= 2, users
    for row in users:
        assert row["password_hash"] == "", row
    # The actual bcrypt hash must appear nowhere in the serialized export.
    assert real_hash.encode() not in blob

    # --- Secret Setting rows: dropped entirely ---
    setting_keys = {r["key"] for r in database["settings"]}
    assert SECRET_KEYS.isdisjoint(setting_keys), setting_keys
    # The cleartext secret values must appear nowhere in the serialized export.
    for secret in (SKYDIO_TOKEN, SKYDIO_TOKEN_ID, SMTP_PASSWORD):
        assert secret.encode() not in blob, secret

    # --- Non-secret data still present (export is not just empty) ---
    assert "org_name" in setting_keys
    assert b"Drone Squad" in blob
    usernames = {r["username"] for r in users}
    assert {"admin", "exportuser"} <= usernames


def test_verify_password_fails_closed_on_empty_hash():
    # A blanked password_hash (as produced by export sanitization) must never
    # authenticate, regardless of supplied password.
    assert verify_password("", "") is False
    assert verify_password("any-input", "") is False
    # An empty supplied password against a real hash also fails.
    real_hash = hash_password(USER_PASSWORD)
    assert verify_password("", real_hash) is False
    # Sanity: the real password still verifies against its real hash.
    assert verify_password(USER_PASSWORD, real_hash) is True
