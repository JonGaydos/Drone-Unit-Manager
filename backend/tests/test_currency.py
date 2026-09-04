"""Currency status math + per-pilot needs-attention tests.

Covers the real behavior of two endpoints:

* GET ``/api/currency/status`` (``app.routers.currency``) computes per-pilot
  currency from ``Flight`` rows against active ``CurrencyRule`` rows. A pilot is
  ``is_current`` on a rule when, within the rule's ``period_days`` window
  (cutoff = ``today - period_days``), accumulated flight ``actual_hours >=
  required_hours`` AND (``required_flights is None`` or ``actual_flights >=
  required_flights``). The pilot's overall ``is_current`` is the AND of every
  active rule. There are no green/amber/red strings here -- currency is a
  boolean per rule and overall.

* GET ``/api/pilots/{id}/needs-attention`` (``app.routers.pilots``) aggregates
  lapsed currency rules (level "red", category "currency") and certifications
  (joined to their type) whose ``expiration_date`` is set: already past
  (``days < 0``) -> level "red"; expiring within 30 days
  (``0 <= days <= 30``) -> level "amber"; further out -> omitted; null
  expiration -> omitted. Response shape: ``{"count": int, "items": [...]}``
  with each item ``{"level", "category", "text"}``.

Both endpoints require only an authenticated user (``CurrentUser``); any role
including pilot is allowed.

Dates are computed relative to ``date.today()`` with ``timedelta`` so the
window/expiry thresholds are exercised deterministically across calendar dates.
Main-db rows are seeded via the ``db`` fixture; the app commits.
"""

from datetime import date, timedelta

from app.models.certification import CertificationType, PilotCertification
from app.models.currency_rule import CurrencyRule
from app.models.flight import Flight
from app.models.pilot import Pilot

CURRENCY_STATUS_URL = "/api/currency/status"
TODAY = date.today()


def _seed_pilot(db, *, first="Test", last="Pilot", status="active"):
    pilot = Pilot(first_name=first, last_name=last, status=status)
    db.add(pilot)
    db.commit()
    db.refresh(pilot)
    return pilot


