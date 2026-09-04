"""Photo link/unlink authz and signed-URL HMAC tests.

Covers the real behavior of ``app.routers.photos``:

* POST/DELETE ``/api/photos/{id}/flight/{id}`` and ``.../incident/{id}`` are
  supervisor-gated (``SupervisorUser``); a pilot gets 403, an admin succeeds and
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
