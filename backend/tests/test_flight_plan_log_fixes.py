"""Regression tests for the flights, plans, logs and checklists fixes
(staging test 2026-11-08, Area 5)."""

from datetime import date, datetime

from app.models.flight import Flight

FLIGHTS_URL = "/api/flights"


def _flight(db, **kwargs):
    kwargs.setdefault("date", date(2026, 11, 1))
    f = Flight(**kwargs)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


# --- B-1: landing before takeoff, date and duration consistency ---


def test_create_refuses_landing_before_takeoff(client, admin_headers):
    r = client.post(FLIGHTS_URL, headers=admin_headers, json={
        "case_number": "T-1", "takeoff_time": "2026-11-01T15:00:00Z",
        "landing_time": "2026-11-01T14:00:00Z"})
    assert r.status_code == 422
    assert "Landing time must be after takeoff time" in r.text


def test_patch_refuses_landing_before_stored_takeoff(client, db, admin_headers):
    f = _flight(db, takeoff_time=datetime(2026, 11, 1, 15, 0), landing_time=datetime(2026, 11, 1, 15, 30),
                duration_seconds=1800)
    r = client.patch(f"{FLIGHTS_URL}/{f.id}", headers=admin_headers,
                     json={"landing_time": "2026-11-01T14:00:00Z"})
    assert r.status_code == 422
    assert "Landing time must be after takeoff time" in r.text


def test_create_refuses_date_other_than_takeoff_date(client, admin_headers):
    r = client.post(FLIGHTS_URL, headers=admin_headers, json={
        "date": "2026-10-20", "takeoff_time": "2026-11-01T15:00:00Z"})
    assert r.status_code == 422
    assert "Date must match the takeoff date" in r.text


def test_create_refuses_duration_that_disagrees_with_times(client, admin_headers):
    r = client.post(FLIGHTS_URL, headers=admin_headers, json={
        "takeoff_time": "2026-11-01T15:00:00Z", "landing_time": "2026-11-01T15:30:00Z",
        "duration_seconds": 9000})
    assert r.status_code == 422
    assert "Duration must match the takeoff and landing times" in r.text


