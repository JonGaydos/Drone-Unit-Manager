"""Battery merge tests: child-row repointing + audit trail + self-merge guard + authz.

Covers the real behavior of ``app.routers.equipment.merge_batteries``
(``POST /api/batteries/{bid}/merge?merge_from_id=<source>``, supervisor-gated):

* The path battery (``bid``) is the merge TARGET; ``merge_from_id`` is the SOURCE.
* The handler repoints child rows off the source onto the target, then DELETES
  the source:
    - ``battery_readings.battery_id``: source.id -> target.id
    - ``equipment_checkouts`` polymorphic rows (``entity_type == "battery"``):
      ``entity_id`` source.id -> target.id
    - (flights are repointed by serial; covered elsewhere)
* It writes one audit row via ``log_action(... "merge", "battery", target.id ...)``.
* Self-merge (``bid == merge_from_id``) returns 400 and makes no changes.
* Merge is supervisor-gated; a pilot gets 403.

Main-db rows are seeded via the ``db`` fixture; the app commits, so cross-session
reads see committed rows after ``expire_all``.
"""

from datetime import datetime

from app.models.audit_log import AuditLog
from app.models.battery import Battery
from app.models.battery_reading import BatteryReading
from app.models.equipment_checkout import EquipmentCheckout
from app.models.pilot import Pilot


def _merge_url(target_id, source_id):
    return f"/api/batteries/{target_id}/merge?merge_from_id={source_id}"


def _seed_battery(db, *, serial):
    b = Battery(serial_number=serial, status="active")
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def _seed_reading(db, *, battery_id, health_pct):
    r = BatteryReading(battery_id=battery_id, health_pct=health_pct, source="manual")
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _seed_pilot(db):
    p = Pilot(first_name="Check", last_name="Out", status="active")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _seed_checkout(db, *, entity_id, pilot_id):
    c = EquipmentCheckout(
        entity_type="battery",
        entity_id=entity_id,
        checked_out_by_id=pilot_id,
        checked_out_at=datetime.utcnow(),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_merge_repoints_child_rows_and_deletes_source(client, db, admin_headers):
    """Merge repoints battery_readings + equipment_checkouts to the target and
    deletes the source, leaving no dangling references."""
    source = _seed_battery(db, serial="SRC-001")
    target = _seed_battery(db, serial="TGT-001")
    pilot = _seed_pilot(db)

    r1 = _seed_reading(db, battery_id=source.id, health_pct=90.0)
    r2 = _seed_reading(db, battery_id=source.id, health_pct=88.0)
    co1 = _seed_checkout(db, entity_id=source.id, pilot_id=pilot.id)
    co2 = _seed_checkout(db, entity_id=source.id, pilot_id=pilot.id)
    source_id, target_id = source.id, target.id

    resp = client.post(_merge_url(target_id, source_id), headers=admin_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True

    db.expire_all()
    # Source battery deleted.
    assert db.query(Battery).filter(Battery.id == source_id).first() is None
    assert db.query(Battery).filter(Battery.id == target_id).first() is not None

    # Every previously-source reading now points at the target; none at source.
    for rid in (r1.id, r2.id):
        assert db.get(BatteryReading, rid).battery_id == target_id
    assert db.query(BatteryReading).filter(
        BatteryReading.battery_id == source_id
    ).count() == 0

    # Every previously-source battery checkout now points at the target.
    for cid in (co1.id, co2.id):
        co = db.get(EquipmentCheckout, cid)
        assert co.entity_type == "battery"
        assert co.entity_id == target_id
    assert db.query(EquipmentCheckout).filter(
        EquipmentCheckout.entity_type == "battery",
        EquipmentCheckout.entity_id == source_id,
    ).count() == 0


def test_merge_writes_audit_row(client, db, admin_headers):
    """The merge logs one audit row: action='merge', entity_type='battery',
    entity_id=target.id, with the human-readable summary in details."""
    source = _seed_battery(db, serial="SRC-AUD")
    target = _seed_battery(db, serial="TGT-AUD")
    source_id, target_id = source.id, target.id

    resp = client.post(_merge_url(target_id, source_id), headers=admin_headers)
    assert resp.status_code == 200, resp.text

    db.expire_all()
    rows = db.query(AuditLog).filter(
        AuditLog.action == "merge",
        AuditLog.entity_type == "battery",
        AuditLog.entity_id == target_id,
    ).all()
    assert len(rows) == 1
    # The human-readable merge summary belongs in details, not entity_name.
    assert "SRC-AUD -> TGT-AUD" in (rows[0].details or "")
    assert "SRC-AUD -> TGT-AUD" not in (rows[0].entity_name or "")
    # entity_name carries the target's display name (its serial number).
    assert rows[0].entity_name == "TGT-AUD"


def test_self_merge_rejected_400_no_changes(client, db, admin_headers):
    """Merging a battery into itself returns 400, leaves the battery intact, and
    writes no merge audit row."""
    b = _seed_battery(db, serial="SELF-001")
    bid = b.id

    resp = client.post(_merge_url(bid, bid), headers=admin_headers)

    assert resp.status_code == 400, resp.text

    db.expire_all()
    # Battery still exists.
    assert db.query(Battery).filter(Battery.id == bid).first() is not None
    # No successful merge was recorded.
    assert db.query(AuditLog).filter(
        AuditLog.action == "merge",
        AuditLog.entity_type == "battery",
    ).count() == 0


def test_merge_requires_supervisor_pilot_forbidden(client, db, pilot_headers):
    """Merge is supervisor-gated; a pilot-role user gets 403 and the source
    battery is untouched."""
    source = _seed_battery(db, serial="SRC-403")
    target = _seed_battery(db, serial="TGT-403")
    source_id, target_id = source.id, target.id

    resp = client.post(_merge_url(target_id, source_id), headers=pilot_headers)

    assert resp.status_code == 403, resp.text

    db.expire_all()
    assert db.query(Battery).filter(Battery.id == source_id).first() is not None
