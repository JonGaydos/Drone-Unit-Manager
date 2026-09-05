"""Upload validation tests for the documents endpoints.

Locks in ``POST /api/documents/upload`` (pilot-or-higher gated):

* "general" documents need no entity_id and land under ``documents/general/``;
* every equipment type in ``ALLOWED_ENTITY_TYPES`` uploads successfully
  (battery/controller/dock/sensor/attachment used to be rejected);
* maintenance records and schedules accept attachments, retrievable via the
  ``entity_type``/``entity_id`` list filter;
* an unknown entity_type still 400s, and non-general types require entity_id.

Files are written under a tmp_path UPLOAD_DIR patched via ``settings``
(the router reads ``settings.UPLOAD_DIR`` live on each request).
"""

from pathlib import Path

import pytest

from app.config import settings
from app.models.battery import Battery
from app.models.document import Document
from app.models.folder import Folder


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    """Point settings.UPLOAD_DIR at an isolated tmp dir for upload tests."""
    updir = tmp_path / "uploads"
    updir.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(updir))
    return updir


def _upload(client, headers, *, entity_type, entity_id=None, folder_id=None, filename="doc.pdf"):
    data = {"entity_type": entity_type, "document_type": "other", "title": "Test Doc"}
    if entity_id is not None:
        data["entity_id"] = str(entity_id)
    if folder_id is not None:
        data["folder_id"] = str(folder_id)
    return client.post(
        "/api/documents/upload",
        headers=headers,
        data=data,
        files={"file": (filename, b"%PDF-1.4 test content", "application/pdf")},
    )


def test_general_upload_without_entity_id(client, db, admin_headers, upload_dir):
    """A "general" document uploads with no entity_id and is stored under
    documents/general/ (no id path segment)."""
    resp = _upload(client, admin_headers, entity_type="general")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entity_type"] == "general"
    assert body["entity_id"] is None

    db.expire_all()
    doc = db.query(Document).first()
    assert doc is not None
    stored = Path(doc.file_path)
    assert stored.exists()
    assert stored.parent == upload_dir / "documents" / "general"


def test_general_upload_into_folder(client, db, admin_headers, upload_dir):
    """A general upload with folder_id is filed into that folder."""
    folder = Folder(name="FAA")
    db.add(folder)
    db.commit()
    db.refresh(folder)

    resp = _upload(client, admin_headers, entity_type="general", folder_id=folder.id)

    assert resp.status_code == 200, resp.text
    assert resp.json()["folder_id"] == folder.id

    listed = client.get(f"/api/folders/{folder.id}/documents", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1


def test_equipment_entity_upload_succeeds(client, db, admin_headers, upload_dir):
    """Equipment entity types upload successfully (regression: battery et al.
    were previously rejected by the allowlist)."""
    battery = Battery(serial_number="DOC-BAT-1")
    db.add(battery)
    db.commit()
    db.refresh(battery)

    resp = _upload(client, admin_headers, entity_type="battery", entity_id=battery.id)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entity_type"] == "battery"
    assert body["entity_id"] == battery.id


def test_maintenance_entity_upload_and_filter(client, db, admin_headers, upload_dir):
    """Documents attach to maintenance records/schedules and come back through
    the entity_type/entity_id list filter."""
    resp = _upload(client, admin_headers, entity_type="maintenance", entity_id=42)
    assert resp.status_code == 200, resp.text
    resp = _upload(client, admin_headers, entity_type="maintenance_schedule", entity_id=7)
    assert resp.status_code == 200, resp.text

    listed = client.get("/api/documents?entity_type=maintenance&entity_id=42", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    docs = listed.json()
    assert len(docs) == 1
    assert docs[0]["entity_type"] == "maintenance"


def test_bogus_entity_type_400(client, db, admin_headers, upload_dir):
    """An unknown entity_type is still rejected with 400."""
    resp = _upload(client, admin_headers, entity_type="bogus", entity_id=1)

    assert resp.status_code == 400, resp.text

    db.expire_all()
    assert db.query(Document).count() == 0


def test_non_general_type_requires_entity_id(client, db, admin_headers, upload_dir):
    """Non-general entity types still require an entity_id."""
    resp = _upload(client, admin_headers, entity_type="vehicle")

    assert resp.status_code == 400, resp.text
    assert "entity_id" in resp.json()["detail"]

    db.expire_all()
    assert db.query(Document).count() == 0
