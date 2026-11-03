"""Backup and restore of role permissions."""

import io
import json
import zipfile

from app.config import settings as app_settings
from app.models.document import Document
from app.models.role_permission import RolePermission
from app.routers.backup import DATABASE_FILE, build_backup_archive
from app.services import permissions

IMPORT_URL = "/api/backup/import"


def _store(db, role, key, value):
    db.add(RolePermission(role=role, permission_key=key, value=value))
    db.commit()


def _archive(db, edit=None):
    """A backup archive of the database, with database.json edited by `edit`."""
    spooled, _manifest = build_backup_archive(db, include_telemetry=False)
    if edit is None:
        return spooled.read()
    source = zipfile.ZipFile(spooled)
    tables = json.loads(source.read(DATABASE_FILE))
    edit(tables)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for name in source.namelist():
            data = json.dumps(tables) if name == DATABASE_FILE else source.read(name)
            target.writestr(name, data)
    return out.getvalue()


def _restore(client, headers, archive, tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(app_settings, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)
    resp = client.post(IMPORT_URL, headers=headers, files={"file": ("b.zip", archive, "application/zip")})
    assert resp.status_code == 200, resp.text


def _stored(db):
    db.expire_all()
    return {(r.role, r.permission_key): r.value for r in db.query(RolePermission).all()}


def _row(role, key, value, row_id):
    return {"id": row_id, "role": role, "permission_key": key, "value": value}


def test_backup_includes_role_permissions(db):
    _store(db, "pilot", "flights.delete", "own")
    spooled, manifest = build_backup_archive(db, include_telemetry=False)
    tables = json.loads(zipfile.ZipFile(spooled).read(DATABASE_FILE))
    assert manifest["tables"]["role_permissions"] == 1
    assert tables["role_permissions"][0]["permission_key"] == "flights.delete"


def test_restore_round_trip(client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    _store(db, "pilot", "flights.delete", "own")
    _store(db, "supervisor", "audit.view", "yes")
    archive = _archive(db)
    db.query(RolePermission).delete()
    _store(db, "viewer", "pilots.contacts", "yes")

    _restore(client, admin_headers, archive, tmp_path, monkeypatch)

    assert _stored(db) == {("pilot", "flights.delete"): "own", ("supervisor", "audit.view"): "yes"}


def test_older_backup_restores_defaults(client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    archive = _archive(db, lambda tables: tables.pop("role_permissions"))
    _store(db, "pilot", "flights.delete", "own")

    _restore(client, admin_headers, archive, tmp_path, monkeypatch)

    assert _stored(db) == {}
    assert permissions.get_value(db, "pilot", "flights.delete") == "none"


def test_restore_drops_locked_viewer_row(client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    rows = [_row("viewer", "flights.create", "yes", 1), _row("pilot", "flights.delete", "own", 2)]
    archive = _archive(db, lambda tables: tables.update(role_permissions=rows))

    _restore(client, admin_headers, archive, tmp_path, monkeypatch)

    assert _stored(db) == {("pilot", "flights.delete"): "own"}
    assert permissions.get_value(db, "viewer", "flights.create") == "no"


def test_restore_drops_unknown_key_invalid_value_and_admin(client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    rows = [
        _row("pilot", "nothing.here", "yes", 1),
        _row("pilot", "flights.delete", "maybe", 2),
        _row("admin", "flights.delete", "none", 3),
        _row("pilot", "flights.delete", "own", 4),
    ]
    archive = _archive(db, lambda tables: tables.update(role_permissions=rows))

    _restore(client, admin_headers, archive, tmp_path, monkeypatch)

    assert _stored(db) == {("pilot", "flights.delete"): "own"}


def _flights_values(db, role):
    return {key: permissions.get_value(db, role, key) for key in permissions.REGISTRY if key.startswith("flights.")}


def _assert_valid_grid(db):
    changes = [{"role": role, "key": key, "value": value} for (role, key), value in _stored(db).items()]
    assert permissions.validate_grid(db, changes) == []


def test_restore_forces_dependents_off_when_view_is_off(client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    rows = [_row("pilot", "flights.view", "no", 1), _row("pilot", "flights.create", "no", 2)]
    archive = _archive(db, lambda tables: tables.update(role_permissions=rows))

    _restore(client, admin_headers, archive, tmp_path, monkeypatch)

    values = _flights_values(db, "pilot")
    assert values == {key: ("no" if key != "flights.edit" and key != "flights.delete" else "none") for key in values}
    assert permissions.get_value(db, "pilot", "flights.edit") == "none"
    assert _flights_values(db, "supervisor")["flights.edit"] == "all"
    _assert_valid_grid(db)


def test_restore_forces_a_dropped_explicit_row_to_lowest(client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    rows = [_row("supervisor", "flights.view", "no", 1), _row("supervisor", "flights.edit", "own", 2)]
    archive = _archive(db, lambda tables: tables.update(role_permissions=rows))

    _restore(client, admin_headers, archive, tmp_path, monkeypatch)

    assert permissions.get_value(db, "supervisor", "flights.edit") == "none"
    assert permissions.get_value(db, "supervisor", "flights.review") == "no"
    _assert_valid_grid(db)


def test_older_backup_documents_restore_without_uploader(client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    db.add(Document(entity_type="general", document_type="other", title="T", filename="t.txt",
                    file_path="documents/t.txt", mime_type="text/plain", file_size_bytes=1,
                    uploaded_by_id=admin_user.id))
    db.commit()

    def drop_uploader(tables):
        for row in tables["documents"]:
            row.pop("uploaded_by_id")

    archive = _archive(db, drop_uploader)

    _restore(client, admin_headers, archive, tmp_path, monkeypatch)

    db.expire_all()
    assert db.query(Document).one().uploaded_by_id is None


def test_restorable_overrides_keeps_valid_rows_and_counts_drops():
    rows = [
        _row("supervisor", "flights.delete", "own", 1),
        _row("supervisor", "flights.delete", "none", 2),
        _row("pilot", "flights.view", "no", 3),
        _row("pilot", "flights.edit", "own", 4),
        {"id": 5, "role": None, "permission_key": ["x"], "value": "yes"},
    ]
    kept, dropped = permissions.restorable_overrides(rows + ["not a row", None])
    assert {(r["role"], r["permission_key"]): r["value"] for r in kept} == {
        ("supervisor", "flights.delete"): "none",
        ("pilot", "flights.view"): "no",
        ("pilot", "flights.create"): "no",
        ("pilot", "flights.edit"): "none",
    }
    assert dropped == 4
