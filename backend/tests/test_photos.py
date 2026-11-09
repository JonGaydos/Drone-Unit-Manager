"""Photo link/unlink authz and signed-URL HMAC tests.

Covers the real behavior of ``app.routers.photos``:

* POST/DELETE ``/api/photos/{id}/flight/{id}`` and ``.../incident/{id}`` are
  gated by ``files.custody``; a pilot gets 403 by default, an admin succeeds and
  a junction row (``PhotoFlight`` / ``PhotoIncident``) is created/removed.
* Linking to a nonexistent flight/incident returns 404 and leaves NO dangling
  junction row.
* The signed-URL serve path (``/api/photos/{id}/view``) authenticates an
  unauthenticated request via an HMAC signature over ``"{photo_id}:{action}:{exp}"``
  keyed by ``settings.SECRET_KEY`` (helper ``_sign_photo`` / verifier
  ``_verify_photo_sig``). A valid, unexpired sig serves the file (200); a tampered
  sig or an expired sig is rejected (401).
"""

import os
import time
from datetime import date
from pathlib import Path

import pytest

from app.config import settings
from app.routers import photos as photos_router
from app.routers.photos import _sign_photo, SIGNED_URL_TTL_SECONDS
from app.models.audit_log import AuditLog
from app.models.photo import Photo, PhotoFlight, PhotoIncident
from app.models.flight import Flight
from app.models.incident import Incident

# A 1x1 PNG so FileResponse has a real file to stream for the valid-sig case.
_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f8f0000000049454e44ae42"
    "6082"
)


def _seed_photo(db, **kwargs):
    kwargs.setdefault("filename", "p.png")
    photo = Photo(original_filename="p.png", mime_type="image/png", **kwargs)
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


def _seed_flight(db):
    flight = Flight(date=date(2025, 6, 1), purpose="patrol")
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return flight


def _seed_incident(db):
    incident = Incident(date=date(2025, 6, 1), title="I", severity="minor", category="other", description="d")
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


# 1. Link/unlink supervisor-gated -------------------------------------------

def test_link_flight_requires_supervisor(client, db, pilot_headers):
    photo = _seed_photo(db)
    flight = _seed_flight(db)
    resp = client.post(f"/api/photos/{photo.id}/flight/{flight.id}", headers=pilot_headers)
    assert resp.status_code == 403, resp.text

    db.expire_all()
    assert db.query(PhotoFlight).filter(
        PhotoFlight.photo_id == photo.id, PhotoFlight.flight_id == flight.id).first() is None


