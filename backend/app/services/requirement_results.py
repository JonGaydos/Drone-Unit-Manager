"""Saved results of flight requirement periods, open misses and the Requirements score.

Once a period's grace time has ended, ``close_due_periods`` saves each assigned
pilot's result with a copy of the requirement's target. Saved rows never change
on their own: edits to the requirement and later reviews leave them alone until
an admin recalculates the period on purpose with ``recalculate_period``.
"""

import math
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from itertools import groupby
from operator import attrgetter

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.flight_requirement import FlightRequirement, FlightRequirementResult
from app.services.audit import log_action
from app.services.audit_capture import machine_run
from app.services.local_time import local_flight_date
from app.services.requirement_eval import (
    EXCUSED, MET, MISSED, PilotProgress, UnitEvalSettings, assigned_pilots, evaluate_period,
    unit_eval_settings,
)
from app.services.requirement_periods import Period, periods_between

SCORE_WINDOW_DAYS = 365
OFF_REASON = "Requirement was switched off"


def _clock(value) -> str | None:
    return value.isoformat(timespec="minutes") if value is not None else None


def target_snapshot(req: FlightRequirement) -> dict:
    """The requirement's target and scope as saved with each result."""
    return {
        "name": req.name,
        "period_type": req.period_type,
        "target_minutes": req.target_minutes,
        "target_flights": req.target_flights,
        "model_mode": req.model_mode,
        "models": sorted((row.model for row in req.models), key=str.casefold),
        "time_mode": req.time_mode,
        "window_start_time": _clock(req.window_start_time),
        "window_end_time": _clock(req.window_end_time),
        "purposes": sorted((row.purpose for row in req.purposes), key=str.casefold),
    }


def _fill(row: FlightRequirementResult, progress: PilotProgress, period_end: date, snapshot: dict,
          now: datetime) -> None:
    """Write an evaluation into a result row. A stored excusal is kept as it is;
    an automatic one is recorded when it decides the status. Minutes are rounded
    down, so a saved miss never shows the target's minutes."""
    row.period_end = period_end
    row.status = progress.status
    row.totals = {key: {"minutes": math.floor(total["minutes"]), "flights": total["flights"]}
                  for key, total in progress.totals.items()}
    row.target_snapshot = snapshot
    row.saved_at = now
    if row.excused is None and progress.status == EXCUSED:
        row.excused = True
        row.excused_reason = progress.excused_reason


def _closing_ends(req: FlightRequirement, settings: UnitEvalSettings, today: date) -> tuple[date, date] | None:
    """The earliest and latest period end that can close today, or None.

    A period closes once its grace time has ended. For a requirement switched
    back on, periods that ended while it was off close at once (they are saved
    as excused, so there is nothing to wait for). An inactive requirement
    closes only periods that ended by the day it was switched off, and nothing
    if it was never on."""
    latest = today - timedelta(days=settings.grace_days + 1)
    changed = local_flight_date(req.active_changed_at, settings.zone)
    if req.is_active:
        return date.min, latest if changed is None else max(latest, changed - timedelta(days=1))
    if changed is None:
        return None
    return date.min, min(latest, changed)


def _on_since(req: FlightRequirement, settings: UnitEvalSettings) -> date | None:
    """For a requirement switched back on, the local day it was; periods that
    ended before it fell while it was off."""
    return local_flight_date(req.active_changed_at, settings.zone) if req.is_active else None


def saved_through(db: Session, requirement_id: int) -> date | None:
    """The end of the requirement's latest saved period; periods up to it are closed."""
    return db.query(func.max(FlightRequirementResult.period_end)).filter(
        FlightRequirementResult.requirement_id == requirement_id, FlightRequirementResult.saved_at.isnot(None),
    ).scalar()


