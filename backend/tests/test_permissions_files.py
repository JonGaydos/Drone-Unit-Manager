"""Document, photo and media routes enforce the role permission grid."""

import os
import time
from datetime import datetime

import pytest

from app.config import settings
from app.models.certification import CertificationType, PilotCertification
from app.models.document import Document
from app.models.media import MediaFile
from app.models.photo import Photo
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.routers.photos import _sign_photo
from app.services.permissions import LEVEL, REGISTRY

PERMISSIONS_URL = "/api/permissions"
DOCS_URL = "/api/documents"
UPLOAD_URL = "/api/documents/upload"
PHOTOS_URL = "/api/photos"
MEDIA_URL = "/api/media"
DELETED = "deleted"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f8f0000000049454e44ae42"
    "6082"
)


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    monkeypatch.setattr("app.routers.photos.UPLOAD_DIR", str(photos_dir))
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return str(photos_dir)


def _grid(client, headers, *changes):
    body = {"changes": [{"role": r, "key": k, "value": v} for r, k, v in changes]}
    resp = client.put(PERMISSIONS_URL, headers=headers, json=body)
    assert resp.status_code == 200, resp.text


def _upload(client, headers, entity_type="general", entity_id=None):
    data = {"entity_type": entity_type, "document_type": "other", "title": "Doc"}
    if entity_id is not None:
        data["entity_id"] = str(entity_id)
    return client.post(UPLOAD_URL, headers=headers, data=data,
                       files={"file": ("doc.pdf", b"%PDF-1.4 test", "application/pdf")})


def _upload_photo(client, headers, **data):
    return client.post(f"{PHOTOS_URL}/upload", headers=headers, data=data,
                       files={"file": ("p.png", PNG, "image/png")})


def _other_pilot(db):
    pilot = Pilot(first_name="Other", last_name="Pilot")
    db.add(pilot)
    db.commit()
    db.refresh(pilot)
    return pilot


def _certification(db, pilot_id):
    cert_type = CertificationType(name=f"Type {pilot_id}", category="faa")
    db.add(cert_type)
    db.flush()
    cert = PilotCertification(pilot_id=pilot_id, certification_type_id=cert_type.id)
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


def _doc(db, uploaded_by_id=None, **kwargs):
    doc = Document(entity_type=kwargs.pop("entity_type", "general"), document_type="other", title="Doc",
                   filename="d.pdf", file_path="/nonexistent/d.pdf", mime_type="application/pdf",
                   file_size_bytes=1, uploaded_by_id=uploaded_by_id, **kwargs)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _photo(db, uploaded_by_id=None, **kwargs):
    kwargs.setdefault("filename", "p.png")
    photo = Photo(original_filename="p.png", mime_type="image/png", uploaded_by_id=uploaded_by_id, **kwargs)
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


def _view_off(client, admin_headers):
    """Pilot with files.view off, and every pilot key that needs it off too."""
    changes = [("pilot", "files.view", "no")]
    for key, definition in REGISTRY.items():
        if definition.requires == "files.view":
            lowest = "none" if definition.kind == LEVEL else "no"
            changes.append(("pilot", key, lowest))
    _grid(client, admin_headers, *changes)


def test_upload_sets_uploaded_by(client, db, pilot_headers, pilot_user, upload_dir):
    resp = _upload(client, pilot_headers)
    assert resp.status_code == 200, resp.text
    assert db.get(Document, resp.json()["id"]).uploaded_by_id == pilot_user.id


def test_own_upload_general_vehicle_and_own_record_allowed(client, db, pilot_headers, linked_pilot, upload_dir):
    cert = _certification(db, linked_pilot.id)
    assert _upload(client, pilot_headers).status_code == 200
    vehicle = Vehicle(serial_number="SN1", manufacturer="Acme", model="X1", status="active")
    db.add(vehicle)
    db.commit()
    assert _upload(client, pilot_headers, "vehicle", vehicle.id).status_code == 200
    assert _upload(client, pilot_headers, "pilot", linked_pilot.id).status_code == 200
    assert _upload(client, pilot_headers, "certification", cert.id).status_code == 200
    assert _upload_photo(client, pilot_headers).status_code == 200


def test_own_upload_other_pilot_record_refused(client, db, pilot_headers, linked_pilot, upload_dir):
    other = _other_pilot(db)
    cert = _certification(db, other.id)
    assert _upload(client, pilot_headers, "pilot", other.id).status_code == 403
    assert _upload(client, pilot_headers, "certification", cert.id).status_code == 403


def test_photo_tags_naming_other_pilots_allowed_at_own(client, db, pilot_headers, upload_dir):
    other = _other_pilot(db)
    assert _upload_photo(client, pilot_headers, pilot_ids=str(other.id)).status_code == 200


