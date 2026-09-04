"""entity_type validation tests for the equipment-checkout create endpoint.

Locks in ``app.routers.equipment_checkouts._validate_entity`` as called from
``POST /api/equipment-checkouts`` (pilot-or-higher gated). The handler must:

* reject an unknown ``entity_type`` with 400 (and list the allowed types);
* reject a valid type whose ``entity_id`` row does not exist with 404;
* create the checkout (200) when the type is allowed and the entity exists.

The entity_type check runs BEFORE the double-checkout and pilot-existence
checks, so the 400/404 cases need no other seeded state. Allowed types
(``ENTITY_MODELS``): vehicle, battery, controller, dock, sensor, attachment —
all table-backed, so every type is existence-checked.

Main-db rows are seeded via the ``db`` fixture; the app commits, so cross-session
reads see committed rows after ``expire_all``.
"""

from app.models.equipment_checkout import EquipmentCheckout
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle


def _seed_vehicle(db, *, serial):
    v = Vehicle(serial_number=serial, manufacturer="Skydio", model="X10", status="active")
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _seed_pilot(db):
    p = Pilot(first_name="Check", last_name="Out", status="active")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_create_checkout_bad_entity_type_400(client, db, admin_headers):
    """An unknown entity_type returns 400, names the bad type, lists the
    allowed types, and creates no row."""
    resp = client.post(
        "/api/equipment-checkouts",
        headers=admin_headers,
        json={"entity_type": "bogus", "entity_id": 1, "checked_out_by_id": 1},
    )

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "entity_type" in detail
    assert "bogus" in detail
    assert "vehicle" in detail  # the allowed-types list is included

    db.expire_all()
    assert db.query(EquipmentCheckout).count() == 0


def test_create_checkout_missing_entity_id_404(client, db, admin_headers):
    """A valid (table-backed) type with a nonexistent entity_id returns 404 and
    creates no row."""
    resp = client.post(
        "/api/equipment-checkouts",
        headers=admin_headers,
        json={"entity_type": "vehicle", "entity_id": 999999, "checked_out_by_id": 1},
    )

    assert resp.status_code == 404, resp.text

    db.expire_all()
    assert db.query(EquipmentCheckout).count() == 0


def test_create_checkout_valid_entity_succeeds(client, db, admin_headers):
    """A valid type pointing at an existing entity creates the checkout (200)."""
    vehicle = _seed_vehicle(db, serial="CO-V1")
    pilot = _seed_pilot(db)
    vehicle_id, pilot_id = vehicle.id, pilot.id

    resp = client.post(
        "/api/equipment-checkouts",
        headers=admin_headers,
        json={
            "entity_type": "vehicle",
            "entity_id": vehicle_id,
            "checked_out_by_id": pilot_id,
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entity_type"] == "vehicle"
    assert body["entity_id"] == vehicle_id

    db.expire_all()
    rows = db.query(EquipmentCheckout).filter(
        EquipmentCheckout.entity_type == "vehicle",
        EquipmentCheckout.entity_id == vehicle_id,
    ).all()
    assert len(rows) == 1
    assert rows[0].checked_out_by_id == pilot_id
