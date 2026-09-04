"""Tests for short-form duplicate battery handling.

Covers both halves of the fix:

* ``app.services.battery_dedupe.merge_duplicate_batteries`` — the idempotent
  startup merge that folds dash-prefixed/short-form duplicates (created by the
  old exact-string equipment auto-create) into the canonical full-serial
  battery, rewriting flight serial strings and re-pointing attached records.
* ``app.services.sync_manager._ensure_simple_equipment`` /
  ``_ensure_equipment_records`` — prevention: a short-form serial resolves to
  the existing battery (and the flight string is normalized) instead of
  creating a duplicate.
"""

from datetime import date

from app.models.battery import Battery
from app.models.document import Document
from app.models.equipment_checkout import EquipmentCheckout
from app.models.flight import Flight
from app.models.maintenance import MaintenanceRecord
from app.models.pilot import Pilot
from app.services.battery_dedupe import merge_duplicate_batteries
from app.services.sync_manager import _ensure_equipment_records, _ensure_simple_equipment

FULL_SERIAL = "k01-231117-1-00061"
SHORT_SERIAL = "-231117-1-00061"
DASH_FULL_SERIAL = "-k01-231117-1-00061"  # Skydio /batteries `battery_serial` form


def _seed_battery(db, serial, **kwargs):
    b = Battery(serial_number=serial, **kwargs)
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def test_merge_folds_short_form_duplicate(db):
    """The dup's flights, attached records, and data fold into the canonical
    battery, and the dup row is deleted."""
    canonical = _seed_battery(db, FULL_SERIAL, manufacturer="Skydio", api_provider="skydio")
    dup = _seed_battery(db, SHORT_SERIAL, notes="found in case 3", acquired_date=date(2024, 1, 5))

    pilot = Pilot(first_name="Test", last_name="Pilot", status="active")
    db.add(pilot)
    db.flush()
    db.add(Flight(external_id="F1", battery_serial=SHORT_SERIAL))
    db.add(MaintenanceRecord(entity_type="battery", entity_id=dup.id, maintenance_type="unscheduled", description="cell swap"))
    db.add(Document(entity_type="battery", entity_id=dup.id, document_type="other", title="Receipt", filename="r.pdf", file_path="uploads/documents/battery/r.pdf", mime_type="application/pdf", file_size_bytes=1))
    db.add(EquipmentCheckout(entity_type="battery", entity_id=dup.id, checked_out_by_id=pilot.id))
    db.commit()

    merged = merge_duplicate_batteries(db)

    assert merged == 1
    db.expire_all()
    assert db.query(Battery).count() == 1
    survivor = db.query(Battery).first()
    assert survivor.id == canonical.id
    assert survivor.serial_number == FULL_SERIAL
    # Data the canonical lacked is filled from the dup
    assert survivor.notes == "found in case 3"
    assert survivor.acquired_date == date(2024, 1, 5)

    assert db.query(Flight).filter(Flight.battery_serial == FULL_SERIAL).count() == 1
    assert db.query(Flight).filter(Flight.battery_serial == SHORT_SERIAL).count() == 0
    assert db.query(MaintenanceRecord).filter(MaintenanceRecord.entity_id == canonical.id).count() == 1
    assert db.query(Document).filter(Document.entity_id == canonical.id).count() == 1
    assert db.query(EquipmentCheckout).filter(EquipmentCheckout.entity_id == canonical.id).count() == 1


def test_merge_is_idempotent_and_skips_ambiguous(db):
    """A second run merges nothing; a suffix matching two full serials is
    left alone."""
    _seed_battery(db, FULL_SERIAL)
    _seed_battery(db, SHORT_SERIAL)
    assert merge_duplicate_batteries(db) == 1
    assert merge_duplicate_batteries(db) == 0

    # Ambiguous: "-1-00099" is the tail of two different full serials. The
    # dash artifact is still stripped, but the record is never merged.
    _seed_battery(db, "k01-231117-1-00099")
    _seed_battery(db, "g00-210719-1-00099")
    _seed_battery(db, "-1-00099")
    assert merge_duplicate_batteries(db) == 0
    db.expire_all()
    assert db.query(Battery).filter(Battery.serial_number == "1-00099").count() == 1


def test_merge_ignores_unrelated_and_short_tails(db):
    """Distinct full serials never merge into each other, and tiny fragments
    are ignored even if unique."""
    _seed_battery(db, FULL_SERIAL)
    _seed_battery(db, "m2090490d58b0226")
    _seed_battery(db, "-61")  # tail shorter than MIN_SUFFIX_LEN
    assert merge_duplicate_batteries(db) == 0
    db.expire_all()
    assert db.query(Battery).count() == 3


