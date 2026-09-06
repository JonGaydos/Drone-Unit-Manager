"""Uploads are streamed and capped, and an archive is capped separately.

A full Airdata export runs to hundreds of megabytes and is the first thing a
new unit imports. Held to the single-file limit it could not be imported at
all, which is a first-day blocker rather than an edge case.

Raising the number alone would have been worse than leaving it: the endpoint
read the whole upload into memory before measuring it, so a bigger limit just
means a bigger thing to run out of memory on. The archive is streamed to a temp
file and its entries are read one at a time, so what it costs is the largest
entry rather than the archive.
"""

import io
import json
import zipfile

from app.config import settings

LOG_URL = "/api/export/flights/import/log"
SKYDIO_URL = "/api/export/flights/import"


def _airdata(flight_id, lat=28.5, lon=-81.4):
    return json.dumps({"data": {
        "flight": {"flight_id": flight_id, "takeoff": "2026-05-01T10:00:00+00:00",
                   "landing": "2026-05-01T10:05:00+00:00"},
        "flight_telemetry": {
            "gps": {"data": [[lat, lon], [lat + 0.01, lon]],
                    "timestamps": ["2026-05-01T10:00:00+00:00", "2026-05-01T10:00:10+00:00"]},
            "height_above_takeoff": {"data": [10.0, 25.0]}}}})


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in entries.items():
            zf.writestr(name, body)
    return buf.getvalue()


def _post(client, headers, name, body):
    return client.post(LOG_URL, headers=headers,
                       files={"file": (name, body, "application/octet-stream")})


# 1. The caps differ by kind -------------------------------------------------

def test_an_archive_is_allowed_past_the_single_file_limit(client, admin_headers, monkeypatch):
    """The whole point. A full export is larger than any one file would be, and
    it is what a unit imports on day one."""
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 4096)
    monkeypatch.setattr(settings, "MAX_ARCHIVE_SIZE", 10 * 1024 * 1024)

    payload = _zip({f"flight_logs/f{i}.json": _airdata(f"AD-{i}") for i in range(30)})
    assert len(payload) > 4096, "the archive has to exceed the single-file cap to prove anything"

    resp = _post(client, admin_headers, "export.zip", payload)

    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 30


def test_a_single_file_is_still_held_to_the_smaller_limit(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 1024)

    resp = _post(client, admin_headers, "flight.json", _airdata("AD-BIG") + " " * 2048)

    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


def test_an_archive_past_its_own_limit_is_refused(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "MAX_ARCHIVE_SIZE", 2048)

    payload = _zip({f"flight_logs/f{i}.json": _airdata(f"AD-{i}") for i in range(40)})
    assert len(payload) > 2048

    assert _post(client, admin_headers, "export.zip", payload).status_code == 413


# 2. The archive is not trusted about its contents ---------------------------

def test_an_entry_that_claims_to_be_enormous_is_skipped(client, admin_headers, monkeypatch):
    """An archive can be small and claim to decompress to gigabytes. The entry
    is refused on its declared size, before it is read."""
    monkeypatch.setattr(settings, "MAX_ARCHIVE_ENTRY_SIZE", 512)

    payload = _zip({"flight_logs/ok.json": _airdata("AD-OK"),
                    "flight_logs/bomb.json": "x" * 100_000})

    body = _post(client, admin_headers, "export.zip", payload).json()

    assert body["imported"] == 1
    assert any("too large" in e for e in body["errors"]), body["errors"]


def test_one_bad_entry_does_not_stop_the_rest(client, admin_headers):
    payload = _zip({"flight_logs/good.json": _airdata("AD-1"),
                    "flight_logs/bad.json": "{not json",
                    "flight_logs/also-good.json": _airdata("AD-2")})

    body = _post(client, admin_headers, "export.zip", payload).json()

    assert body["imported"] == 2
    assert len(body["errors"]) == 1


# 3. Where the work runs ------------------------------------------------------

def test_the_archive_import_does_not_run_on_the_event_loop(client, admin_headers, monkeypatch):
    """Importing a full export is minutes of synchronous parsing and database
    work. On the event loop it freezes every other request in the app for the
    duration: nobody can load a page while one person imports.

    Inside a worker thread there is no running loop, so asking for one raises.
    That is the check.
    """
    import asyncio
    from app.routers import export as export_router

    ran_off_the_loop = {}
    real = export_router._import_zip_flight_logs

    def spy(*args, **kwargs):
        try:
            asyncio.get_running_loop()
            ran_off_the_loop["value"] = False
        except RuntimeError:
            ran_off_the_loop["value"] = True
        return real(*args, **kwargs)

    monkeypatch.setattr(export_router, "_import_zip_flight_logs", spy)

    payload = _zip({"flight_logs/a.json": _airdata("AD-THREAD")})
    resp = _post(client, admin_headers, "export.zip", payload)

    assert resp.status_code == 200, resp.text
    assert ran_off_the_loop.get("value") is True, "the import ran on the event loop"


# 4. What the archive path still does ----------------------------------------

def test_a_duplicate_inside_an_archive_is_skipped_not_imported(client, admin_headers):
    """Re-importing an export must not double every flight in it."""
    payload = _zip({"flight_logs/a.json": _airdata("AD-DUPE")})

    first = _post(client, admin_headers, "export.zip", payload).json()
    second = _post(client, admin_headers, "export.zip", payload).json()

    assert first["imported"] == 1
    assert first["skipped"] == 0
    assert second["imported"] == 0
    assert second["skipped"] == 1


def test_an_empty_archive_reports_nothing_rather_than_failing(client, admin_headers):
    body = _post(client, admin_headers, "export.zip", _zip({"readme.txt": "hello"})).json()

    assert body["total"] == 0
    assert body["imported"] == 0


# 5. The Skydio workbook endpoint keeps the single-file cap -------------------

def test_the_skydio_import_still_refuses_an_oversized_file(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 1024)

    resp = client.post(SKYDIO_URL, headers=admin_headers,
                       files={"file": ("export.csv", "a," * 2048, "text/csv")})

    assert resp.status_code == 413
