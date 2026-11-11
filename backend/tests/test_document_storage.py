"""Unique stored names for new document uploads.

A new upload is stored under a generated name and keeps the name the user gave
in ``Document.filename``. Documents stored before this layout (stored name equal
to the display name, with a counter suffix for repeats) keep working.
"""

import hashlib
import json
import zipfile
from pathlib import Path
from urllib.parse import unquote

import pytest

from app.config import settings
from app.models.document import Document
from app.models.operating_authority import OperatingAuthority

PDF_A = b"%PDF-1.4 first"
PDF_B = b"%PDF-1.4 second, different"


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    updir = tmp_path / "uploads"
    updir.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(updir))
    return updir


def _upload(client, headers, content, filename="report.pdf", entity_type="general", entity_id=None):
    data = {"entity_type": entity_type, "document_type": "other", "title": "Doc"}
    if entity_id is not None:
        data["entity_id"] = str(entity_id)
    resp = client.post("/api/documents/upload", headers=headers, data=data,
                       files={"file": (filename, content, "application/pdf")})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _old_layout(db, upload_dir, name, content):
    """A row and file as an earlier release stored them."""
    folder = upload_dir / "documents" / "general"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(content)
    doc = Document(entity_type="general", document_type="other", title="Old", filename=name,
                   file_path=str(path), mime_type="application/pdf", file_size_bytes=len(content),
                   sha256=hashlib.sha256(content).hexdigest())
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_same_name_uploads_get_separate_files(client, db, admin_headers, upload_dir):
    a = _upload(client, admin_headers, PDF_A)
    b = _upload(client, admin_headers, PDF_B)

    db.expire_all()
    docs = {d.id: d for d in db.query(Document).all()}
    pa, pb = Path(docs[a["id"]].file_path), Path(docs[b["id"]].file_path)
    assert pa != pb
    assert pa.read_bytes() == PDF_A
    assert pb.read_bytes() == PDF_B
    assert docs[a["id"]].sha256 == hashlib.sha256(PDF_A).hexdigest()
    assert docs[b["id"]].sha256 == hashlib.sha256(PDF_B).hexdigest()


def test_stored_name_is_generated_in_the_same_folder(client, db, admin_headers, upload_dir):
    body = _upload(client, admin_headers, PDF_A, filename="My Report.PDF")

    db.expire_all()
    stored = Path(db.get(Document, body["id"]).file_path)
    assert stored.parent == upload_dir / "documents" / "general"
    assert stored.name != "My Report.PDF"
    assert stored.suffix == ".pdf"
    assert len(stored.stem) == 32


def test_original_name_shown_and_used_for_download(client, admin_headers, upload_dir):
    body = _upload(client, admin_headers, PDF_A, filename="Insurance 2026.pdf")

    assert body["filename"] == "Insurance 2026.pdf"
    listed = client.get("/api/documents", headers=admin_headers).json()
    assert [d["filename"] for d in listed] == ["Insurance 2026.pdf"]
    resp = client.get(f"/api/documents/{body['id']}/view", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.content == PDF_A
    assert "Insurance 2026.pdf" in unquote(resp.headers["content-disposition"])


def test_existing_document_still_opens(client, db, admin_headers, upload_dir):
    doc = _old_layout(db, upload_dir, "coa.pdf", PDF_A)

    resp = client.get(f"/api/documents/{doc.id}/view", headers=admin_headers)

    assert resp.status_code == 200
    assert resp.content == PDF_A
    assert "coa.pdf" in resp.headers["content-disposition"]


def test_old_and_new_same_name_both_open(client, db, admin_headers, upload_dir):
    old = _old_layout(db, upload_dir, "coa.pdf", PDF_A)
    new = _upload(client, admin_headers, PDF_B, filename="coa.pdf")

    old_resp = client.get(f"/api/documents/{old.id}/view", headers=admin_headers)
    new_resp = client.get(f"/api/documents/{new['id']}/view", headers=admin_headers)

    assert old_resp.content == PDF_A
    assert new_resp.content == PDF_B
    assert "coa.pdf" in old_resp.headers["content-disposition"]
    assert "coa.pdf" in new_resp.headers["content-disposition"]


def test_purge_of_one_leaves_the_other(client, db, admin_headers, upload_dir):
    old = _old_layout(db, upload_dir, "coa.pdf", PDF_A)
    new = _upload(client, admin_headers, PDF_B, filename="coa.pdf")
    new_path = Path(db.get(Document, new["id"]).file_path)
    assert client.delete(f"/api/documents/{new['id']}", headers=admin_headers).status_code == 200

    assert client.delete(f"/api/documents/{new['id']}/purge", headers=admin_headers).status_code == 200

    assert not new_path.exists()
    assert Path(old.file_path).read_bytes() == PDF_A
    assert client.get(f"/api/documents/{old.id}/view", headers=admin_headers).content == PDF_A


def test_operating_authority_document_gets_unique_name(client, db, admin_headers, upload_dir):
    authority = OperatingAuthority(authority_type="coa", title="Blanket COA")
    db.add(authority)
    db.commit()
    assert authority.id == 1
    a = _upload(client, admin_headers, PDF_A, filename="coa.pdf", entity_type="operating_authority", entity_id=1)
    b = _upload(client, admin_headers, PDF_B, filename="coa.pdf", entity_type="operating_authority", entity_id=1)

    db.expire_all()
    pa, pb = Path(db.get(Document, a["id"]).file_path), Path(db.get(Document, b["id"]).file_path)
    assert pa != pb
    assert pa.parent == upload_dir / "documents" / "operating_authority" / "1"
    assert (pa.read_bytes(), pb.read_bytes()) == (PDF_A, PDF_B)


def test_backup_includes_new_file_and_its_row_points_at_it(client, db, admin_headers, upload_dir):
    from app.routers.backup import build_backup_archive

    body = _upload(client, admin_headers, PDF_A, filename="coa.pdf")
    db.expire_all()
    stored = Path(db.get(Document, body["id"]).file_path)

    spooled, _ = build_backup_archive(db, include_telemetry=False)
    with zipfile.ZipFile(spooled) as zf:
        rows = json.loads(zf.read("database.json"))["documents"]
        member = "uploads/" + stored.relative_to(upload_dir).as_posix()
        assert zf.read(member) == PDF_A
    assert [r["file_path"] for r in rows] == [str(stored)]
    assert [r["filename"] for r in rows] == ["coa.pdf"]
