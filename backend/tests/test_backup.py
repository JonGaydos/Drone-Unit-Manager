"""Backup export contents and empty-hash bypass tests.

Covers the security-critical core of ``app.routers.backup`` and
``app.routers.auth.verify_password``:

* GET ``/api/backup/export`` is admin-gated (pilot gets 403) and produces a ZIP
  whose ``database.json`` carries everything a restore needs: user password
  hashes, API token rows and the secret settings (``SECRET_KEYS``), with no
  encryption. A backup restores everything, so the ZIP must be stored as
  carefully as the database itself.
* ``verify_password`` fails closed on an empty stored hash: a blank
  ``password_hash`` (from a backup made before hashes were included) can never
  authenticate.

Assertions check the live export via ``client`` and the real ``verify_password``
function directly.
"""

import io
import json
import zipfile

from app.models.api_token import ApiToken
from app.models.setting import Setting
from app.models.user import User
from app.routers.auth import hash_password, verify_password
from app.routers.backup import DATABASE_FILE
from app.routers.settings import SECRET_KEYS
from app.services.api_tokens import generate_token, hash_token

EXPORT_URL = "/api/backup/export"

# Known cleartext secrets seeded into secret Setting rows. The export must keep
# them, so a restored install keeps its integrations.
SKYDIO_TOKEN = "skydio-cleartext-token-abc123"
SKYDIO_TOKEN_ID = "skydio-token-id-cleartext-456"
SMTP_PASSWORD = "smtp-cleartext-password-789"

# Known plaintext password for a seeded user. Its bcrypt hash must be exported.
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


def test_export_includes_secrets_password_hashes_and_api_tokens(client, db, admin_user, admin_headers):
    # Seed a known-password user, an API token and secret settings.
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
    raw_token = generate_token()
    db.add(ApiToken(name="integration", token_hash=hash_token(raw_token), token_prefix=raw_token[:12],
                    user_id=extra.id, read_only=False, scopes='["flights"]'))
    db.commit()

    _seed_secret_settings(db)

    resp = client.get(EXPORT_URL, headers=admin_headers)
    assert resp.status_code == 200, resp.text

    _, database = _read_database_blob(resp)

    # --- Password hashes: exported as stored ---
    hashes = {r["username"]: r["password_hash"] for r in database["users"]}
    assert hashes["exportuser"] == real_hash
    assert hashes["admin"] == admin_user.password_hash

    # --- API tokens: exported with hash, scopes and flags ---
    (token_row,) = database["api_tokens"]
    assert token_row["token_hash"] == hash_token(raw_token)
    assert token_row["scopes"] == '["flights"]'
    assert token_row["read_only"] is False
    assert token_row["user_id"] == extra.id

    # --- Secret Setting rows: exported with their values ---
    settings = {r["key"]: r["value"] for r in database["settings"]}
    assert SECRET_KEYS <= settings.keys()
    assert settings["skydio_api_token"] == SKYDIO_TOKEN
    assert settings["skydio_token_id"] == SKYDIO_TOKEN_ID
    assert settings["smtp_password"] == SMTP_PASSWORD
    assert settings["org_name"] == "Drone Squad"


def test_verify_password_fails_closed_on_empty_hash():
    # A blank password_hash (as in backups made before hashes were included)
    # must never authenticate, regardless of supplied password.
    assert verify_password("", "") is False
    assert verify_password("any-input", "") is False
    # An empty supplied password against a real hash also fails.
    real_hash = hash_password(USER_PASSWORD)
    assert verify_password("", real_hash) is False
    # Sanity: the real password still verifies against its real hash.
    assert verify_password(USER_PASSWORD, real_hash) is True
