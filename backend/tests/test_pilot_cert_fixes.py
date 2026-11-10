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
