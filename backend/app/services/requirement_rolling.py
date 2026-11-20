"""Each assigned pilot's standing on a rolling flight requirement.

A rolling requirement has no periods: on any day its window is the last N days,
weeks or months ending that day. Flights count by the same rules, scope,
purposes and time-of-day windows as periodic requirements (see
``requirement_eval``). A pilot is current when every required model meets every
set target inside today's window, else lapsed, or not yet due (instead of
lapsed) until one full window has passed since tracking began or they joined;
or excused until a date.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from operator import itemgetter

from sqlalchemy.orm import Session

from app.models.flight_requirement import FlightRequirement, FlightRequirementExcusal
from app.services.requirement_eval import (
    Tally, assigned_pilots, eval_context, late_joiners, reaches, scope_models, tally_flights, unit_eval_settings,
)
from app.services.requirement_periods import Period, add_months

CURRENT, LAPSED, NOT_YET_DUE, EXCUSED = "current", "lapsed", "not_yet_due", "excused"


@dataclass
class RollingProgress:
    pilot_id: int
    status: str
    totals: dict[str, dict]
    met_by_model: dict[str, bool]
    lapse_date: date | None  # while current: the first day the window, with no new flights, falls short
    excused_until: date | None  # while excused: the last day of the excusal
    excluded_no_takeoff: int
    unreviewed_in_window: int
    due_on: date  # the first day the pilot can be lapsed (not yet due before it)


def rolling_window(day: date, length: int, unit: str) -> tuple[date, date]:
    """The ``length`` days or weeks ending on ``day``, inclusive; for months,
    the day after the same day ``length`` months back (clamped to the month's
    length) through ``day``."""
    if unit == "months":
        return add_months(day, -length) + timedelta(days=1), day
    days = length * (7 if unit == "weeks" else 1)
    return day - timedelta(days=days - 1), day


def _ages_out(day: date, length: int, unit: str) -> date:
    """The first day whose window no longer holds ``day``."""
    if unit != "months":
        return day + timedelta(days=length * (7 if unit == "weeks" else 1))
    out = add_months(day, length)
    while rolling_window(out, length, unit)[0] <= day:
        out += timedelta(days=1)
    return out


def _key_lapse(entries: list[tuple[str, date, float, int]], req: FlightRequirement, window: Period) -> date | None:
    """Walk one key's flights newest to oldest; the flight that first meets
    every target is the oldest one still needed, and its aging out is the lapse."""
    total = {"minutes": 0.0, "flights": 0}
    for _key, day, minutes, flights in sorted(entries, key=itemgetter(1), reverse=True):
        total["minutes"] += minutes
        total["flights"] += flights
        if reaches(total, req):
            # A flight from the evening before counts only its part inside the window's first day.
            return _ages_out(max(day, window[0]), req.span_length, req.span_unit)
    return None


def _lapse_date(tally: Tally, req: FlightRequirement, window: Period) -> date | None:
    """The earliest lapse over the required keys."""
    dates = [_key_lapse([entry for entry in tally.counted if entry[0] == key], req, window) for key in tally.totals]
    return min((day for day in dates if day is not None), default=None)


def _status(met: bool, excused_until: date | None, due_on: date, today: date) -> str:
    """Excused wins; a pilot meeting every target is current; not yet due only
    replaces what would otherwise be lapsed."""
    if excused_until is not None:
        return EXCUSED
    if met:
        return CURRENT
    return NOT_YET_DUE if today < due_on else LAPSED


def _excused_until(db: Session, req: FlightRequirement, today: date) -> dict[int, date]:
    """Per pilot, the last day of an excusal that covers ``today``."""
    rows = db.query(FlightRequirementExcusal.pilot_id, FlightRequirementExcusal.excused_until).filter(
        FlightRequirementExcusal.requirement_id == req.id, FlightRequirementExcusal.excused_until >= today)
    return dict(rows.all())


def _progress(req: FlightRequirement, window: Period, pilot_id: int, tally: Tally, due_on: date,
              excused_until: date | None) -> RollingProgress:
    met_by_model = {key: reaches(total, req) for key, total in tally.totals.items()}
    status = _status(bool(met_by_model) and all(met_by_model.values()), excused_until, due_on, window[1])
    return RollingProgress(
        pilot_id=pilot_id, status=status, totals=tally.totals, met_by_model=met_by_model,
        lapse_date=_lapse_date(tally, req, window) if status == CURRENT else None,
        excused_until=excused_until, excluded_no_takeoff=tally.excluded_no_takeoff,
        unreviewed_in_window=tally.unreviewed_in_period, due_on=due_on,
    )


def evaluate_rolling(db: Session, req: FlightRequirement, today: date) -> dict[int, RollingProgress]:
    """Standing of every assigned pilot on rolling ``req`` on ``today``, keyed by pilot id.

    Totals are over ``rolling_window(today, ...)``, keyed as in
    ``evaluate_period``. A pilot short of a target is not yet due, rather
    than lapsed, until one window after the
    later of the requirement's start and their join date; a join date counts
    only when it is after the requirement's start and creation, as for
    periodic automatic excusals. Each separately and all active models take the
    models present at the window's start.
    """
    pilots = assigned_pilots(db, req)
    if not pilots:
        return {}
    settings = unit_eval_settings(db)
    window = rolling_window(today, req.span_length, req.span_unit)
    ctx = eval_context(req, window, settings, scope_models(db, req, window[0]))
    tallies = tally_flights(db, [pilot.id for pilot in pilots], ctx)
    joined = late_joiners(req, pilots, req.start_date, settings.zone)
    excused = _excused_until(db, req, today)
    return {
        pilot_id: _progress(req, window, pilot_id, tally,
                            _ages_out(joined.get(pilot_id, req.start_date), req.span_length, req.span_unit),
                            excused.get(pilot_id))
        for pilot_id, tally in tallies.items()
    }
