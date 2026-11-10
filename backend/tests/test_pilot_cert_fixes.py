"""Regression tests for the pilots, certifications and compliance fixes
(staging test 2026-11-08, Area 4)."""

from datetime import date, timedelta

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
