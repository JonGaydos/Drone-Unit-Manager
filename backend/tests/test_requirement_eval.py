"""Progress evaluation for flight requirements: scope, totals, statuses and excusals."""

from datetime import date, datetime, time, timezone

import pytest

from app.models.flight import Flight
from app.models.flight_requirement import (
    FlightRequirement, FlightRequirementModel, FlightRequirementPilot, FlightRequirementPurpose,
    FlightRequirementResult,
)
from app.models.pilot import Pilot
from app.models.setting import Setting
from app.models.vehicle import Vehicle
from app.services.requirement_eval import (
    assigned_pilots, evaluate_period, scope_models, unit_eval_settings,
)

OCT = (date(2026, 10, 1), date(2026, 10, 31))
MID_OCT = date(2026, 10, 15)
LONG_AGO = datetime(2025, 1, 1, tzinfo=timezone.utc)
GRACE = 14


@pytest.fixture(autouse=True)
def chicago(db):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()


def _pilot(db, status="active", created_at=LONG_AGO):
    pilot = Pilot(first_name="Test", last_name="Pilot", status=status, created_at=created_at)
    db.add(pilot)
    db.commit()
    return pilot


_serials = iter(range(1, 10_000))


def _vehicle(db, model, status="active", created_at=LONG_AGO):
    vehicle = Vehicle(serial_number=f"SN{next(_serials)}", manufacturer="Acme", model=model,
                      status=status, created_at=created_at)
    db.add(vehicle)
    db.commit()
    return vehicle


def _flight(db, pilot, vehicle=None, day=date(2026, 10, 10), minutes=10, **extra):
    values = {"review_status": "reviewed", "takeoff_time": datetime.combine(day, time(15, 0))}
    values.update(extra)
    flight = Flight(pilot_id=pilot.id, vehicle_id=vehicle.id if vehicle else None, date=day,
                    duration_seconds=minutes * 60, **values)
    db.add(flight)
    db.commit()
    return flight


def _req(db, models=(), purposes=(), pilots=(), added_at=LONG_AGO, **extra):
    values = {"name": "R", "period_type": "calendar_month", "start_date": date(2026, 10, 1),
              "recurring": True, "model_mode": "all", "time_mode": "any", "target_minutes": 60,
              "created_at": LONG_AGO}
    values.update(extra)
    req = FlightRequirement(
        models=[FlightRequirementModel(model=m) for m in models],
        purposes=[FlightRequirementPurpose(purpose=p) for p in purposes],
        pilots=[FlightRequirementPilot(pilot_id=p.id, added_at=added_at) for p in pilots],
        **values)
    db.add(req)
    db.commit()
    return req


def _progress(db, req, pilot, today=MID_OCT, period=OCT):
    return evaluate_period(db, req, period, today, GRACE)[pilot.id]


# Targets


def test_met_on_hours_only(db):
    pilot = _pilot(db)
    req = _req(db, target_minutes=60)
    _flight(db, pilot, minutes=40)
    assert _progress(db, req, pilot).status == "on_track"
    _flight(db, pilot, minutes=20)
    progress = _progress(db, req, pilot)
    assert progress.status == "met"
    assert progress.totals == {"*": {"minutes": 60, "flights": 2}}
    assert progress.met_by_model == {"*": True}


def test_met_on_flights_only(db):
    pilot = _pilot(db)
    req = _req(db, target_minutes=None, target_flights=2)
    _flight(db, pilot, minutes=1)
    assert _progress(db, req, pilot).status == "on_track"
    _flight(db, pilot, minutes=1)
    assert _progress(db, req, pilot).status == "met"


def test_met_needs_both_targets_when_both_set(db):
    pilot = _pilot(db)
    req = _req(db, target_minutes=60, target_flights=2)
    _flight(db, pilot, minutes=60)
    assert _progress(db, req, pilot).status == "on_track"
    _flight(db, pilot, minutes=1)
    assert _progress(db, req, pilot).status == "met"


def test_flights_outside_the_period_do_not_count(db):
    pilot = _pilot(db)
    req = _req(db)
    _flight(db, pilot, day=date(2026, 9, 30), minutes=60)
    _flight(db, pilot, day=date(2026, 11, 1), minutes=60)
    assert _progress(db, req, pilot).totals == {"*": {"minutes": 0, "flights": 0}}


# Models


