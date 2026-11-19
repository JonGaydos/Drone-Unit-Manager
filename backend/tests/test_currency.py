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
from app.models.vehicle import Vehicle

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
    f = Flight(pilot_id=pilot_id, date=flight_date, duration_seconds=duration_seconds, review_status="reviewed")
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


# --- Model list on rules ---

RULES_URL = "/api/currency/rules"


def _vehicle(db, model, serial):
    v = Vehicle(serial_number=serial, manufacturer="Acme", model=model)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _flight_on(db, pilot, vehicle, hours, days_ago=5):
    f = Flight(pilot_id=pilot.id, vehicle_id=vehicle.id if vehicle else None,
               date=TODAY - timedelta(days=days_ago), duration_seconds=int(hours * 3600),
               review_status="reviewed")
    db.add(f)
    db.commit()
    return f


def _post_rule(client, headers, **extra):
    body = {"name": "Rule", "required_hours": 3, "period_days": 90, **extra}
    return client.post(RULES_URL, headers=headers, json=body)


def test_rule_with_two_models_counts_both(client, db, admin_headers):
    assert _post_rule(client, admin_headers, vehicle_models=["X10", "X2E"]).status_code == 200
    x10, x2e, lemur = _vehicle(db, "X10", "S1"), _vehicle(db, "X2E", "S2"), _vehicle(db, "LEMUR 2", "S3")
    both, other = _seed_pilot(db, last="Both"), _seed_pilot(db, last="Other")
    _flight_on(db, both, x10, 2)
    _flight_on(db, both, x2e, 1.5)
    _flight_on(db, other, lemur, 4)
    payload = client.get(CURRENCY_STATUS_URL, headers=admin_headers).json()
    assert _status_for(payload, both.id)["rules"][0]["is_current"] is True
    assert _status_for(payload, other.id)["rules"][0]["is_current"] is False


def test_rule_model_match_ignores_case_and_spaces(client, db, admin_headers):
    _post_rule(client, admin_headers, required_hours=1, vehicle_models=["x10 "])
    pilot = _seed_pilot(db)
    _flight_on(db, pilot, _vehicle(db, "X10", "S1"), 1)
    payload = client.get(CURRENCY_STATUS_URL, headers=admin_headers).json()
    assert _status_for(payload, pilot.id)["rules"][0]["is_current"] is True


def test_rule_without_models_counts_all_aircraft(client, db, admin_headers):
    _post_rule(client, admin_headers, required_hours=3)
    pilot = _seed_pilot(db)
    _flight_on(db, pilot, _vehicle(db, "X10", "S1"), 1)
    _flight_on(db, pilot, None, 2)
    payload = client.get(CURRENCY_STATUS_URL, headers=admin_headers).json()
    rule = _status_for(payload, pilot.id)["rules"][0]
    assert rule["is_current"] is True
    assert rule["actual_hours"] == 3.0


def test_model_rule_skips_flight_without_vehicle(client, db, admin_headers):
    _post_rule(client, admin_headers, required_hours=1, vehicle_models=["X10"])
    pilot = _seed_pilot(db)
    _flight_on(db, pilot, None, 2)
    payload = client.get(CURRENCY_STATUS_URL, headers=admin_headers).json()
    assert _status_for(payload, pilot.id)["rules"][0]["actual_hours"] == 0.0


def test_create_dedupes_models(client, admin_headers):
    r = _post_rule(client, admin_headers, vehicle_models=["X10", "x10", "X2E"])
    assert r.status_code == 200, r.text
    assert r.json()["vehicle_models"] == ["X10", "X2E"]


def test_patch_dedupes_models(client, admin_headers):
    rule = _post_rule(client, admin_headers, vehicle_models=["X2E"]).json()
    r = client.patch(f"{RULES_URL}/{rule['id']}", headers=admin_headers, json={"vehicle_models": ["X10", "x10"]})
    assert r.status_code == 200
    assert r.json()["vehicle_models"] == ["X10"]


