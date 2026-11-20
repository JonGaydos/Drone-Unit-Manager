"""Lapse history of rolling flight requirements.

``sync_lapses`` compares each assigned pilot's standing today with the open
lapse rows: a lapsed pilot with none gets one dated today, and an open lapse
closes today once the pilot is current, excused or not yet due, or no longer
assigned. Later reviews never edit a lapse; an admin may delete one.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models.flight_requirement import FlightRequirement, FlightRequirementLapse
from app.services.audit_capture import machine_run
from app.services.requirement_rolling import LAPSED, evaluate_rolling

ROLLING = "rolling"


def rolling_requirements(db: Session) -> list[FlightRequirement]:
    """Active rolling requirements, by name."""
    return (db.query(FlightRequirement)
            .filter(FlightRequirement.is_active.is_(True), FlightRequirement.period_type == ROLLING)
            .order_by(FlightRequirement.name, FlightRequirement.id).all())


def _open_rows(db: Session, req: FlightRequirement) -> dict[int, FlightRequirementLapse]:
    """Each pilot's open lapse on ``req``. A pilot merge can leave two; the
    earliest is kept and the later ones, which it already covers, are deleted."""
    rows = (db.query(FlightRequirementLapse)
            .filter(FlightRequirementLapse.requirement_id == req.id, FlightRequirementLapse.recovered_on.is_(None))
            .order_by(FlightRequirementLapse.lapsed_on, FlightRequirementLapse.id).all())
    found: dict[int, FlightRequirementLapse] = {}
    for row in rows:
        if row.pilot_id in found:
            db.delete(row)
        else:
            found[row.pilot_id] = row
    return found


def _open(db: Session, req: FlightRequirement, pilot_id: int, today: date) -> FlightRequirementLapse:
    """A lapse starting today; one that started and closed today is reopened,
    as the unique index allows one row per day."""
    row = db.query(FlightRequirementLapse).filter_by(
        requirement_id=req.id, pilot_id=pilot_id, lapsed_on=today).first()
    if row is None:
        row = FlightRequirementLapse(requirement_id=req.id, pilot_id=pilot_id, lapsed_on=today)
        db.add(row)
    row.recovered_on = None
    return row


def _sync_requirement(db: Session, req: FlightRequirement, today: date,
                      opened: list[FlightRequirementLapse], closed: list[FlightRequirementLapse]) -> None:
    open_rows = _open_rows(db, req)
    for pilot_id, progress in evaluate_rolling(db, req, today).items():
        row = open_rows.pop(pilot_id, None)
        if progress.status == LAPSED and row is None:
            opened.append(_open(db, req, pilot_id, today))
        elif progress.status != LAPSED and row is not None:
            row.recovered_on = today
            closed.append(row)
    # Pilots no longer assigned, or no longer active.
    for row in open_rows.values():
        row.recovered_on = today
        closed.append(row)


def sync_lapses(db: Session, today: date) -> tuple[list[FlightRequirementLapse], list[FlightRequirementLapse]]:
    """Open and close lapses on every active rolling requirement for ``today``.
    Returns (opened, closed). Safe to run again: a second run changes nothing.
    Commits, and records the run as one audit entry when it changes anything."""
    opened: list[FlightRequirementLapse] = []
    closed: list[FlightRequirementLapse] = []
    with machine_run(db, "sync_lapses", "flight_requirement_lapse", details="Recorded rolling requirement lapses"):
        for req in rolling_requirements(db):
            _sync_requirement(db, req, today, opened, closed)
    db.commit()
    return opened, closed


def open_lapses(db: Session, pilot_ids: list[int] | None = None) -> list[tuple[FlightRequirementLapse, str]]:
    """Open lapses on active rolling requirements, with the requirement's name,
    by pilot, requirement and start."""
    query = (db.query(FlightRequirementLapse, FlightRequirement.name)
             .join(FlightRequirement, FlightRequirement.id == FlightRequirementLapse.requirement_id)
             .filter(FlightRequirementLapse.recovered_on.is_(None), FlightRequirement.is_active.is_(True),
                     FlightRequirement.period_type == ROLLING))
    if pilot_ids is not None:
        query = query.filter(FlightRequirementLapse.pilot_id.in_(pilot_ids))
    return query.order_by(FlightRequirementLapse.pilot_id, FlightRequirementLapse.requirement_id,
                          FlightRequirementLapse.lapsed_on).all()
