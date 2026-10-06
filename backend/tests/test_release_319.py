"""3.1.9: the app page is revalidated on every visit, so an update reaches the
browser (the hashed script files it names may be cached as usual), and a
backup records the version that made it."""

import pytest

import app.main


@pytest.fixture
def static_dir(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<script src="/assets/index-abc.js"></script>')
    (tmp_path / "assets" / "index-abc.js").write_text("console.log(1)")
    monkeypatch.setattr(app.main, "_static_dir", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("path", ["/", "/missions", "/index.html"])
def test_the_page_is_revalidated_on_every_visit(client, static_dir, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert "index-abc.js" in resp.text
    assert resp.headers["cache-control"] == "no-cache"


def test_hashed_scripts_are_not_marked_no_cache(client, static_dir):
    resp = client.get("/assets/index-abc.js")
    assert resp.status_code == 200
    assert "cache-control" not in resp.headers


def test_a_backup_records_the_running_version(db):
    """The manifest said 2.2.0 whatever was running: backup.py kept its own
    copy of the version from before 3.0."""
    import json
    import zipfile

    from app.constants import APP_VERSION
    from app.routers.backup import build_backup_archive

    spooled, manifest = build_backup_archive(db)
    with zipfile.ZipFile(spooled) as zf:
        assert json.loads(zf.read("manifest.json"))["app_version"] == APP_VERSION
    assert manifest["app_version"] == APP_VERSION