def _seed_rule(db, *, name, required_hours, period_days, required_flights=None):
    rule = CurrencyRule(
        name=name,
        required_hours=required_hours,
        period_days=period_days,
        required_flights=required_flights,
        is_active=True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _seed_flight(db, *, pilot_id, flight_date, duration_seconds):
    f = Flight(pilot_id=pilot_id, date=flight_date, duration_seconds=duration_seconds)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def _seed_cert_type(db, *, name):
    ct = CertificationType(name=name, category="custom", has_expiration=True)
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return ct


def _seed_cert(db, *, pilot_id, cert_type_id, expiration_date, status="complete"):
    pc = PilotCertification(
        pilot_id=pilot_id,
        certification_type_id=cert_type_id,
        status=status,
        expiration_date=expiration_date,
    )
    db.add(pc)
    db.commit()
    db.refresh(pc)
    return pc


def _status_for(payload, pilot_id):
    return next(row for row in payload if row["pilot_id"] == pilot_id)


def test_currency_status_current_vs_lapsed_pilot(client, db, admin_headers):
    """One active rule (2h within 90 days). A pilot with a recent qualifying
    flight is current; a pilot whose only flight is older than the window is
    lapsed."""
    period_days = 90
    _seed_rule(db, name="Quarterly 2h", required_hours=2.0, period_days=period_days)

    current = _seed_pilot(db, last="Current")
    lapsed = _seed_pilot(db, last="Lapsed")

    # Current: a 3h flight 10 days ago (inside the 90-day window).
    _seed_flight(
        db,
        pilot_id=current.id,
        flight_date=TODAY - timedelta(days=10),
        duration_seconds=3 * 3600,
    )
    # Lapsed: a 3h flight, but (window + 10) days ago -> aged out of the window.
    _seed_flight(
        db,
        pilot_id=lapsed.id,
        flight_date=TODAY - timedelta(days=period_days + 10),
        duration_seconds=3 * 3600,
    )

    resp = client.get(CURRENCY_STATUS_URL, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    cur_row = _status_for(payload, current.id)
    lap_row = _status_for(payload, lapsed.id)

    # Overall currency boolean.
    assert cur_row["is_current"] is True
    assert lap_row["is_current"] is False

    # Per-rule detail: the current pilot has 3 in-window hours; the lapsed pilot
    # has 0 (its only flight aged out of the window).
    cur_rule = cur_row["rules"][0]
    lap_rule = lap_row["rules"][0]
    assert cur_rule["is_current"] is True
    assert cur_rule["actual_hours"] == 3.0
    assert lap_rule["is_current"] is False
    assert lap_rule["actual_hours"] == 0.0


def test_currency_status_required_flights_count(client, db, admin_headers):
    """A rule with required_flights makes hours alone insufficient: the pilot
    needs the flight count too, even within the window."""
    _seed_rule(
        db,
        name="2 flights",
        required_hours=1.0,
        period_days=30,
        required_flights=2,
    )
    pilot = _seed_pilot(db, last="OneFlight")

    # One long flight: meets hours, but only 1 flight (< 2 required).
    _seed_flight(
        db,
        pilot_id=pilot.id,
        flight_date=TODAY - timedelta(days=5),
        duration_seconds=2 * 3600,
    )

    resp = client.get(CURRENCY_STATUS_URL, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    row = _status_for(resp.json(), pilot.id)
    rule = row["rules"][0]
    assert rule["actual_hours"] == 2.0
    assert rule["actual_flights"] == 1
    assert rule["is_current"] is False
    assert row["is_current"] is False


def test_currency_status_requires_auth(client, db):
    """Unauthenticated request is rejected."""
    resp = client.get(CURRENCY_STATUS_URL)
    assert resp.status_code == 401, resp.text


def test_currency_status_allows_pilot_role(client, db, pilot_headers):
    """The status endpoint is open to any authenticated user (CurrentUser)."""
    resp = client.get(CURRENCY_STATUS_URL, headers=pilot_headers)
    assert resp.status_code == 200, resp.text


def test_needs_attention_red_and_amber_certs(client, db, admin_headers):
    """A pilot with an expired cert (red), an expiring-soon cert (amber), and a
    far-future cert (omitted). No active currency rules, so only cert items
    appear."""
    pilot = _seed_pilot(db, last="Mixed")

    expired_type = _seed_cert_type(db, name="Expired Cert")
    soon_type = _seed_cert_type(db, name="Soon Cert")
    valid_type = _seed_cert_type(db, name="Valid Cert")

    expired_date = TODAY - timedelta(days=5)
    soon_date = TODAY + timedelta(days=10)   # within the 30-day amber band
    valid_date = TODAY + timedelta(days=365)  # far future -> omitted

    _seed_cert(db, pilot_id=pilot.id, cert_type_id=expired_type.id,
               expiration_date=expired_date)
    _seed_cert(db, pilot_id=pilot.id, cert_type_id=soon_type.id,
               expiration_date=soon_date)
    _seed_cert(db, pilot_id=pilot.id, cert_type_id=valid_type.id,
               expiration_date=valid_date)

    resp = client.get(f"/api/pilots/{pilot.id}/needs-attention", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    # Only the expired (red) and soon (amber) certs surface; valid omitted.
    assert payload["count"] == 2
    items = payload["items"]
    assert len(items) == 2

    reds = [i for i in items if i["level"] == "red"]
    ambers = [i for i in items if i["level"] == "amber"]
    assert len(reds) == 1
    assert len(ambers) == 1

    red = reds[0]
    assert red["category"] == "certification"
    assert "Expired Cert" in red["text"]
    assert str(expired_date) in red["text"]

    amber = ambers[0]
    assert amber["category"] == "certification"
    assert "Soon Cert" in amber["text"]
    assert str(soon_date) in amber["text"]

    # The far-future valid cert must not appear in any item.
    assert all("Valid Cert" not in i["text"] for i in items)


def test_needs_attention_null_expiration_omitted(client, db, admin_headers):
    """A cert with no expiration_date is skipped entirely."""
    pilot = _seed_pilot(db, last="NoExpiry")
    ct = _seed_cert_type(db, name="No Expiry Cert")
    _seed_cert(db, pilot_id=pilot.id, cert_type_id=ct.id, expiration_date=None)

    resp = client.get(f"/api/pilots/{pilot.id}/needs-attention", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["count"] == 0
    assert payload["items"] == []


def test_needs_attention_includes_lapsed_currency_as_red(client, db, admin_headers):
    """A lapsed currency rule surfaces as a red currency item alongside certs."""
    period_days = 60
    _seed_rule(db, name="Bimonthly 2h", required_hours=2.0, period_days=period_days)
    pilot = _seed_pilot(db, last="LapsedCurrency")

    # Only flight is outside the window -> lapsed.
    _seed_flight(
        db,
        pilot_id=pilot.id,
        flight_date=TODAY - timedelta(days=period_days + 5),
        duration_seconds=3 * 3600,
    )

    resp = client.get(f"/api/pilots/{pilot.id}/needs-attention", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]

    currency_items = [i for i in items if i["category"] == "currency"]
    assert len(currency_items) == 1
    assert currency_items[0]["level"] == "red"
    assert "Bimonthly 2h" in currency_items[0]["text"]


def test_needs_attention_unknown_pilot_404(client, db, admin_headers):
    resp = client.get("/api/pilots/999999/needs-attention", headers=admin_headers)
    assert resp.status_code == 404, resp.text


def test_needs_attention_requires_auth(client, db):
    resp = client.get("/api/pilots/1/needs-attention")
    assert resp.status_code == 401, resp.text