def test_combined_counts_any_selected_model(db):
    pilot = _pilot(db)
    x10, x2e, lemur = _vehicle(db, "X10"), _vehicle(db, "X2E"), _vehicle(db, "LEMUR 2")
    req = _req(db, model_mode="combined", models=["X10", "x2e"])
    _flight(db, pilot, lemur, minutes=60)
    assert _progress(db, req, pilot).totals == {"*": {"minutes": 0, "flights": 0}}
    _flight(db, pilot, x2e, minutes=30)
    _flight(db, pilot, x10, minutes=30)
    assert _progress(db, req, pilot).status == "met"


def test_each_separately_fails_when_one_model_is_short(db):
    pilot = _pilot(db)
    x10, x2e = _vehicle(db, "X10"), _vehicle(db, "X2E")
    req = _req(db, model_mode="each", models=["x10", "X2E"], target_minutes=15)
    _flight(db, pilot, x10, minutes=20)
    _flight(db, pilot, x2e, minutes=10)
    progress = _progress(db, req, pilot)
    assert progress.status == "on_track"
    assert progress.totals == {"X10": {"minutes": 20, "flights": 1}, "X2E": {"minutes": 10, "flights": 1}}
    assert progress.met_by_model == {"X10": True, "X2E": False}
    _flight(db, pilot, x2e, minutes=5)
    assert _progress(db, req, pilot).status == "met"


def test_scope_models(db):
    _vehicle(db, "X10")
    _vehicle(db, "X2E", created_at=datetime(2026, 10, 5, tzinfo=timezone.utc))
    _vehicle(db, "Old", status="retired")
    assert scope_models(db, _req(db), OCT[0]) is None
    assert scope_models(db, _req(db, model_mode="combined"), OCT[0]) is None
    assert scope_models(db, _req(db, model_mode="combined", models=["x10", "X2E"]), OCT[0]) == ["X10", "X2E"]
    assert scope_models(db, _req(db, model_mode="each_all_active"), OCT[0]) == ["X10"]
    assert scope_models(db, _req(db, model_mode="each_all_active"), date(2026, 11, 1)) == ["X10", "X2E"]


def test_each_all_active_ignores_model_added_after_period_start(db):
    pilot = _pilot(db)
    x10 = _vehicle(db, "X10")
    # 03:00 UTC on Oct 1 is still Sept 30 in Chicago, so this model is in October.
    x2e = _vehicle(db, "X2E", created_at=datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc))
    _vehicle(db, "LEMUR 2", created_at=datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc))
    req = _req(db, model_mode="each_all_active", target_minutes=15)
    _flight(db, pilot, x10, minutes=15)
    _flight(db, pilot, x2e, minutes=15)
    progress = _progress(db, req, pilot)
    assert set(progress.totals) == {"X10", "X2E"}
    assert progress.status == "met"


def test_each_all_active_with_no_models_in_scope_is_never_met(db):
    pilot = _pilot(db)
    _vehicle(db, "X10", created_at=datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc))
    req = _req(db, model_mode="each_all_active", target_minutes=15)
    progress = _progress(db, req, pilot)
    assert (progress.status, progress.totals, progress.met_by_model) == ("on_track", {}, {})
    assert _progress(db, req, pilot, today=date(2026, 12, 1)).status == "missed"


# Flight filters


def test_purpose_filter_excludes_other_purposes_and_no_purpose(db):
    pilot = _pilot(db)
    req = _req(db, purposes=["Training"], target_minutes=None, target_flights=5)
    _flight(db, pilot, purpose=" training ")
    _flight(db, pilot, purpose="Patrol")
    _flight(db, pilot, purpose=None)
    assert _progress(db, req, pilot).totals["*"]["flights"] == 1


def test_unreviewed_and_excluded_flights_do_not_count(db):
    pilot = _pilot(db)
    req = _req(db)
    _flight(db, pilot, minutes=10)
    _flight(db, pilot, minutes=30, review_status="needs_review")
    _flight(db, pilot, minutes=30, counts_toward_totals=False)
    _flight(db, pilot, minutes=30, review_status="needs_review", day=date(2026, 11, 2))
    progress = _progress(db, req, pilot)
    assert progress.totals == {"*": {"minutes": 10, "flights": 1}}
    assert progress.unreviewed_in_period == 1


def test_excluded_pilot_flights_do_not_count(db):
    pilot = _pilot(db)
    pilot.counts_toward_totals = False
    db.commit()
    req = _req(db)
    _flight(db, pilot, minutes=60)
    assert _progress(db, req, pilot).totals["*"]["minutes"] == 0


CLOCK_0_TO_6 = {"time_mode": "clock", "window_start_time": time(0, 0), "window_end_time": time(6, 0)}


