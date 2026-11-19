"""Saved requirement results: closing periods, recalculation, open misses and the score."""

from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.models.audit_log import AuditLog
from app.models.flight import Flight
from app.models.flight_requirement import (
    FlightRequirement, FlightRequirementModel, FlightRequirementPurpose, FlightRequirementResult,
)
from app.models.pilot import Pilot
from app.models.setting import Setting
from app.services.requirement_results import (
    close_due_periods, open_misses, recalculate_period, requirements_score, target_snapshot,
)

LONG_AGO = datetime(2025, 1, 1, tzinfo=timezone.utc)
AUG = (date(2026, 8, 1), date(2026, 8, 31))
SEP = (date(2026, 9, 1), date(2026, 9, 30))
OCT = (date(2026, 10, 1), date(2026, 10, 31))
LAST_GRACE_DAY = date(2026, 11, 14)  # October ends on the 31st; 14 grace days
DAY_AFTER_GRACE = date(2026, 11, 15)


@pytest.fixture(autouse=True)
def chicago(db):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()


def _pilot(db, status="active"):
    pilot = Pilot(first_name="Test", last_name="Pilot", status=status, created_at=LONG_AGO)
    db.add(pilot)
    db.commit()
    return pilot


def _flight(db, pilot, day=date(2026, 10, 10), minutes=60, review_status="reviewed"):
    flight = Flight(pilot_id=pilot.id, date=day, duration_seconds=round(minutes * 60), review_status=review_status,
                    takeoff_time=datetime.combine(day, time(15, 0)))
    db.add(flight)
    db.commit()
    return flight


def _req(db, **extra):
    values = {"name": "Monthly 1 hr", "period_type": "calendar_month", "start_date": OCT[0],
              "recurring": True, "model_mode": "all", "time_mode": "any", "target_minutes": 60,
              "created_at": LONG_AGO}
    values.update(extra)
    req = FlightRequirement(**values)
    db.add(req)
    db.commit()
    return req


def _rows(db, req=None):
    query = db.query(FlightRequirementResult)
    if req is not None:
        query = query.filter(FlightRequirementResult.requirement_id == req.id)
    return query.order_by(FlightRequirementResult.period_start).all()


def _saved(db, req, pilot, period, status, excused=None):
    row = FlightRequirementResult(requirement_id=req.id, pilot_id=pilot.id, period_start=period[0],
                                  period_end=period[1], status=status, totals={}, target_snapshot={},
                                  excused=excused, saved_at=LONG_AGO)
    db.add(row)
    db.commit()
    return row


# Closing periods


def test_period_inside_its_grace_time_is_not_saved(db):
    _pilot(db)
    req = _req(db)
    assert close_due_periods(db, LAST_GRACE_DAY) == []
    assert _rows(db, req) == []


def test_period_is_saved_the_day_after_its_grace_time(db):
    pilot = _pilot(db)
    req = _req(db)
    _flight(db, pilot, minutes=45)
    _flight(db, pilot, minutes=20.4)
    saved = close_due_periods(db, DAY_AFTER_GRACE)
    assert len(saved) == 1
    row = _rows(db, req)[0]
    assert (row.pilot_id, row.period_start, row.period_end) == (pilot.id, *OCT)
    assert row.status == "met"
    assert row.totals == {"*": {"minutes": 65, "flights": 2}}
    assert row.saved_at is not None
    assert row.target_snapshot["target_minutes"] == 60


def test_missed_period_is_saved_as_missed(db):
    pilot = _pilot(db)
    req = _req(db)
    _flight(db, pilot, minutes=30)
    close_due_periods(db, DAY_AFTER_GRACE)
    assert _rows(db, req)[0].status == "missed"


def test_running_twice_saves_nothing_new(db):
    _pilot(db)
    _req(db)
    assert len(close_due_periods(db, DAY_AFTER_GRACE)) == 1
    assert close_due_periods(db, DAY_AFTER_GRACE) == []
    assert len(_rows(db)) == 1


def test_requirement_created_for_past_months_saves_every_closed_period(db):
    pilot = _pilot(db)
    req = _req(db, start_date=date(2026, 7, 1))
    saved = close_due_periods(db, DAY_AFTER_GRACE)
    assert sorted(row.period_start for row in saved) == [date(2026, m, 1) for m in (7, 8, 9, 10)]
    assert {row.pilot_id for row in _rows(db, req)} == {pilot.id}


def test_reactivated_pilot_gets_no_rows_for_closed_periods(db):
    _pilot(db)
    returning = _pilot(db, status="inactive")
    req = _req(db, start_date=date(2026, 7, 1))
    assert len(close_due_periods(db, DAY_AFTER_GRACE)) == 4
    returning.status = "active"
    db.commit()
    assert close_due_periods(db, DAY_AFTER_GRACE + timedelta(days=1)) == []
    assert returning.id not in {row.pilot_id for row in _rows(db, req)}
    assert open_misses(db, [returning.id]) == {}


