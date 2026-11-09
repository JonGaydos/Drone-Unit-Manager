"""Pilot and vehicle profile photos: upload and view.

* A rejected upload (content not an image, too large) keeps the current photo.
* Every extension the upload accepts is one the view route serves.
"""

import io

import pytest
from PIL import Image

from app.config import settings
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle


def _image(fmt: str, color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), color).save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    return tmp_path


@pytest.fixture(params=["pilots", "vehicles"])
def owner_url(request, db):
    if request.param == "pilots":
        row = Pilot(first_name="Test", last_name="Photo")
    else:
        row = Vehicle(manufacturer="Acme", model="Quad", serial_number="SN-PHOTO-1")
    db.add(row)
    db.commit()
    return f"/api/{request.param}/{row.id}/photo"


def _upload(client, headers, url, name, content):
    return client.post(url, headers=headers, files={"file": (name, content, "application/octet-stream")})


def test_rejected_content_keeps_the_current_photo(client, admin_headers, uploads, owner_url):
    original = _image("PNG")
    assert _upload(client, admin_headers, owner_url, "ok.png", original).status_code == 200

    bad = _upload(client, admin_headers, owner_url, "fake.png", b"just some text, not an image")
    assert bad.status_code == 400

    view = client.get(f"{owner_url}/view", headers=admin_headers)
    assert view.status_code == 200
    assert view.content == original


def test_rejected_content_with_a_new_extension_keeps_the_current_photo(client, admin_headers, uploads, owner_url):
    original = _image("JPEG")
    assert _upload(client, admin_headers, owner_url, "ok.jpg", original).status_code == 200

    assert _upload(client, admin_headers, owner_url, "fake.webp", b"not an image").status_code == 400

    view = client.get(f"{owner_url}/view", headers=admin_headers)
    assert view.status_code == 200
    assert view.content == original


def test_too_large_keeps_the_current_photo(client, admin_headers, uploads, owner_url, monkeypatch):
    original = _image("PNG")
    assert _upload(client, admin_headers, owner_url, "ok.png", original).status_code == 200
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", len(original) - 1)

    assert _upload(client, admin_headers, owner_url, "big.png", original).status_code == 413

    assert client.get(f"{owner_url}/view", headers=admin_headers).content == original


def test_replacing_with_another_type_serves_only_the_new_photo(client, admin_headers, uploads, owner_url):
    assert _upload(client, admin_headers, owner_url, "first.png", _image("PNG")).status_code == 200
    second = _image("JPEG", "blue")
    assert _upload(client, admin_headers, owner_url, "second.jpg", second).status_code == 200

    assert client.get(f"{owner_url}/view", headers=admin_headers).content == second
    folder = next(uploads.joinpath("photos").glob(f"*/{owner_url.split('/')[3]}"))
    assert sorted(p.name for p in folder.iterdir()) == ["profile.jpg"]


@pytest.mark.parametrize("name, fmt, mime", [
    ("anim.gif", "GIF", "image/gif"),
    ("photo.webp", "WEBP", "image/webp"),
    ("photo.jpeg", "JPEG", "image/jpeg"),
])
def test_every_accepted_type_is_served(client, admin_headers, uploads, owner_url, name, fmt, mime):
    content = _image(fmt)
    assert _upload(client, admin_headers, owner_url, name, content).status_code == 200

    view = client.get(f"{owner_url}/view", headers=admin_headers)
    assert view.status_code == 200
    assert view.headers["content-type"] == mime
    assert view.content == content
