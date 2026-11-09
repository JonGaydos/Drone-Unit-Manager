"""The organization logo is stored under the extension its content has (F-10).

A PNG named x.jpg used to be stored as logo.jpg and served as image/jpeg, and a
file with no extension was stored as .png whatever it held.
"""

import io

import pytest
from PIL import Image

from app.config import settings

LOGO_URL = "/api/settings/logo"


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


def _image(fmt: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(buf, format=fmt)
    return buf.getvalue()


@pytest.mark.parametrize("filename, fmt, stored, mime", [
    ("x.jpg", "PNG", "logo.png", "image/png"),
    ("badge", "JPEG", "logo.jpg", "image/jpeg"),
    ("badge.png", "WEBP", "logo.webp", "image/webp"),
    ("badge.jpeg", "JPEG", "logo.jpg", "image/jpeg"),
])
def test_logo_is_stored_and_served_as_its_content(client, admin_headers, uploads, filename, fmt, stored, mime):
    content = _image(fmt)

    resp = client.post(LOGO_URL, headers=admin_headers, files={"file": (filename, content, "image/png")})

    assert resp.status_code == 200, resp.text
    assert sorted(p.name for p in (uploads / "org").iterdir()) == [stored]
    view = client.get(f"{LOGO_URL}/view")
    assert view.headers["content-type"] == mime
    assert view.content == content


def test_logo_of_an_unsupported_image_type_is_refused(client, admin_headers, uploads):
    resp = client.post(LOGO_URL, headers=admin_headers, files={"file": ("x.png", _image("GIF"), "image/png")})

    assert resp.status_code == 400
