"""Batch 1 security fixes: file serving, client IP and login lockout, flight plan
approval, flight review fields, pilot self-edits, roles and the last admin.

Each test pins a hole that was open before the fix, so a regression shows up as
a failing test rather than an exploitable endpoint.
"""

import os
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.config import settings
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.flight import Flight
from app.models.flight_approval import FlightPlan
from app.models.photo import Photo
from app.models.pilot import Pilot
from app.models.user import User
from app.routers import auth as auth_router
from app.routers.auth import create_token
from app.routers.photos import _sign_photo
from app.services.file_validation import USER_FILE_CSP
from tests.conftest import _seed_user, ADMIN_PASSWORD, PILOT_PASSWORD

_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f8f0000000049454e44ae42"
    "6082"
)


def _headers(user):
    return {"Authorization": f"Bearer {create_token(user.id)}"}


@pytest.fixture
def supervisor_user(db):
    return _seed_user(db, username="super", role="supervisor", password="SuperPassw0rd!!")


@pytest.fixture
def photo_dir(tmp_path, monkeypatch):
    photos = tmp_path / "photos"
    photos.mkdir()
    monkeypatch.setattr("app.routers.photos.UPLOAD_DIR", str(photos))
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return photos


@pytest.fixture
def doc_dir(tmp_path, monkeypatch):
    updir = tmp_path / "uploads"
    updir.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(updir))
    return updir


# 1. Uploaded files are typed and served by the server, never the uploader ----

def test_photo_upload_ignores_client_content_type(client, db, admin_headers, photo_dir):
    """A real PNG labelled text/html by the client is stored and served as a PNG."""
    resp = client.post(
        "/api/photos/upload", headers=admin_headers,
        files={"file": ("evil.png", _PNG_1x1, "text/html")},
    )
    assert resp.status_code == 200, resp.text
    photo = db.get(Photo, resp.json()["id"])
    assert photo.mime_type == "image/png"

    sig, exp = _sign_photo(photo.id, "view")
    served = client.get(f"/api/photos/{photo.id}/view?sig={sig}&exp={exp}")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.headers["content-security-policy"] == USER_FILE_CSP
    assert served.headers["x-content-type-options"] == "nosniff"


def test_photo_with_spoofed_stored_type_is_served_as_image(client, db, photo_dir):
    """A record saved before the fix with an attacker-chosen type is still
    served by its extension, so it can never be delivered as HTML or script."""
    (photo_dir / "legacy.png").write_bytes(_PNG_1x1)
    photo = Photo(filename="legacy.png", original_filename="legacy.png", mime_type="text/html")
    db.add(photo)
    db.commit()
    sig, exp = _sign_photo(photo.id, "view")
    served = client.get(f"/api/photos/{photo.id}/view?sig={sig}&exp={exp}")
    assert served.headers["content-type"] == "image/png"


def _upload_doc(client, headers, filename, content, content_type):
    return client.post(
        "/api/documents/upload", headers=headers,
        data={"entity_type": "general", "document_type": "other", "title": "T"},
        files={"file": (filename, content, content_type)},
    )


def test_document_without_extension_is_rejected(client, admin_headers, doc_dir):
    resp = _upload_doc(client, admin_headers, "memo", b"<script>x</script>", "text/html")
    assert resp.status_code == 400


def test_document_type_comes_from_extension_and_downloads_sandboxed(client, db, admin_headers, doc_dir):
    """A .txt labelled text/html is stored as text/plain and served as a
    sandboxed attachment, so it cannot render as a page on this origin."""
    resp = _upload_doc(client, admin_headers, "memo.txt", b"<script>x</script>", "text/html")
    assert resp.status_code == 200, resp.text
    doc = db.get(Document, resp.json()["id"])
    assert doc.mime_type == "text/plain"

    served = client.get(f"/api/documents/{doc.id}/view", headers=admin_headers)
    assert served.headers["content-type"].startswith("text/plain")
    assert served.headers["content-disposition"].startswith("attachment")
    assert served.headers["content-security-policy"] == USER_FILE_CSP


def test_pdf_document_is_inline_without_sandbox(client, db, admin_headers, doc_dir):
    """PDFs stay viewable in the browser: sandbox would disable its PDF viewer."""
    resp = _upload_doc(client, admin_headers, "faa.pdf", b"%PDF-1.4 x", "application/pdf")
    doc_id = resp.json()["id"]
    served = client.get(f"/api/documents/{doc_id}/view", headers=admin_headers)
    assert served.headers["content-type"] == "application/pdf"
    assert served.headers["content-disposition"].startswith("inline")
    assert "sandbox" not in served.headers.get("content-security-policy", "")


def test_global_csp_restricts_form_targets(client):
    csp = client.get("/api/health").headers["content-security-policy"]
    assert "form-action 'self'" in csp


# 2. Client IP resolution and login lockout -----------------------------------

def _req(peer, headers=None):
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers={k.lower(): v for k, v in (headers or {}).items()})


