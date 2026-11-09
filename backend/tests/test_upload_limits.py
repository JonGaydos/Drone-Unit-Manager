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

import ast
import asyncio
import inspect
import io
import json
import re
import sys
import textwrap
import zipfile
from typing import Annotated

import pytest
from fastapi import APIRouter, FastAPI, File, Request, UploadFile, params
from fastapi.routing import iter_route_contexts
from PIL import Image

from app.body_limit import ARCHIVE_PATHS, DEFAULT_BODY_LIMIT, FORM_OVERHEAD, UPLOAD_PATHS, body_limit_for
from app.config import settings
from app.deps import AdminForm
from app.main import app
from app.models.pilot import Pilot

LOG_URL = "/api/export/flights/import/log"
SKYDIO_URL = "/api/export/flights/import"
LOGIN_URL = "/api/auth/login"
LOGO_URL = "/api/settings/logo"
DOCUMENT_URL = "/api/documents/upload"
GEOFENCE_URL = "/api/geofences"
PNG_MIME = "image/png"
LARGE_PNG_NAME = "big.png"


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


# 6. Every route taking a file is named, and everything else gets 1 MB -----------

def _dependants(dependant):
    yield dependant
    for child in dependant.dependencies:
        yield from _dependants(child)


def _reads_form_by_hand(fn, seen=None) -> bool:
    """Whether this function, or a helper in its own module, calls request.form()."""
    seen = seen if seen is not None else set()
    if not inspect.isfunction(fn) or fn in seen:
        return False
    seen.add(fn)
    module = sys.modules[fn.__module__]
    for node in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(fn)))):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "form":
            return True
        helper = getattr(module, node.func.id, None) if isinstance(node.func, ast.Name) else None
        if getattr(helper, "__module__", None) == fn.__module__ and _reads_form_by_hand(helper, seen):
            return True
    return False


def _takes_a_file(context) -> bool:
    root = getattr(context, "dependant", None)
    if root is None:
        return False
    for dependant in _dependants(root):
        if any(isinstance(field.field_info, params.File) for field in dependant.body_params):
            return True
        # A dependency may say outright whether it reads a file; otherwise its
        # source is searched for a hand-read form.
        reads_form = getattr(dependant.call, "reads_form", None)
        if reads_form if reads_form is not None else _reads_form_by_hand(dependant.call):
            return True
    return False


def _file_routes(target) -> set[str]:
    return {context.path for context in iter_route_contexts(target.routes) if _takes_a_file(context)}


def _upload_list_problems(found: set[str]) -> list[str]:
    listed = UPLOAD_PATHS | ARCHIVE_PATHS
    return ([f"{path}: takes a file but is not on UPLOAD_PATHS or ARCHIVE_PATHS" for path in sorted(found - listed)]
            + [f"{path}: on the upload list but takes no file" for path in sorted(listed - found)])


