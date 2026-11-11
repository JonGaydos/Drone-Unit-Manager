"""A restore onto an install that has a usable login needs a typed confirmation.

Restoring replaces every table, user, token, setting and uploaded file, and
signs everyone out. An admin JWT alone used to be enough, so one stray request
replaced a live install with no warning. A fresh install (install-token path,
no usable login) restores without the extra step.
"""

from sqlalchemy import text

from app.config import settings as app_settings
from app.models.pilot import Pilot
from app.routers.backup import CONFIRM_RESTORE_TEXT, EXPORT_ORDER, _install_token_path, build_backup_archive

IMPORT_URL = "/api/backup/import"


def _env(tmp_path, monkeypatch):
    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(app_settings, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)


def _post(client, headers, archive, **form):
    return client.post(IMPORT_URL, headers=headers, data=form,
                       files={"file": ("b.zip", archive, "application/zip")})


def test_restore_on_a_live_install_needs_the_typed_confirmation(
        client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    archive = build_backup_archive(db, include_telemetry=False)[0].read()
    db.add(Pilot(first_name="Added", last_name="Later", status="active"))
    db.commit()

    resp = _post(client, admin_headers, archive)

    assert resp.status_code == 409
    body = resp.json()
    assert body["confirm_restore_text"] == CONFIRM_RESTORE_TEXT == "REPLACE ALL DATA"
    assert "signs everyone out" in body["detail"]
    db.expire_all()
    assert db.query(Pilot).filter_by(last_name="Later").count() == 1

    wrong = _post(client, admin_headers, archive, confirm_restore="replace all data")
    assert wrong.status_code == 409
    db.expire_all()
    assert db.query(Pilot).filter_by(last_name="Later").count() == 1

    ok = _post(client, admin_headers, archive, confirm_restore=CONFIRM_RESTORE_TEXT)
    assert ok.status_code == 200, ok.text
    db.expire_all()
    assert db.query(Pilot).filter_by(last_name="Later").count() == 0


def test_restore_on_a_fresh_install_needs_no_confirmation(client, db, admin_user, tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    archive = build_backup_archive(db, include_telemetry=False)[0].read()
    db.execute(text("PRAGMA foreign_keys=OFF"))
    for _name, model in EXPORT_ORDER:
        db.execute(model.__table__.delete())
    db.commit()
    with open(_install_token_path(), "w") as f:
        f.write("fresh-token")

    resp = _post(client, {"X-Install-Token": "fresh-token"}, archive)

    assert resp.status_code == 200, resp.text
