"""Regression tests for the pilots, certifications and compliance fixes
(staging test 2026-11-08, Area 4)."""

from datetime import date, timedelta

from app.models.certification import CertificationType, PilotCertification
from app.models.currency_rule import CurrencyRule
from app.models.flight import Flight
from app.models.pilot import Pilot

TODAY = date.today()


def _pilot(db, first="Test", last="Pilot", status="active"):
    p = Pilot(first_name=first, last_name=last, status=status)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# --- C-F12: a huge period_days must not crash currency evaluation ---


def test_currency_rule_period_days_out_of_range_is_refused(client, admin_headers):
    for days in (99999999, 3651, 0, -10):
        r = client.post("/api/currency/rules", headers=admin_headers, json={
            "name": "Huge", "required_hours": 1, "period_days": days})
        assert r.status_code == 422, (days, r.text)
    ok = client.post("/api/currency/rules", headers=admin_headers, json={
        "name": "Ten years", "required_hours": 1, "period_days": 3650})
    assert ok.status_code == 200
    r = client.patch(f"/api/currency/rules/{ok.json()['id']}", headers=admin_headers,
                     json={"period_days": 99999999})
    assert r.status_code == 422


def test_stored_huge_period_rule_does_not_break_compliance(client, db, admin_headers):
    pilot = _pilot(db)
    db.add(Flight(pilot_id=pilot.id, date=TODAY, duration_seconds=7200,
                  review_status="reviewed"))
    db.add(CurrencyRule(name="Huge", required_hours=1, period_days=99999999, is_active=True))
    db.add(CurrencyRule(name="Backwards", required_hours=1, period_days=-10, is_active=True))
    db.commit()
    for url in ("/api/currency/status", f"/api/currency/status/{pilot.id}",
                "/api/dashboard/compliance", f"/api/pilots/{pilot.id}/needs-attention"):
        r = client.get(url, headers=admin_headers)
        assert r.status_code == 200, (url, r.text)
    status = client.get(f"/api/currency/status/{pilot.id}", headers=admin_headers).json()
    # Both stored rules are evaluated within the allowed range, so the recent
    # two-hour flight keeps the pilot current on each.
    assert all(r["is_current"] for r in status["rules"])


# --- C-F1: pilot names must not be blank ---


def test_blank_pilot_names_are_refused(client, db, admin_headers):
    for body in ({"first_name": "", "last_name": ""}, {"first_name": "  ", "last_name": "Smith"},
                 {"first_name": "Ann", "last_name": " "}):
        r = client.post("/api/pilots", headers=admin_headers, json=body)
        assert r.status_code == 422, (body, r.text)
    ok = client.post("/api/pilots", headers=admin_headers, json={"first_name": " Ann ", "last_name": "Lee"})
    assert ok.status_code == 200
    assert ok.json()["first_name"] == "Ann"
    pid = ok.json()["id"]
    for body in ({"first_name": ""}, {"last_name": "   "}, {"first_name": None}):
        r = client.patch(f"/api/pilots/{pid}", headers=admin_headers, json=body)
        assert r.status_code == 422, (body, r.text)


# --- C-F7: certification dates, status and NIST level ---


def _cert_type(db, name="Part 107", months=None):
    ct = CertificationType(name=name, category="faa", has_expiration=True, renewal_period_months=months)
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return ct


def _cert(db, pilot_id, ct_id, *, status="complete", issue=None, expiry=None):
    pc = PilotCertification(pilot_id=pilot_id, certification_type_id=ct_id, status=status,
                            issue_date=issue, expiration_date=expiry)
    db.add(pc)
    db.commit()
    db.refresh(pc)
    return pc


def test_cert_expiry_before_issue_is_refused(client, db, admin_headers):
    pilot = _pilot(db)
    ct = _cert_type(db)
    r = client.post("/api/pilot-certifications", headers=admin_headers, json={
        "pilot_id": pilot.id, "certification_type_id": ct.id,
        "issue_date": "2026-06-01", "expiration_date": "2025-01-01"})
    assert r.status_code == 422
    pc = _cert(db, pilot.id, ct.id, issue=date(2026, 6, 1), expiry=date(2028, 6, 1))
    r = client.patch(f"/api/pilot-certifications/{pc.id}", headers=admin_headers,
                     json={"expiration_date": "2026-01-01"})
    assert r.status_code == 422
    r = client.patch(f"/api/pilot-certifications/{pc.id}", headers=admin_headers,
                     json={"issue_date": "2029-01-01"})
    assert r.status_code == 422
    r = client.post(f"/api/pilot-certifications/{pc.id}/renew", headers=admin_headers,
                    json={"issue_date": "2028-06-01", "expiration_date": "2027-01-01"})
    assert r.status_code == 422
    db.refresh(pc)
    assert pc.status == "complete"


