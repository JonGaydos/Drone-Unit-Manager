"""Backup restore coverage: _parse_rows and the /api/backup/import round trip.

The export side is covered by test_backup.py and test_backup_memory.py; the
restore side had none, which is why this file exists before that code is
refactored. It pins:

* _parse_rows: ISO datetime/date revival, None and non-temporal passthrough, a
  malformed value falling back to the raw string, and the legacy column rename.
* A full round trip via the install-token (fresh-install) auth path: build an
  archive from a seeded database, wipe every table, import the archive, and
  confirm the main tables, an uploaded file, and telemetry all come back, the
  install token is retired, and the response counts are right.

The round trip is the faithful test for the restore: it drives the real
endpoint (auth, ZIP parsing, FK-off bulk insert, telemetry chunk insert, upload
extraction, token retirement) rather than any one piece in isolation.
"""

import io
import json
import zipfile
from datetime import date, datetime

from sqlalchemy import text

from app.config import settings as app_settings
from app.routers.backup import build_backup_archive, EXPORT_ORDER, _install_token_path
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.flight import Flight
from app.models.setting import Setting
from app.models.telemetry import TelemetryPoint

IMPORT_URL = "/api/backup/import"


# --- _parse_rows ------------------------------------------------------------

def test_parse_rows_revives_iso_datetime_and_date():
    from app.routers.backup import _parse_rows
    rows = [{"id": 1, "date": "2025-06-01", "takeoff_time": "2025-06-01T13:30:00", "purpose": "Patrol"}]

    parsed = _parse_rows(rows, Flight)

    assert parsed[0]["date"] == date(2025, 6, 1)
    assert parsed[0]["takeoff_time"] == datetime(2025, 6, 1, 13, 30)
    assert parsed[0]["purpose"] == "Patrol"      # non-temporal column untouched


def test_parse_rows_keeps_none_values():
    from app.routers.backup import _parse_rows
    parsed = _parse_rows([{"id": 1, "date": None, "takeoff_time": None}], Flight)
    assert parsed[0]["date"] is None
    assert parsed[0]["takeoff_time"] is None


def test_parse_rows_tolerates_a_malformed_temporal_value():
    """A bad date string falls back to the raw value rather than raising, so one
    corrupt cell cannot abort a whole restore."""
    from app.routers.backup import _parse_rows
    parsed = _parse_rows([{"id": 1, "date": "not-a-date"}], Flight)
    assert parsed[0]["date"] == "not-a-date"


def test_parse_rows_applies_legacy_column_rename():
    from app.routers.backup import _parse_rows
    from app.models.battery import Battery
    parsed = _parse_rows([{"serial_number": "B-1", "purchase_date": "2024-01-01"}], Battery)
    assert "purchase_date" not in parsed[0]
    assert parsed[0]["acquired_date"] == date(2024, 1, 1)   # renamed AND parsed


# --- full round trip --------------------------------------------------------

def _clear_all(db, telemetry_db):
    """Empty every backed-up table so the restore has a clean target (the
    restore inserts with explicit ids and would otherwise hit PK conflicts)."""
    db.execute(text("PRAGMA foreign_keys=OFF"))
    for _name, model in EXPORT_ORDER:
        db.execute(model.__table__.delete())
    db.commit()
    db.execute(text("PRAGMA foreign_keys=ON"))
    telemetry_db.query(TelemetryPoint).delete()
    telemetry_db.commit()