def test_untrusted_peer_cannot_claim_an_address():
    """A public peer's forwarding headers are ignored entirely."""
    req = _req("203.0.113.9", {"X-Forwarded-For": "1.2.3.4", "CF-Connecting-IP": "5.6.7.8"})
    assert auth_router._client_ip(req) == "203.0.113.9"


def test_trusted_proxy_prefers_cf_connecting_ip():
    req = _req("172.17.0.1", {"X-Forwarded-For": "1.2.3.4, 198.51.100.7", "CF-Connecting-IP": "198.51.100.7"})
    assert auth_router._client_ip(req) == "198.51.100.7"


def test_trusted_proxy_reads_x_forwarded_for_from_the_right():
    """The leftmost entry is whatever the client sent; the rightmost
    non-proxy hop is the address the proxy actually saw."""
    req = _req("172.17.0.1", {"X-Forwarded-For": "1.2.3.4, 198.51.100.7, 10.0.0.2"})
    assert auth_router._client_ip(req) == "198.51.100.7"


def test_malformed_trusted_proxy_entry_is_skipped_not_fatal():
    """A typo in TRUSTED_PROXIES must not break every login; the bad entry is
    ignored and the valid ones still apply."""
    nets = auth_router._trusted_networks("10.0.0.0/8, not-a-network ,192.168.0.0/16")
    assert [str(n) for n in nets] == ["10.0.0.0/8", "192.168.0.0/16"]


def test_forged_forwarded_for_does_not_reset_login_limit(client, admin_user):
    """Rotating X-Forwarded-For used to give every guess a fresh bucket."""
    codes = [
        client.post("/api/auth/login", headers={"X-Forwarded-For": f"10.9.9.{i}"},
                    json={"username": "admin", "password": "wrong-password-X1"}).status_code
        for i in range(6)
    ]
    assert codes[-1] == 429


def test_account_locks_after_repeated_failures(client, admin_user, monkeypatch):
    """Guesses spread across addresses still lock the targeted account, and the
    lock holds even for the right password."""
    monkeypatch.setattr(auth_router, "_RATE_LIMIT", 1000)
    for _ in range(auth_router._USER_FAIL_LIMIT):
        assert client.post("/api/auth/login", json={"username": "admin", "password": "Wrong1Password"}).status_code == 401
    locked = client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert locked.status_code == 429


def test_successful_login_clears_failure_count(client, admin_user, monkeypatch):
    monkeypatch.setattr(auth_router, "_RATE_LIMIT", 1000)
    for _ in range(auth_router._USER_FAIL_LIMIT - 1):
        client.post("/api/auth/login", json={"username": "admin", "password": "Wrong1Password"})
    assert client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    assert "admin" not in auth_router._failed_by_user


# 3. Flight plans: no self-approval, edits go back for review -----------------

def _plan(db, submitter, status="pending"):
    pilot = Pilot(first_name="P", last_name="One", status="active")
    db.add(pilot)
    db.flush()
    plan = FlightPlan(title="Search", date_planned=datetime(2026, 9, 1, 12), pilot_id=pilot.id,
                      submitted_by_id=submitter.id, status=status)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def test_pilot_cannot_approve_own_plan_through_edit(client, db, pilot_user, pilot_headers):
    plan = _plan(db, pilot_user)
    resp = client.patch(f"/api/flight-plans/{plan.id}", headers=pilot_headers, json={"status": "approved"})
    assert resp.status_code == 403
    db.refresh(plan)
    assert plan.status == "pending"


def test_supervisor_cannot_approve_own_plan(client, db, supervisor_user):
    plan = _plan(db, supervisor_user)
    resp = client.post(f"/api/flight-plans/{plan.id}/approve", headers=_headers(supervisor_user), json={})
    assert resp.status_code == 403


