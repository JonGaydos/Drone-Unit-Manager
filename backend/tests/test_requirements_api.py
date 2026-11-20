"""The flight requirements API: definitions, status, excusals, templates and settings."""

from datetime import date, datetime, time, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.audit_log import AuditLog
from app.models.flight import Flight
from app.models.flight_requirement import (
    FlightRequirement, FlightRequirementPilot, FlightRequirementResult,
)
from app.models.pilot import Pilot
from app.models.setting import Setting
from app.models.vehicle import Vehicle
from app.routers import requirements as requirements_router
from app.services.requirement_results import OFF_REASON

URL = "/api/requirements"
TODAY = date(2026, 11, 19)
LONG_AGO = datetime(2025, 1, 1, tzinfo=timezone.utc)
SEP = "2026-09-01"
OCT = "2026-10-01"
NOV = "2026-11-01"
NIGHT_REFUSED = "Set the unit default location in Settings before using night"
BASE = {"name": "Monthly 1 hr", "period_type": "calendar_month", "start_date": SEP,
        "recurring": True, "target_minutes": 60}


@pytest.fixture(autouse=True)
def unit(db, monkeypatch):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()
    monkeypatch.setattr(requirements_router, "local_today", lambda _db: TODAY)


def _pilot(db):
    pilot = Pilot(first_name="Test", last_name="Pilot", status="active", created_at=LONG_AGO)
    db.add(pilot)
    db.commit()
    return pilot


def _vehicle(db, model, status="active"):
    vehicle = Vehicle(serial_number=f"SN-{model}-{status}-{db.query(Vehicle).count()}", manufacturer="Maker",
                      model=model, status=status, created_at=LONG_AGO)
    db.add(vehicle)
    db.commit()
    return vehicle


def _flight(db, pilot, day, minutes, review_status="reviewed"):
    db.add(Flight(pilot_id=pilot.id, date=day, duration_seconds=minutes * 60, review_status=review_status,
                  takeoff_time=datetime.combine(day, time(15, 0))))
    db.commit()