def pending_periods(db: Session, req: FlightRequirement, settings: UnitEvalSettings,
                    today: date) -> list[Period]:
    """Periods that have ended and are still inside their grace time, not saved, oldest first."""
    first = today - timedelta(days=settings.grace_days)
    watermark = saved_through(db, req.id)
    spec = req.to_period_spec(settings.fiscal_start_month)
    return [period for period in periods_between(spec, first, today - timedelta(days=1))
            if first <= period[1] < today and (watermark is None or period[0] > watermark)]


def _due_periods(db: Session, req: FlightRequirement, settings: UnitEvalSettings,
                 today: date) -> list[Period]:
    """The requirement's periods ready to close: due, and starting after the
    last saved period ended. Closed periods never reopen, so a pilot added or
    reactivated later, or a changed period layout, does not save past dates."""
    ends = _closing_ends(req, settings, today)
    if ends is None:
        return []
    watermark = saved_through(db, req.id)
    spec = req.to_period_spec(settings.fiscal_start_month)
    return [period for period in periods_between(spec, *ends)
            if period[1] <= ends[1] and (watermark is None or period[0] > watermark)]


def _switched_off(progress: PilotProgress) -> PilotProgress:
    """A pilot's result for a period that ended while the requirement was off."""
    zeros = {key: {"minutes": 0, "flights": 0} for key in progress.totals}
    return replace(progress, status=EXCUSED, totals=zeros, excused=True, excused_reason=OFF_REASON)


def _save_rows(db: Session, req: FlightRequirement, period: Period, progress: dict[int, PilotProgress],
               overrides: dict[tuple[int, date], FlightRequirementResult], now: datetime,
               off: bool) -> list[FlightRequirementResult]:
    """Save each evaluated pilot's result for ``period``, filling an excusal row
    if there is one. A period that ended while the requirement was off is saved
    as excused for that reason, whatever any excusal row said."""
    snapshot = target_snapshot(req)
    saved: list[FlightRequirementResult] = []
    for pilot_id, pilot_progress in progress.items():
        row = overrides.get((pilot_id, period[0]))
        if row is None:
            row = FlightRequirementResult(requirement_id=req.id, pilot_id=pilot_id, period_start=period[0])
            db.add(row)
        if off:
            row.excused, row.excused_by_id, row.excused_reason = True, None, OFF_REASON
        _fill(row, _switched_off(pilot_progress) if off else pilot_progress, period[1], snapshot, now)
        saved.append(row)
    return saved


def _close_requirement(db: Session, req: FlightRequirement, settings: UnitEvalSettings,
                       today: date, now: datetime) -> list[FlightRequirementResult]:
    periods = _due_periods(db, req, settings, today)
    if not periods or not assigned_pilots(db, req):
        return []
    overrides = {
        (row.pilot_id, row.period_start): row for row in db.query(FlightRequirementResult).filter(
            FlightRequirementResult.requirement_id == req.id,
            FlightRequirementResult.saved_at.is_(None),
        )
    }
    on_since = _on_since(req, settings)
    saved: list[FlightRequirementResult] = []
    for period in periods:
        progress = evaluate_period(db, req, period, today, settings.grace_days)
        off = on_since is not None and period[1] < on_since
        saved.extend(_save_rows(db, req, period, progress, overrides, now, off))
    return saved


def close_due_periods(db: Session, today: date) -> list[FlightRequirementResult]:
    """Save each assigned pilot's result for every period, of every requirement,
    whose grace time ended before ``today`` and which starts after the
    requirement's last saved period ended. A period is saved for every assigned
    pilot at once and is closed from then on; an open-period excusal row is
    filled in. An inactive requirement saves only periods that ended by the day
    it was switched off. One switched back on saves the periods that ended
    while it was off as excused, so a later switch-off cannot reopen them.
    Returns the rows saved now. Safe to run again: a second
    run saves nothing. Commits, and records the run as one audit entry when it
    saves anything."""
    settings = unit_eval_settings(db)
    now = datetime.now(timezone.utc)
    saved: list[FlightRequirementResult] = []
    with machine_run(db, "close_periods", "flight_requirement_result",
                     details="Saved flight requirement periods past their grace time"):
        for req in db.query(FlightRequirement).order_by(FlightRequirement.id).all():
            saved.extend(_close_requirement(db, req, settings, today, now))
    db.commit()
    return saved