@pytest.mark.parametrize("day,takeoff_utc,expected", [
    (date(2026, 10, 10), datetime(2026, 10, 10, 15, 0), 0),  # 10 AM Chicago, outside the window
    (date(2026, 10, 10), datetime(2026, 10, 10, 8, 0), 1),  # 3 AM Chicago, inside
    (date(2026, 9, 30), datetime(2026, 10, 1, 4, 30), 1),  # Sept 30, 11:30 PM, runs into Oct 1
])
def test_unreviewed_follows_the_clock_window(db, day, takeoff_utc, expected):
    pilot = _pilot(db)
    req = _req(db, **CLOCK_0_TO_6)
    _flight(db, pilot, day=day, minutes=60, takeoff_time=takeoff_utc, review_status="needs_review")
    assert _progress(db, req, pilot).unreviewed_in_period == expected


# Time of day


def test_no_takeoff_is_left_out_of_a_clock_window(db):
    pilot = _pilot(db)
    clock = _req(db, time_mode="clock", window_start_time=time(0, 0), window_end_time=time(6, 0))
    _flight(db, pilot, minutes=60, takeoff_time=None)
    # 10:30 UTC is 5:30 AM in Chicago (CDT): 30 of its 45 minutes fall before 6 AM.
    _flight(db, pilot, minutes=45, takeoff_time=datetime(2026, 10, 10, 10, 30))
    # 15:00 UTC is 10 AM: outside the window, so not a flight toward the count.
    _flight(db, pilot, minutes=45, takeoff_time=datetime(2026, 10, 10, 15, 0))
    progress = _progress(db, clock, pilot)
    assert progress.excluded_no_takeoff == 1
    assert progress.totals == {"*": {"minutes": 30, "flights": 1}}


def test_no_takeoff_counts_for_any_time(db):
    pilot = _pilot(db)
    req = _req(db)
    _flight(db, pilot, minutes=60, takeoff_time=None)
    progress = _progress(db, req, pilot)
    assert progress.status == "met"
    assert progress.excluded_no_takeoff == 0


def test_clock_window_counts_the_evening_before_the_period(db):
    pilot = _pilot(db)
    req = _req(db, time_mode="clock", window_start_time=time(22, 0), window_end_time=time(2, 0))
    # Sept 30, 11 PM Chicago (Oct 1 04:00 UTC), 2 hours: only the hour after midnight is in October.
    _flight(db, pilot, day=date(2026, 9, 30), minutes=120, takeoff_time=datetime(2026, 10, 1, 4, 0))
    assert _progress(db, req, pilot).totals == {"*": {"minutes": 60, "flights": 1}}


def test_night_without_location_counts_nothing(db):
    pilot = _pilot(db)
    req = _req(db, time_mode="night")
    _flight(db, pilot, minutes=60, takeoff_time=datetime(2026, 10, 10, 6, 0))
    assert _progress(db, req, pilot).totals == {"*": {"minutes": 0, "flights": 0}}


def test_night_uses_the_unit_location(db):
    db.add_all([Setting(key="org_default_lat", value="41.9"), Setting(key="org_default_lon", value="-87.6")])
    db.commit()
    pilot = _pilot(db)
    req = _req(db, time_mode="night")
    # 06:00 UTC is 1 AM in Chicago: the whole hour is night.
    _flight(db, pilot, minutes=60, takeoff_time=datetime(2026, 10, 10, 6, 0))
    assert _progress(db, req, pilot).totals == {"*": {"minutes": 60, "flights": 1}}


# Status by date


@pytest.mark.parametrize("today,status", [
    (date(2026, 10, 31), "on_track"),
    (date(2026, 11, 1), "pending_review"),
    (date(2026, 11, 14), "pending_review"),
    (date(2026, 11, 15), "missed"),
])
def test_status_by_date(db, today, status):
    pilot = _pilot(db)
    req = _req(db)
    _flight(db, pilot, minutes=30)
    assert _progress(db, req, pilot, today=today).status == status


def test_met_stays_met_after_the_period(db):
    pilot = _pilot(db)
    req = _req(db)
    _flight(db, pilot, minutes=60)
    assert _progress(db, req, pilot, today=date(2027, 1, 1)).status == "met"


# Excusals


def test_pilot_created_mid_period_is_excused(db):
    pilot = _pilot(db, created_at=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc))
    req = _req(db)
    progress = _progress(db, req, pilot, today=date(2026, 12, 1))
    assert progress.status == "excused"
    assert progress.excused is True
    assert progress.excused_reason


