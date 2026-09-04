"""Repair battery records left behind by Skydio serial artifacts.

Skydio's API reports battery serials with a leading-dash artifact (its
``battery_serial`` field, e.g. "-k01-231117-1-00061" for the battery the
agency knows as "k01-231117-1-00061"), and older flight data reported bare
short forms (e.g. "-231117-1-00061"). Earlier app versions stored those
strings verbatim, so a fleet could accumulate dash-prefixed and short-form
duplicates of the same physical battery. Ingestion now normalizes serials,
and this module repairs what previous versions stored, in two passes:

1. Dash normalization — every dash-prefixed serial is folded into the
   existing record under the clean serial (the clean serial always stays
   canonical), or simply renamed in place when no clean twin exists.
2. Short-form merge — a serial that is the tail of exactly ONE other, longer
   battery serial is folded into that record.

Folding a duplicate means:

* flights referencing the duplicate's serial string are rewritten to the
  canonical serial (consolidating flight history);
* maintenance records/schedules, documents, and equipment checkouts attached
  to the duplicate's id are re-pointed at the canonical battery;
* fields the canonical record is missing (nickname, notes, lifecycle dates,
  cycle count, health) are filled in from the duplicate before it is deleted.

Both passes are conservative, idempotent, and safe to run on every app
startup.
"""

import logging

from sqlalchemy.orm import Session

from app.models.battery import Battery
from app.models.document import Document
from app.models.equipment_checkout import EquipmentCheckout
from app.models.flight import Flight
from app.models.maintenance import MaintenanceRecord
from app.models.maintenance_schedule import MaintenanceSchedule

logger = logging.getLogger(__name__)

# Shortest serial tail considered for a merge; anything shorter is too
# ambiguous to act on even if it happens to be unique right now.
MIN_SUFFIX_LEN = 4

# Models that reference a battery by id through the generic
# entity_type/entity_id pattern.
_ENTITY_REFS = (MaintenanceRecord, MaintenanceSchedule, EquipmentCheckout, Document)


def _fill_missing_fields(canonical: Battery, dup: Battery) -> None:
    """Copy data the duplicate collected that the canonical record lacks."""
    for field in ("nickname", "notes", "acquired_date", "decommissioned_date", "model", "vehicle_model", "health_pct"):
        if getattr(canonical, field) in (None, "") and getattr(dup, field) not in (None, ""):
            setattr(canonical, field, getattr(dup, field))
    if not canonical.cycle_count and dup.cycle_count:
        canonical.cycle_count = dup.cycle_count


def _merge_into(db: Session, canonical: Battery, dup: Battery) -> None:
    db.query(Flight).filter(Flight.battery_serial == dup.serial_number).update(
        {Flight.battery_serial: canonical.serial_number}, synchronize_session=False
    )
    for model in _ENTITY_REFS:
        db.query(model).filter(
            model.entity_type == "battery", model.entity_id == dup.id
        ).update({model.entity_id: canonical.id}, synchronize_session=False)
    _fill_missing_fields(canonical, dup)
    db.delete(dup)


def _normalize_dash_serials(db: Session, batteries: list[Battery]) -> tuple[int, int]:
    """Strip the leading-dash artifact from battery serials.

    A dash-prefixed battery is folded into the record already holding the
    clean serial when one exists (the clean serial stays canonical);
    otherwise it is renamed in place and its flight serial strings are
    rewritten. Returns (merged, renamed). Merged duplicates are removed from
    `batteries` in place.
    """
    merged = renamed = 0
    by_serial = {(b.serial_number or "").strip().lower(): b for b in batteries}
    for dup in batteries.copy():
        serial = (dup.serial_number or "").strip()
        clean = serial.lstrip("-").strip()
        if clean == serial or len(clean) < MIN_SUFFIX_LEN:
            continue
        twin = by_serial.get(clean.lower())
        if twin is not None and twin is not dup:
            logger.info("Merging dash-prefixed battery %r into %r", serial, twin.serial_number)
            _merge_into(db, twin, dup)
            batteries.remove(dup)
            merged += 1
        else:
            logger.info("Normalizing battery serial %r to %r", serial, clean)
            db.query(Flight).filter(Flight.battery_serial == dup.serial_number).update(
                {Flight.battery_serial: clean}, synchronize_session=False
            )
            dup.serial_number = clean
            by_serial[clean.lower()] = dup
            renamed += 1
    return merged, renamed


def merge_duplicate_batteries(db: Session) -> int:
    """Normalize dash-prefixed serials, then fold short-form duplicates.

    Returns the number of duplicate records folded away. Commits when
    anything changed.
    """
    batteries = db.query(Battery).all()
    merged, renamed = _normalize_dash_serials(db, batteries)
    # Iterate over a snapshot: merged duplicates are removed from `batteries`
    # so they can't be picked as a canonical target afterwards.
    for dup in batteries.copy():
        serial = (dup.serial_number or "").strip()
        tail = serial.lstrip("-").strip().lower()
        if len(tail) < MIN_SUFFIX_LEN:
            continue
        candidates = [
            b for b in batteries
            if b.id != dup.id
            and len((b.serial_number or "").strip()) > len(serial)
            and (b.serial_number or "").strip().lower().endswith(tail)
        ]
        if len(candidates) != 1:
            if len(candidates) > 1:
                logger.warning(
                    "Battery %r matches multiple full serials (%s); skipping merge",
                    serial, ", ".join(c.serial_number for c in candidates),
                )
            continue
        canonical = candidates[0]
        logger.info("Merging duplicate battery %r into %r", serial, canonical.serial_number)
        _merge_into(db, canonical, dup)
        batteries.remove(dup)
        merged += 1
    if merged or renamed:
        db.commit()
        logger.info(
            "Merged %d duplicate battery record(s), normalized %d serial(s)",
            merged, renamed,
        )
    return merged