def test_all_upload_any_record(client, db, supervisor_headers, admin_headers, upload_dir):
    other = _other_pilot(db)
    cert = _certification(db, other.id)
    for headers in (supervisor_headers, admin_headers):
        assert _upload(client, headers, "pilot", other.id).status_code == 200
        assert _upload(client, headers, "certification", cert.id).status_code == 200


def test_upload_none_refused_for_documents_and_photos(client, admin_headers, pilot_headers, viewer_headers, upload_dir):
    _grid(client, admin_headers, ("pilot", "files.upload", "none"))
    assert _upload(client, pilot_headers).status_code == 403
    assert _upload_photo(client, pilot_headers).status_code == 403
    assert _upload(client, viewer_headers).status_code == 403


def test_document_without_uploader_needs_all(client, db, pilot_headers, supervisor_headers):
    doc = _doc(db)
    assert client.patch(f"{DOCS_URL}/{doc.id}", headers=pilot_headers, json={"title": "X"}).status_code == 403
    assert client.delete(f"{DOCS_URL}/{doc.id}", headers=pilot_headers).status_code == 403
    assert client.patch(f"{DOCS_URL}/{doc.id}", headers=supervisor_headers, json={"title": "X"}).status_code == 200


def test_pilot_edit_and_soft_delete_own_only(client, db, pilot_headers, pilot_user, supervisor_user, linked_pilot):
    mine = _doc(db, pilot_user.id)
    attached = _doc(db, supervisor_user.id, entity_type="pilot", entity_id=linked_pilot.id, pilot_id=linked_pilot.id)
    theirs = _doc(db, supervisor_user.id)
    for doc in (mine, attached):
        assert client.patch(f"{DOCS_URL}/{doc.id}", headers=pilot_headers, json={"title": "X"}).status_code == 200
    assert client.patch(f"{DOCS_URL}/{theirs.id}", headers=pilot_headers, json={"title": "X"}).status_code == 403
    assert client.delete(f"{DOCS_URL}/{theirs.id}", headers=pilot_headers).status_code == 403
    assert client.delete(f"{DOCS_URL}/{mine.id}", headers=pilot_headers).status_code == 200

    my_photo = _photo(db, pilot_user.id)
    other_photo = _photo(db, supervisor_user.id)
    assert client.patch(f"{PHOTOS_URL}/{my_photo.id}", headers=pilot_headers, data={"title": "X"}).status_code == 200
    assert client.patch(f"{PHOTOS_URL}/{other_photo.id}", headers=pilot_headers, data={"title": "X"}).status_code == 403
    assert client.delete(f"{PHOTOS_URL}/{other_photo.id}", headers=pilot_headers).status_code == 403
    assert client.delete(f"{PHOTOS_URL}/{my_photo.id}", headers=pilot_headers).status_code == 200


def test_document_on_a_certification_follows_its_pilot(client, db, pilot_headers, supervisor_user, linked_pilot):
    def on_certification_of(pilot_id):
        cert_id = _certification(db, pilot_id).id
        return _doc(db, supervisor_user.id, entity_type="certification", certification_id=cert_id)

    mine = on_certification_of(linked_pilot.id)
    theirs = on_certification_of(_other_pilot(db).id)
    assert client.patch(f"{DOCS_URL}/{mine.id}", headers=pilot_headers, json={"title": "X"}).status_code == 200
    assert client.patch(f"{DOCS_URL}/{theirs.id}", headers=pilot_headers, json={"title": "X"}).status_code == 403


def test_edit_none_refuses_own_records(client, db, admin_headers, pilot_headers, pilot_user):
    _grid(client, admin_headers, ("pilot", "files.edit", "none"))
    doc = _doc(db, pilot_user.id)
    assert client.delete(f"{DOCS_URL}/{doc.id}", headers=pilot_headers).status_code == 403


def test_legal_hold_blocks_delete_even_with_all(client, db, admin_headers, supervisor_headers):
    doc = _doc(db, legal_hold=True)
    photo = _photo(db, legal_hold=True)
    for headers in (supervisor_headers, admin_headers):
        assert client.delete(f"{DOCS_URL}/{doc.id}", headers=headers).status_code == 409
        assert client.delete(f"{PHOTOS_URL}/{photo.id}", headers=headers).status_code == 409


