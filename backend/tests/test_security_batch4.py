"""Batch 4 evidence handling: soft delete, restore, legal hold, admin purge,
upload digests, and audited views, for photos, documents and folders."""

import hashlib
import io
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image

from app.config import settings
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.folder import Folder
from app.models.photo import Photo, PhotoFlight
from app.routers.auth import create_token
from tests.conftest import _seed_user

SUPERVISOR_PASSWORD = "SupervisorPassw0rd!"


def _bearer(user):
    return {"Authorization": f"Bearer {create_token(user.id, user.token_version)}"}


def _actions(db, entity_type, entity_id=None):
    q = db.query(AuditLog).filter(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        q = q.filter(AuditLog.entity_id == entity_id)
    return [e.action for e in q.order_by(AuditLog.id)]


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "blue").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def supervisor_user(db):
    return _seed_user(db, username="sup", role="supervisor", password=SUPERVISOR_PASSWORD)


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr("app.routers.photos.UPLOAD_DIR", str(tmp_path / "photos"))
    return tmp_path


@pytest.fixture
def photo(client, db, pilot_user, upload_dir):
    """A photo uploaded through the API and linked to a flight."""
    from app.models.flight import Flight
    content = _png()
    resp = client.post("/api/photos/upload", headers=_bearer(pilot_user),
                       files={"file": ("scene.png", content, "image/png")})
    assert resp.status_code == 200
    flight = Flight(date=date(2026, 9, 1))
    db.add(flight)
    db.commit()
    db.add(PhotoFlight(photo_id=resp.json()["id"], flight_id=flight.id))
    db.commit()
    p = db.get(Photo, resp.json()["id"])
    p.content = content
    return p


@pytest.fixture
def document(client, db, pilot_user, upload_dir):
    content = b"%PDF-1.4 warrant"
    resp = client.post("/api/documents/upload", headers=_bearer(pilot_user),
                       data={"entity_type": "general", "document_type": "other", "title": "Warrant"},
                       files={"file": ("warrant.pdf", content, "application/pdf")})
    assert resp.status_code == 200
    d = db.get(Document, resp.json()["id"])
    d.content = content
    return d


def _photo_file(photo):
    return settings.UPLOAD_DIR / "photos" / photo.filename


# 1. A delete hides, it does not destroy ------------------------------------------

def test_deleted_photo_is_hidden_but_kept_with_its_links(client, db, photo, pilot_user):
    assert client.delete(f"/api/photos/{photo.id}", headers=_bearer(pilot_user)).status_code == 200
    db.expire_all()
    assert _photo_file(photo).exists()
    assert db.query(PhotoFlight).filter(PhotoFlight.photo_id == photo.id).count() == 1
    assert client.get("/api/photos", headers=_bearer(pilot_user)).json() == []
    assert client.get(f"/api/photos/{photo.id}/view", headers=_bearer(pilot_user)).status_code == 404
    assert client.patch(f"/api/photos/{photo.id}", headers=_bearer(pilot_user),
                        data={"title": "x"}).status_code == 404


def test_supervisor_restores_a_photo_and_a_pilot_cannot(client, db, photo, pilot_user, supervisor_user):
    client.delete(f"/api/photos/{photo.id}", headers=_bearer(pilot_user))
    deleted = client.get("/api/photos/deleted", headers=_bearer(supervisor_user)).json()
    assert [(d["id"], d["deleted_by"]) for d in deleted] == [(photo.id, pilot_user.display_name)]

    assert client.post(f"/api/photos/{photo.id}/restore", headers=_bearer(pilot_user)).status_code == 403
    assert client.post(f"/api/photos/{photo.id}/restore", headers=_bearer(supervisor_user)).status_code == 200
    listed = client.get("/api/photos?flight_id=1", headers=_bearer(pilot_user)).json()
    assert [p["id"] for p in listed] == [photo.id]
    assert _actions(db, "photo", photo.id)[-2:] == ["delete", "restore"]


