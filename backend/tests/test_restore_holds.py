"""Restore and legal holds: a restore that would remove or change a held item
needs the typed confirmation, and restored audit entries are marked imported."""

import io
import json
import zipfile

import pytest
from sqlalchemy import text

import app.database as database
from app.config import settings as app_settings
from app.models.audit_log import AuditLog
from app.models.pilot import Pilot
from app.models.photo import Photo
from app.models.document import Document
from app.models.user import User
from app.routers import backup as backup_router
from app.routers.backup import build_backup_archive

IMPORT_URL = "/api/backup/import"
CONFIRM = "RESTORE HELD ITEMS"


def _env(tmp_path, monkeypatch):
    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(app_settings, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)


def _held_photo(db, sha="a" * 64):
    p = Photo(filename="p1.jpg", original_filename="scene.jpg", title="Scene photo",
              legal_hold=True, sha256=sha)
    db.add(p)
    db.commit()
    return p


def _archive(db):
    return build_backup_archive(db, include_telemetry=False)[0].read()


def _post(client, headers, archive, **form):
    # These tests restore onto a live install; that confirmation has its own tests.
    form.setdefault("confirm_restore", "REPLACE ALL DATA")
    return client.post(IMPORT_URL, headers=headers, data=form,
                       files={"file": ("b.zip", archive, "application/zip")})


def _audit(db, **filters):
    db.expire_all()
    return db.query(AuditLog).filter_by(**filters).all()


