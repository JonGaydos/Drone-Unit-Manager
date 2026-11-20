"""Rolling flight requirements: windows, status, lapse date, excusals and validation."""

from datetime import date, datetime, time, timezone

import pytest
from pydantic import ValidationError

from app.models.flight import Flight
from app.models.flight_requirement import (
    FlightRequirement, FlightRequirementExcusal, FlightRequirementModel, FlightRequirementPilot,
)
from app.models.pilot import Pilot
from app.models.setting import Setting
from app.models.vehicle import Vehicle
from app.schemas.requirement import RequirementIn
from app.services.requirement_periods import PeriodSpec, first_period, period_containing, periods_between
from app.services.requirement_rolling import evaluate_rolling, rolling_window

TODAY = date(2026, 11, 20)
LONG_AGO = datetime(2025, 1, 1, tzinfo=timezone.utc)
NOV_1_NOON = datetime(2026, 11, 1, 18, 0, tzinfo=timezone.utc)
URL = "/api/requirements"


@pytest.fixture
def chicago(db):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()


def _pilot(db, created_at=LONG_AGO, status="active"):
    pilot = Pilot(first_name="Test", last_name="Pilot", status=status, created_at=created_at)
    db.add(pilot)
    db.commit()
    return pilot


def _vehicle(db, model):
    vehicle = Vehicle(serial_number=f"SN-{model}-{db.query(Vehicle).count()}", manufacturer="Acme",
                      model=model, status="active", created_at=LONG_AGO)
    db.add(vehicle)
    db.commit()
    return vehicle


def _flight(db, pilot, day, minutes, vehicle=None, takeoff=time(15, 0), **extra):
    values = {"review_status": "reviewed", "takeoff_time": datetime.combine(day, takeoff)}
    values.update(extra)
    db.add(Flight(pilot_id=pilot.id, vehicle_id=vehicle.id if vehicle else None, date=day,
                  duration_seconds=minutes * 60, **values))
    db.commit()


def _req(db, models=(), pilots=(), added_at=LONG_AGO, **extra):
    values = {"name": "Rolling", "period_type": "rolling", "start_date": date(2026, 1, 1), "recurring": False,
              "span_length": 30, "span_unit": "days", "model_mode": "all", "time_mode": "any",
              "target_minutes": 60, "created_at": LONG_AGO}
    values.update(extra)
    req = FlightRequirement(
        models=[FlightRequirementModel(model=m) for m in models],
        pilots=[FlightRequirementPilot(pilot_id=p.id, added_at=added_at) for p in pilots],
        **values)
    db.add(req)
    db.commit()
    return req


def _progress(db, req, pilot, today=TODAY):
    return evaluate_rolling(db, req, today)[pilot.id]


# Windows


def test_window_in_days_ends_on_the_day():
    assert rolling_window(TODAY, 30, "days") == (date(2026, 10, 22), TODAY)


def test_window_of_one_day_is_the_day():
    assert rolling_window(TODAY, 1, "days") == (TODAY, TODAY)


def test_window_in_weeks():
    assert rolling_window(TODAY, 2, "weeks") == (date(2026, 11, 7), TODAY)


def test_window_in_months_starts_the_day_after_the_same_day_back():
    assert rolling_window(date(2026, 3, 15), 1, "months") == (date(2026, 2, 16), date(2026, 3, 15))


def test_window_in_months_clamps_across_a_month_end():
    assert rolling_window(date(2026, 3, 31), 1, "months") == (date(2026, 3, 1), date(2026, 3, 31))


def test_window_in_months_clamps_several_months_back():
    assert rolling_window(date(2026, 5, 31), 3, "months") == (date(2026, 3, 1), date(2026, 5, 31))


def test_window_across_the_daylight_saving_change():
    assert rolling_window(date(2026, 11, 7), 7, "days") == (date(2026, 11, 1), date(2026, 11, 7))


def test_rolling_has_no_periods():
    spec = PeriodSpec(period_type="rolling", start=date(2026, 1, 1), end=None, recurring=False,
                      span_length=30, span_unit="days")
    assert first_period(spec) is None
    assert period_containing(spec, TODAY) is None
    assert periods_between(spec, date(2026, 1, 1), TODAY) == []


# Status and totals


def test_current_with_exact_target(db, chicago):
    pilot = _pilot(db)
    req = _req(db)
    _flight(db, pilot, date(2026, 11, 10), 30)
    _flight(db, pilot, date(2026, 10, 22), 30)
    progress = _progress(db, req, pilot)
    assert progress.status == "current"
    assert progress.totals == {"*": {"minutes": 60, "flights": 2}}
    assert progress.met_by_model == {"*": True}
    assert progress.lapse_date == date(2026, 11, 21)


