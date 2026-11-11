"""A legal hold freezes a document's or photo's metadata.

Delete and purge were already refused while held; editing the title, type,
notes or description is refused too (409). A held document can still be moved
between folders, which changes where it is filed, not what it says.
"""

import pytest

from app.config import settings
from app.models.document import Document
from app.models.photo import Photo

HELD = "This item is on legal hold. Release the hold before editing it."


@pytest.fixture
def held_doc(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    doc = Document(entity_type="general", document_type="other", title="Statement", filename="s.pdf",
                   file_path=str(tmp_path / "s.pdf"), mime_type="application/pdf", file_size_bytes=1,
                   notes="Original", legal_hold=True)
    db.add(doc)
    db.commit()
    return doc.id


@pytest.mark.parametrize("change", [{"notes": "Edited"}, {"title": "Edited"}, {"document_type": "manual"}])
def test_held_document_metadata_cannot_change(client, db, admin_headers, held_doc, change):
    resp = client.patch(f"/api/documents/{held_doc}", headers=admin_headers, json=change)

    assert resp.status_code == 409
    assert resp.json()["detail"] == HELD
    db.expire_all()
    doc = db.get(Document, held_doc)
    assert (doc.title, doc.notes, doc.document_type) == ("Statement", "Original", "other")


def test_held_document_can_move_folders(client, db, admin_headers, held_doc):
    folder_id = client.post("/api/folders", headers=admin_headers, json={"name": "Case"}).json()["id"]

    resp = client.patch(f"/api/documents/{held_doc}", headers=admin_headers, json={"folder_id": folder_id})

    assert resp.status_code == 200, resp.text
    assert resp.json()["folder_id"] == folder_id


def test_released_document_can_be_edited(client, admin_headers, held_doc):
    client.put(f"/api/documents/{held_doc}/hold", headers=admin_headers, json={"legal_hold": False})

    resp = client.patch(f"/api/documents/{held_doc}", headers=admin_headers, json={"notes": "Edited"})

    assert resp.status_code == 200
    assert resp.json()["notes"] == "Edited"


def test_held_photo_metadata_cannot_change(client, db, admin_headers):
    photo = Photo(filename="p.png", original_filename="p.png", mime_type="image/png",
                  title="Scene", legal_hold=True)
    db.add(photo)
    db.commit()

    resp = client.patch(f"/api/photos/{photo.id}", headers=admin_headers, files={"title": (None, "Edited")})

    assert resp.status_code == 409
    assert resp.json()["detail"] == HELD
    db.expire_all()
    assert db.get(Photo, photo.id).title == "Scene"