def test_restore_refused_without_confirmation_lists_items(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    archive = _archive(db)               # taken before the held photo exists
    photo = _held_photo(db)
    db.add(Pilot(first_name="Later", last_name="Pilot", status="active"))
    db.commit()

    resp = _post(client, admin_headers, archive)

    assert resp.status_code == 409
    body = resp.json()
    assert body["confirm_text"] == CONFIRM
    assert body["held_items"] == [{"type": "photo", "id": photo.id, "title": "Scene photo"}]
    # Nothing changed.
    db.expire_all()
    assert db.query(Photo).count() == 1
    assert db.query(Pilot).filter_by(last_name="Pilot").count() == 1

    wrong = _post(client, admin_headers, archive, confirm_holds="restore held items")
    assert wrong.status_code == 409
    assert db.query(Photo).count() == 1


def test_restore_with_confirmation_proceeds_and_logs_each_held_item(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    archive = _archive(db)
    photo = _held_photo(db)
    photo_id = photo.id
    doc = Document(entity_type="general", document_type="other", title="Report",
                   filename="r.pdf", file_path="documents/r.pdf", mime_type="application/pdf",
                   file_size_bytes=1, legal_hold=True)
    db.add(doc)
    db.commit()
    doc_id = doc.id

    resp = _post(client, admin_headers, archive, confirm_holds=CONFIRM)

    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.query(Photo).count() == 0
    logged = {(e.entity_type, e.entity_id) for e in _audit(db, action="restore_held_item")}
    assert logged == {("photo", photo_id), ("document", doc_id)}


def test_restore_without_affected_holds_needs_no_confirmation(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    db.add(Pilot(first_name="Plain", last_name="Pilot", status="active"))
    db.add(Photo(filename="x.jpg", original_filename="x.jpg", legal_hold=False))
    db.commit()
    archive = _archive(db)
    db.query(Photo).delete()
    db.commit()

    resp = _post(client, admin_headers, archive)

    assert resp.status_code == 200, resp.text
    assert _audit(db, action="restore_held_item") == []


def test_unchanged_held_item_does_not_need_confirmation(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    _held_photo(db)
    archive = _archive(db)

    resp = _post(client, admin_headers, archive)

    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.query(Photo).filter_by(legal_hold=True).count() == 1
    assert _audit(db, action="restore_held_item") == []


def test_changed_digest_of_held_item_needs_confirmation(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    _held_photo(db, sha="a" * 64)
    archive = _archive(db)
    photo = db.query(Photo).one()
    photo.sha256 = "b" * 64
    db.commit()

    assert _post(client, admin_headers, archive).status_code == 409


def test_restored_audit_rows_marked_imported(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    db.add(AuditLog(user_name="Old Timer", action="create", entity_type="pilot",
                    entity_id=7, entity_name="Seven"))
    db.commit()
    archive = _archive(db)
    db.query(AuditLog).delete()
    db.commit()

    resp = _post(client, admin_headers, archive)

    assert resp.status_code == 200, resp.text
    rows = _audit(db, user_name="Old Timer")
    assert len(rows) == 1
    assert rows[0].imported is True


def test_restore_writes_one_summary_entry(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    for n in range(3):
        db.add(AuditLog(user_name="Old Timer", action="create", entity_type="pilot", entity_id=n))
    db.commit()
    archive = _archive(db)
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        backup_date = json.loads(zf.read("manifest.json"))["export_date"][:10]
    db.query(AuditLog).delete()
    db.commit()

    assert _post(client, admin_headers, archive).status_code == 200

    summaries = _audit(db, action="import", entity_type="backup")
    assert len(summaries) == 1
    assert backup_date in summaries[0].details
    assert "audit_rows=3" in summaries[0].details
    assert summaries[0].imported is False


def test_pre_release_backup_restores(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    """A backup from before the user_username and imported columns existed."""
    _env(tmp_path, monkeypatch)
    old_row = {"id": 5, "user_id": None, "user_name": "Legacy", "action": "update",
               "entity_type": "pilot", "entity_id": 2, "entity_name": "Two",
               "changes": None, "ip_address": None, "details": None,
               "created_at": "2025-01-02T03:04:05"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"app_version": "3.0", "export_date": "2025-01-03T00:00:00"}))
        zf.writestr("database.json", json.dumps({"audit_logs": [old_row, dict(old_row, id=6, entity_id=3)]}))

    resp = _post(client, admin_headers, buf.getvalue())

    assert resp.status_code == 200, resp.text
    rows = _audit(db, user_name="Legacy")
    assert len(rows) == 2
    assert all(r.imported and r.user_username is None for r in rows)
    summary = _audit(db, action="import", entity_type="backup")[0]
    assert "2025-01-03" in summary.details
    assert "audit_rows=2" in summary.details


def _soft_deleted_photo(db, when):
    p = Photo(filename="p2.jpg", original_filename="s.jpg", title="Gone", legal_hold=True,
              sha256="c" * 64, deleted_at=when)
    db.add(p)
    db.commit()
    return p


def test_unchanged_soft_deleted_held_photo_needs_no_confirmation(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    from datetime import datetime, timezone
    _env(tmp_path, monkeypatch)
    _soft_deleted_photo(db, datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
    archive = _archive(db)

    resp = _post(client, admin_headers, archive)

    assert resp.status_code == 200, resp.text


def test_different_deleted_at_of_held_photo_is_flagged(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    from datetime import datetime, timezone
    _env(tmp_path, monkeypatch)
    photo = _soft_deleted_photo(db, datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
    archive = _archive(db)
    photo.deleted_at = datetime(2026, 2, 2, 3, 4, 5, tzinfo=timezone.utc)
    db.commit()

    assert _post(client, admin_headers, archive).status_code == 409


def test_changed_metadata_of_held_photo_is_flagged(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    for field, value in (("title", "Renamed"), ("original_filename", "other.jpg"), ("file_size", 99)):
        photo = _held_photo(db)
        archive = _archive(db)
        setattr(photo, field, value)
        db.commit()
        assert _post(client, admin_headers, archive).status_code == 409, field
        db.delete(photo)
        db.commit()


def _held_doc(db):
    doc = Document(entity_type="general", document_type="other", title="Report",
                   filename="r.pdf", file_path="documents/r.pdf", mime_type="application/pdf",
                   file_size_bytes=10, legal_hold=True, sha256="d" * 64)
    db.add(doc)
    db.commit()
    return doc


def test_unchanged_held_document_needs_no_confirmation(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    _held_doc(db)
    archive = _archive(db)

    assert _post(client, admin_headers, archive).status_code == 200


def test_changed_held_document_needs_confirmation(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    for field, value in (("title", "Renamed"), ("file_size_bytes", 11), ("sha256", "e" * 64)):
        doc = _held_doc(db)
        archive = _archive(db)
        setattr(doc, field, value)
        db.commit()
        resp = _post(client, admin_headers, archive)
        assert resp.status_code == 409, field
        assert resp.json()["held_items"][0]["type"] == "document"
        db.delete(doc)
        db.commit()


def test_old_backup_without_metadata_keys_is_not_flagged(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    _held_photo(db)
    archive = _archive(db)
    src = zipfile.ZipFile(io.BytesIO(archive))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name in src.namelist():
            data = src.read(name)
            if name == "database.json":
                d = json.loads(data)
                for r in d["photos"]:
                    for k in ("title", "file_size"):
                        r.pop(k, None)
                data = json.dumps(d)
            zf.writestr(name, data)

    assert _post(client, admin_headers, out.getvalue()).status_code == 200


def _with_telemetry(archive, telemetry: bytes) -> bytes:
    buf = io.BytesIO(archive)
    with zipfile.ZipFile(buf, "a") as zf:
        zf.writestr("telemetry.json", telemetry)
    return buf.getvalue()


def _summary(db):
    summaries = _audit(db, action="import", entity_type="backup")
    assert len(summaries) == 1
    return summaries[0]


def test_restore_summary_says_what_was_restored(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    archive = _with_telemetry(_archive(db), b"[]")

    assert _post(client, admin_headers, archive).status_code == 200

    details = _summary(db).details
    assert "tables=" in details
    assert "rows=" in details
    assert "telemetry_points=0" in details
    assert "files=0" in details
    assert "pending" not in details


def test_truncated_telemetry_still_leaves_the_summary(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    db.add(AuditLog(user_name="Old Timer", action="create", entity_type="pilot", entity_id=1))
    db.add(Pilot(first_name="In", last_name="Backup", status="active"))
    db.commit()
    archive = _with_telemetry(_archive(db), b'[{"id": 1, "flight_id"')
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        backup_date = json.loads(zf.read("manifest.json"))["export_date"][:10]
    db.query(AuditLog).delete()
    db.query(Pilot).filter(Pilot.first_name == "In").delete()
    db.commit()

    resp = _post(client, admin_headers, archive)

    assert resp.status_code == 500
    db.expire_all()
    assert db.query(Pilot).filter_by(first_name="In").count() == 1
    summary = _summary(db)
    assert summary.imported is False
    assert backup_date in summary.details
    assert "audit_rows=1" in summary.details
    assert "tables=" in summary.details
    assert "rows=" in summary.details
    assert "telemetry=failed" in summary.details
    assert "files=not restored" in summary.details


def test_restore_failing_after_the_main_tables_leaves_a_working_login(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    from tests.conftest import ADMIN_PASSWORD
    _env(tmp_path, monkeypatch)
    archive = _with_telemetry(_archive(db), b'[{"id": 1, "flight_id"')

    resp = _post(client, admin_headers, archive)

    assert resp.status_code == 500
    login = client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert login.status_code == 200


def _blank_hashes(archive: bytes) -> bytes:
    """The archive as a backup from before password hashes were included."""
    src = zipfile.ZipFile(io.BytesIO(archive))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name in src.namelist():
            data = src.read(name)
            if name == "database.json":
                tables = json.loads(data)
                for row in tables["users"]:
                    row["password_hash"] = ""
                data = json.dumps(tables)
            zf.writestr(name, data)
    return out.getvalue()


def test_blank_hash_restore_failing_after_the_main_tables_leaves_an_install_token(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    archive = _with_telemetry(_blank_hashes(_archive(db)), b'[{"id": 1, "flight_id"')

    resp = _post(client, admin_headers, archive)

    assert resp.status_code == 500
    assert (tmp_path / "install_token.txt").read_text().strip()


def test_uploads_failing_still_leaves_the_summary(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    archive = _archive(db)

    def refuse(_zf, _upload_dir):
        raise RuntimeError("disk full")

    monkeypatch.setattr(backup_router, "_restore_uploads", refuse)

    with pytest.raises(RuntimeError):
        _post(client, admin_headers, archive)

    assert "files=failed" in _summary(db).details


def test_restore_that_cannot_write_its_summary_changes_nothing(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    archive = _archive(db)
    db.add(Pilot(first_name="After", last_name="Backup", status="active"))
    db.commit()
    with database.engine.begin() as conn:
        conn.execute(text(
            "CREATE TRIGGER block_summary BEFORE INSERT ON audit_logs WHEN NEW.entity_type = 'backup' "
            "BEGIN SELECT RAISE(ABORT, 'audit write refused'); END"))

    assert _post(client, admin_headers, archive).status_code >= 400

    db.expire_all()
    assert db.query(Pilot).filter_by(first_name="After").count() == 1
    assert db.get(User, admin_user.id).password_hash


def test_held_item_and_summary_entries_name_the_acting_user(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    archive = _archive(db)
    _held_photo(db)

    assert _post(client, admin_headers, archive, confirm_holds=CONFIRM).status_code == 200

    held = _audit(db, action="restore_held_item")
    assert len(held) == 1
    assert held[0].user_username == admin_user.username
    assert _summary(db).user_username == admin_user.username