def test_deleted_document_is_hidden_and_restorable(client, db, document, pilot_user, supervisor_user):
    assert client.delete(f"/api/documents/{document.id}", headers=_bearer(pilot_user)).status_code == 200
    assert (settings.UPLOAD_DIR / "documents" / "general" / "warrant.pdf").exists()
    assert client.get("/api/documents", headers=_bearer(pilot_user)).json() == []
    assert client.get(f"/api/documents/{document.id}/view", headers=_bearer(pilot_user)).status_code == 404

    assert client.post(f"/api/documents/{document.id}/restore", headers=_bearer(supervisor_user)).status_code == 200
    assert [d["id"] for d in client.get("/api/documents", headers=_bearer(pilot_user)).json()] == [document.id]


def test_deleted_folder_is_hidden_but_its_record_stays(client, db, pilot_user):
    folder_id = client.post("/api/folders", headers=_bearer(pilot_user), json={"name": "Case 7"}).json()["id"]
    assert client.delete(f"/api/folders/{folder_id}", headers=_bearer(pilot_user)).status_code == 200
    assert all(f["id"] != folder_id for f in client.get("/api/folders", headers=_bearer(pilot_user)).json())
    db.expire_all()
    assert db.get(Folder, folder_id).deleted_at is not None
    assert client.get(f"/api/folders/{folder_id}/documents", headers=_bearer(pilot_user)).status_code == 404


def test_folder_listing_skips_deleted_documents(client, db, pilot_user, upload_dir):
    folder_id = client.post("/api/folders", headers=_bearer(pilot_user), json={"name": "Case 8"}).json()["id"]
    doc_id = client.post("/api/documents/upload", headers=_bearer(pilot_user),
                         data={"entity_type": "general", "document_type": "other", "title": "A",
                               "folder_id": str(folder_id)},
                         files={"file": ("a.pdf", b"%PDF-1.4 a", "application/pdf")}).json()["id"]
    client.delete(f"/api/documents/{doc_id}", headers=_bearer(pilot_user))
    assert client.get(f"/api/folders/{folder_id}/documents", headers=_bearer(pilot_user)).json() == []
    folder = next(f for f in client.get("/api/folders", headers=_bearer(pilot_user)).json() if f["id"] == folder_id)
    assert folder["document_count"] == 0


# 2. Only an admin purges, and only what is already deleted -------------------------

def test_purge_is_admin_only_and_needs_a_prior_delete(client, db, photo, pilot_user, supervisor_user, admin_user):
    assert client.delete(f"/api/photos/{photo.id}/purge", headers=_bearer(admin_user)).status_code == 409
    client.delete(f"/api/photos/{photo.id}", headers=_bearer(pilot_user))
    assert client.delete(f"/api/photos/{photo.id}/purge", headers=_bearer(supervisor_user)).status_code == 403

    path, photo_id = _photo_file(photo), photo.id
    assert client.delete(f"/api/photos/{photo_id}/purge", headers=_bearer(admin_user)).status_code == 200
    db.expire_all()
    assert db.get(Photo, photo_id) is None
    assert db.query(PhotoFlight).count() == 0
    assert not path.exists()
    purge = db.query(AuditLog).filter(AuditLog.action == "purge").one()
    assert hashlib.sha256(photo.content).hexdigest() in purge.details


def test_document_purge_removes_the_file(client, db, document, pilot_user, admin_user):
    path = settings.UPLOAD_DIR / "documents" / "general" / "warrant.pdf"
    client.delete(f"/api/documents/{document.id}", headers=_bearer(pilot_user))
    assert client.delete(f"/api/documents/{document.id}/purge", headers=_bearer(admin_user)).status_code == 200
    assert not path.exists()


def test_purge_never_removes_a_file_outside_the_upload_directory(client, db, admin_user, upload_dir, tmp_path_factory):
    outside = tmp_path_factory.mktemp("elsewhere") / "system.cfg"
    outside.write_text("keep me")
    doc = Document(entity_type="general", document_type="other", title="planted", filename="system.cfg",
                   file_path=str(outside), mime_type="text/plain", file_size_bytes=7)
    db.add(doc)
    db.commit()
    client.delete(f"/api/documents/{doc.id}", headers=_bearer(admin_user))
    assert client.delete(f"/api/documents/{doc.id}/purge", headers=_bearer(admin_user)).status_code == 200
    assert outside.exists()