def test_link_flight_admin_succeeds(client, db, admin_headers):
    photo = _seed_photo(db)
    flight = _seed_flight(db)
    resp = client.post(f"/api/photos/{photo.id}/flight/{flight.id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    db.expire_all()
    assert db.query(PhotoFlight).filter(
        PhotoFlight.photo_id == photo.id, PhotoFlight.flight_id == flight.id).count() == 1


def test_unlink_flight_requires_supervisor(client, db, pilot_headers, admin_headers):
    photo = _seed_photo(db)
    flight = _seed_flight(db)
    db.add(PhotoFlight(photo_id=photo.id, flight_id=flight.id))
    db.commit()

    resp = client.delete(f"/api/photos/{photo.id}/flight/{flight.id}", headers=pilot_headers)
    assert resp.status_code == 403, resp.text

    db.expire_all()
    assert db.query(PhotoFlight).filter(
        PhotoFlight.photo_id == photo.id, PhotoFlight.flight_id == flight.id).count() == 1

    # Admin can remove it.
    resp = client.delete(f"/api/photos/{photo.id}/flight/{flight.id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.query(PhotoFlight).filter(
        PhotoFlight.photo_id == photo.id, PhotoFlight.flight_id == flight.id).first() is None


def test_link_incident_requires_supervisor(client, db, pilot_headers, admin_headers):
    photo = _seed_photo(db)
    incident = _seed_incident(db)
    resp = client.post(f"/api/photos/{photo.id}/incident/{incident.id}", headers=pilot_headers)
    assert resp.status_code == 403, resp.text
    db.expire_all()
    assert db.query(PhotoIncident).filter(
        PhotoIncident.photo_id == photo.id, PhotoIncident.incident_id == incident.id).first() is None

    resp = client.post(f"/api/photos/{photo.id}/incident/{incident.id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.query(PhotoIncident).filter(
        PhotoIncident.photo_id == photo.id, PhotoIncident.incident_id == incident.id).count() == 1


# 2. Link to nonexistent target -> 404, no dangling junction row ------------

def test_link_nonexistent_flight_404_no_junction(client, db, admin_headers):
    photo = _seed_photo(db)
    resp = client.post(f"/api/photos/{photo.id}/flight/999999", headers=admin_headers)
    assert resp.status_code == 404, resp.text

    db.expire_all()
    assert db.query(PhotoFlight).filter(PhotoFlight.photo_id == photo.id).count() == 0
    assert db.query(PhotoFlight).filter(PhotoFlight.flight_id == 999999).count() == 0


def test_link_nonexistent_incident_404_no_junction(client, db, admin_headers):
    photo = _seed_photo(db)
    resp = client.post(f"/api/photos/{photo.id}/incident/999999", headers=admin_headers)
    assert resp.status_code == 404, resp.text

    db.expire_all()
    assert db.query(PhotoIncident).filter(PhotoIncident.photo_id == photo.id).count() == 0


# 3. Signed-URL HMAC --------------------------------------------------------

@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    """Point the photos upload dir at an isolated tmp_path subdir so tests that
    write a backing file never touch the real data tree. Patches the module
    attribute the path resolver/validator read (``app.routers.photos.UPLOAD_DIR``)
    plus ``settings.UPLOAD_DIR`` for anything that reads it live. tmp_path
    teardown removes the file."""
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    monkeypatch.setattr("app.routers.photos.UPLOAD_DIR", str(photos_dir))
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return str(photos_dir)


def _photo_on_disk(db, upload_dir):
    """Seed a photo and write its backing file where the serve endpoint resolves
    it (``UPLOAD_DIR/<photo.filename>``). Returns (photo, abs_path)."""
    stored = "test_photos_sig.png"
    photo = _seed_photo(db, filename=stored)
    abs_path = os.path.join(upload_dir, stored)
    with open(abs_path, "wb") as f:
        f.write(_PNG_1x1)
    return photo, abs_path


def test_valid_signed_url_serves(client, db, upload_dir):
    photo, abs_path = _photo_on_disk(db, upload_dir)
    sig, exp = _sign_photo(photo.id, "view")
    resp = client.get(f"/api/photos/{photo.id}/view?sig={sig}&exp={exp}")
    assert resp.status_code == 200, resp.text
    assert resp.content == _PNG_1x1


def test_tampered_signature_rejected(client, db, upload_dir):
    photo, abs_path = _photo_on_disk(db, upload_dir)
    sig, exp = _sign_photo(photo.id, "view")
    # Flip the last hex char of the signature.
    bad = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    resp = client.get(f"/api/photos/{photo.id}/view?sig={bad}&exp={exp}")
    assert resp.status_code == 401, resp.text


def test_tampered_exp_rejected(client, db, upload_dir):
    """Extending exp after signing breaks the signature (exp is part of the payload)."""
    photo, abs_path = _photo_on_disk(db, upload_dir)
    sig, exp = _sign_photo(photo.id, "view")
    resp = client.get(f"/api/photos/{photo.id}/view?sig={sig}&exp={exp + 3600}")
    assert resp.status_code == 401, resp.text


def test_expired_signed_url_rejected(client, db, upload_dir):
    """A signature valid for a past exp is rejected because exp is in the past."""
    photo, abs_path = _photo_on_disk(db, upload_dir)
    # Sign with a negative TTL so exp is already in the past, signed correctly.
    sig, exp = _sign_photo(photo.id, "view", ttl=-10)
    assert exp < int(time.time())
    resp = client.get(f"/api/photos/{photo.id}/view?sig={sig}&exp={exp}")
    assert resp.status_code == 401, resp.text


# 4. Thumbnail fallback audit -----------------------------------------------

def _view_entries(photo_id):
    from app import database
    from app.models.audit_log import AuditLog
    s = database.SessionLocal()
    try:
        return s.query(AuditLog).filter(AuditLog.entity_type == "photo", AuditLog.entity_id == photo_id,
                                        AuditLog.action == "view").count()
    finally:
        s.close()


def _photo_entries(photo_id):
    from app import database
    s = database.SessionLocal()
    try:
        return s.query(AuditLog).filter(AuditLog.entity_type == "photo", AuditLog.entity_id == photo_id).count()
    finally:
        s.close()


def _thumbnail_url(photo_id):
    sig, exp = _sign_photo(photo_id, "thumbnail")
    return f"/api/photos/{photo_id}/thumbnail?sig={sig}&exp={exp}"


def _decodable_photo_on_disk(db, upload_dir):
    """A photo whose file Pillow can decode (``_PNG_1x1`` only passes the type sniff)."""
    from PIL import Image
    photo, abs_path = _photo_on_disk(db, upload_dir)
    Image.new("RGB", (800, 600), (10, 20, 30)).save(abs_path, "PNG")
    with open(abs_path, "rb") as f:
        return photo, f.read()


def test_missing_thumbnail_is_built_and_served_with_no_audit_entry(client, db, upload_dir):
    photo, _ = _decodable_photo_on_disk(db, upload_dir)

    resp = client.get(_thumbnail_url(photo.id))

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content[:3] == b"\xff\xd8\xff"
    db.expire_all()
    assert photo.thumbnail_path == os.path.join(upload_dir, "thumb_test_photos_sig.png")
    assert os.path.exists(photo.thumbnail_path)
    assert _photo_entries(photo.id) == 0


def test_thumbnail_lost_from_disk_is_built_again(client, db, upload_dir):
    photo, _ = _decodable_photo_on_disk(db, upload_dir)
    photo.thumbnail_path = os.path.join(upload_dir, "gone.jpg")
    db.commit()

    resp = client.get(_thumbnail_url(photo.id))

    assert resp.content[:3] == b"\xff\xd8\xff"
    assert _view_entries(photo.id) == 0


def test_thumbnail_that_cannot_be_built_is_a_placeholder(client, db, upload_dir, caplog):
    photo, abs_path = _photo_on_disk(db, upload_dir)
    unreadable = b"\x89PNG\r\n\x1a\n not really an image"
    with open(abs_path, "wb") as f:
        f.write(unreadable)

    resp = client.get(_thumbnail_url(photo.id))

    assert resp.status_code == 200, resp.text
    assert resp.content == photos_router.placeholder_thumbnail()
    assert resp.content != unreadable
    assert _photo_entries(photo.id) == 0
    db.expire_all()
    assert photo.thumbnail_path is None
    assert "not really" not in caplog.text


def test_placeholder_is_a_small_image():
    from io import BytesIO
    from PIL import Image
    image = Image.open(BytesIO(photos_router.placeholder_thumbnail()))
    assert image.width <= photos_router.THUMB_WIDTH


@pytest.mark.parametrize(("mode", "fmt"), [
    ("I;16", "PNG"), ("I;16", "TIFF"), ("F", "TIFF"), ("LA", "PNG"), ("CMYK", "TIFF"), ("1", "PNG"),
])
def test_thumbnail_is_built_from_any_image_mode(upload_dir, mode, fmt):
    from PIL import Image
    source = Image.new(mode, (800, 600))
    if mode in ("I;16", "F"):
        source.putpixel((0, 0), 7000)
        source.putpixel((1, 0), 9000)
    path = os.path.join(upload_dir, f"source.{fmt.lower()}")
    source.save(path, fmt)

    thumb = photos_router._generate_thumbnail(path, upload_dir, "source.jpg")

    assert thumb is not None
    built = Image.open(thumb)
    assert built.format == "JPEG"
    assert built.mode in ("L", "RGB")
    assert built.width == photos_router.THUMB_WIDTH


def test_sixteen_bit_thumbnail_keeps_its_contrast(upload_dir):
    from PIL import Image
    source = Image.new("I;16", (2, 1), 7000)
    source.putpixel((1, 0), 9000)
    path = os.path.join(upload_dir, "thermal.png")
    source.save(path, "PNG")

    thumb = photos_router._generate_thumbnail(path, upload_dir, "thermal.png")

    low, high = Image.open(thumb).getextrema()
    assert high - low > 200


def test_full_view_after_a_thumbnail_records_the_viewer(client, db, upload_dir, admin_user, admin_headers):
    photo, full = _decodable_photo_on_disk(db, upload_dir)
    client.get(_thumbnail_url(photo.id))

    resp = client.get(f"/api/photos/{photo.id}/view", headers=admin_headers)

    assert resp.content == full
    entry = db.query(AuditLog).filter_by(action="view", entity_id=photo.id).one()
    assert entry.user_id == admin_user.id


def test_real_thumbnail_writes_no_view_audit(client, db, upload_dir, admin_headers):
    photo, _ = _photo_on_disk(db, upload_dir)
    thumb = os.path.join(upload_dir, "thumb.jpg")
    with open(thumb, "wb") as f:
        f.write(_PNG_1x1)
    photo.thumbnail_path = thumb
    db.commit()
    resp = client.get(f"/api/photos/{photo.id}/thumbnail", headers=admin_headers)
    assert resp.status_code == 200
    assert _view_entries(photo.id) == 0


def test_signed_view_entry_names_the_known_viewer(client, db, upload_dir, pilot_user):
    photo, _ = _photo_on_disk(db, upload_dir)
    sig, exp = _sign_photo(photo.id, "view", viewer=pilot_user.id)

    resp = client.get(f"/api/photos/{photo.id}/view?sig={sig}&exp={exp}&u={pilot_user.id}")

    assert resp.status_code == 200, resp.text
    entry = db.query(AuditLog).filter_by(action="view", entity_id=photo.id).one()
    assert entry.user_id == pilot_user.id
    assert entry.user_username == pilot_user.username


# 5. Thumbnail builds: remembered failures, one build at a time per photo ----

@pytest.fixture(autouse=True)
def _forget_thumbnail_failures():
    photos_router._failed_thumbnails.clear()
    yield
    photos_router._failed_thumbnails.clear()


def _counting_render(monkeypatch, before=None):
    """Count calls to the thumbnail decoder, running ``before`` first in each."""
    calls = []
    real = photos_router._render_thumbnail

    def render(file_path):
        calls.append(file_path)
        if before:
            before()
        return real(file_path)

    monkeypatch.setattr(photos_router, "_render_thumbnail", render)
    return calls


def _unreadable_photo_on_disk(db, upload_dir):
    photo, abs_path = _photo_on_disk(db, upload_dir)
    with open(abs_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n not really an image")
    return photo, abs_path


def _thumbnail_in_thread(photo_id, results):
    from app import database
    sig, exp = _sign_photo(photo_id, "thumbnail")
    session = database.SessionLocal()
    try:
        results.append(photos_router.view_thumbnail(photo_id, session, None, None, sig, exp))
    finally:
        session.close()


def test_a_failed_thumbnail_is_decoded_once(client, db, upload_dir, monkeypatch):
    photo, _ = _unreadable_photo_on_disk(db, upload_dir)
    calls = _counting_render(monkeypatch)

    first = client.get(_thumbnail_url(photo.id))
    second = client.get(_thumbnail_url(photo.id))

    assert len(calls) == 1
    assert first.content == photos_router.placeholder_thumbnail()
    assert second.content == photos_router.placeholder_thumbnail()


def test_a_failed_thumbnail_is_tried_again_once_its_file_changes(client, db, upload_dir, monkeypatch):
    from PIL import Image
    photo, abs_path = _unreadable_photo_on_disk(db, upload_dir)
    calls = _counting_render(monkeypatch)
    client.get(_thumbnail_url(photo.id))
    Image.new("RGB", (800, 600)).save(abs_path, "PNG")

    resp = client.get(_thumbnail_url(photo.id))

    assert len(calls) == 2
    assert resp.content[:3] == b"\xff\xd8\xff"


def test_concurrent_requests_for_one_photo_build_it_once(db, upload_dir, monkeypatch):
    import threading
    photo, _ = _decodable_photo_on_disk(db, upload_dir)
    started, release = threading.Event(), threading.Event()

    def hold_first_build():
        started.set()
        release.wait(5)

    calls = _counting_render(monkeypatch, hold_first_build)
    results = []
    first = threading.Thread(target=_thumbnail_in_thread, args=(photo.id, results))
    second = threading.Thread(target=_thumbnail_in_thread, args=(photo.id, results))
    first.start()
    started.wait(5)
    second.start()
    time.sleep(0.2)
    release.set()
    first.join(5)
    second.join(5)

    assert len(calls) == 1
    assert [Path(r.path).name for r in results] == ["thumb_test_photos_sig.png"] * 2


def test_a_build_that_would_wait_too_long_gets_the_placeholder(client, db, upload_dir, monkeypatch):
    photo, _ = _decodable_photo_on_disk(db, upload_dir)
    monkeypatch.setattr(photos_router, "THUMB_BUILD_WAIT_SECONDS", 0.01)
    monkeypatch.setattr(photos_router, "_thumbnail_builds", photos_router.threading.Semaphore(0))

    resp = client.get(_thumbnail_url(photo.id))

    assert resp.content == photos_router.placeholder_thumbnail()


def test_a_photo_deleted_during_its_build_keeps_no_thumbnail(client, db, upload_dir, monkeypatch):
    from datetime import datetime
    from app import database
    photo, _ = _decodable_photo_on_disk(db, upload_dir)

    def delete_meanwhile():
        session = database.SessionLocal()
        session.get(Photo, photo.id).deleted_at = datetime.now()
        session.commit()
        session.close()

    _counting_render(monkeypatch, delete_meanwhile)

    resp = client.get(_thumbnail_url(photo.id))

    assert resp.status_code == 404
    assert not os.path.exists(os.path.join(upload_dir, "thumb_test_photos_sig.png"))


def test_a_thumbnail_whose_save_does_not_commit_is_removed(db, upload_dir, monkeypatch):
    from sqlalchemy.orm.exc import StaleDataError
    from app import database
    photo, _ = _decodable_photo_on_disk(db, upload_dir)
    real_save = photos_router._save_thumbnail

    def save_then_purge(*args):
        path = real_save(*args)
        session = database.SessionLocal()
        session.delete(session.get(Photo, photo.id))
        session.commit()
        session.close()
        return path

    monkeypatch.setattr(photos_router, "_save_thumbnail", save_then_purge)
    sig, exp = _sign_photo(photo.id, "thumbnail")

    with pytest.raises(StaleDataError):
        photos_router.view_thumbnail(photo.id, db, None, None, sig, exp)

    assert not os.path.exists(os.path.join(upload_dir, "thumb_test_photos_sig.png"))


def test_a_thumbnail_save_that_fails_leaves_no_file(upload_dir, monkeypatch):
    from PIL import Image

    class HalfWritten:
        def save(self, path, *_args, **_kwargs):
            with open(path, "wb") as f:
                f.write(b"\xff\xd8\xff partial")
            raise OSError("disk full")

    path = os.path.join(upload_dir, "source.png")
    Image.new("RGB", (8, 8)).save(path, "PNG")
    monkeypatch.setattr(photos_router, "_jpeg_ready", lambda _img: HalfWritten())

    assert photos_router._generate_thumbnail(path, upload_dir, "source.png") is None
    assert os.listdir(upload_dir) == ["source.png"]


def test_purge_removes_a_thumbnail_the_record_never_named(client, db, upload_dir, admin_headers):
    from datetime import datetime
    photo, abs_path = _photo_on_disk(db, upload_dir)
    photo.deleted_at = datetime.now()
    db.commit()
    stray = os.path.join(upload_dir, "thumb_test_photos_sig.png")
    with open(stray, "wb") as f:
        f.write(_PNG_1x1)

    resp = client.delete(f"/api/photos/{photo.id}/purge", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    assert not os.path.exists(stray)


# 4. API tokens on the file routes (D-24) -----------------------------------

def _api_token(client, admin_headers, **overrides):
    resp = client.post("/api/api-tokens", headers=admin_headers,
                       json={"name": "Reader", "read_only": True, **overrides})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.mark.parametrize("action", ["view", "thumbnail"])
def test_api_token_fetches_photo_files(client, db, admin_headers, upload_dir, action):
    photo, _ = _photo_on_disk(db, upload_dir)

    resp = client.get(f"/api/photos/{photo.id}/{action}", headers=_api_token(client, admin_headers))

    assert resp.status_code == 200, resp.text


def test_api_token_out_of_scope_is_refused(client, db, admin_headers, upload_dir):
    photo, _ = _photo_on_disk(db, upload_dir)

    resp = client.get(f"/api/photos/{photo.id}/view", headers=_api_token(client, admin_headers, scopes=["flights"]))

    assert resp.status_code == 403