def test_backup_import_round_trip(client, db, telemetry_db, tmp_path, monkeypatch):
    # Isolate the upload and data directories to tmp so the archive walk and the
    # install-token file never touch the real filesystem.
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "documents").mkdir()
    (upload_dir / "documents" / "evidence.txt").write_text("body-camera notes")
    monkeypatch.setattr(app_settings, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)

    # Seed representative data across tiers, plus one telemetry point.
    p = Pilot(first_name="Ana", last_name="Alvarez", status="active")
    v = Vehicle(serial_number="SN-1", manufacturer="Skydio", model="X10", status="active")
    db.add_all([p, v]); db.commit(); db.refresh(p); db.refresh(v)
    db.add(Flight(date=date(2025, 6, 1), pilot_id=p.id, vehicle_id=v.id,
                  duration_seconds=600, external_id="F-1", purpose="Patrol"))
    db.add(Setting(key="org_name", value="Drone Squad"))
    db.commit()
    telemetry_db.add(TelemetryPoint(flight_id=1, timestamp_ms=0, lat=28.5, lon=-81.4,
                                    altitude_m=30.0, source="test"))
    telemetry_db.commit()

    # Build the archive from the seeded database.
    spooled, manifest = build_backup_archive(db, include_telemetry=True)
    archive = spooled.read()
    assert manifest["tables"]["flights"] == 1

    # Wipe everything, so this is a fresh-install target (no users -> the import
    # takes the install-token auth path).
    _clear_all(db, telemetry_db)
    assert db.query(Flight).count() == 0

    # Write the install token the endpoint will check.
    token = "round-trip-install-token"
    with open(_install_token_path(), "w") as f:
        f.write(token)

    resp = client.post(
        IMPORT_URL,
        headers={"X-Install-Token": token},
        files={"file": ("backup.zip", archive, "application/zip")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["telemetry_imported"] is True
    assert body["files_restored"] == 1
    assert body["rows_imported"] >= 3     # pilot + vehicle + flight + setting

    # The rows are actually back (query fresh; the import committed on its own session).
    db.expire_all()
    assert db.query(Pilot).filter_by(last_name="Alvarez").count() == 1
    flight = db.query(Flight).filter_by(external_id="F-1").one()
    assert flight.date == date(2025, 6, 1)          # date revived, not a string
    assert flight.duration_seconds == 600
    assert db.query(Setting).filter_by(key="org_name").one().value == "Drone Squad"

    telemetry_db.expire_all()
    assert telemetry_db.query(TelemetryPoint).count() == 1

    # The uploaded file was extracted back to disk.
    assert (upload_dir / "documents" / "evidence.txt").read_text() == "body-camera notes"

    # A restore blanks every password hash, so the install is left with no usable
    # login. The same install token is kept in place (not retired, not replaced)
    # so the operator can reactivate an admin on the setup screen; it is retired
    # only once that succeeds.
    token_file = tmp_path / "install_token.txt"
    assert token_file.exists()
    assert token_file.read_text().strip() == token   # unchanged, not a new token


def test_backup_import_rejects_a_non_zip(client, db, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    # No users -> install-token path; write a matching token.
    db.execute(text("PRAGMA foreign_keys=OFF"))
    for _name, model in EXPORT_ORDER:
        db.execute(model.__table__.delete())
    db.commit()
    token = "tok"
    with open(_install_token_path(), "w") as f:
        f.write(token)

    resp = client.post(
        IMPORT_URL,
        headers={"X-Install-Token": token},
        files={"file": ("not.zip", b"this is not a zip", "application/zip")},
    )
    assert resp.status_code == 400


def test_backup_import_requires_auth(client, db, tmp_path, monkeypatch):
    """With users present, a missing bearer token is rejected before any work."""
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    from app.models.user import User
    from app.routers.auth import hash_password
    db.add(User(username="admin2", password_hash=hash_password("AdminPassw0rd!"),
                display_name="Admin Two", role="admin", is_active=True))
    db.commit()

    resp = client.post(IMPORT_URL, files={"file": ("b.zip", b"PK", "application/zip")})
    assert resp.status_code == 401


# --- replace semantics, streaming, and surfaced telemetry failure -----------

def test_backup_import_replaces_existing_rows(client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    """A restore makes the database match the backup: rows present at import
    time but absent from the backup are gone afterward (replace, not merge)."""
    upload_dir = tmp_path / "uploads"; upload_dir.mkdir()
    monkeypatch.setattr(app_settings, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)

    db.add(Pilot(first_name="Keep", last_name="Me", status="active"))
    db.commit()
    archive = build_backup_archive(db, include_telemetry=False)[0].read()

    # Added after the snapshot -> must not survive the restore.
    db.add(Pilot(first_name="Gone", last_name="After", status="active"))
    db.add(Setting(key="added_later", value="x"))
    db.commit()

    resp = client.post(IMPORT_URL, headers=admin_headers,
                       files={"file": ("b.zip", archive, "application/zip")})
    assert resp.status_code == 200, resp.text

    db.expire_all()
    last_names = {p.last_name for p in db.query(Pilot).all()}
    assert "Me" in last_names
    assert "After" not in last_names
    assert db.query(Setting).filter_by(key="added_later").count() == 0


def test_stream_json_array_handles_chunk_splits():
    """Objects that straddle read boundaries must still parse whole."""
    from app.routers.backup import _stream_json_array
    records = [{"i": n, "s": "x" * 40} for n in range(20)]
    blob = json.dumps(records).encode()
    # A tiny read size forces most objects to span several reads.
    assert list(_stream_json_array(io.BytesIO(blob), read_size=8)) == records


def test_stream_json_array_empty_array():
    from app.routers.backup import _stream_json_array
    assert list(_stream_json_array(io.BytesIO(b"[]"), read_size=4)) == []


def test_backup_import_surfaces_telemetry_failure(client, db, telemetry_db, tmp_path, monkeypatch):
    """A malformed telemetry.json must fail the import (500), not be swallowed
    behind an ok:true response as the old code did."""
    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(app_settings, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    _clear_all(db, telemetry_db)   # no users -> install-token path

    token = "tok-tel"
    with open(_install_token_path(), "w") as f:
        f.write(token)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"app_version": "x", "tables": {}}))
        zf.writestr("database.json", json.dumps({}))
        zf.writestr("telemetry.json", '[{"flight_id": 1, "timestamp_ms":')  # truncated

    resp = client.post(IMPORT_URL, headers={"X-Install-Token": token},
                       files={"file": ("b.zip", buf.getvalue(), "application/zip")})
    assert resp.status_code == 500
    assert "telemetry" in resp.text.lower()
