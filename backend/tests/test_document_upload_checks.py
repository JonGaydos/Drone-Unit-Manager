"""Document upload naming and linking checks (D-22).

* Directory parts are stripped from the file name, whichever slash they use.
* A .pdf or image upload must carry that type's signature.
* entity_id must name an existing record, and a general document takes none.
"""

import io

import pytest
from PIL import Image

from app.config import settings
from app.models.battery import Battery
from app.models.document import Document

UPLOAD_URL = "/api/documents/upload"
PDF = b"%PDF-1.4 form"


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    updir = tmp_path / "uploads"
    updir.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(updir))
    return updir


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(buf, format="PNG")
    return buf.getvalue()


def _upload(client, headers, filename="form.pdf", content=PDF, entity_type="general", entity_id=None):
    data = {"entity_type": entity_type, "document_type": "other", "title": "Form"}
    if entity_id is not None:
        data["entity_id"] = str(entity_id)
    return client.post(UPLOAD_URL, headers=headers, data=data,
                       files={"file": (filename, content, "application/octet-stream")})


@pytest.mark.parametrize("filename", [r"..\..\notes.txt", "../../notes.txt", r"C:\Users\x\notes.txt", r"a/b\notes.txt"])
def test_directory_parts_are_stripped(client, admin_headers, upload_dir, filename):
    resp = _upload(client, admin_headers, filename=filename, content=b"plain text")

    assert resp.status_code == 200, resp.text
    assert resp.json()["filename"] == "notes.txt"


@pytest.mark.parametrize("filename, content", [
    ("form.pdf", b"just text"),
    ("photo.png", b"just text"),
    ("photo.jpg", None),  # PNG bytes named .jpg
])
def test_content_must_match_a_pdf_or_image_extension(client, db, admin_headers, upload_dir, filename, content):
    resp = _upload(client, admin_headers, filename=filename, content=content if content is not None else _png())

    assert resp.status_code == 400
    db.expire_all()
    assert db.query(Document).count() == 0


@pytest.mark.parametrize("filename, content", [
    ("form.pdf", PDF),
    ("photo.png", None),
    ("notes.txt", b"plain text"),
])
def test_matching_content_is_accepted(client, admin_headers, upload_dir, filename, content):
    resp = _upload(client, admin_headers, filename=filename, content=content if content is not None else _png())

    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize("entity_type", [
    "pilot", "vehicle", "certification", "battery", "controller", "dock", "sensor",
    "attachment", "other", "maintenance", "maintenance_schedule", "operating_authority",
])
def test_missing_entity_is_refused(client, db, admin_headers, upload_dir, entity_type):
    resp = _upload(client, admin_headers, entity_type=entity_type, entity_id=999999)

    assert resp.status_code == 404
    db.expire_all()
    assert db.query(Document).count() == 0


def test_existing_entity_is_accepted(client, db, admin_headers, upload_dir):
    battery = Battery(serial_number="DOC-CHECK-1")
    db.add(battery)
    db.commit()

    resp = _upload(client, admin_headers, entity_type="battery", entity_id=battery.id)

    assert resp.status_code == 200, resp.text
    assert resp.json()["entity_id"] == battery.id


def test_general_document_takes_no_entity_id(client, db, admin_headers, upload_dir):
    resp = _upload(client, admin_headers, entity_type="general", entity_id=5)

    assert resp.status_code == 400
    db.expire_all()
    assert db.query(Document).count() == 0