def test_cert_status_and_nist_level_are_checked(client, db, admin_headers):
    pilot = _pilot(db)
    ct = _cert_type(db)
    for body in ({"status": "banana"}, {"nist_level": -3}, {"nist_level": 6}):
        r = client.post("/api/pilot-certifications", headers=admin_headers,
                        json={"pilot_id": pilot.id, "certification_type_id": ct.id, **body})
        assert r.status_code == 422, body
    pc = _cert(db, pilot.id, ct.id)
    for body in ({"status": "zzz"}, {"status": None}, {"nist_level": 0}):
        r = client.patch(f"/api/pilot-certifications/{pc.id}", headers=admin_headers, json=body)
        assert r.status_code == 422, body
    r = client.patch(f"/api/pilot-certifications/{pc.id}", headers=admin_headers,
                     json={"status": "in_progress", "nist_level": 3})
    assert r.status_code == 200


def test_equipment_qual_status_is_checked(client, db, admin_headers):
    pilot = _pilot(db)
    r = client.post("/api/pilot-equipment-quals", headers=admin_headers,
                    json={"pilot_id": pilot.id, "vehicle_model": "X10", "status": "banana"})
    assert r.status_code == 422
    r = client.post("/api/pilot-equipment-quals", headers=admin_headers,
                    json={"pilot_id": pilot.id, "vehicle_model": "X10", "status": "qualified"})
    assert r.status_code == 200
    r = client.patch(f"/api/pilot-equipment-quals/{r.json()['id']}", headers=admin_headers,
                     json={"status": "zzz"})
    assert r.status_code == 422


# --- C-F8: one live certification per pilot and type ---


def test_second_live_cert_of_a_type_is_refused(client, db, admin_headers):
    pilot = _pilot(db)
    ct = _cert_type(db)
    body = {"pilot_id": pilot.id, "certification_type_id": ct.id, "status": "complete"}
    first = client.post("/api/pilot-certifications", headers=admin_headers,
                        json={**body, "expiration_date": "2026-11-27"})
    assert first.status_code == 200
    r = client.post("/api/pilot-certifications", headers=admin_headers,
                    json={**body, "expiration_date": "2030-01-01"})
    assert r.status_code == 400
    assert "already" in r.json()["detail"]
    # Another pilot, or the same pilot once the first is renewed, is fine.
    other = _pilot(db, first="Other")
    assert client.post("/api/pilot-certifications", headers=admin_headers,
                       json={**body, "pilot_id": other.id}).status_code == 200
    old = db.get(PilotCertification, first.json()["id"])
    old.status = "renewed"
    db.commit()
    assert client.post("/api/pilot-certifications", headers=admin_headers, json=body).status_code == 200
    # Reviving the renewed one would make two live certs again.
    r = client.patch(f"/api/pilot-certifications/{old.id}", headers=admin_headers, json={"status": "complete"})
    assert r.status_code == 400


# --- C-F10: Needs Attention leaves out renewed and not-issued certs ---


def test_needs_attention_skips_renewed_and_not_issued_certs(client, db, admin_headers):
    pilot = _pilot(db)
    old_type = _cert_type(db, "Part 107")
    other = _cert_type(db, "Night Ops")
    soon = TODAY + timedelta(days=20)
    _cert(db, pilot.id, old_type.id, status="renewed", expiry=TODAY - timedelta(days=5))
    _cert(db, pilot.id, old_type.id, status="complete", expiry=TODAY + timedelta(days=700))
    _cert(db, pilot.id, other.id, status="not_issued", expiry=soon)
    r = client.get(f"/api/pilots/{pilot.id}/needs-attention", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"count": 0, "items": []}


# --- C-F14: calendar events need a title and may not end before they start ---


