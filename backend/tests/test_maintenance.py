"""entity_type validation tests for the maintenance create endpoint.

Locks in ``app.routers.maintenance._validate_entity`` as called from
``POST /api/maintenance`` (pilot-or-higher gated). The handler must:

* reject an unknown ``entity_type`` with 400 (and list the allowed types);
* reject a valid type whose ``entity_id`` row does not exist with 404;
* create the record (200) when the type is allowed and the entity exists.

Allowed types (``ENTITY_MODELS``): vehicle, battery, controller, dock, sensor,
attachment — all table-backed, so every type is existence-checked.

Main-db rows are seeded via the ``db`` fixture; the app commits, so cross-session
reads see committed rows after ``expire_all``.
"""

from app.models.maintenance import MaintenanceRecord
from app.models.vehicle import Vehicle


def _seed_vehicle(db, *, serial):
    v = Vehicle(serial_number=serial, manufacturer="Skydio", model="X10", status="active")
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def test_create_maintenance_bad_entity_type_400(client, db, admin_headers):
    """An unknown entity_type returns 400, names the bad type, lists the
    allowed types, and creates no row."""
    resp = client.post(
        "/api/maintenance",
        headers=admin_headers,
        json={"entity_type": "bogus", "entity_id": 1, "description": "oil change"},
    )

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "entity_type" in detail
    assert "bogus" in detail
    assert "vehicle" in detail  # the allowed-types list is included

    db.expire_all()
    assert db.query(MaintenanceRecord).count() == 0


def test_create_maintenance_missing_entity_id_404(client, db, admin_headers):
    """A valid (table-backed) type with a nonexistent entity_id returns 404 and
    creates no row."""
    resp = client.post(
        "/api/maintenance",
        headers=admin_headers,
        json={"entity_type": "vehicle", "entity_id": 999999, "description": "oil change"},
    )

    assert resp.status_code == 404, resp.text

    db.expire_all()
    assert db.query(MaintenanceRecord).count() == 0


def test_create_maintenance_valid_entity_succeeds(client, db, admin_headers):
    """A valid type pointing at an existing entity creates the record (200)."""
    vehicle = _seed_vehicle(db, serial="MAINT-V1")
    vehicle_id = vehicle.id

    resp = client.post(
        "/api/maintenance",
        headers=admin_headers,
        json={
            "entity_type": "vehicle",
            "entity_id": vehicle_id,
            "description": "oil change",
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entity_type"] == "vehicle"
    assert body["entity_id"] == vehicle_id

    db.expire_all()
    rows = db.query(MaintenanceRecord).filter(
        MaintenanceRecord.entity_type == "vehicle",
        MaintenanceRecord.entity_id == vehicle_id,
    ).all()
    assert len(rows) == 1
    assert rows[0].description == "oil change"


def test_create_maintenance_other_entity_type_no_entity_id(client, db, admin_headers):
    """entity_type "other" needs no entity_id; the record stores the sentinel 0
    (the column is NOT NULL, matching the schedule-complete convention)."""
    resp = client.post(
        "/api/maintenance",
        headers=admin_headers,
        json={"entity_type": "other", "description": "FAA Authorization renewal"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entity_type"] == "other"
    assert body["entity_id"] == 0

    db.expire_all()
    row = db.query(MaintenanceRecord).filter(MaintenanceRecord.entity_type == "other").first()
    assert row is not None
    assert row.entity_id == 0
    assert row.description == "FAA Authorization renewal"


def test_create_maintenance_organization_entity_type_allowed(client, db, admin_headers):
    """entity_type "organization" is accepted without an entity_id."""
    resp = client.post(
        "/api/maintenance",
        headers=admin_headers,
        json={"entity_type": "organization", "description": "Org-wide audit"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["entity_id"] == 0


def test_create_maintenance_table_backed_type_requires_entity_id(client, db, admin_headers):
    """A table-backed type without an entity_id returns 400 and creates no row."""
    resp = client.post(
        "/api/maintenance",
        headers=admin_headers,
        json={"entity_type": "vehicle", "description": "oil change"},
    )

    assert resp.status_code == 400, resp.text
    assert "entity_id" in resp.json()["detail"]

    db.expire_all()
    assert db.query(MaintenanceRecord).count() == 0


def _seed_record(client, admin_headers, vehicle_id):
    resp = client.post(
        "/api/maintenance",
        headers=admin_headers,
        json={"entity_type": "vehicle", "entity_id": vehicle_id, "description": "oil change"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_update_maintenance_can_change_entity(client, db, admin_headers):
    """PATCH can move a record to a different entity type + id (regression:
    entity fields were silently dropped from updates)."""
    from app.models.battery import Battery

    vehicle = _seed_vehicle(db, serial="MAINT-EDIT-V1")
    battery = Battery(serial_number="MAINT-EDIT-B1")
    db.add(battery)
    db.commit()
    db.refresh(battery)
    record_id = _seed_record(client, admin_headers, vehicle.id)

    resp = client.patch(
        f"/api/maintenance/{record_id}",
        headers=admin_headers,
        json={"entity_type": "battery", "entity_id": battery.id},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entity_type"] == "battery"
    assert body["entity_id"] == battery.id

    db.expire_all()
    row = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    assert row.entity_type == "battery"
    assert row.entity_id == battery.id


def test_update_maintenance_type_change_requires_entity_id(client, db, admin_headers):
    """Changing to a different table-backed entity_type without a new
    entity_id is rejected — the old id must not be reused across tables."""
    vehicle = _seed_vehicle(db, serial="MAINT-EDIT-V2")
    record_id = _seed_record(client, admin_headers, vehicle.id)

    resp = client.patch(
        f"/api/maintenance/{record_id}",
        headers=admin_headers,
        json={"entity_type": "battery"},
    )

    assert resp.status_code == 400, resp.text
    assert "entity_id" in resp.json()["detail"]

    db.expire_all()
    row = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    assert row.entity_type == "vehicle"  # unchanged


def test_update_maintenance_entity_missing_row_404(client, db, admin_headers):
    """PATCHing to an entity that doesn't exist returns 404 and changes nothing."""
    vehicle = _seed_vehicle(db, serial="MAINT-EDIT-V3")
    record_id = _seed_record(client, admin_headers, vehicle.id)

    resp = client.patch(
        f"/api/maintenance/{record_id}",
        headers=admin_headers,
        json={"entity_type": "battery", "entity_id": 999999},
    )

    assert resp.status_code == 404, resp.text

    db.expire_all()
    row = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    assert row.entity_type == "vehicle"
    assert row.entity_id == vehicle.id


def test_update_maintenance_to_other_clears_entity(client, db, admin_headers):
    """Changing entity_type to "other" needs no entity_id and stores the
    sentinel 0."""
    vehicle = _seed_vehicle(db, serial="MAINT-EDIT-V4")
    record_id = _seed_record(client, admin_headers, vehicle.id)

    resp = client.patch(
        f"/api/maintenance/{record_id}",
        headers=admin_headers,
        json={"entity_type": "other"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entity_type"] == "other"
    assert body["entity_id"] == 0
