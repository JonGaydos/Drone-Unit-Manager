"""Documents and folders cannot be filed into a deleted or missing folder.

Folder delete is soft, so a deleted folder's id still exists. A document or
folder pointed at it would show in no folder at all; each route answers 404.
"""

import pytest

from app.config import settings
from app.models.document import Document
from app.models.folder import Folder

FOLDERS_URL = "/api/folders"
UPLOAD_URL = "/api/documents/upload"


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    updir = tmp_path / "uploads"
    updir.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(updir))
    return updir


def _folder(client, headers, name, parent_id=None):
    resp = client.post(FOLDERS_URL, headers=headers, json={"name": name, "parent_id": parent_id})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _deleted_folder(client, headers):
    folder_id = _folder(client, headers, "Old Forms")
    assert client.delete(f"{FOLDERS_URL}/{folder_id}", headers=headers).status_code == 200
    return folder_id


def _upload(client, headers, folder_id=None):
    data = {"entity_type": "general", "document_type": "other", "title": "Form"}
    if folder_id is not None:
        data["folder_id"] = str(folder_id)
    return client.post(UPLOAD_URL, headers=headers, data=data,
                       files={"file": ("form.pdf", b"%PDF-1.4 form", "application/pdf")})


def test_move_into_a_deleted_folder_is_refused(client, db, admin_headers, upload_dir):
    doc_id = _upload(client, admin_headers).json()["id"]
    gone = _deleted_folder(client, admin_headers)

    resp = client.patch(f"/api/documents/{doc_id}", headers=admin_headers, json={"folder_id": gone})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Folder not found"
    db.expire_all()
    assert db.get(Document, doc_id).folder_id is None


def test_move_into_a_missing_folder_is_refused(client, admin_headers, upload_dir):
    doc_id = _upload(client, admin_headers).json()["id"]

    resp = client.patch(f"/api/documents/{doc_id}", headers=admin_headers, json={"folder_id": 999999})

    assert resp.status_code == 404


def test_move_to_a_live_folder_and_back_to_unfiled(client, admin_headers, upload_dir):
    doc_id = _upload(client, admin_headers).json()["id"]
    folder_id = _folder(client, admin_headers, "Forms")

    moved = client.patch(f"/api/documents/{doc_id}", headers=admin_headers, json={"folder_id": folder_id})
    assert moved.status_code == 200
    assert moved.json()["folder_id"] == folder_id

    unfiled = client.patch(f"/api/documents/{doc_id}", headers=admin_headers, json={"folder_id": None})
    assert unfiled.status_code == 200
    assert unfiled.json()["folder_id"] is None


def test_upload_into_a_deleted_folder_is_refused(client, db, admin_headers, upload_dir):
    gone = _deleted_folder(client, admin_headers)

    resp = _upload(client, admin_headers, folder_id=gone)

    assert resp.status_code == 404
    db.expire_all()
    assert db.query(Document).count() == 0
    assert not any(p.is_file() for p in upload_dir.rglob("*"))


def test_new_folder_under_a_deleted_parent_is_refused(client, db, admin_headers):
    gone = _deleted_folder(client, admin_headers)

    resp = client.post(FOLDERS_URL, headers=admin_headers, json={"name": "Child", "parent_id": gone})

    assert resp.status_code == 404
    db.expire_all()
    assert db.query(Folder).filter(Folder.name == "Child").count() == 0


def test_new_folder_under_a_missing_parent_is_refused(client, admin_headers):
    resp = client.post(FOLDERS_URL, headers=admin_headers, json={"name": "Child", "parent_id": 999999})

    assert resp.status_code == 404


def test_new_folder_under_a_live_parent(client, db, admin_headers):
    parent = _folder(client, admin_headers, "Parent")

    child = _folder(client, admin_headers, "Child", parent_id=parent)

    db.expire_all()
    assert db.get(Folder, child).parent_id == parent