def test_lapsed_when_short_and_flights_before_the_window_do_not_count(db, chicago):
    pilot = _pilot(db)
    req = _req(db)
    _flight(db, pilot, date(2026, 11, 10), 30)
    _flight(db, pilot, date(2026, 10, 21), 30)
    progress = _progress(db, req, pilot)
    assert progress.status == "lapsed"
    assert progress.totals == {"*": {"minutes": 30, "flights": 1}}
    assert progress.lapse_date is None


def test_no_assigned_pilots_gives_no_progress(db, chicago):
    _pilot(db, status="inactive")
    assert evaluate_rolling(db, _req(db), TODAY) == {}


# Lapse date


def _three_flights(db, pilot, minutes=(30, 30, 30)):
    for day, length in zip((date(2026, 11, 10), date(2026, 11, 1), date(2026, 10, 25)), minutes):
        _flight(db, pilot, day, length)


def test_lapse_date_on_minutes_only(db, chicago):
    pilot = _pilot(db)
    req = _req(db, target_minutes=60)
    _three_flights(db, pilot)
    assert _progress(db, req, pilot).lapse_date == date(2026, 12, 1)


def test_lapse_date_on_flights_only(db, chicago):
    pilot = _pilot(db)
    req = _req(db, target_minutes=None, target_flights=3)
    _three_flights(db, pilot)
    assert _progress(db, req, pilot).lapse_date == date(2026, 11, 24)


def test_lapse_date_on_both_targets(db, chicago):
    pilot = _pilot(db)
    req = _req(db, target_minutes=60, target_flights=3)
    _three_flights(db, pilot, minutes=(60, 5, 5))
    assert _progress(db, req, pilot).lapse_date == date(2026, 11, 24)


def test_lapse_date_in_months_waits_for_the_clamped_window(db, chicago):
    pilot = _pilot(db)
    req = _req(db, span_length=1, span_unit="months")
    _flight(db, pilot, date(2026, 1, 31), 60)
    assert _progress(db, req, pilot, today=date(2026, 2, 20)).lapse_date == date(2026, 3, 1)


def test_lapse_date_in_weeks(db, chicago):
    pilot = _pilot(db)
    req = _req(db, span_length=2, span_unit="weeks")
    _flight(db, pilot, date(2026, 11, 10), 60)
    assert _progress(db, req, pilot).lapse_date == date(2026, 11, 24)


# Models


def test_each_separately_with_one_model_short_is_lapsed(db, chicago):
    pilot = _pilot(db)
    x10, x2e = _vehicle(db, "X10"), _vehicle(db, "X2E")
    req = _req(db, model_mode="each", models=["X10", "X2E"], target_minutes=15)
    _flight(db, pilot, date(2026, 11, 10), 20, x10)
    _flight(db, pilot, date(2026, 11, 10), 10, x2e)
    progress = _progress(db, req, pilot)
    assert progress.status == "lapsed"
    assert progress.met_by_model == {"X10": True, "X2E": False}


def test_each_separately_lapses_on_the_earliest_model(db, chicago):
    pilot = _pilot(db)
    x10, x2e = _vehicle(db, "X10"), _vehicle(db, "X2E")
    req = _req(db, model_mode="each", models=["X10", "X2E"], target_minutes=15)
    _flight(db, pilot, date(2026, 11, 15), 20, x10)
    _flight(db, pilot, date(2026, 11, 5), 20, x2e)
    progress = _progress(db, req, pilot)
    assert progress.status == "current"
    assert progress.lapse_date == date(2026, 12, 5)


# Time of day


def test_time_of_day_lapse_uses_counted_minutes(db, chicago):
    pilot = _pilot(db)
    req = _req(db, time_mode="clock", window_start_time=time(18, 0), window_end_time=time(21, 30))
    # 03:00 UTC is 21:00 in Chicago the evening before: 30 of the 60 minutes are inside the window.
    _flight(db, pilot, date(2026, 11, 10), 60, takeoff=time(3, 0))
    _flight(db, pilot, date(2026, 11, 5), 60, takeoff=time(3, 0))
    progress = _progress(db, req, pilot)
    assert progress.totals == {"*": {"minutes": 60, "flights": 2}}
    assert progress.lapse_date == date(2026, 12, 5)


def test_time_of_day_counts_real_minutes_across_the_daylight_saving_change(db, chicago):
    pilot = _pilot(db)
    req = _req(db, span_length=7, target_minutes=180, time_mode="clock",
               window_start_time=time(0, 0), window_end_time=time(2, 0))
    # 05:00 UTC on Nov 1 is midnight CDT; three real hours later it is 02:00 CST.
    _flight(db, pilot, date(2026, 11, 1), 180, takeoff=time(5, 0))
    progress = _progress(db, req, pilot, today=date(2026, 11, 7))
    assert progress.status == "current"
    assert progress.totals == {"*": {"minutes": 180, "flights": 1}}