def test_pilot_added_later_gets_no_rows_for_closed_periods(db):
    _pilot(db)
    req = _req(db, start_date=date(2026, 7, 1))
    close_due_periods(db, DAY_AFTER_GRACE)
    newcomer = _pilot(db)
    assert close_due_periods(db, DAY_AFTER_GRACE + timedelta(days=1)) == []
    assert newcomer.id not in {row.pilot_id for row in _rows(db, req)}


def test_changed_period_layout_never_saves_dates_already_closed(db):
    _pilot(db)
    req = _req(db, start_date=date(2026, 7, 1))
    close_due_periods(db, DAY_AFTER_GRACE)
    req.period_type, req.span_length, req.span_unit = "span", 2, "weeks"
    db.commit()
    # Two-week spans from Jul 1: Oct 21 to Nov 3 starts before October's saved end,
    # Nov 4 to Nov 17 is the first new one and is due after Dec 1.
    assert close_due_periods(db, date(2026, 12, 1)) == []
    saved = close_due_periods(db, date(2026, 12, 2))
    assert [(row.period_start, row.period_end) for row in saved] == [(date(2026, 11, 4), date(2026, 11, 17))]
    assert close_due_periods(db, date(2026, 12, 2)) == []


def _switch(db, req, active, at):
    req.is_active = active
    req.active_changed_at = at
    db.commit()


MAR_10 = datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc)
JUL_5 = datetime(2026, 7, 5, 15, 0, tzinfo=timezone.utc)


def test_inactive_requirement_saves_only_periods_ended_before_switch_off(db):
    _pilot(db)
    inactive = _req(db, start_date=date(2026, 1, 1))
    active = _req(db, start_date=date(2026, 1, 1))
    _switch(db, inactive, False, MAR_10)
    close_due_periods(db, DAY_AFTER_GRACE)
    assert [row.period_start for row in _rows(db, inactive)] == [date(2026, 1, 1), date(2026, 2, 1)]
    assert [row.period_start for row in _rows(db, active)] == [date(2026, m, 1) for m in range(1, 11)]


def test_editing_an_inactive_requirement_saves_nothing_more(db):
    _pilot(db)
    req = _req(db, start_date=date(2026, 1, 1))
    _switch(db, req, False, MAR_10)
    close_due_periods(db, DAY_AFTER_GRACE)
    req.name = "Renamed"
    db.commit()
    assert close_due_periods(db, DAY_AFTER_GRACE + timedelta(days=1)) == []
    assert len(_rows(db, req)) == 2


def test_reactivated_requirement_skips_the_months_it_was_off(db):
    _pilot(db)
    req = _req(db, start_date=date(2026, 1, 1))
    _switch(db, req, False, MAR_10)
    close_due_periods(db, date(2026, 6, 1))
    _switch(db, req, True, JUL_5)
    assert close_due_periods(db, date(2026, 8, 14)) == []
    saved = close_due_periods(db, DAY_AFTER_GRACE)
    assert [row.period_start for row in saved] == [date(2026, m, 1) for m in (7, 8, 9, 10)]
    assert [row.period_start for row in _rows(db, req)] == [date(2026, m, 1) for m in (1, 2, 7, 8, 9, 10)]
    assert close_due_periods(db, DAY_AFTER_GRACE) == []


def test_requirement_created_inactive_saves_nothing(db):
    _pilot(db)
    req = _req(db, start_date=date(2026, 1, 1), is_active=False)
    assert req.active_changed_at is None
    assert close_due_periods(db, DAY_AFTER_GRACE) == []


def test_switching_on_or_off_is_stamped_only_on_a_real_change(db):
    req = _req(db)
    assert req.active_changed_at is None
    req.is_active = True
    db.commit()
    assert req.active_changed_at is None
    req.is_active = False
    db.commit()
    stamped = req.active_changed_at
    assert stamped is not None
    req.is_active = False
    db.commit()
    assert req.active_changed_at == stamped


def test_saved_minutes_round_down(db):
    pilot = _pilot(db)
    req = _req(db)
    _flight(db, pilot, minutes=59.6)
    close_due_periods(db, DAY_AFTER_GRACE)
    row = _rows(db, req)[0]
    assert (row.status, row.totals) == ("missed", {"*": {"minutes": 59, "flights": 1}})


