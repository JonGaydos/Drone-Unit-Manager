"""The backup download streams while the archive is built.

A full backup with telemetry took minutes to build, and nothing reached the
browser until the whole archive was done. The export now sends the ZIP as it is
written, so the first bytes arrive at once and a long export shows progress.
"""

import io
import json
import threading
import time
import zipfile

from app.config import settings as app_settings
from app.models.setting import Setting
from app.models.telemetry import TelemetryPoint
from app.routers import backup as backup_router


def _seed(db, telemetry_db):
    db.add(Setting(key="org_name", value="Stream Unit"))
    db.commit()
    telemetry_db.add(TelemetryPoint(flight_id=1, timestamp_ms=0, lat=28.5, lon=-81.4,
                                    altitude_m=30.0, source="test"))
    telemetry_db.commit()


def _uploads(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    (upload_dir / "documents").mkdir(parents=True)
    (upload_dir / "documents" / "note.txt").write_text("streamed file")
    monkeypatch.setattr(app_settings, "UPLOAD_DIR", upload_dir)


def test_export_sends_bytes_before_the_archive_is_finished(db, telemetry_db, tmp_path, monkeypatch):
    _uploads(tmp_path, monkeypatch)
    _seed(db, telemetry_db)
    release = threading.Event()
    original = backup_router._write_telemetry

    def held(zf, expected):
        assert release.wait(10), "test never released the telemetry step"
        return original(zf, expected)

    monkeypatch.setattr(backup_router, "_write_telemetry", held)

    chunks = backup_router.stream_backup_archive(include_telemetry=True)
    first = next(chunks)          # arrives while telemetry is still held back
    assert first.startswith(b"PK")
    release.set()
    archive = zipfile.ZipFile(io.BytesIO(first + b"".join(chunks)))

    assert {"manifest.json", "database.json", "telemetry.json", "uploads/documents/note.txt"} <= set(archive.namelist())
    assert archive.testzip() is None
    tables = json.loads(archive.read("database.json"))
    assert {"key": "org_name", "value": "Stream Unit"}.items() <= tables["settings"][0].items()
    assert len(json.loads(archive.read("telemetry.json"))) == 1
    assert archive.read("uploads/documents/note.txt") == b"streamed file"


def test_a_stopped_download_ends_the_build(db, telemetry_db, tmp_path, monkeypatch):
    """A client that goes away must not leave the builder blocked forever."""
    _uploads(tmp_path, monkeypatch)
    _seed(db, telemetry_db)
    monkeypatch.setattr(backup_router, "EXPORT_QUEUE_CHUNKS", 1)

    chunks = backup_router.stream_backup_archive(include_telemetry=True)
    next(chunks)
    chunks.close()

    deadline = time.monotonic() + 10
    while any(t.name == "backup-export" for t in threading.enumerate()):
        assert time.monotonic() < deadline, "backup builder still running after the download stopped"
        time.sleep(0.05)


def test_export_endpoint_returns_a_valid_streamed_archive(client, db, telemetry_db, admin_headers, tmp_path, monkeypatch):
    _uploads(tmp_path, monkeypatch)
    _seed(db, telemetry_db)

    resp = client.get("/api/backup/export?include_telemetry=true", headers=admin_headers)

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    assert archive.testzip() is None
    assert json.loads(archive.read("manifest.json"))["tables"]["telemetry_points"] == 1
