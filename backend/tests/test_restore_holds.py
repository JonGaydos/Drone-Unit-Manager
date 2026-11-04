"""Restore and legal holds: a restore that would remove or change a held item
needs the typed confirmation, and restored audit entries are marked imported."""

import io
import json
import zipfile

from app.config import settings as app_settings
from app.models.audit_log import AuditLog
from app.models.pilot import Pilot
from app.models.photo import Photo
from app.models.document import Document
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
    assert len(rows) == 1 and rows[0].imported is True


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
    assert "2025-01-03" in summary.details and "audit_rows=2" in summary.details