def test_calendar_event_end_before_start_or_blank_title_is_refused(client, db, admin_headers):
    url = "/api/calendar/events"
    r = client.post(url, headers=admin_headers, json={
        "title": "Backwards", "start_date": "2026-11-25", "end_date": "2026-11-01"})
    assert r.status_code == 422
    r = client.post(url, headers=admin_headers, json={"title": "   ", "start_date": "2026-11-25"})
    assert r.status_code == 422
    ok = client.post(url, headers=admin_headers, json={
        "title": " Course ", "start_date": "2026-11-25", "end_date": "2026-11-26"})
    assert ok.status_code == 200
    assert ok.json()["title"] == "Course"
    eid = ok.json()["id"]
    for body in ({"end_date": "2026-11-20"}, {"start_date": "2026-11-30"}, {"title": ""}, {"title": None},
                 {"start_date": None}):
        r = client.patch(f"{url}/{eid}", headers=admin_headers, json=body)
        assert r.status_code == 422, body


# --- C-F15: calendar cert expirations follow the compliance filters ---


def test_calendar_cert_events_skip_renewed_not_issued_and_inactive_pilots(client, db, admin_headers):
    active = _pilot(db, first="Active")
    gone = _pilot(db, first="Gone", status="inactive")
    ct = _cert_type(db)
    other = _cert_type(db, "Night Ops")
    day = TODAY + timedelta(days=10)
    renewed = _cert(db, active.id, ct.id, status="renewed", expiry=day)
    live = _cert(db, active.id, ct.id, status="complete", expiry=day)
    not_issued = _cert(db, active.id, other.id, status="not_issued", expiry=day)
    inactive = _cert(db, gone.id, ct.id, status="complete", expiry=day)
    r = client.get("/api/calendar", headers=admin_headers,
                   params={"start": TODAY.isoformat(), "end": (TODAY + timedelta(days=30)).isoformat()})
    ids = {e["id"] for e in r.json()["events"] if e["category"] == "cert_expiration"}
    assert f"cert-{live.id}" in ids
    for pc in (renewed, not_issued, inactive):
        assert f"cert-{pc.id}" not in ids


# --- C-F2: pilot status, email, lengths and badge numbers ---


def test_pilot_status_email_and_lengths_are_checked(client, db, admin_headers):
    base = {"first_name": "Test", "last_name": "X"}
    for extra in ({"status": "banana"}, {"email": "not-an-email"}, {"badge_number": "B" * 51},
                  {"phone": "1" * 51}, {"first_name": "A" * 101}):
        r = client.post("/api/pilots", headers=admin_headers, json={**base, **extra})
        assert r.status_code == 422, extra
    ok = client.post("/api/pilots", headers=admin_headers,
                     json={**base, "status": "inactive", "email": "t.x@example.org", "badge_number": ""})
    assert ok.status_code == 200
    pid = ok.json()["id"]
    for body in ({"status": "zzz"}, {"status": None}, {"email": "a@b"}, {"notes": "n" * 10001}):
        r = client.patch(f"/api/pilots/{pid}", headers=admin_headers, json=body)
        assert r.status_code == 422, body
    assert client.patch(f"/api/pilots/{pid}", headers=admin_headers, json={"status": "active"}).status_code == 200


def test_duplicate_badge_number_is_refused(client, db, admin_headers):
    first = client.post("/api/pilots", headers=admin_headers,
                        json={"first_name": "A", "last_name": "One", "badge_number": "K-9"})
    assert first.status_code == 200
    r = client.post("/api/pilots", headers=admin_headers,
                    json={"first_name": "B", "last_name": "Two", "badge_number": " k-9 "})
    assert r.status_code == 400
    assert "A One" in r.json()["detail"]
    second = client.post("/api/pilots", headers=admin_headers,
                         json={"first_name": "B", "last_name": "Two", "badge_number": "K-10"})
    r = client.patch(f"/api/pilots/{second.json()['id']}", headers=admin_headers, json={"badge_number": "K-9"})
    assert r.status_code == 400
    # Re-saving a pilot's own badge, or leaving badges blank, is fine.
    assert client.patch(f"/api/pilots/{first.json()['id']}", headers=admin_headers,
                        json={"badge_number": "K-9"}).status_code == 200
    for name in ("C", "D"):
        assert client.post("/api/pilots", headers=admin_headers,
                           json={"first_name": name, "last_name": "Z", "badge_number": ""}).status_code == 200