def test_create_fills_date_and_duration_from_times(client, admin_headers):
    r = client.post(FLIGHTS_URL, headers=admin_headers, json={
        "takeoff_time": "2026-11-01T15:00:00Z", "landing_time": "2026-11-01T15:30:00Z"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["date"] == "2026-11-01"
    assert body["duration_seconds"] == 1800


def test_create_accepts_consistent_values(client, admin_headers):
    r = client.post(FLIGHTS_URL, headers=admin_headers, json={
        "date": "2026-11-01", "takeoff_time": "2026-11-01T15:00:00Z",
        "landing_time": "2026-11-01T15:30:00Z", "duration_seconds": 1790})
    assert r.status_code == 200, r.text
    assert r.json()["duration_seconds"] == 1790


def test_patch_takeoff_moves_date_and_duration(client, db, admin_headers):
    f = _flight(db, takeoff_time=datetime(2026, 11, 1, 15, 0), landing_time=datetime(2026, 11, 1, 15, 30),
                duration_seconds=1800)
    r = client.patch(f"{FLIGHTS_URL}/{f.id}", headers=admin_headers,
                     json={"takeoff_time": "2026-11-01T15:10:00Z"})
    assert r.status_code == 200, r.text
    assert r.json()["duration_seconds"] == 1200
    assert r.json()["date"] == "2026-11-01"


def test_patch_unrelated_field_ignores_stored_inconsistency(client, db, admin_headers):
    # Imported flights may carry a duration that does not match their times;
    # an edit that touches neither must still save.
    f = _flight(db, takeoff_time=datetime(2026, 11, 1, 15, 0), landing_time=datetime(2026, 11, 1, 15, 30),
                duration_seconds=99999)
    r = client.patch(f"{FLIGHTS_URL}/{f.id}", headers=admin_headers, json={"notes": "x"})
    assert r.status_code == 200, r.text


# --- B-7: the flights CSV keeps the date of a flight with no takeoff time ---


def test_flights_csv_has_date_case_number_and_notes(client, db, admin_headers):
    import csv
    import io
    _flight(db, date=date(2026, 10, 5), case_number="CASE-77", notes="Manual entry")
    resp = client.get("/api/export/flights/csv", headers=admin_headers)
    assert resp.status_code == 200
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert rows[0]["Date"] == "2026-10-05"
    assert rows[0]["Case Number"] == "CASE-77"
    assert rows[0]["Notes"] == "Manual entry"
    # The Skydio columns keep their order, with the additions after Purpose.
    header = resp.text.splitlines()[0].split(",")
    assert header[-4:] == ["Purpose", "Date", "Case Number", "Notes"]


# --- B-10 / H-1: no self-review on deny ---

PLANS_URL = "/api/flight-plans"


def _plan(db, submitter, status="pending", **kwargs):
    from app.models.flight_approval import FlightPlan
    from app.models.pilot import Pilot
    pilot = Pilot(first_name="Plan", last_name="Pilot", status="active")
    db.add(pilot)
    db.flush()
    plan = FlightPlan(title="Survey", date_planned=datetime(2026, 12, 1, 10), pilot_id=pilot.id,
                      submitted_by_id=submitter.id, status=status, **kwargs)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def test_submitter_cannot_deny_own_plan(client, db, admin_user, admin_headers):
    plan = _plan(db, admin_user)
    r = client.post(f"{PLANS_URL}/{plan.id}/deny", headers=admin_headers, json={"denial_reason": "x"})
    assert r.status_code == 403
    assert "You cannot deny a flight plan you submitted" in r.text
    db.refresh(plan)
    assert plan.status == "pending"


def test_reviewer_can_deny_someone_elses_plan(client, db, pilot_user, admin_headers):
    plan = _plan(db, pilot_user)
    r = client.post(f"{PLANS_URL}/{plan.id}/deny", headers=admin_headers, json={"denial_reason": "Weather"})
    assert r.status_code == 200
    assert r.json()["status"] == "denied"


# --- B-13: training outcome and type come from fixed lists ---

TRAINING_URL = "/api/training-logs"


def _training_body(**overrides):
    body = {"date": "2026-11-04", "title": "Night ops", "training_type": "Recurrent", "outcome": "completed"}
    body.update(overrides)
    return body


def test_training_outcome_and_type_must_be_listed(client, admin_headers):
    for bad in ({"outcome": "banana"}, {"training_type": "Nonsense"}):
        r = client.post(TRAINING_URL, headers=admin_headers, json=_training_body(**bad))
        assert r.status_code == 422, (bad, r.text)
    ok = client.post(TRAINING_URL, headers=admin_headers, json=_training_body())
    assert ok.status_code == 200, ok.text
    tid = ok.json()["id"]
    for bad in ({"outcome": "zzz"}, {"training_type": "Nonsense"}):
        r = client.patch(f"{TRAINING_URL}/{tid}", headers=admin_headers, json=bad)
        assert r.status_code == 422, (bad, r.text)
    r = client.patch(f"{TRAINING_URL}/{tid}", headers=admin_headers,
                     json={"outcome": "failed", "training_type": "Special"})
    assert r.status_code == 200
    assert r.json()["outcome"] == "failed"


def test_training_stored_legacy_type_can_be_resent(client, db, admin_headers):
    from app.models.training_log import TrainingLog
    t = TrainingLog(date=date(2026, 11, 4), title="Imported", training_type="Practice", outcome="completed")
    db.add(t)
    db.commit()
    r = client.patch(f"{TRAINING_URL}/{t.id}", headers=admin_headers,
                     json={"training_type": "Practice", "notes": "kept"})
    assert r.status_code == 200, r.text


# --- B-2 / B-3: coordinate ranges and address length ---


def test_flight_coordinates_are_range_checked(client, db, admin_headers):
    for bad in ({"takeoff_lat": 999}, {"takeoff_lon": -500}, {"landing_lat": -200}, {"landing_lon": 720}):
        r = client.post(FLIGHTS_URL, headers=admin_headers, json={"case_number": "C", **bad})
        assert r.status_code == 422, (bad, r.text)
    f = _flight(db)
    for bad in ({"takeoff_lat": 90.5}, {"landing_lon": 181}):
        assert client.patch(f"{FLIGHTS_URL}/{f.id}", headers=admin_headers, json=bad).status_code == 422
    ok = client.post(FLIGHTS_URL, headers=admin_headers, json={
        "takeoff_lat": -90, "takeoff_lon": 180, "landing_lat": 90, "landing_lon": -180})
    assert ok.status_code == 200, ok.text


def test_flight_addresses_have_a_max_length(client, db, admin_headers):
    for field in ("takeoff_address", "landing_address"):
        r = client.post(FLIGHTS_URL, headers=admin_headers, json={field: "A" * 501})
        assert r.status_code == 422, field
        assert client.post(FLIGHTS_URL, headers=admin_headers, json={field: "A" * 500}).status_code == 200
    f = _flight(db)
    assert client.patch(f"{FLIGHTS_URL}/{f.id}", headers=admin_headers,
                        json={"landing_address": "B" * 2009}).status_code == 422