def recalculate_period(db: Session, req: FlightRequirement, period_start: date, actor) -> int:
    """Re-evaluate one saved period of ``req`` against today's flights and
    requirement, overwriting its saved rows but keeping their excusals.

    Only pilots still assigned are re-evaluated. Returns how many rows were
    re-evaluated and records a ``recalculate`` audit entry on the requirement. Commits.
    """
    rows = db.query(FlightRequirementResult).filter(
        FlightRequirementResult.requirement_id == req.id,
        FlightRequirementResult.period_start == period_start,
        FlightRequirementResult.saved_at.isnot(None),
    ).all()
    count = 0
    if rows:
        period = (period_start, rows[0].period_end)
        grace_days = unit_eval_settings(db).grace_days
        after_grace = period[1] + timedelta(days=grace_days + 1)
        progress = evaluate_period(db, req, period, after_grace, grace_days)
        snapshot = target_snapshot(req)
        now = datetime.now(timezone.utc)
        for row in rows:
            if row.pilot_id in progress:
                _fill(row, progress[row.pilot_id], period[1], snapshot, now)
                count += 1
    log_action(db, actor.id, actor.display_name, "recalculate", "flight_requirement", req.id, req.name,
               details=f"Recalculated the period starting {period_start.isoformat()}: {count} results")
    db.commit()
    return count


def _open_in_group(rows: list[FlightRequirementResult]) -> list[FlightRequirementResult]:
    """One pilot's saved results on one requirement, by period start: the misses
    not excused and not followed by any met result."""
    found: list[FlightRequirementResult] = []
    met_later = False
    for row in reversed(rows):
        met_later = met_later or row.status == MET
        if row.status == MISSED and not row.excused and not met_later:
            found.append(row)
    return found[::-1]


def open_misses(db: Session, pilot_ids: list[int] | None = None) -> dict[int, list[dict]]:
    """Per pilot, the saved misses still flagged, oldest first by requirement.

    A miss clears when any later saved result of the pilot on the same
    requirement is met, or when the miss is excused. Pilots with none are left out.
    """
    query = (
        db.query(FlightRequirementResult, FlightRequirement.name)
        .join(FlightRequirement, FlightRequirement.id == FlightRequirementResult.requirement_id)
        .filter(FlightRequirementResult.saved_at.isnot(None))
    )
    if pilot_ids is not None:
        query = query.filter(FlightRequirementResult.pilot_id.in_(pilot_ids))
    found = query.order_by(FlightRequirementResult.pilot_id, FlightRequirementResult.requirement_id,
                           FlightRequirementResult.period_start).all()
    names = {row.requirement_id: name for row, name in found}
    flags: dict[int, list[dict]] = {}
    rows = (row for row, _ in found)
    for (pilot_id, _req_id), group in groupby(rows, key=attrgetter("pilot_id", "requirement_id")):
        for row in _open_in_group(list(group)):
            flags.setdefault(pilot_id, []).append({
                "result_id": row.id, "requirement_id": row.requirement_id,
                "name": names[row.requirement_id],
                "period_start": row.period_start, "period_end": row.period_end,
            })
    return flags


def requirements_score(db: Session, today: date) -> float | None:
    """Met over met and missed, for saved results whose period ended in the
    365 days before ``today``. Excused results are left out; None when none
    count."""
    statuses = [status for (status,) in db.query(FlightRequirementResult.status).filter(
        FlightRequirementResult.saved_at.isnot(None),
        FlightRequirementResult.status.in_((MET, MISSED)),
        FlightRequirementResult.period_end >= today - timedelta(days=SCORE_WINDOW_DAYS),
        FlightRequirementResult.period_end < today,
    )]
    if not statuses:
        return None
    return statuses.count(MET) / len(statuses)