# Flight filters


def test_unreviewed_and_non_unit_flights_do_not_count(db, chicago):
    pilot = _pilot(db)
    req = _req(db)
    _flight(db, pilot, date(2026, 11, 10), 10)
    _flight(db, pilot, date(2026, 11, 10), 60, review_status="needs_review")
    _flight(db, pilot, date(2026, 11, 10), 60, counts_toward_totals=False)
    progress = _progress(db, req, pilot)
    assert progress.status == "lapsed"
    assert progress.totals == {"*": {"minutes": 10, "flights": 1}}
    assert progress.unreviewed_in_window == 1


# Not yet due


def test_new_pilot_is_not_yet_due_for_one_window(db, chicago):
    pilot = _pilot(db, created_at=NOV_1_NOON)
    req = _req(db)
    assert _progress(db, req, pilot).status == "not_yet_due"
    assert _progress(db, req, pilot, today=date(2026, 11, 30)).status == "not_yet_due"
    assert _progress(db, req, pilot, today=date(2026, 12, 1)).status == "lapsed"


def test_newly_assigned_pilot_is_not_yet_due(db, chicago):
    pilot = _pilot(db)
    req = _req(db, pilots=[pilot], added_at=NOV_1_NOON)
    assert _progress(db, req, pilot).status == "not_yet_due"


def test_new_requirement_is_not_yet_due_for_one_window(db, chicago):
    pilot = _pilot(db)
    req = _req(db, start_date=date(2026, 11, 1), created_at=NOV_1_NOON)
    assert _progress(db, req, pilot).status == "not_yet_due"
    assert _progress(db, req, pilot, today=date(2026, 12, 1)).status == "lapsed"


def test_pilots_selected_when_a_backdated_requirement_was_created_are_due(db, chicago):
    pilot = _pilot(db)
    req = _req(db, pilots=[pilot], added_at=NOV_1_NOON, created_at=NOV_1_NOON)
    assert _progress(db, req, pilot).status == "lapsed"


# Excusals


def _excuse(db, req, pilot, until):
    db.add(FlightRequirementExcusal(requirement_id=req.id, pilot_id=pilot.id, excused_until=until,
                                    reason="Leave"))
    db.commit()


def test_excused_until_a_date(db, chicago):
    pilot = _pilot(db)
    req = _req(db)
    _excuse(db, req, pilot, TODAY)
    progress = _progress(db, req, pilot)
    assert progress.status == "excused"
    assert progress.excused_until == TODAY
    assert _progress(db, req, pilot, today=date(2026, 11, 21)).status == "lapsed"


def test_excusal_wins_over_current(db, chicago):
    pilot = _pilot(db)
    req = _req(db)
    _flight(db, pilot, date(2026, 11, 10), 60)
    _excuse(db, req, pilot, date(2026, 12, 31))
    assert _progress(db, req, pilot).status == "excused"


# Validation


ROLLING = {"name": "Rolling", "period_type": "rolling", "start_date": "2026-01-01", "recurring": False,
           "span_length": 90, "span_unit": "days", "target_minutes": 60}


def test_rolling_definition_is_accepted_and_clears_other_period_fields():
    data = RequirementIn.model_validate({**ROLLING, "window_start_day": 5, "every_months": 2})
    assert (data.span_length, data.span_unit, data.recurring) == (90, "days", False)
    assert (data.window_start_day, data.every_months, data.end_date) == (None, None, None)


def test_rolling_recurring_defaults_to_false():
    data = RequirementIn.model_validate({k: v for k, v in ROLLING.items() if k != "recurring"})
    assert data.recurring is False


@pytest.mark.parametrize("changes", [
    {"span_length": None},
    {"span_unit": None},
    {"span_length": 0},
    {"span_length": 366},
    {"span_unit": "years"},
    {"recurring": True},
    {"end_date": "2026-12-31"},
    {"start_date": None},
])
def test_invalid_rolling_definition_is_refused(changes):
    with pytest.raises(ValidationError):
        RequirementIn.model_validate({**ROLLING, **changes})


# API paths that iterate periods


def test_rolling_requirement_does_not_break_period_routes(client, admin_headers, db):
    pilot = _pilot(db)
    response = client.post(URL, headers=admin_headers, json=ROLLING)
    assert response.status_code == 201, response.text
    assert response.json()["current_period"] is None
    assert client.get(URL, headers=admin_headers).status_code == 200
    status = client.get(f"{URL}/status", headers=admin_headers)
    assert status.status_code == 200, status.text
    assert client.get(f"{URL}/pilots/{pilot.id}", headers=admin_headers).status_code == 200