def _create(client, headers, **changes):
    response = client.post(URL, headers=headers, json={**BASE, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def _status_row(client, headers, req_id):
    body = client.get(f"{URL}/status", headers=headers).json()
    return next(row for row in body["requirements"] if row["requirement_id"] == req_id)


def _progress(client, headers, req_id, pilot_id):
    row = _status_row(client, headers, req_id)
    return next(p for p in row["current_period"]["pilots"] if p["pilot_id"] == pilot_id)


def _history(client, headers, pilot_id):
    response = client.get(f"{URL}/pilots/{pilot_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["history"]


def _excuse(client, headers, req_id, pilot_id, period_start, excused=True, reason=None):
    return client.post(f"{URL}/{req_id}/excuse", headers=headers,
                       json={"pilot_id": pilot_id, "period_start": period_start, "excused": excused,
                             "reason": reason})


# Definitions


def test_crud_round_trip(client, db, admin_headers):
    first, second, third = _pilot(db), _pilot(db), _pilot(db)
    created = _create(client, admin_headers, model_mode="combined", models=["X10", " x10 ", "X2E"],
                      purposes=["Training", " training", "Search"],
                      pilot_ids=[first.id, second.id, first.id], description="Monthly hours")
    assert created["models"] == ["X10", "X2E"]
    assert created["purposes"] == ["Training", "Search"]
    assert sorted(created["pilot_ids"]) == [first.id, second.id]
    assert created["current_period"] == {"start": NOV, "end": "2026-11-30", "days_left": 12}

    listed = client.get(URL, headers=admin_headers).json()
    assert [row["id"] for row in listed] == [created["id"]]
    assert listed[0]["description"] == "Monthly hours"

    patched = client.patch(f"{URL}/{created['id']}", headers=admin_headers,
                           json={"name": "Renamed", "pilot_ids": [second.id, third.id], "models": ["X2E", "LEMUR 2"]})
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Renamed"
    assert sorted(patched.json()["pilot_ids"]) == [second.id, third.id]
    assert patched.json()["models"] == ["X2E", "LEMUR 2"]

    assert client.delete(f"{URL}/{created['id']}", headers=admin_headers).status_code == 200
    assert client.get(URL, headers=admin_headers).json() == []


def test_patch_keeps_the_assignment_time_of_a_kept_pilot(client, db, admin_headers):
    kept, other = _pilot(db), _pilot(db)
    req_id = _create(client, admin_headers, pilot_ids=[kept.id])["id"]
    row = db.query(FlightRequirementPilot).filter_by(requirement_id=req_id, pilot_id=kept.id).one()
    row.added_at = LONG_AGO
    db.commit()
    response = client.patch(f"{URL}/{req_id}", headers=admin_headers, json={"pilot_ids": [kept.id, other.id]})
    assert response.status_code == 200, response.text
    db.expire_all()
    row = db.query(FlightRequirementPilot).filter_by(requirement_id=req_id, pilot_id=kept.id).one()
    assert row.added_at.year == LONG_AGO.year


def test_models_are_ignored_for_all_aircraft(client, admin_headers):
    assert _create(client, admin_headers, model_mode="all", models=["X10"])["models"] == []
    assert _create(client, admin_headers, model_mode="each_all_active", models=["X10"])["models"] == []


def test_fields_of_other_period_types_are_cleared(client, admin_headers):
    created = _create(client, admin_headers, span_length=3, span_unit="months", every_months=2)
    assert (created["span_length"], created["span_unit"], created["every_months"]) == (None, None, None)


@pytest.mark.parametrize("changes", [
    {"name": ""},
    {"name": "x" * 201},
    {"target_minutes": None},
    {"target_minutes": 0},
    {"target_minutes": 100001},
    {"target_minutes": None, "target_flights": 0},
    {"target_flights": 10001},
    {"period_type": "weekly"},
    {"period_type": "monthly_window", "window_start_day": 19},
    {"period_type": "monthly_window", "window_start_day": 0, "window_end_day": 5},
    {"period_type": "monthly_window", "window_start_day": 19, "window_end_day": 32},
    {"period_type": "span", "span_length": 3},
    {"period_type": "span", "span_length": 0, "span_unit": "days"},
    {"period_type": "span", "span_length": -2, "span_unit": "weeks"},
    {"period_type": "span", "span_length": 366, "span_unit": "days"},
    {"period_type": "span", "span_length": 2, "span_unit": "years"},
    {"period_type": "every_n_months"},
    {"period_type": "every_n_months", "every_months": 0},
    {"period_type": "every_n_months", "every_months": 25},
    {"period_type": "custom"},
    {"period_type": "custom", "end_date": "2026-08-31"},
    {"end_date": "2026-08-31"},
    {"time_mode": "clock", "window_start_time": "00:00"},
    {"time_mode": "dusk"},
    {"model_mode": "combined"},
    {"model_mode": "each", "models": ["X10"]},
    {"model_mode": "each", "models": ["X10", "x10"]},
    {"reminder_days": -1},
    {"reminder_days": 61},
])
def test_invalid_definition_is_refused(client, admin_headers, changes):
    response = client.post(URL, headers=admin_headers, json={**BASE, **changes})
    assert response.status_code == 422, response.text


def test_valid_period_types_are_accepted(client, admin_headers):
    _create(client, admin_headers, period_type="monthly_window", window_start_day=19, window_end_day=5)
    _create(client, admin_headers, period_type="span", span_length=2, span_unit="weeks")
    _create(client, admin_headers, period_type="every_n_months", every_months=2)
    _create(client, admin_headers, period_type="custom", end_date="2026-12-31")
    _create(client, admin_headers, time_mode="clock", window_start_time="18:00", window_end_time="02:00")
    _create(client, admin_headers, model_mode="combined", models=["X10"], target_minutes=None, target_flights=2)


def test_patch_validates_the_merged_definition(client, admin_headers):
    req_id = _create(client, admin_headers)["id"]
    for body in ({"period_type": "monthly_window"}, {"name": None}, {"target_minutes": None},
                 {"span_length": 0}):
        response = client.patch(f"{URL}/{req_id}", headers=admin_headers, json=body)
        assert response.status_code == 422, (body, response.text)
    response = client.patch(f"{URL}/{req_id}", headers=admin_headers,
                            json={"period_type": "monthly_window", "window_start_day": 19, "window_end_day": 5})
    assert response.status_code == 200, response.text


def test_unknown_pilot_is_refused(client, admin_headers):
    response = client.post(URL, headers=admin_headers, json={**BASE, "pilot_ids": [9999]})
    assert response.status_code == 422


def test_night_needs_the_unit_location(client, db, admin_headers):
    response = client.post(URL, headers=admin_headers, json={**BASE, "time_mode": "night"})
    assert (response.status_code, response.json()["detail"]) == (422, NIGHT_REFUSED)
    req_id = _create(client, admin_headers)["id"]
    response = client.patch(f"{URL}/{req_id}", headers=admin_headers, json={"time_mode": "night"})
    assert (response.status_code, response.json()["detail"]) == (422, NIGHT_REFUSED)

    db.add_all([Setting(key="org_default_lat", value="41.88"), Setting(key="org_default_lon", value="")])
    db.commit()
    assert client.post(URL, headers=admin_headers, json={**BASE, "time_mode": "night"}).status_code == 422
    db.query(Setting).filter_by(key="org_default_lon").one().value = "-87.63"
    db.commit()
    _create(client, admin_headers, time_mode="night")


def test_missing_requirement_is_404(client, admin_headers):
    assert client.patch(f"{URL}/999", headers=admin_headers, json={"name": "X"}).status_code == 404
    assert client.delete(f"{URL}/999", headers=admin_headers).status_code == 404
    assert _excuse(client, admin_headers, 999, 1, NOV).status_code == 404


# Permissions


def _seed(client, db, admin_headers):
    """A requirement, a template and a pilot, made fresh for each request."""
    req = _create(client, admin_headers, start_date=NOV)
    template = client.post(f"{URL}/templates", headers=admin_headers,
                           json={"name": f"T{req['id']}", "settings": BASE}).json()
    return req["id"], template["id"], _pilot(db).id


MANAGE_ROUTES = [
    ("POST", lambda r, t, p: URL, BASE, 201),
    ("PATCH", lambda r, t, p: f"{URL}/{r}", {"name": "Changed"}, 200),
    ("DELETE", lambda r, t, p: f"{URL}/{r}", None, 200),
    ("GET", lambda r, t, p: f"{URL}/models", None, 200),
    ("PUT", lambda r, t, p: f"{URL}/settings", {"grace_days": 10, "fiscal_year_start_month": 10}, 200),
    ("GET", lambda r, t, p: f"{URL}/templates", None, 200),
    ("POST", lambda r, t, p: f"{URL}/templates", {"name": "New", "settings": BASE}, 201),
    ("PATCH", lambda r, t, p: f"{URL}/templates/{t}", {"name": "Renamed"}, 200),
    ("DELETE", lambda r, t, p: f"{URL}/templates/{t}", None, 200),
]
EXCUSE_ROUTE = ("POST", lambda r, t, p: f"{URL}/{r}/excuse", None, 200)
VIEW_ROUTES = [
    ("GET", lambda r, t, p: URL, None, 200),
    ("GET", lambda r, t, p: f"{URL}/status", None, 200),
    ("GET", lambda r, t, p: f"{URL}/pilots/{p}", None, 200),
    ("GET", lambda r, t, p: f"{URL}/flags", None, 200),
    ("GET", lambda r, t, p: f"{URL}/settings", None, 200),
]


def _send(client, db, admin_headers, headers, route):
    method, url, body, _ok = route
    req_id, template_id, pilot_id = _seed(client, db, admin_headers)
    if body is None and route is EXCUSE_ROUTE:
        body = {"pilot_id": pilot_id, "period_start": NOV, "excused": True}
    return client.request(method, url(req_id, template_id, pilot_id), headers=headers, json=body).status_code


@pytest.mark.parametrize("route", [*MANAGE_ROUTES, EXCUSE_ROUTE], ids=lambda r: f"{r[0]}-{r[1](1, 2, 3)}")
def test_supervisor_may_and_pilot_and_viewer_may_not_manage(client, db, admin_headers, supervisor_headers,
                                                            pilot_headers, viewer_headers, route):
    assert _send(client, db, admin_headers, supervisor_headers, route) == route[3]
    assert _send(client, db, admin_headers, pilot_headers, route) == 403
    assert _send(client, db, admin_headers, viewer_headers, route) == 403


@pytest.mark.parametrize("route", VIEW_ROUTES, ids=lambda r: r[1](1, 2, 3))
def test_everyone_may_view(client, db, admin_headers, pilot_headers, viewer_headers, route):
    assert _send(client, db, admin_headers, pilot_headers, route) == route[3]
    assert _send(client, db, admin_headers, viewer_headers, route) == route[3]


def test_recalculate_is_for_admins_only(client, db, admin_headers, supervisor_headers):
    pilot = _pilot(db)
    req_id = _create(client, admin_headers)["id"]
    client.get(f"{URL}/status", headers=admin_headers)  # saves September and October as missed
    _flight(db, pilot, date(2026, 9, 10), 70)
    body = {"period_start": SEP}
    assert client.post(f"{URL}/{req_id}/recalculate", headers=supervisor_headers, json=body).status_code == 403
    response = client.post(f"{URL}/{req_id}/recalculate", headers=admin_headers, json=body)
    assert response.status_code == 200, response.text
    assert response.json() == {"recalculated": 1}
    statuses = {row["period_start"]: row["status"] for row in _history(client, admin_headers, pilot.id)}
    assert statuses == {SEP: "met", OCT: "missed"}
    missing = client.post(f"{URL}/{req_id}/recalculate", headers=admin_headers, json={"period_start": NOV})
    assert missing.status_code == 404


# Status, history and flags


def test_status_reports_progress_and_score(client, db, viewer_headers, admin_headers):
    pilot = _pilot(db)
    _flight(db, pilot, date(2026, 11, 3), 45)
    req_id = _create(client, admin_headers)["id"]
    body = client.get(f"{URL}/status", headers=viewer_headers).json()
    assert body["score"] == 0.0  # September and October saved as missed
    row = next(r for r in body["requirements"] if r["requirement_id"] == req_id)
    period = row["current_period"]
    assert {key: period[key] for key in ("start", "end", "days_left", "review_until")} == {
        "start": NOV, "end": "2026-11-30", "days_left": 12, "review_until": "2026-12-14"}
    assert row["pending_periods"] == []
    progress = period["pilots"][0]
    assert progress["pilot_id"] == pilot.id
    assert progress["pilot_name"] == "Test Pilot"
    assert progress["status"] == "on_track"
    assert progress["totals"] == {"*": {"minutes": 45.0, "flights": 1}}


def test_inactive_requirement_is_left_out_of_status(client, admin_headers):
    req_id = _create(client, admin_headers, is_active=False)["id"]
    body = client.get(f"{URL}/status", headers=admin_headers).json()
    assert req_id not in [row["requirement_id"] for row in body["requirements"]]


def test_pilot_page_shows_current_progress_and_history_newest_first(client, db, admin_headers):
    pilot = _pilot(db)
    req_id = _create(client, admin_headers)["id"]
    body = client.get(f"{URL}/pilots/{pilot.id}", headers=admin_headers).json()
    assert [row["period_start"] for row in body["history"]] == [OCT, SEP]
    assert body["history"][0]["name"] == "Monthly 1 hr"
    assert body["history"][0]["status"] == "missed"
    assert [(row["requirement_id"], row["period"]["start"], row["status"]) for row in body["current"]] == [
        (req_id, NOV, "on_track")]
    assert client.get(f"{URL}/pilots/9999", headers=admin_headers).status_code == 404


def test_a_racing_close_does_not_fail_a_page_load(client, db, admin_headers, monkeypatch):
    _create(client, admin_headers)

    def racing(*_args):
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))

    monkeypatch.setattr(requirements_router, "close_due_periods", racing)
    assert client.get(f"{URL}/status", headers=admin_headers).status_code == 200
    assert client.get(f"{URL}/pilots/{_pilot(db).id}", headers=admin_headers).status_code == 200
    assert client.get(f"{URL}/flags", headers=admin_headers).status_code == 200


def test_editing_mid_period_changes_the_open_period_but_not_a_saved_one(client, db, admin_headers):
    pilot = _pilot(db)
    _flight(db, pilot, date(2026, 9, 10), 45)
    _flight(db, pilot, date(2026, 11, 3), 45)
    req_id = _create(client, admin_headers)["id"]
    assert _progress(client, admin_headers, req_id, pilot.id)["status"] == "on_track"
    response = client.patch(f"{URL}/{req_id}", headers=admin_headers, json={"target_minutes": 30})
    assert response.status_code == 200, response.text
    assert _progress(client, admin_headers, req_id, pilot.id)["status"] == "met"
    september = next(row for row in _history(client, admin_headers, pilot.id) if row["period_start"] == SEP)
    assert september["status"] == "missed"
    assert september["target_snapshot"]["target_minutes"] == 60


# Excusals


def test_excusing_an_open_period_then_un_excusing(client, db, admin_headers, supervisor_headers, supervisor_user):
    pilot = _pilot(db)
    req_id = _create(client, admin_headers, start_date=NOV)["id"]
    response = _excuse(client, supervisor_headers, req_id, pilot.id, NOV, reason="Leave")
    assert response.status_code == 200, response.text
    progress = _progress(client, admin_headers, req_id, pilot.id)
    assert (progress["status"], progress["excused_reason"]) == ("excused", "Leave")
    row = db.query(FlightRequirementResult).filter_by(requirement_id=req_id, pilot_id=pilot.id).one()
    assert (row.excused_by_id, row.saved_at) == (supervisor_user.id, None)

    assert _excuse(client, supervisor_headers, req_id, pilot.id, NOV, excused=False).status_code == 200
    assert _progress(client, admin_headers, req_id, pilot.id)["status"] == "on_track"


def test_excuse_needs_a_period_start_of_the_requirement(client, db, admin_headers):
    pilot = _pilot(db)
    req_id = _create(client, admin_headers, start_date=NOV)["id"]
    assert _excuse(client, admin_headers, req_id, pilot.id, "2026-11-05").status_code == 422
    assert _excuse(client, admin_headers, req_id, 9999, NOV).status_code == 404


def test_excusing_a_saved_miss_clears_its_flag(client, db, admin_headers, supervisor_headers, supervisor_user):
    pilot = _pilot(db)
    req_id = _create(client, admin_headers)["id"]
    flags = client.get(f"{URL}/flags", headers=admin_headers).json()
    assert [flag["period_start"] for flag in flags[str(pilot.id)]] == [SEP, OCT]

    assert _excuse(client, supervisor_headers, req_id, pilot.id, SEP, reason="Injury").status_code == 200
    flags = client.get(f"{URL}/flags", headers=admin_headers).json()
    assert [flag["period_start"] for flag in flags[str(pilot.id)]] == [OCT]
    row = db.query(FlightRequirementResult).filter_by(requirement_id=req_id, period_start=date(2026, 9, 1)).one()
    assert (row.status, row.excused, row.excused_by_id, row.excused_reason) == (
        "excused", True, supervisor_user.id, "Injury")
    entry = db.query(AuditLog).filter_by(entity_type="flight_requirement_result", entity_id=row.id).one()
    assert (entry.action, entry.user_id) == ("update", supervisor_user.id)

    assert _excuse(client, supervisor_headers, req_id, pilot.id, SEP, excused=False).status_code == 200
    db.refresh(row)
    assert (row.status, row.excused, row.excused_reason) == ("missed", False, None)
    flags = client.get(f"{URL}/flags", headers=admin_headers).json()
    assert [flag["period_start"] for flag in flags[str(pilot.id)]] == [SEP, OCT]


def test_excusing_a_saved_met_result_keeps_it_met(client, db, admin_headers):
    pilot = _pilot(db)
    _flight(db, pilot, date(2026, 9, 10), 70)
    req_id = _create(client, admin_headers)["id"]
    client.get(f"{URL}/status", headers=admin_headers)
    assert _excuse(client, admin_headers, req_id, pilot.id, SEP).status_code == 200
    assert _excuse(client, admin_headers, req_id, pilot.id, SEP, excused=False).status_code == 200
    _excuse(client, admin_headers, req_id, pilot.id, SEP)
    row = db.query(FlightRequirementResult).filter_by(requirement_id=req_id, period_start=date(2026, 9, 1)).one()
    assert (row.status, row.excused) == ("met", True)


def test_un_excusing_a_saved_excused_result_re_evaluates_it_as_met(client, db, admin_headers):
    pilot = _pilot(db)
    _flight(db, pilot, date(2026, 9, 10), 70)
    req_id = _create(client, admin_headers, start_date=SEP)["id"]
    db.add(FlightRequirementResult(requirement_id=req_id, pilot_id=pilot.id, period_start=date(2026, 9, 1),
                                   period_end=date(2026, 9, 30), status="excused",
                                   totals={"*": {"minutes": 70, "flights": 1}},
                                   target_snapshot={"target_minutes": 60, "target_flights": None},
                                   excused=True, excused_reason="Leave", saved_at=LONG_AGO))
    db.commit()
    assert _excuse(client, admin_headers, req_id, pilot.id, SEP, excused=False).status_code == 200
    row = db.query(FlightRequirementResult).filter_by(requirement_id=req_id, period_start=date(2026, 9, 1)).one()
    db.refresh(row)
    assert row.status == "met"


def test_excuse_refuses_a_closed_period_with_no_saved_row(client, db, admin_headers):
    _pilot(db)
    req_id = _create(client, admin_headers)["id"]
    client.get(f"{URL}/status", headers=admin_headers)  # closes September and October
    late = _pilot(db)
    response = _excuse(client, admin_headers, req_id, late.id, SEP)
    assert response.status_code == 422, response.text


def test_excuse_refuses_a_period_closed_with_no_pilots(client, db, admin_headers):
    req_id = _create(client, admin_headers)["id"]
    client.get(f"{URL}/status", headers=admin_headers)  # closes September and October with no pilots
    late = _pilot(db)
    response = _excuse(client, admin_headers, req_id, late.id, SEP)
    assert response.status_code == 422, response.text


def test_excuse_refuses_to_un_excuse_a_month_the_requirement_was_off(client, db, admin_headers):
    pilot = _pilot(db)
    req_id = _create(client, admin_headers, start_date=SEP)["id"]
    db.add(FlightRequirementResult(requirement_id=req_id, pilot_id=pilot.id, period_start=date(2026, 9, 1),
                                   period_end=date(2026, 9, 30), status="excused", totals={"*": {"minutes": 0,
                                                                                                  "flights": 0}},
                                   target_snapshot={"target_minutes": 60}, excused=True,
                                   excused_reason=OFF_REASON, saved_at=LONG_AGO))
    db.commit()
    assert _excuse(client, admin_headers, req_id, pilot.id, SEP, excused=False).status_code == 422


# Switching a requirement on and off


def test_switching_on_closes_due_periods_before_and_after(client, db, admin_headers):
    pilot = _pilot(db)
    req_id = _create(client, admin_headers)["id"]
    req = db.get(FlightRequirement, req_id)
    req.is_active = False
    req.active_changed_at = datetime(2026, 10, 10, 17, 0, tzinfo=timezone.utc)
    db.commit()
    response = client.patch(f"{URL}/{req_id}", headers=admin_headers, json={"is_active": True})
    assert response.status_code == 200, response.text
    db.expire_all()
    rows = {row.period_start.isoformat(): row for row in db.query(FlightRequirementResult).filter_by(
        requirement_id=req_id, pilot_id=pilot.id)}
    assert rows[SEP].status == "missed"  # closed while still off, with its real result
    assert (rows[OCT].status, rows[OCT].excused_reason) == ("excused", OFF_REASON)
    assert db.get(FlightRequirement, req_id).active_changed_at > datetime(2026, 10, 11, tzinfo=timezone.utc)


# Templates, models and settings


def test_templates_leave_out_dates_and_pilots(client, db, admin_headers):
    pilot = _pilot(db)
    settings = {**BASE, "end_date": "2027-01-31", "pilot_ids": [pilot.id], "model_mode": "combined",
                "models": ["X10", "x10"], "purposes": ["Training"]}
    response = client.post(f"{URL}/templates", headers=admin_headers, json={"name": "Monthly", "settings": settings})
    assert response.status_code == 201, response.text
    saved = response.json()["settings"]
    assert not {"start_date", "end_date", "pilot_ids"} & set(saved)
    assert (saved["name"], saved["models"], saved["purposes"]) == ("Monthly 1 hr", ["X10"], ["Training"])

    template_id = response.json()["id"]
    assert [t["name"] for t in client.get(f"{URL}/templates", headers=admin_headers).json()] == ["Monthly"]
    duplicate = client.post(f"{URL}/templates", headers=admin_headers, json={"name": "Monthly", "settings": BASE})
    assert duplicate.status_code == 409
    invalid = {**BASE, "target_minutes": None}
    assert client.post(f"{URL}/templates", headers=admin_headers,
                       json={"name": "Bad", "settings": invalid}).status_code == 422
    patched = client.patch(f"{URL}/templates/{template_id}", headers=admin_headers,
                           json={"name": "Quarterly", "settings": {**BASE, "period_type": "calendar_quarter"}})
    assert patched.status_code == 200, patched.text
    assert (patched.json()["name"], patched.json()["settings"]["period_type"]) == ("Quarterly", "calendar_quarter")
    assert client.delete(f"{URL}/templates/{template_id}", headers=admin_headers).status_code == 200
    assert client.get(f"{URL}/templates", headers=admin_headers).json() == []
    assert client.delete(f"{URL}/templates/{template_id}", headers=admin_headers).status_code == 404


def test_models_lists_the_fleet(client, db, admin_headers):
    _vehicle(db, "X10")
    _vehicle(db, "x10")
    _vehicle(db, "X2E", status="retired")
    response = client.get(f"{URL}/models", headers=admin_headers)
    assert response.json() == [{"name": "X10", "aircraft": 2, "retired": 0},
                               {"name": "X2E", "aircraft": 0, "retired": 1}]


def test_settings_round_trip(client, admin_headers, viewer_headers):
    assert client.get(f"{URL}/settings", headers=viewer_headers).json() == {
        "grace_days": 14, "fiscal_year_start_month": 10}
    response = client.put(f"{URL}/settings", headers=admin_headers,
                          json={"grace_days": 0, "fiscal_year_start_month": 1})
    assert response.status_code == 200, response.text
    assert client.get(f"{URL}/settings", headers=viewer_headers).json() == {
        "grace_days": 0, "fiscal_year_start_month": 1}


@pytest.mark.parametrize("body", [
    {"grace_days": -1, "fiscal_year_start_month": 10},
    {"grace_days": 61, "fiscal_year_start_month": 10},
    {"grace_days": 14, "fiscal_year_start_month": 0},
    {"grace_days": 14, "fiscal_year_start_month": 13},
    {"grace_days": 14},
])
def test_settings_out_of_range_are_refused(client, admin_headers, body):
    assert client.put(f"{URL}/settings", headers=admin_headers, json=body).status_code == 422


# Fix round 1


def test_a_period_in_its_grace_time_shows_as_pending_until_saved(client, db, admin_headers, monkeypatch):
    pilot = _pilot(db)
    _flight(db, pilot, date(2026, 11, 10), 30, review_status="needs_review")
    req_id = _create(client, admin_headers, period_type="span", start_date="2026-11-03", span_length=2,
                     span_unit="weeks")["id"]
    row = _status_row(client, admin_headers, req_id)
    assert row["current_period"]["start"] == "2026-11-17"
    [pending] = row["pending_periods"]
    assert (pending["start"], pending["end"], pending["days_left"], pending["review_until"]) == (
        "2026-11-03", "2026-11-16", 0, "2026-11-30")
    progress = pending["pilots"][0]
    assert (progress["status"], progress["unreviewed_in_period"], progress["excluded_no_takeoff"]) == (
        "pending_review", 1, 0)
    body = client.get(f"{URL}/pilots/{pilot.id}", headers=admin_headers).json()
    assert [(r["period"]["start"], r["status"]) for r in body["pending"]] == [("2026-11-03", "pending_review")]
    assert body["history"] == []

    monkeypatch.setattr(requirements_router, "local_today", lambda _db: date(2026, 12, 1))
    row = _status_row(client, admin_headers, req_id)
    assert [p["start"] for p in row["pending_periods"]] == ["2026-11-17"]
    body = client.get(f"{URL}/pilots/{pilot.id}", headers=admin_headers).json()
    assert [r["period"]["start"] for r in body["pending"]] == ["2026-11-17"]
    assert [(r["period_start"], r["status"]) for r in body["history"]] == [("2026-11-03", "missed")]


def test_excuse_refuses_a_pilot_not_assigned(client, db, admin_headers):
    assigned, other = _pilot(db), _pilot(db)
    req_id = _create(client, admin_headers, start_date=NOV, pilot_ids=[assigned.id])["id"]
    assert _excuse(client, admin_headers, req_id, other.id, NOV).status_code == 422
    assert _excuse(client, admin_headers, req_id, assigned.id, NOV).status_code == 200


def test_delete_refuses_a_requirement_with_saved_results(client, db, admin_headers):
    _pilot(db)
    req_id = _create(client, admin_headers)["id"]
    client.get(f"{URL}/status", headers=admin_headers)  # saves September and October
    response = client.delete(f"{URL}/{req_id}", headers=admin_headers)
    assert (response.status_code, response.json()["detail"]) == (
        409, "This requirement has saved results. Switch it off instead.")
    unsaved = _create(client, admin_headers, start_date=NOV)["id"]
    assert client.delete(f"{URL}/{unsaved}", headers=admin_headers).status_code == 200


def test_narrowing_to_selected_pilots_does_not_excuse_covered_pilots(client, db, admin_headers):
    pilot = _pilot(db)
    req_id = _create(client, admin_headers, start_date=NOV)["id"]
    req = db.get(FlightRequirement, req_id)
    req.created_at = LONG_AGO
    db.commit()
    assert _progress(client, admin_headers, req_id, pilot.id)["status"] == "on_track"
    response = client.patch(f"{URL}/{req_id}", headers=admin_headers, json={"pilot_ids": [pilot.id]})
    assert response.status_code == 200, response.text
    assert _progress(client, admin_headers, req_id, pilot.id)["status"] == "on_track"
    late = _pilot(db)
    response = client.patch(f"{URL}/{req_id}", headers=admin_headers, json={"pilot_ids": [pilot.id, late.id]})
    assert response.status_code == 200, response.text
    assert _progress(client, admin_headers, req_id, late.id)["status"] == "excused"


def test_night_template_needs_the_unit_location(client, admin_headers):
    body = {"name": "Night", "settings": {**BASE, "time_mode": "night"}}
    response = client.post(f"{URL}/templates", headers=admin_headers, json=body)
    assert (response.status_code, response.json()["detail"]) == (422, NIGHT_REFUSED)
    template_id = client.post(f"{URL}/templates", headers=admin_headers,
                              json={"name": "Day", "settings": BASE}).json()["id"]
    response = client.patch(f"{URL}/templates/{template_id}", headers=admin_headers,
                            json={"settings": {**BASE, "time_mode": "night"}})
    assert response.status_code == 422


def test_changing_settings_saves_due_periods_first(client, db, admin_headers):
    _pilot(db)
    req_id = _create(client, admin_headers)["id"]
    response = client.put(f"{URL}/settings", headers=admin_headers,
                          json={"grace_days": 60, "fiscal_year_start_month": 10})
    assert response.status_code == 200, response.text
    saved = db.query(FlightRequirementResult).filter_by(requirement_id=req_id).count()
    assert saved == 2  # September and October closed under the old 14 grace days
