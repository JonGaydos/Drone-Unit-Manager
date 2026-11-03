"""Only reviewed flights count toward pilot currency, wherever it is evaluated."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.models.currency_rule import CurrencyRule
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.setting import Setting
from app.routers.currency import counted_flights_filter
from app.services import email_digest
from app.services.sync_manager import SyncResult, _upsert_flights

STATUS_URL = "/api/currency/status"
COMPLIANCE_URL = "/api/dashboard/compliance"
REMINDERS_URL = "/api/currency/send-reminders"
FLIGHTS_URL = "/api/flights"
REVIEWED = "reviewed"
NEEDS_REVIEW = "needs_review"
RECENT = date.today() - timedelta(days=5)


@pytest.fixture
def rule(db):
    row = CurrencyRule(name="Monthly hour", required_hours=1, period_days=30, is_active=True)
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def flyer(db):
    pilot = Pilot(first_name="Fay", last_name="Flyer", status="active", email="fay@example.com")
    db.add(pilot)
    db.commit()
    db.refresh(pilot)
    return pilot


def _flight(db, pilot, review_status):
    flight = Flight(pilot_id=pilot.id, date=RECENT, duration_seconds=3600, review_status=review_status)
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return flight


def _is_current(client, headers, pilot):
    resp = client.get(f"{STATUS_URL}/{pilot.id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["is_current"]


def test_filter_requires_reviewed(db, flyer):
    reviewed = _flight(db, flyer, REVIEWED)
    _flight(db, flyer, NEEDS_REVIEW)
    assert [f.id for f in db.query(Flight).filter(counted_flights_filter()).all()] == [reviewed.id]


def test_unreviewed_flight_does_not_count_toward_currency(client, db, rule, flyer, admin_headers):
    _flight(db, flyer, NEEDS_REVIEW)
    assert _is_current(client, admin_headers, flyer) is False


def test_reviewed_flight_counts(client, db, rule, flyer, admin_headers):
    _flight(db, flyer, REVIEWED)
    assert _is_current(client, admin_headers, flyer) is True


def test_edit_back_to_queue_stops_counting(client, db, rule, pilot_user, linked_pilot, pilot_headers, admin_headers):
    flight = _flight(db, linked_pilot, REVIEWED)
    assert _is_current(client, admin_headers, linked_pilot) is True

    resp = client.patch(f"{FLIGHTS_URL}/{flight.id}", json={"purpose": "Changed"}, headers=pilot_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["review_status"] == NEEDS_REVIEW
    assert _is_current(client, admin_headers, linked_pilot) is False


def test_synced_flight_needs_review_to_count(client, db, rule, flyer, admin_headers, supervisor_headers):
    """A flight arrives from a provider sync awaiting review, and counts once reviewed."""
    listed = {"external_id": "ext-1", "date": str(RECENT), "duration_seconds": 3600, "pilot_name": "Fay Flyer"}
    _upsert_flights([listed], [{"name": "Fay Flyer"}], db, SyncResult())
    db.commit()
    flight = db.query(Flight).filter(Flight.pilot_id == flyer.id).one()
    assert flight.review_status == NEEDS_REVIEW
    assert _is_current(client, admin_headers, flyer) is False

    resp = client.patch(f"{FLIGHTS_URL}/{flight.id}", json={"review_status": REVIEWED}, headers=supervisor_headers)
    assert resp.status_code == 200, resp.text
    assert _is_current(client, admin_headers, flyer) is True


@pytest.mark.parametrize("review_status,current", [(REVIEWED, True), (NEEDS_REVIEW, False)])
def test_currency_rule_same_on_dashboard_and_status_routes(client, db, rule, flyer, admin_headers,
                                                           review_status, current):
    _flight(db, flyer, review_status)

    single = client.get(f"{STATUS_URL}/{flyer.id}", headers=admin_headers).json()
    unit = client.get(STATUS_URL, headers=admin_headers).json()[0]
    compliance = client.get(COMPLIANCE_URL, headers=admin_headers).json()
    attention = client.get(f"/api/pilots/{flyer.id}/needs-attention", headers=admin_headers).json()

    assert single["is_current"] is current
    assert unit["is_current"] is current
    assert compliance["pilot_currency_status"][0]["is_current"] is current
    assert compliance["pilots_current"] == (1 if current else 0)
    assert compliance["pilots_lapsed"] == (0 if current else 1)
    assert any(item["category"] == "currency" for item in attention["items"]) is not current
    assert single["rules"][0]["actual_flights"] == (1 if current else 0)
    assert compliance["pilot_currency_status"][0]["rules"] == single["rules"]


def test_reminder_goes_to_a_pilot_with_only_unreviewed_flights(client, db, rule, flyer, admin_headers):
    _flight(db, flyer, NEEDS_REVIEW)
    db.add(Setting(key="smtp_enabled", value="true"))
    db.commit()
    with patch.object(email_digest, "send_email", return_value=True) as send:
        resp = client.post(REMINDERS_URL, json={}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["sent"] == 1
    send.assert_called_once()