# --- C-F6: certification type validation ---


def test_cert_type_fields_are_checked(client, db, admin_headers):
    url = "/api/certification-types"
    for body in ({"name": ""}, {"name": "   "}, {"name": "X", "renewal_period_months": -5},
                 {"name": "X", "renewal_period_months": 0}, {"name": "X", "category": "banana"}):
        r = client.post(url, headers=admin_headers, json=body)
        assert r.status_code == 422, body
    ok = client.post(url, headers=admin_headers, json={"name": " Night Ops 12mo ", "renewal_period_months": 12})
    assert ok.status_code == 200
    assert ok.json()["name"] == "Night Ops 12mo"
    for name in ("night ops 12mo", "NIGHT OPS 12MO "):
        r = client.post(url, headers=admin_headers, json={"name": name})
        assert r.status_code == 400, name
    other = client.post(url, headers=admin_headers, json={"name": "Other"}).json()
    for body in ({"name": "Night ops 12MO"}, ):
        assert client.patch(f"{url}/{other['id']}", headers=admin_headers, json=body).status_code == 400
    for body in ({"name": ""}, {"name": None}, {"category": "zzz"}, {"renewal_period_months": -1}):
        assert client.patch(f"{url}/{other['id']}", headers=admin_headers, json=body).status_code == 422, body
    # Renaming a type to its own name in another case is fine.
    assert client.patch(f"{url}/{other['id']}", headers=admin_headers, json={"name": "OTHER"}).status_code == 200


# --- C-F9: a renewed cert cannot be renewed again ---


def test_renewing_a_renewed_cert_is_refused(client, db, admin_headers):
    pilot = _pilot(db)
    ct = _cert_type(db, months=24)
    pc = _cert(db, pilot.id, ct.id, issue=date(2024, 1, 1), expiry=date(2026, 1, 1))
    url = f"/api/pilot-certifications/{pc.id}/renew"
    assert client.post(url, headers=admin_headers, json={"issue_date": "2026-01-01"}).status_code == 200
    r = client.post(url, headers=admin_headers, json={"issue_date": "2026-02-01"})
    assert r.status_code == 400
    assert "already renewed" in r.json()["detail"]
    assert db.query(PilotCertification).filter(PilotCertification.renewed_from_id == pc.id).count() == 1


# --- C-F11: upcoming expirations leave out inactive pilots ---


def test_upcoming_expirations_skip_inactive_pilots(client, db, admin_headers):
    active = _pilot(db, first="Active")
    gone = _pilot(db, first="Gone", status="inactive")
    ct = _cert_type(db)
    _cert(db, active.id, ct.id, expiry=TODAY + timedelta(days=10))
    _cert(db, gone.id, ct.id, expiry=TODAY + timedelta(days=10))
    r = client.get("/api/dashboard/upcoming-expirations", headers=admin_headers)
    assert r.status_code == 200
    assert [row["pilot_id"] for row in r.json()] == [active.id]


# --- C-F13: currency rule name, hours and flights ---


def test_currency_rule_fields_are_checked(client, db, admin_headers):
    url = "/api/currency/rules"
    base = {"name": "Quarterly", "required_hours": 5, "period_days": 90}
    for extra in ({"name": ""}, {"name": "  "}, {"required_hours": -1}, {"required_flights": -2},
                  {"name": "N" * 301}):
        r = client.post(url, headers=admin_headers, json={**base, **extra})
        assert r.status_code == 422, extra
    ok = client.post(url, headers=admin_headers, json={**base, "name": " Quarterly ", "required_flights": 0})
    assert ok.status_code == 200
    assert ok.json()["name"] == "Quarterly"
    rid = ok.json()["id"]
    for body in ({"name": ""}, {"name": None}, {"required_hours": -0.5}, {"required_hours": None},
                 {"period_days": None}, {"required_flights": -1}, {"is_active": None}):
        r = client.patch(f"{url}/{rid}", headers=admin_headers, json=body)
        assert r.status_code == 422, body
    assert client.patch(f"{url}/{rid}", headers=admin_headers, json={"required_flights": None}).status_code == 200