def test_supervisor_can_approve_someone_elses_plan(client, db, pilot_user, supervisor_user):
    plan = _plan(db, pilot_user)
    resp = client.post(f"/api/flight-plans/{plan.id}/approve", headers=_headers(supervisor_user), json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_editing_a_denied_plan_resubmits_it(client, db, pilot_user, pilot_headers):
    plan = _plan(db, pilot_user, status="denied")
    resp = client.patch(f"/api/flight-plans/{plan.id}", headers=pilot_headers, json={"location": "North field"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_admin_edit_of_approved_plan_returns_it_to_review(client, db, pilot_user, admin_user, admin_headers):
    plan = _plan(db, pilot_user, status="approved")
    resp = client.patch(f"/api/flight-plans/{plan.id}", headers=admin_headers, json={"location": "Changed"})
    assert resp.json()["status"] == "pending"


def test_bookkeeping_edit_keeps_plan_approved(client, db, pilot_user, admin_headers):
    """Adding notes or linking the executed flight is not a change to what the
    supervisor reviewed, so it must not undo the approval."""
    plan = _plan(db, pilot_user, status="approved")
    resp = client.patch(f"/api/flight-plans/{plan.id}", headers=admin_headers, json={"notes": "Flown as planned"})
    assert resp.json()["status"] == "approved"


def test_resending_unchanged_date_with_offset_keeps_plan_approved(client, db, pilot_user, admin_headers):
    plan = _plan(db, pilot_user, status="approved")
    resp = client.patch(f"/api/flight-plans/{plan.id}", headers=admin_headers,
                        json={"date_planned": "2026-09-01T12:00:00+00:00", "title": "Search"})
    assert resp.json()["status"] == "approved"


def test_admin_can_reopen_a_plan_as_pending(client, db, pilot_user, admin_headers):
    plan = _plan(db, pilot_user, status="approved")
    resp = client.patch(f"/api/flight-plans/{plan.id}", headers=admin_headers, json={"status": "pending"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_plan_update_enforces_altitude_ceiling(client, db, pilot_user, pilot_headers):
    plan = _plan(db, pilot_user)
    resp = client.patch(f"/api/flight-plans/{plan.id}", headers=pilot_headers, json={"max_altitude_planned": 900})
    assert resp.status_code == 422


# 4. Flights: review fields are a supervisor decision --------------------------

def _flight(db, **kwargs):
    flight = Flight(date=date(2026, 9, 1), purpose="Training", review_status="needs_review", **kwargs)
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return flight


@pytest.mark.parametrize("field,value", [
    ("review_status", "reviewed"), ("pilot_confirmed", False), ("counts_toward_totals", False),
])
def test_pilot_cannot_change_flight_review_fields(client, db, pilot_headers, field, value):
    flight = _flight(db)
    resp = client.patch(f"/api/flights/{flight.id}", headers=pilot_headers, json={field: value})
    assert resp.status_code == 403


def test_pilot_edit_echoing_review_status_still_saves(client, db, pilot_headers):
    """An edit form that sends back the unchanged review state is not refused."""
    flight = _flight(db)
    resp = client.patch(f"/api/flights/{flight.id}", headers=pilot_headers,
                        json={"review_status": "needs_review", "purpose": "Search"})
    assert resp.status_code == 200
    assert resp.json()["purpose"] == "Search"


def test_supervisor_can_mark_flight_reviewed(client, db, supervisor_user):
    flight = _flight(db)
    resp = client.patch(f"/api/flights/{flight.id}", headers=_headers(supervisor_user), json={"review_status": "reviewed"})
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "reviewed"


def test_every_changed_flight_field_is_audited(client, db, pilot_headers):
    flight = _flight(db)
    client.patch(f"/api/flights/{flight.id}", headers=pilot_headers,
                 json={"takeoff_address": "1 Main St", "case_number": "2026-001"})
    entry = db.query(AuditLog).filter(AuditLog.entity_type == "flight").order_by(AuditLog.id.desc()).first()
    assert "takeoff_address" in entry.changes
    assert "case_number" in entry.changes


# 5. Pilots cannot grant themselves supervisor-controlled profile fields -------

def _linked_pilot(db, user, status="active"):
    pilot = Pilot(first_name="Pat", last_name="Pilot", status=status)
    db.add(pilot)
    db.flush()
    user.pilot_id = pilot.id
    db.commit()
    return pilot


@pytest.mark.parametrize("field,value", [
    ("status", "active"), ("counts_toward_totals", False), ("photo_url", "https://tracker.example/p.gif"),
])
def test_pilot_cannot_change_supervisor_fields_on_own_profile(client, db, pilot_user, pilot_headers, field, value):
    pilot = _linked_pilot(db, pilot_user, status="inactive")
    resp = client.patch(f"/api/pilots/{pilot.id}", headers=pilot_headers, json={field: value})
    assert resp.status_code == 403


def test_pilot_can_update_own_contact_details(client, db, pilot_user, pilot_headers):
    pilot = _linked_pilot(db, pilot_user)
    resp = client.patch(f"/api/pilots/{pilot.id}", headers=pilot_headers, json={"phone": "555-0100"})
    assert resp.status_code == 200
    assert resp.json()["phone"] == "555-0100"


# 6. Roles are validated and the last admin cannot be removed ------------------

def test_unknown_role_is_rejected(client, admin_headers):
    resp = client.post("/api/auth/users", headers=admin_headers, json={
        "username": "odd", "password": PILOT_PASSWORD, "display_name": "Odd", "role": "superuser",
    })
    assert resp.status_code == 422


@pytest.mark.parametrize("change", [{"role": "pilot"}, {"is_active": False}])
def test_last_admin_cannot_be_demoted_or_deactivated(client, admin_user, admin_headers, change):
    resp = client.patch(f"/api/auth/users/{admin_user.id}", headers=admin_headers, json=change)
    assert resp.status_code == 400


def test_admin_can_be_demoted_when_another_admin_remains(client, db, admin_user, admin_headers):
    second = _seed_user(db, username="admin2", role="admin", password=ADMIN_PASSWORD)
    resp = client.patch(f"/api/auth/users/{second.id}", headers=admin_headers, json={"role": "supervisor"})
    assert resp.status_code == 200
    db.expire_all()
    assert db.get(User, second.id).role == "supervisor"
