"""Standing on the unit's flight requirements, for the compliance score.

An active pilot is out of standing when they missed the most recently saved
period of an active periodic requirement (unless excused), or have an open
lapse on an active rolling requirement. ``refresh_requirements`` saves due
periods and records lapses first, so a read sees today's standing.
"""

from datetime import date

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.models.flight_requirement import FlightRequirement, FlightRequirementResult
from app.models.pilot import Pilot
from app.services.requirement_eval import MISSED
from app.services.requirement_lapses import ROLLING, open_lapses, sync_lapses
from app.services.requirement_results import close_due_periods


def close_safely(db: Session, today: date) -> None:
    """Save due periods. When the scheduler saves the same period at the same
    moment, the unique index refuses the second writer; its rows are already
    saved, so roll back and carry on."""
    try:
        close_due_periods(db, today)
    except IntegrityError:
        db.rollback()


def sync_safely(db: Session, today: date, req: FlightRequirement | None = None) -> None:
    """Record rolling lapses. A racing writer is handled as in
    ``close_safely``; one that changed or deleted a lapse meanwhile
    (StaleDataError) likewise."""
    try:
        sync_lapses(db, today, req)
    except (IntegrityError, StaleDataError):
        db.rollback()


def refresh_requirements(db: Session, today: date) -> None:
    """Save due periods and record lapses before a read shows results."""
    close_safely(db, today)
    sync_safely(db, today)


def _missed_latest_period(db: Session, today: date) -> set[int]:
    """Pilots whose result for the latest saved period of an active periodic
    requirement is an unexcused miss. The latest period is the requirement's,
    not the pilot's: once a newer period is saved, an older miss stops counting."""
    result = FlightRequirementResult
    latest = (db.query(result.requirement_id, func.max(result.period_start).label("period_start"))
              .filter(result.saved_at.isnot(None), result.period_end < today)
              .group_by(result.requirement_id).subquery())
    rows = (db.query(result.pilot_id)
            .join(latest, and_(latest.c.requirement_id == result.requirement_id,
                               latest.c.period_start == result.period_start))
            .join(FlightRequirement, FlightRequirement.id == result.requirement_id)
            .filter(FlightRequirement.is_active.is_(True), FlightRequirement.period_type != ROLLING,
                    result.saved_at.isnot(None), result.status == MISSED,
                    or_(result.excused.is_(None), result.excused.is_(False))))
    return {pilot_id for (pilot_id,) in rows}


def pilots_not_in_standing(db: Session, today: date) -> tuple[set[int], int]:
    """(Active pilots out of standing on ``today``, each once; the number of
    active requirements, periodic and rolling)."""
    active_pilots = {pilot_id for (pilot_id,) in db.query(Pilot.id).filter(Pilot.status == "active")}
    lapsed = {lapse.pilot_id for lapse, _name in open_lapses(db) if lapse.lapsed_on <= today}
    active_requirements = db.query(func.count(FlightRequirement.id)).filter(
        FlightRequirement.is_active.is_(True)).scalar()
    return (_missed_latest_period(db, today) | lapsed) & active_pilots, active_requirements