def test_excusal_override_row_is_filled_in(db):
    pilot = _pilot(db)
    req = _req(db)
    override = FlightRequirementResult(requirement_id=req.id, pilot_id=pilot.id, period_start=OCT[0],
                                       period_end=OCT[1], excused=True, excused_reason="Deployed")
    db.add(override)
    db.commit()
    saved = close_due_periods(db, DAY_AFTER_GRACE)
    assert [row.id for row in saved] == [override.id]
    db.refresh(override)
    assert override.status == "excused"
    assert override.excused is True
    assert override.excused_reason == "Deployed"
    assert override.saved_at is not None


def test_editing_the_target_after_a_save_does_not_change_the_saved_row(db):
    pilot = _pilot(db)
    req = _req(db)
    _flight(db, pilot, minutes=60)
    close_due_periods(db, DAY_AFTER_GRACE)
    req.target_minutes = 120
    req.name = "Monthly 2 hr"
    db.commit()
    close_due_periods(db, DAY_AFTER_GRACE + timedelta(days=1))
    row = _rows(db, req)[0]
    db.refresh(row)
    assert row.status == "met"
    assert row.target_snapshot["target_minutes"] == 60
    assert row.target_snapshot["name"] == "Monthly 1 hr"


def test_re_reviewing_a_flight_after_a_save_does_not_change_it(db):
    pilot = _pilot(db)
    req = _req(db)
    flight = _flight(db, pilot, minutes=60, review_status="needs_review")
    close_due_periods(db, DAY_AFTER_GRACE)
    flight.review_status = "reviewed"
    db.commit()
    close_due_periods(db, DAY_AFTER_GRACE + timedelta(days=1))
    row = _rows(db, req)[0]
    db.refresh(row)
    assert row.status == "missed"
    assert row.totals == {"*": {"minutes": 0, "flights": 0}}


# Recalculation


def test_recalculate_period_changes_the_row_and_is_audited(db, admin_user):
    pilot = _pilot(db)
    req = _req(db)
    flight = _flight(db, pilot, minutes=60, review_status="needs_review")
    close_due_periods(db, DAY_AFTER_GRACE)
    flight.review_status = "reviewed"
    req.target_minutes = 50
    db.commit()
    assert recalculate_period(db, req, OCT[0], admin_user) == 1
    row = _rows(db, req)[0]
    db.refresh(row)
    assert row.status == "met"
    assert row.totals == {"*": {"minutes": 60, "flights": 1}}
    assert row.target_snapshot["target_minutes"] == 50
    entry = db.query(AuditLog).filter(AuditLog.action == "recalculate").one()
    assert (entry.entity_type, entry.entity_id, entry.user_id) == ("flight_requirement", req.id, admin_user.id)


def test_recalculate_keeps_excusals(db, admin_user):
    pilot = _pilot(db)
    req = _req(db)
    db.add(FlightRequirementResult(requirement_id=req.id, pilot_id=pilot.id, period_start=OCT[0],
                                   period_end=OCT[1], excused=True, excused_reason="Deployed"))
    db.commit()
    close_due_periods(db, DAY_AFTER_GRACE)
    assert recalculate_period(db, req, OCT[0], admin_user) == 1
    row = _rows(db, req)[0]
    db.refresh(row)
    assert (row.status, row.excused, row.excused_reason) == ("excused", True, "Deployed")


def test_closing_in_an_app_session_writes_one_summary_entry(_engines, db):
    _pilot(db)
    _pilot(db)
    _req(db)
    session_factory, _ = _engines
    session = session_factory()
    try:
        assert len(close_due_periods(session, DAY_AFTER_GRACE)) == 2
    finally:
        session.close()
    entries = db.query(AuditLog).all()
    assert len(entries) == 1
    assert entries[0].action == "close_periods"


# Open misses


def test_miss_is_open_until_the_next_period_is_met(db):
    pilot = _pilot(db)
    req = _req(db, start_date=SEP[0])
    sep = _saved(db, req, pilot, SEP, "missed")
    flags = open_misses(db)
    assert flags == {pilot.id: [{"result_id": sep.id, "requirement_id": req.id, "name": "Monthly 1 hr",
                                 "period_start": SEP[0], "period_end": SEP[1]}]}
    _saved(db, req, pilot, OCT, "met")
    assert open_misses(db) == {}


def test_misses_stay_open_while_every_later_result_is_missed(db):
    pilot = _pilot(db)
    req = _req(db, start_date=SEP[0])
    _saved(db, req, pilot, SEP, "missed")
    _saved(db, req, pilot, OCT, "missed")
    assert [f["period_start"] for f in open_misses(db)[pilot.id]] == [SEP[0], OCT[0]]


def test_any_later_met_clears_earlier_misses(db):
    pilot = _pilot(db)
    req = _req(db, start_date=AUG[0])
    _saved(db, req, pilot, AUG, "missed")
    _saved(db, req, pilot, SEP, "missed")
    _saved(db, req, pilot, OCT, "met")
    assert open_misses(db) == {}