def test_normalize_renames_dash_serial_without_twin(db):
    """A dash-prefixed serial with no clean twin is renamed in place (same
    row, data kept) and its flight serial strings are rewritten."""
    b = _seed_battery(db, "-k01-231025-1-01022", nickname="X10 Battery 1")
    db.add(Flight(external_id="F3", battery_serial="-k01-231025-1-01022"))
    db.commit()

    assert merge_duplicate_batteries(db) == 0  # nothing deleted, only renamed
    db.expire_all()
    row = db.query(Battery).one()
    assert row.id == b.id
    assert row.serial_number == "k01-231025-1-01022"
    assert row.nickname == "X10 Battery 1"
    assert db.query(Flight).filter(Flight.battery_serial == "k01-231025-1-01022").count() == 1


def test_normalize_merges_dash_serial_into_clean_twin(db):
    """When both forms exist, the clean serial stays canonical and the
    dash-prefixed Skydio record folds into it."""
    canonical = _seed_battery(db, FULL_SERIAL, nickname="X2 Battery 8")
    dup = _seed_battery(db, DASH_FULL_SERIAL, manufacturer="Skydio", api_provider="skydio", cycle_count=8)
    db.add(Flight(external_id="F4", battery_serial=DASH_FULL_SERIAL))
    db.add(MaintenanceRecord(entity_type="battery", entity_id=dup.id, maintenance_type="unscheduled", description="cell swap"))
    db.commit()

    assert merge_duplicate_batteries(db) == 1
    db.expire_all()
    survivor = db.query(Battery).one()
    assert survivor.id == canonical.id
    assert survivor.serial_number == FULL_SERIAL
    assert survivor.nickname == "X2 Battery 8"
    assert survivor.cycle_count == 8  # filled from the dup
    assert db.query(Flight).filter(Flight.battery_serial == FULL_SERIAL).count() == 1
    assert db.query(MaintenanceRecord).filter(MaintenanceRecord.entity_id == canonical.id).count() == 1


def test_normalize_chain_converges_on_clean_serial(db):
    """The live regression: a user record, its dash-prefixed Skydio sync
    twin, and an old short form all converge on the clean serial."""
    _seed_battery(db, FULL_SERIAL)
    _seed_battery(db, DASH_FULL_SERIAL)
    _seed_battery(db, SHORT_SERIAL)

    assert merge_duplicate_batteries(db) == 2
    db.expire_all()
    assert db.query(Battery).one().serial_number == FULL_SERIAL
    # Idempotent
    assert merge_duplicate_batteries(db) == 0


def test_ensure_equipment_resolves_short_form_without_duplicating(db):
    """The auto-create path matches a short-form serial to the existing
    battery and normalizes the flight's serial string."""
    _seed_battery(db, FULL_SERIAL)
    flight = Flight(external_id="F2", battery_serial=SHORT_SERIAL)
    db.add(flight)
    db.flush()

    _ensure_equipment_records(db, flight)
    db.commit()

    db.expire_all()
    assert db.query(Battery).count() == 1  # no duplicate created
    assert flight.battery_serial == FULL_SERIAL  # normalized in place


def test_ensure_equipment_creates_unknown_dash_serial_clean(db):
    """A dash-prefixed serial matching nothing is created under its clean
    form, and the caller gets the clean serial to store on the flight."""
    created = _ensure_simple_equipment(db, DASH_FULL_SERIAL, Battery, "battery")
    db.commit()

    assert created == FULL_SERIAL
    db.expire_all()
    assert db.query(Battery).one().serial_number == FULL_SERIAL


def test_ensure_equipment_still_creates_unknown_serials(db):
    """A serial that matches nothing (exactly or by suffix) is still created."""
    _seed_battery(db, FULL_SERIAL)
    created = _ensure_simple_equipment(db, "m2090490d58b0226", Battery, "battery")
    db.commit()

    assert created == "m2090490d58b0226"
    db.expire_all()
    assert db.query(Battery).count() == 2


def test_ensure_equipment_exact_match_case_insensitive(db):
    """Case differences don't create duplicates either."""
    _seed_battery(db, FULL_SERIAL)
    resolved = _ensure_simple_equipment(db, FULL_SERIAL.upper(), Battery, "battery")

    assert resolved == FULL_SERIAL
    db.expire_all()
    assert db.query(Battery).count() == 1
