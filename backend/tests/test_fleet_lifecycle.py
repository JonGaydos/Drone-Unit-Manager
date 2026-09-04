"""Fleet lifecycle dates and the Other equipment type.

Covers the uniform acquired_date/decommissioned_date fields across fleet
types (including the battery purchase_date -> acquired_date rename), the
decommissioned_date auto-fill on retire/damage, the other_equipment CRUD,
and its participation in maintenance and checkouts. Also verifies that
legacy backups containing purchase_date still restore.
"""

from datetime import date

from app.models.battery import Battery
from app.models.other_equipment import OtherEquipment
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.routers.backup import _parse_rows

TODAY = date.today().isoformat()


def _seed_pilot(db):
    p = Pilot(first_name="Test", last_name="Pilot", status="active")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ── Uniform dates ────────────────────────────────────────────────────────────

def test_battery_acquired_date_round_trip(client, admin_headers):
    resp = client.post("/api/batteries", headers=admin_headers, json={
        "serial_number": "LIFE-B1", "acquired_date": "2024-03-01",
    })
    assert resp.status_code == 200, resp.text
    bid = resp.json()["id"]

    got = client.get(f"/api/batteries/{bid}", headers=admin_headers).json()
    assert got["acquired_date"] == "2024-03-01"
    assert got["decommissioned_date"] is None
    assert "purchase_date" not in got


def test_all_fleet_types_accept_lifecycle_dates(client, admin_headers):
    cases = [
        ("/api/controllers", {"serial_number": "LIFE-C1"}),
        ("/api/docks", {"serial_number": "LIFE-D1"}),
        ("/api/sensors", {"serial_number": "LIFE-S1"}),
        ("/api/attachments", {"serial_number": "LIFE-A1"}),
        ("/api/other-equipment", {"name": "Pelican case"}),
    ]
    for url, payload in cases:
        resp = client.post(url, headers=admin_headers, json={
            **payload, "acquired_date": "2023-06-15", "decommissioned_date": "2026-01-01",
        })
        assert resp.status_code == 200, f"{url}: {resp.text}"
        body = resp.json()
        assert body["acquired_date"] == "2023-06-15", url
        assert body["decommissioned_date"] == "2026-01-01", url


# ── Decommission auto-fill ───────────────────────────────────────────────────

def test_retiring_battery_autofills_decommissioned_date(client, admin_headers):
    bid = client.post("/api/batteries", headers=admin_headers,
                      json={"serial_number": "LIFE-B2"}).json()["id"]

    resp = client.patch(f"/api/batteries/{bid}", headers=admin_headers,
                        json={"status": "retired"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["decommissioned_date"] == TODAY


def test_autofill_respects_existing_and_explicit_dates(client, admin_headers):
    bid = client.post("/api/batteries", headers=admin_headers, json={
        "serial_number": "LIFE-B3", "decommissioned_date": "2025-05-05",
    }).json()["id"]

    # Existing date survives a status change
    resp = client.patch(f"/api/batteries/{bid}", headers=admin_headers,
                        json={"status": "damaged"})
    assert resp.json()["decommissioned_date"] == "2025-05-05"

    # An explicit date in the same request wins
    bid2 = client.post("/api/batteries", headers=admin_headers,
                       json={"serial_number": "LIFE-B4"}).json()["id"]
    resp = client.patch(f"/api/batteries/{bid2}", headers=admin_headers,
                        json={"status": "retired", "decommissioned_date": "2026-02-02"})
    assert resp.json()["decommissioned_date"] == "2026-02-02"


def test_reactivating_does_not_clear_date(client, admin_headers):
    bid = client.post("/api/batteries", headers=admin_headers,
                      json={"serial_number": "LIFE-B5"}).json()["id"]
    client.patch(f"/api/batteries/{bid}", headers=admin_headers, json={"status": "retired"})

    resp = client.patch(f"/api/batteries/{bid}", headers=admin_headers, json={"status": "active"})
    assert resp.json()["decommissioned_date"] == TODAY  # kept, still clearable by hand


def test_vehicle_soft_delete_sets_decommissioned_date(client, db, admin_headers):
    v = Vehicle(serial_number="LIFE-V1", manufacturer="Skydio", model="X10")
    db.add(v)
    db.commit()
    db.refresh(v)

    resp = client.delete(f"/api/vehicles/{v.id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    db.expire_all()
    row = db.query(Vehicle).filter(Vehicle.id == v.id).one()
    assert row.status == "retired"
    assert row.decommissioned_date == date.today()


# ── Other equipment CRUD ─────────────────────────────────────────────────────

def test_other_equipment_crud(client, admin_headers):
    resp = client.post("/api/other-equipment", headers=admin_headers, json={
        "name": "iPad Mini", "category": "tablet", "serial_number": "IPAD-01",
    })
    assert resp.status_code == 200, resp.text
    oid = resp.json()["id"]
    assert resp.json()["status"] == "active"

    listing = client.get("/api/other-equipment", headers=admin_headers).json()
    assert [o["name"] for o in listing] == ["iPad Mini"]

    resp = client.patch(f"/api/other-equipment/{oid}", headers=admin_headers,
                        json={"status": "retired"})
    assert resp.json()["decommissioned_date"] == TODAY

    assert client.delete(f"/api/other-equipment/{oid}", headers=admin_headers).status_code == 200
    assert client.get(f"/api/other-equipment/{oid}", headers=admin_headers).status_code == 404


def test_other_equipment_serial_is_optional(client, admin_headers):
    resp = client.post("/api/other-equipment", headers=admin_headers,
                       json={"name": "USB-C cable", "category": "cable"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["serial_number"] is None


# ── Maintenance and checkouts with "other" items ─────────────────────────────

def test_maintenance_record_for_other_item(client, db, admin_headers):
    item = OtherEquipment(name="Equipment bag")
    db.add(item)
    db.commit()
    db.refresh(item)

    resp = client.post("/api/maintenance", headers=admin_headers, json={
        "entity_type": "other", "entity_id": item.id,
        "maintenance_type": "unscheduled", "description": "zipper repair",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["entity_id"] == item.id

    # Unknown item id is rejected
    resp = client.post("/api/maintenance", headers=admin_headers, json={
        "entity_type": "other", "entity_id": 9999,
        "maintenance_type": "unscheduled", "description": "nope",
    })
    assert resp.status_code == 404


def test_maintenance_other_without_item_still_allowed(client, admin_headers):
    """Legacy behavior: an 'other' record with no specific item."""
    resp = client.post("/api/maintenance", headers=admin_headers, json={
        "entity_type": "other",
        "maintenance_type": "unscheduled", "description": "misc shop work",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["entity_id"] == 0


def test_checkout_other_item(client, db, admin_headers):
    item = OtherEquipment(name="Charging case")
    pilot = _seed_pilot(db)
    db.add(item)
    db.commit()
    db.refresh(item)

    resp = client.post("/api/equipment-checkouts", headers=admin_headers, json={
        "entity_type": "other", "entity_id": item.id, "checked_out_by_id": pilot.id,
    })
    assert resp.status_code == 200, resp.text


# ── Legacy backup restore ────────────────────────────────────────────────────

def test_backup_restore_maps_legacy_purchase_date():
    rows = [{"id": 1, "serial_number": "OLD-B1", "purchase_date": "2023-04-04", "cycle_count": 3}]

    parsed = _parse_rows(rows, Battery)

    assert parsed[0]["acquired_date"] == date(2023, 4, 4)
    assert "purchase_date" not in parsed[0]