def test_miss_after_the_last_met_stays_open(db):
    pilot = _pilot(db)
    req = _req(db, start_date=AUG[0])
    _saved(db, req, pilot, AUG, "missed")
    _saved(db, req, pilot, SEP, "met")
    _saved(db, req, pilot, OCT, "missed")
    assert [f["period_start"] for f in open_misses(db)[pilot.id]] == [OCT[0]]


def test_miss_clears_when_excused(db):
    pilot = _pilot(db)
    req = _req(db, start_date=SEP[0])
    row = _saved(db, req, pilot, SEP, "missed")
    row.excused = True
    db.commit()
    assert open_misses(db) == {}


def test_met_on_another_requirement_does_not_clear_a_miss(db):
    pilot = _pilot(db)
    req = _req(db, start_date=SEP[0])
    other = _req(db, start_date=SEP[0], name="Other")
    _saved(db, req, pilot, SEP, "missed")
    _saved(db, other, pilot, OCT, "met")
    assert [f["requirement_id"] for f in open_misses(db)[pilot.id]] == [req.id]


def test_one_time_miss_clears_only_by_excusal(db):
    pilot = _pilot(db)
    req = _req(db, period_type="custom", start_date=SEP[0], end_date=SEP[1], recurring=False)
    other_pilot = _pilot(db)
    row = _saved(db, req, pilot, SEP, "missed")
    _saved(db, req, other_pilot, SEP, "met")
    assert list(open_misses(db)) == [pilot.id]
    row.excused = True
    db.commit()
    assert open_misses(db) == {}


def test_open_misses_filters_by_pilot(db):
    first, second = _pilot(db), _pilot(db)
    req = _req(db, start_date=SEP[0])
    _saved(db, req, first, SEP, "missed")
    _saved(db, req, second, SEP, "missed")
    assert list(open_misses(db, [second.id])) == [second.id]


def test_unsaved_override_row_is_not_a_miss(db):
    pilot = _pilot(db)
    req = _req(db)
    db.add(FlightRequirementResult(requirement_id=req.id, pilot_id=pilot.id, period_start=OCT[0],
                                   period_end=OCT[1], status="missed", excused=False))
    db.commit()
    assert open_misses(db) == {}


# Score


def _months_back(n):
    end = date(2026, 11, 1) - timedelta(days=1 + 31 * n)
    return end.replace(day=1), end


def test_score_is_met_over_met_and_missed(db):
    pilot = _pilot(db)
    req = _req(db, start_date=date(2025, 11, 1))
    statuses = ["met", "met", "met", "missed", "excused", "excused"]
    for n, status in enumerate(statuses):
        _saved(db, req, pilot, _months_back(n), status)
    assert requirements_score(db, DAY_AFTER_GRACE) == pytest.approx(0.75)


def test_score_leaves_out_results_older_than_365_days(db):
    pilot = _pilot(db)
    req = _req(db, start_date=date(2025, 1, 1))
    today = DAY_AFTER_GRACE
    _saved(db, req, pilot, (date(2025, 10, 1), today - timedelta(days=366)), "missed")
    _saved(db, req, pilot, (date(2025, 11, 1), today - timedelta(days=365)), "met")
    assert requirements_score(db, today) == pytest.approx(1.0)


def test_score_leaves_out_unsaved_rows(db):
    pilot = _pilot(db)
    req = _req(db)
    db.add(FlightRequirementResult(requirement_id=req.id, pilot_id=pilot.id, period_start=OCT[0],
                                   period_end=OCT[1], status="missed", excused=False))
    db.commit()
    assert requirements_score(db, DAY_AFTER_GRACE) is None


def test_no_results_gives_none(db):
    assert requirements_score(db, DAY_AFTER_GRACE) is None


def test_only_excused_results_gives_none(db):
    pilot = _pilot(db)
    req = _req(db)
    _saved(db, req, pilot, OCT, "excused")
    assert requirements_score(db, DAY_AFTER_GRACE) is None


# Snapshot


def test_target_snapshot(db):
    req = _req(db, model_mode="each", time_mode="clock", window_start_time=time(18, 0),
               window_end_time=time(6, 30), target_flights=3,
               models=[FlightRequirementModel(model="X2E"), FlightRequirementModel(model="X10")],
               purposes=[FlightRequirementPurpose(purpose="Training")])
    assert target_snapshot(req) == {
        "name": "Monthly 1 hr", "period_type": "calendar_month", "target_minutes": 60,
        "target_flights": 3, "model_mode": "each", "models": ["X10", "X2E"], "time_mode": "clock",
        "window_start_time": "18:00", "window_end_time": "06:30", "purposes": ["Training"],
    }