def test_create_with_old_vehicle_model_is_refused(client, admin_headers):
    r = _post_rule(client, admin_headers, vehicle_model="X10")
    assert r.status_code == 422
    assert "vehicle_models" in r.text
    assert client.get(RULES_URL, headers=admin_headers).json() == []


def test_patch_with_old_vehicle_model_is_refused(client, admin_headers):
    rule = _post_rule(client, admin_headers, vehicle_models=["X10"]).json()
    r = client.patch(f"{RULES_URL}/{rule['id']}", headers=admin_headers,
                     json={"name": "Renamed", "vehicle_model": "X2E"})
    assert r.status_code == 422
    after = client.get(RULES_URL, headers=admin_headers).json()[0]
    assert (after["name"], after["vehicle_models"]) == ("Rule", ["X10"])


def test_patch_without_models_keeps_them(client, admin_headers):
    rule = _post_rule(client, admin_headers, vehicle_models=["X10"]).json()
    r = client.patch(f"{RULES_URL}/{rule['id']}", headers=admin_headers, json={"name": "Renamed"})
    assert r.status_code == 200
    assert r.json()["vehicle_models"] == ["X10"]


def test_patch_replaces_models(client, admin_headers):
    rule = _post_rule(client, admin_headers, vehicle_models=["X10"]).json()
    r = client.patch(f"{RULES_URL}/{rule['id']}", headers=admin_headers, json={"vehicle_models": ["X2E"]})
    assert r.json()["vehicle_models"] == ["X2E"]


def test_patch_removing_models_audits_each_removal(client, db, admin_headers):
    from app.models import AuditLog
    rule = _post_rule(client, admin_headers, vehicle_models=["X10", "X2E"]).json()
    db.query(AuditLog).delete()
    db.commit()
    r = client.patch(f"{RULES_URL}/{rule['id']}", headers=admin_headers, json={"vehicle_models": []})
    assert r.status_code == 200
    db.expire_all()
    rows = db.query(AuditLog).filter_by(entity_type="currency_rule_model", action="delete").all()
    assert sorted(e.changes["model"]["old"] for e in rows) == ["X10", "X2E"]


def test_patch_empty_list_means_all_aircraft(client, admin_headers):
    rule = _post_rule(client, admin_headers, vehicle_models=["X10"]).json()
    r = client.patch(f"{RULES_URL}/{rule['id']}", headers=admin_headers, json={"vehicle_models": []})
    assert r.status_code == 200
    assert r.json()["vehicle_models"] == []


def test_unknown_model_is_kept(client, admin_headers):
    r = _post_rule(client, admin_headers, vehicle_models=["X11"])
    assert r.json()["vehicle_models"] == ["X11"]
    listed = client.get(RULES_URL, headers=admin_headers).json()
    assert listed[0]["vehicle_models"] == ["X11"]


def test_rule_validation(client, admin_headers):
    for bad in ([" "], ["x" * 201], [f"M{i}" for i in range(51)]):
        r = _post_rule(client, admin_headers, vehicle_models=bad)
        assert r.status_code == 422, bad


def test_status_lists_models(client, db, admin_headers):
    _post_rule(client, admin_headers, vehicle_models=["X10", "X2E"])
    pilot = _seed_pilot(db)
    r = client.get(f"/api/currency/status/{pilot.id}", headers=admin_headers)
    assert r.status_code == 200
    rules = r.json()["rules"]
    assert rules[0]["vehicle_models"] == ["X10", "X2E"]


def test_patch_resending_same_models_succeeds(client, admin_headers):
    rule = _post_rule(client, admin_headers, vehicle_models=["X10", "X2E"]).json()
    r = client.patch(f"{RULES_URL}/{rule['id']}", headers=admin_headers, json={"vehicle_models": ["X10", "X2E"]})
    assert r.status_code == 200, r.text
    assert r.json()["vehicle_models"] == ["X10", "X2E"]
