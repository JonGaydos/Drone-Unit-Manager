"""Saved results of flight requirement periods, open misses and the Requirements score.

Once a period's grace time has ended, ``close_due_periods`` saves each assigned
pilot's result with a copy of the requirement's target. Saved rows never change
on their own: edits to the requirement and later reviews leave them alone until
an admin recalculates the period on purpose with ``recalculate_period``.
"""

from datetime import date, datetime, timedelta, timezone
from itertools import groupby
from operator import attrgetter

from sqlalchemy.orm import Session

from app.models.flight_requirement import FlightRequirement, FlightRequirementResult
from app.services.audit import log_action
from app.services.audit_capture import machine_run
from app.services.requirement_eval import (
    EXCUSED, MET, MISSED, PilotProgress, UnitEvalSettings, assigned_pilots, evaluate_period,
    unit_eval_settings,
)
from app.services.requirement_periods import Period, first_period, periods_between

SCORE_WINDOW_DAYS = 365


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
    an automatic one is recorded when it decides the status."""
    row.period_end = period_end
    row.status = progress.status
    row.totals = {key: {"minutes": round(total["minutes"]), "flights": total["flights"]}
                  for key, total in progress.totals.items()}
    row.target_snapshot = snapshot
    row.saved_at = now
    if row.excused is None and progress.status == EXCUSED:
        row.excused = True
        row.excused_reason = progress.excused_reason


def _due_periods(req: FlightRequirement, settings: UnitEvalSettings, today: date) -> list[Period]:
    """The requirement's periods whose grace time ended before ``today``."""
    spec = req.to_period_spec(settings.fiscal_start_month)
    first = first_period(spec)
    if first is None:
        return []
    last_end = today - timedelta(days=settings.grace_days + 1)
    return [period for period in periods_between(spec, first[0], last_end) if period[1] <= last_end]


def _is_saved(row: FlightRequirementResult | None) -> bool:
    return row is not None and row.saved_at is not None


def _all_saved(by_key: dict[tuple[int, date], FlightRequirementResult], pilot_ids: list[int],
               period_start: date) -> bool:
    return all(_is_saved(by_key.get((pilot_id, period_start))) for pilot_id in pilot_ids)


def _save_rows(db: Session, req: FlightRequirement, period: Period, progress: dict[int, PilotProgress],
               by_key: dict[tuple[int, date], FlightRequirementResult],
               now: datetime) -> list[FlightRequirementResult]:
    """Save each evaluated pilot's result for ``period`` unless already saved."""
    snapshot = target_snapshot(req)
    saved: list[FlightRequirementResult] = []
    for pilot_id, pilot_progress in progress.items():
        row = by_key.get((pilot_id, period[0]))
        if _is_saved(row):
            continue
        if row is None:
            row = FlightRequirementResult(requirement_id=req.id, pilot_id=pilot_id, period_start=period[0])
            db.add(row)
        _fill(row, pilot_progress, period[1], snapshot, now)
        saved.append(row)
    return saved


def _close_requirement(db: Session, req: FlightRequirement, settings: UnitEvalSettings,
                       today: date, now: datetime) -> list[FlightRequirementResult]:
    periods = _due_periods(req, settings, today)
    pilot_ids = [pilot.id for pilot in assigned_pilots(db, req)] if periods else []
    if not pilot_ids:
        return []
    rows = db.query(FlightRequirementResult).filter(FlightRequirementResult.requirement_id == req.id).all()
    by_key = {(row.pilot_id, row.period_start): row for row in rows}
    saved: list[FlightRequirementResult] = []
    for period in periods:
        if _all_saved(by_key, pilot_ids, period[0]):
            continue
        progress = evaluate_period(db, req, period, today, settings.grace_days)
        saved.extend(_save_rows(db, req, period, progress, by_key, now))
    return saved


def close_due_periods(db: Session, today: date) -> list[FlightRequirementResult]:
    """Save each assigned pilot's result for every period, of every requirement,
    whose grace time ended before ``today``. Rows already saved are left alone,
    an open-period excusal row is filled in, and the rows saved now are
    returned. Safe to run again: a second run saves nothing. Commits, and
    records the run as one audit entry when it saves anything."""
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

    Only pilots still assigned are re-evaluated. Returns how many rows changed
    and records a ``recalculate`` audit entry on the requirement. Commits.
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
    not excused and not followed by a met result."""
    return [
        row for i, row in enumerate(rows)
        if row.status == MISSED and not row.excused
        and not (i + 1 < len(rows) and rows[i + 1].status == MET)
    ]


def open_misses(db: Session, pilot_ids: list[int] | None = None) -> dict[int, list[dict]]:
    """Per pilot, the saved misses still flagged, oldest first by requirement.

    A miss clears when the pilot's next saved result on the same requirement is
    met, or when the miss is excused. Pilots with none are left out.
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