def test_pilot_created_on_period_start_in_local_time_is_not_excused(db):
    # 03:00 UTC on Oct 2 is Oct 1 in Chicago, the period's first day.
    pilot = _pilot(db, created_at=datetime(2026, 10, 2, 3, 0, tzinfo=timezone.utc))
    req = _req(db)
    assert _progress(db, req, pilot).excused is False


def test_selected_pilot_added_mid_period_is_excused(db):
    pilot = _pilot(db)
    req = _req(db, pilots=[pilot])
    req.pilots[0].added_at = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    db.commit()
    assert _progress(db, req, pilot).status == "excused"


def test_selected_pilots_assigned_when_the_requirement_was_created_are_not_excused(db):
    # Created mid-October with one selected pilot: the assignment row carries the creation time.
    created = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    pilot = _pilot(db)
    selected = _req(db, pilots=[pilot], added_at=created, created_at=created)
    every = _req(db, created_at=created)
    _flight(db, pilot, minutes=30)
    assert _progress(db, selected, pilot, today=date(2026, 12, 1)).status == "missed"
    assert _progress(db, every, pilot, today=date(2026, 12, 1)).status == "missed"


@pytest.mark.parametrize("selected", [False, True])
def test_pilot_created_after_the_requirement_and_period_start_is_excused(db, selected):
    req_created = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
    pilot_created = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    pilot = _pilot(db, created_at=pilot_created)
    pilots = [pilot] if selected else []
    req = _req(db, pilots=pilots, added_at=pilot_created, created_at=req_created)
    assert _progress(db, req, pilot).status == "excused"


def test_pilot_created_before_a_mid_period_requirement_is_not_excused(db):
    pilot = _pilot(db, created_at=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc))
    req = _req(db, created_at=datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc))
    progress = _progress(db, req, pilot)
    assert (progress.status, progress.excused) == ("on_track", False)


def test_override_false_removes_automatic_excusal(db):
    pilot = _pilot(db, created_at=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc))
    req = _req(db)
    db.add(FlightRequirementResult(requirement_id=req.id, pilot_id=pilot.id, period_start=OCT[0],
                                   period_end=OCT[1], excused=False))
    db.commit()
    progress = _progress(db, req, pilot)
    assert progress.status == "on_track"
    assert progress.excused is False


def test_override_true_excuses_with_reason(db):
    pilot = _pilot(db)
    req = _req(db)
    db.add(FlightRequirementResult(requirement_id=req.id, pilot_id=pilot.id, period_start=OCT[0],
                                   period_end=OCT[1], excused=True, excused_reason="Leave"))
    db.commit()
    progress = _progress(db, req, pilot, today=date(2026, 12, 1))
    assert (progress.status, progress.excused, progress.excused_reason) == ("excused", True, "Leave")


def test_met_wins_over_excused(db):
    pilot = _pilot(db, created_at=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc))
    req = _req(db)
    _flight(db, pilot, minutes=60)
    assert _progress(db, req, pilot).status == "met"


# Assignment and settings


def test_inactive_pilot_is_not_assigned(db):
    active = _pilot(db)
    inactive = _pilot(db, status="inactive")
    assert [p.id for p in assigned_pilots(db, _req(db))] == [active.id]
    other = _pilot(db)
    selected = _req(db, pilots=[inactive, other])
    assert [p.id for p in assigned_pilots(db, selected)] == [other.id]
    assert set(evaluate_period(db, selected, OCT, MID_OCT, GRACE)) == {other.id}


def test_unit_eval_settings_defaults_and_values(db):
    defaults = unit_eval_settings(db)
    assert (defaults.zone.key, defaults.lat, defaults.lon) == ("America/Chicago", None, None)
    assert (defaults.grace_days, defaults.fiscal_start_month) == (14, 10)
    db.add_all([Setting(key="org_default_lat", value="41.5"), Setting(key="org_default_lon", value="-87.5"),
                Setting(key="requirements_grace_days", value="7"),
                Setting(key="fiscal_year_start_month", value="7")])
    db.commit()
    configured = unit_eval_settings(db)
    assert (configured.lat, configured.lon, configured.grace_days, configured.fiscal_start_month) == (
        41.5, -87.5, 7, 7)


@pytest.mark.parametrize("grace, month, expected", [
    ("-5", "0", (0, 1)),
    ("99", "13", (60, 12)),
])
def test_unit_eval_settings_clamps_out_of_range_values(db, grace, month, expected):
    db.add_all([Setting(key="requirements_grace_days", value=grace),
                Setting(key="fiscal_year_start_month", value=month)])
    db.commit()
    settings = unit_eval_settings(db)
    actual = (settings.grace_days, settings.fiscal_start_month)
    assert actual == expected