# 3. A legal hold blocks every way out ---------------------------------------------

def test_held_photo_cannot_be_deleted_or_purged(client, db, photo, pilot_user, supervisor_user, admin_user):
    assert client.put(f"/api/photos/{photo.id}/hold", headers=_bearer(pilot_user),
                      json={"legal_hold": True}).status_code == 403
    assert client.put(f"/api/photos/{photo.id}/hold", headers=_bearer(supervisor_user),
                      json={"legal_hold": True}).status_code == 200
    assert client.delete(f"/api/photos/{photo.id}", headers=_bearer(pilot_user)).status_code == 409
    assert client.get("/api/photos", headers=_bearer(pilot_user)).json()[0]["legal_hold"] is True

    client.put(f"/api/photos/{photo.id}/hold", headers=_bearer(supervisor_user), json={"legal_hold": False})
    client.delete(f"/api/photos/{photo.id}", headers=_bearer(pilot_user))
    client.put(f"/api/photos/{photo.id}/hold", headers=_bearer(supervisor_user), json={"legal_hold": True})
    assert client.delete(f"/api/photos/{photo.id}/purge", headers=_bearer(admin_user)).status_code == 409
    assert _photo_file(photo).exists()
    assert {"hold", "release_hold"} <= set(_actions(db, "photo", photo.id))


def test_held_document_cannot_be_deleted(client, document, pilot_user, supervisor_user):
    client.put(f"/api/documents/{document.id}/hold", headers=_bearer(supervisor_user), json={"legal_hold": True})
    assert client.delete(f"/api/documents/{document.id}", headers=_bearer(pilot_user)).status_code == 409


def test_held_document_blocks_deleting_its_operating_authority(client, db, admin_user, supervisor_user, upload_dir):
    from app.models.operating_authority import OperatingAuthority
    authority = OperatingAuthority(authority_type="coa", title="COA 1",
                                   expiry_date=date.today() + timedelta(days=90))
    db.add(authority)
    db.commit()
    doc_id = client.post("/api/documents/upload", headers=_bearer(admin_user),
                         data={"entity_type": "operating_authority", "entity_id": str(authority.id),
                               "document_type": "faa_authorization", "title": "COA"},
                         files={"file": ("coa.pdf", b"%PDF-1.4 coa", "application/pdf")}).json()["id"]
    client.put(f"/api/documents/{doc_id}/hold", headers=_bearer(supervisor_user), json={"legal_hold": True})
    resp = client.delete(f"/api/operating-authorities/{authority.id}", headers=_bearer(supervisor_user))
    assert resp.status_code == 409
    assert db.get(Document, doc_id) is not None


# 4. Uploads are fingerprinted and views are on the record -------------------------

def test_uploads_record_their_sha256(photo, document):
    assert photo.sha256 == hashlib.sha256(photo.content).hexdigest()
    assert document.sha256 == hashlib.sha256(document.content).hexdigest()


def test_photo_view_through_the_gallery_link_is_audited_to_the_viewer(client, db, photo, supervisor_user):
    view_url = client.get("/api/photos", headers=_bearer(supervisor_user)).json()[0]["view_url"]
    assert client.get(f"/api{view_url}").status_code == 200
    entry = db.query(AuditLog).filter(AuditLog.action == "view", AuditLog.entity_type == "photo").one()
    assert entry.user_id == supervisor_user.id


def test_photo_link_cannot_be_reassigned_to_another_viewer(client, photo, supervisor_user, pilot_user):
    view_url = client.get("/api/photos", headers=_bearer(supervisor_user)).json()[0]["view_url"]
    query = parse_qs(urlparse(view_url).query)
    forged = f"/api/photos/{photo.id}/view?sig={query['sig'][0]}&exp={query['exp'][0]}&u={pilot_user.id}"
    assert client.get(forged).status_code == 401


def test_document_view_is_audited(client, db, document, supervisor_user):
    assert client.get(f"/api/documents/{document.id}/view", headers=_bearer(supervisor_user)).status_code == 200
    entry = db.query(AuditLog).filter(AuditLog.action == "view", AuditLog.entity_type == "document").one()
    assert entry.user_id == supervisor_user.id