def test_custody_routes_refused_for_pilot(client, db, pilot_headers, supervisor_headers):
    doc = _doc(db, deleted_at=datetime(2026, 1, 1))
    photo = _photo(db, deleted_at=datetime(2026, 1, 1))
    for base, item in ((DOCS_URL, doc), (PHOTOS_URL, photo)):
        assert client.get(f"{base}/deleted", headers=pilot_headers).status_code == 403
        assert client.post(f"{base}/{item.id}/restore", headers=pilot_headers).status_code == 403
        assert client.put(f"{base}/{item.id}/hold", headers=pilot_headers, json={"legal_hold": True}).status_code == 403
        assert client.get(f"{base}/deleted", headers=supervisor_headers).status_code == 200
    live = _photo(db)
    assert client.post(f"{PHOTOS_URL}/{live.id}/incident/1", headers=pilot_headers).status_code == 403
    assert client.delete(f"{PHOTOS_URL}/{live.id}/flight/1", headers=pilot_headers).status_code == 403


def test_custody_granted_to_pilot_works(client, db, admin_headers, pilot_headers):
    _grid(client, admin_headers, ("pilot", "files.custody", "yes"))
    doc = _doc(db)
    resp = client.put(f"{DOCS_URL}/{doc.id}/hold", headers=pilot_headers, json={"legal_hold": True})
    assert resp.status_code == 200


def test_purge_admin_only(client, db, supervisor_headers, admin_headers):
    doc = _doc(db, deleted_at=datetime(2026, 1, 1))
    photo = _photo(db, deleted_at=datetime(2026, 1, 1))
    assert client.delete(f"{DOCS_URL}/{doc.id}/purge", headers=supervisor_headers).status_code == 403
    assert client.delete(f"{PHOTOS_URL}/{photo.id}/purge", headers=supervisor_headers).status_code == 403
    assert client.delete(f"{DOCS_URL}/{doc.id}/purge", headers=admin_headers).status_code == 200
    assert client.delete(f"{PHOTOS_URL}/{photo.id}/purge", headers=admin_headers).status_code == 200


def test_view_off_blocks_list_view_and_signed_url_minting(client, db, admin_headers, pilot_headers):
    doc = _doc(db)
    photo = _photo(db)
    assert client.get(PHOTOS_URL, headers=pilot_headers).status_code == 200
    _view_off(client, admin_headers)
    assert client.get(DOCS_URL, headers=pilot_headers).status_code == 403
    assert client.get(f"{DOCS_URL}/{doc.id}/view", headers=pilot_headers).status_code == 403
    assert client.get(PHOTOS_URL, headers=pilot_headers).status_code == 403
    assert client.get(f"{PHOTOS_URL}/{photo.id}/signed-urls", headers=pilot_headers).status_code == 403
    assert client.get(MEDIA_URL, headers=pilot_headers).status_code == 403
    assert client.get(f"{MEDIA_URL}/count", headers=pilot_headers).status_code == 403


def test_view_off_blocks_serving_by_login_token(client, db, admin_headers, pilot_headers, upload_dir):
    photo = _photo(db, filename="served.png")
    with open(os.path.join(upload_dir, "served.png"), "wb") as f:
        f.write(PNG)
    assert client.get(f"{PHOTOS_URL}/{photo.id}/view", headers=pilot_headers).status_code == 200
    _view_off(client, admin_headers)
    for action in ("view", "thumbnail"):
        assert client.get(f"{PHOTOS_URL}/{photo.id}/{action}", headers=pilot_headers).status_code == 403


def test_issued_signed_url_still_valid_until_expiry(client, db, admin_headers, pilot_headers, upload_dir):
    photo = _photo(db, filename="served.png")
    with open(os.path.join(upload_dir, "served.png"), "wb") as f:
        f.write(PNG)
    urls = client.get(f"{PHOTOS_URL}/{photo.id}/signed-urls", headers=pilot_headers).json()
    _view_off(client, admin_headers)
    assert client.get("/api" + urls["view_url"]).status_code == 200
    assert client.get("/api" + urls["thumbnail_url"]).status_code == 200
    sig, exp = _sign_photo(photo.id, "view", ttl=-10)
    assert exp < int(time.time())
    assert client.get(f"{PHOTOS_URL}/{photo.id}/view?sig={sig}&exp={exp}").status_code == 401


def test_media_delete_needs_all(client, db, admin_headers, pilot_headers, supervisor_headers):
    def media():
        row = MediaFile(filename="m.mp4", kind="video")
        db.add(row)
        db.commit()
        return row.id

    assert client.delete(f"{MEDIA_URL}/{media()}", headers=pilot_headers).status_code == 403
    _grid(client, admin_headers, ("pilot", "files.edit", "own"))
    assert client.delete(f"{MEDIA_URL}/{media()}", headers=pilot_headers).status_code == 403
    _grid(client, admin_headers, ("supervisor", "files.edit", "own"))
    assert client.delete(f"{MEDIA_URL}/{media()}", headers=supervisor_headers).status_code == 403
    _grid(client, admin_headers, ("supervisor", "files.edit", "all"))
    assert client.delete(f"{MEDIA_URL}/{media()}", headers=supervisor_headers).status_code == 200