def _filled(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


async def _helper_reading_a_form(request: Request):
    return await request.form()


def test_every_file_route_is_on_the_upload_list():
    assert _upload_list_problems(_file_routes(app)) == []


def test_the_walk_names_each_way_of_taking_a_file():
    router = APIRouter()

    def declared(file: Annotated[UploadFile, File()]):
        return file.filename

    def implicit(file: UploadFile):
        return file.filename

    async def by_hand(request: Request):
        return await _helper_reading_a_form(request)

    def guarded(upload: AdminForm):
        return upload.file.filename

    def plain_json(body: dict):
        return body

    for path, handler in (("/declared", declared), ("/implicit", implicit), ("/by-hand", by_hand),
                          ("/guarded", guarded), ("/json", plain_json)):
        router.add_api_route(path, handler, methods=["POST"])
    scratch = FastAPI()
    scratch.include_router(router)

    assert _file_routes(scratch) == {"/declared", "/implicit", "/by-hand", "/guarded"}
    assert "/declared: takes a file but is not on UPLOAD_PATHS or ARCHIVE_PATHS" in _upload_list_problems({"/declared"})


def test_json_route_refuses_over_1mb(client, admin_headers):
    too_big = b"x" * (DEFAULT_BODY_LIMIT + 1)
    json_type = {"content-type": "application/json"}

    assert DEFAULT_BODY_LIMIT == 1024 * 1024
    for path in (LOGIN_URL, "/api/flights", "/api/flight-plans"):
        resp = client.post(path, content=too_big, headers={**admin_headers, **json_type})
        assert resp.status_code == 413, path
        assert "1MB" in resp.json()["detail"]


def test_json_route_streamed_past_1mb_is_cut_off(client):
    def chunks():
        for _ in range(20):
            yield b"y" * 65536 * 2

    resp = client.post(LOGIN_URL, content=chunks(), headers={"content-type": "application/json"})

    assert resp.status_code == 413


def test_json_body_of_exactly_1mb_is_not_refused(client, admin_user):
    filler = DEFAULT_BODY_LIMIT - len(json.dumps({"username": "admin", "password": ""}))
    body = json.dumps({"username": "admin", "password": "p" * filler})
    assert len(body) == DEFAULT_BODY_LIMIT

    resp = client.post(LOGIN_URL, content=body, headers={"content-type": "application/json"})

    assert resp.status_code != 413


@pytest.mark.parametrize("path", sorted(UPLOAD_PATHS))
def test_upload_routes_keep_todays_limit(path):
    assert body_limit_for(_filled(path)) == settings.MAX_UPLOAD_SIZE + FORM_OVERHEAD


@pytest.mark.parametrize("path", sorted(ARCHIVE_PATHS))
def test_archive_routes_keep_todays_limit(path):
    assert body_limit_for(path) == settings.MAX_ARCHIVE_SIZE + FORM_OVERHEAD


@pytest.mark.parametrize("path", sorted(UPLOAD_PATHS))
def test_a_trailing_slash_keeps_the_upload_limit(path):
    assert body_limit_for(_filled(path) + "/") == settings.MAX_UPLOAD_SIZE + FORM_OVERHEAD


@pytest.mark.parametrize("path", sorted(ARCHIVE_PATHS))
def test_a_trailing_slash_keeps_the_archive_limit(path):
    assert body_limit_for(path + "/") == settings.MAX_ARCHIVE_SIZE + FORM_OVERHEAD


def test_a_trailing_slash_gains_nothing_on_other_routes():
    assert body_limit_for(LOGIN_URL + "/") == DEFAULT_BODY_LIMIT
    assert body_limit_for("/") == DEFAULT_BODY_LIMIT


def test_an_upload_to_a_trailing_slash_path_is_not_cut_off(client, admin_headers):
    resp = client.post(DOCUMENT_URL + "/", content=b"x" * (DEFAULT_BODY_LIMIT + 1), headers=admin_headers,
                       follow_redirects=False)

    assert resp.status_code != 413


def test_a_parameter_matches_one_path_segment_only():
    assert body_limit_for("/api/pilots/7/photo") > DEFAULT_BODY_LIMIT
    assert body_limit_for("/api/pilots/7/8/photo") == DEFAULT_BODY_LIMIT
    assert body_limit_for("/api/pilots/7/photo/extra") == DEFAULT_BODY_LIMIT
    assert body_limit_for("/x/api/pilots/7/photo") == DEFAULT_BODY_LIMIT


def _png_of_size(size: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(buf, format="PNG")
    return buf.getvalue().ljust(size, b"\0")


def test_upload_at_todays_limit_still_accepted(client, admin_headers, db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    pilot = Pilot(first_name="Limit", last_name="Case")
    db.add(pilot)
    db.commit()
    full_size = _png_of_size(settings.MAX_UPLOAD_SIZE)

    photo = client.post(f"/api/pilots/{pilot.id}/photo", headers=admin_headers,
                        files={"file": (LARGE_PNG_NAME, full_size, PNG_MIME)})
    logo = client.post(LOGO_URL, headers=admin_headers,
                       files={"file": (LARGE_PNG_NAME, full_size, PNG_MIME)})
    document = client.post(DOCUMENT_URL, headers=admin_headers,
                           data={"entity_type": "general", "document_type": "other", "title": "Big"},
                           files={"file": ("big.pdf", b"%PDF-1.4\n".ljust(settings.MAX_UPLOAD_SIZE, b" "),
                                           "application/pdf")})

    assert photo.status_code == 200, photo.text
    assert logo.status_code == 200, logo.text
    assert document.status_code == 200, document.text
    assert document.json()["file_size_bytes"] == settings.MAX_UPLOAD_SIZE


def test_report_carrying_a_large_logo_still_runs(client, admin_headers):
    """The reports page sends the selected logo inside the JSON request."""
    config = {"report_type": "flight_summary", "logo_base64": "data:image/png;base64," + "A" * (3 * 1024 * 1024)}

    resp = client.post("/api/reports/generate", headers=admin_headers, json=config)

    assert resp.status_code == 200, resp.text


def test_detailed_geofence_polygon_still_saves(client, admin_headers):
    """A boundary traced from survey data can hold tens of thousands of vertices."""
    points = [[28.123456 + i * 1e-6, -81.123456 - i * 1e-6] for i in range(50_000)]
    body = {"name": "County line", "zone_type": "restricted", "geometry_type": "polygon", "polygon_points": points}
    assert len(json.dumps(body)) > DEFAULT_BODY_LIMIT

    created = client.post(GEOFENCE_URL, headers=admin_headers, json=body)
    assert created.status_code in (200, 201), created.text

    updated = client.patch(f"/api/geofences/{created.json()['id']}", headers=admin_headers,
                           json={"polygon_points": points})
    assert updated.status_code == 200, updated.text


# 7. Who may send a file is settled before any of it is read ---------------------

def _request_counting_reads(path: str, headers: dict) -> tuple[int, int]:
    """Send one POST straight through the ASGI app. Returns (status, body reads)."""
    reads = 0
    status = []
    boundary = "limitcheck"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"f.png\"\r\n"
            f"Content-Type: image/png\r\n\r\nnot an image\r\n--{boundary}--\r\n").encode()

    async def receive():
        nonlocal reads
        reads += 1
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            status.append(message["status"])

    raw_headers = [(b"content-type", f"multipart/form-data; boundary={boundary}".encode()),
                   (b"content-length", str(len(body)).encode())]
    raw_headers += [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
             "scheme": "http", "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
             "headers": raw_headers, "client": ("127.0.0.1", 50000), "server": ("testserver", 80)}
    asyncio.run(app(scope, receive, send))
    return status[0], reads


ALL_UPLOAD_ROUTES = sorted(UPLOAD_PATHS | ARCHIVE_PATHS)
FILES_UPLOAD_ROUTES = frozenset({DOCUMENT_URL, "/api/photos/upload"})


@pytest.mark.parametrize("path", ALL_UPLOAD_ROUTES)
def test_anonymous_upload_refused_before_body_read(client, admin_user, path):
    status, reads = _request_counting_reads(_filled(path), {})

    assert status == 401
    assert reads == 0


@pytest.mark.parametrize("path", ALL_UPLOAD_ROUTES)
def test_wrong_permission_refused_before_body_read(client, admin_headers, pilot_headers, path):
    if path in FILES_UPLOAD_ROUTES:
        body = {"changes": [{"role": "pilot", "key": "files.upload", "value": "none"}]}
        assert client.put("/api/permissions", headers=admin_headers, json=body).status_code == 200

    status, reads = _request_counting_reads(_filled(path), pilot_headers)

    assert status == 403
    assert reads == 0


def test_the_counting_receive_sees_an_authorized_read(client, admin_headers):
    status, reads = _request_counting_reads(LOGO_URL, admin_headers)

    assert status == 400, "past the check, the file's content is what gets refused"
    assert reads > 0


def test_a_missing_file_is_still_a_validation_error(client, admin_headers):
    resp = client.post(LOGO_URL, headers=admin_headers, data={"other": "x"})

    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["body", "file"]


def test_a_missing_form_field_is_still_a_validation_error(client, admin_headers):
    resp = client.post(DOCUMENT_URL, headers=admin_headers,
                       data={"entity_type": "general", "document_type": "other", "title": ""},
                       files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})

    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["body", "title"]


def test_a_malformed_multipart_body_is_a_400(client, admin_headers):
    resp = client.post(LOGO_URL, content=b"junk",
                       headers={**admin_headers, "content-type": "multipart/form-data"})

    assert resp.status_code == 400


def test_a_multipart_parse_error_keeps_its_message(client, admin_headers):
    resp = client.post(LOGO_URL, content=b"junk",
                       headers={**admin_headers, "content-type": "multipart/form-data"})

    assert resp.json()["detail"] == "Missing boundary in multipart."


def test_an_upload_streamed_past_its_limit_is_still_a_413(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 1024)

    def chunks():
        yield b"--b\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.png\"\r\n\r\n"
        for _ in range(40):
            yield b"y" * 65536

    resp = client.post(LOGO_URL, content=chunks(),
                       headers={**admin_headers, "content-type": "multipart/form-data; boundary=b"})

    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"]


def test_the_upload_is_received_with_no_database_connection_held(client, admin_headers, monkeypatch, _engines):
    """The sign-in and permission checks read the database before the body.
    A slow upload must not keep a pooled connection checked out meanwhile."""
    from app import deps

    pool = _engines[0].kw["bind"].pool
    real = deps._parse_form
    held = []

    async def spy(request):
        held.append(pool.checkedout())
        return await real(request)

    monkeypatch.setattr(deps, "_parse_form", spy)
    before = pool.checkedout()    # the test's own seeding session
    _post(client, admin_headers, "one.json", _airdata("held-1"))

    assert held == [before]
