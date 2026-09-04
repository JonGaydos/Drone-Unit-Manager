"""entity_type validation tests for the maintenance-schedule endpoints.

Locks in ``app.routers.maintenance_schedules._validate_entity`` as called from
``POST /api/maintenance/schedules`` (create) and ``PATCH
/api/maintenance/schedules/{id}`` (update), both pilot-or-higher gated. The
validator must:

* reject an unknown ``entity_type`` with 400 (and list the allowed types);
* reject a table-backed type whose ``entity_id`` row does not exist with 404;
* create/update the schedule when the type is allowed and the entity exists;
* re-validate on update when entity_type/entity_id are supplied.

Allowed types (``ENTITY_MODELS``): vehicle, battery, controller, dock, sensor,
attachment (all table-backed), plus "organization" which has NO table — its
existence check is skipped and ``entity_id`` may be null, so the 404 case does
not apply to it.

Main-db rows are seeded via the ``db`` fixture; the app commits, so cross-session
reads see committed rows after ``expire_all``.
"""

from app.models.maintenance_schedule import MaintenanceSchedule
from app.models.vehicle import Vehicle


def _seed_vehicle(db, *, serial):
    v = Vehicle(serial_number=serial, manufacturer="Skydio", model="X10", status="active")
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def test_create_schedule_bad_entity_type_400(client, db, admin_headers):
    """An unknown entity_type returns 400, names the bad type, lists the
    allowed types, and creates no row."""
    resp = client.post(
        "/api/maintenance/schedules",
        headers=admin_headers,
        json={
            "name": "Prop check",
            "entity_type": "bogus",
            "entity_id": 1,
            "frequency": "monthly",
        },
    )

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "entity_type" in detail
    assert "bogus" in detail
    assert "vehicle" in detail  # the allowed-types list is included
    assert "organization" in detail  # no-table type still appears as allowed

    db.expire_all()
    assert db.query(MaintenanceSchedule).count() == 0


def test_create_schedule_missing_entity_id_404(client, db, admin_headers):
    """A table-backed type with a nonexistent entity_id returns 404 and creates
    no row."""
    resp = client.post(
        "/api/maintenance/schedules",
        headers=admin_headers,
        json={
            "name": "Prop check",
            "entity_type": "vehicle",
            "entity_id": 999999,
            "frequency": "monthly",
        },
    )

    assert resp.status_code == 404, resp.text

    db.expire_all()
    assert db.query(MaintenanceSchedule).count() == 0


def test_create_schedule_valid_entity_succeeds(client, db, admin_headers):
    """A table-backed type pointing at an existing entity creates the schedule."""
    vehicle = _seed_vehicle(db, serial="SCHED-V1")
    vehicle_id = vehicle.id

    resp = client.post(
        "/api/maintenance/schedules",
        headers=admin_headers,
        json={
            "name": "Prop check",
            "entity_type": "vehicle",
            "entity_id": vehicle_id,
            "frequency": "monthly",
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    schedule_id = body["id"]

    db.expire_all()
    row = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    assert row is not None
    assert row.entity_type == "vehicle"
    assert row.entity_id == vehicle_id


def test_create_schedule_organization_no_existence_check(client, db, admin_headers):
    """The no-table "organization" type is allowed with a null entity_id and is
    NOT existence-checked, so it creates a schedule (no 404)."""
    resp = client.post(
        "/api/maintenance/schedules",
        headers=admin_headers,
        json={
            "name": "Org-wide audit",
            "entity_type": "organization",
            "entity_id": None,
            "frequency": "yearly",
        },
    )

    assert resp.status_code == 200, resp.text
    schedule_id = resp.json()["id"]

    db.expire_all()
    row = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    assert row is not None
    assert row.entity_type == "organization"
    assert row.entity_id is None


def test_update_schedule_bad_entity_type_400(client, db, admin_headers):
    """Updating an existing schedule with an unknown entity_type returns 400 and
    leaves the stored entity_type unchanged."""
    vehicle = _seed_vehicle(db, serial="SCHED-V2")
    create = client.post(
        "/api/maintenance/schedules",
        headers=admin_headers,
        json={
            "name": "Prop check",
            "entity_type": "vehicle",
            "entity_id": vehicle.id,
            "frequency": "monthly",
        },
    )
    assert create.status_code == 200, create.text
    schedule_id = create.json()["id"]

    resp = client.patch(
        f"/api/maintenance/schedules/{schedule_id}",
        headers=admin_headers,
        json={"entity_type": "bogus"},
    )

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "entity_type" in detail
    assert "bogus" in detail

    db.expire_all()
    row = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    assert row.entity_type == "vehicle"  # unchanged


def test_create_schedule_other_entity_type_allowed(client, db, admin_headers):
    """entity_type "other" has no table: no existence check, entity_id stays null."""
    resp = client.post(
        "/api/maintenance/schedules",
        headers=admin_headers,
        json={
            "name": "FAA Authorization renewal",
            "entity_type": "other",
            "frequency": "yearly",
        },
    )

    assert resp.status_code == 200, resp.text
    schedule_id = resp.json()["id"]

    db.expire_all()
    row = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    assert row.entity_type == "other"
    assert row.entity_id is None


def test_create_one_time_schedule_requires_next_due(client, db, admin_headers):
    """frequency "one_time" without a due date returns 400 and creates no row."""
    resp = client.post(
        "/api/maintenance/schedules",
        headers=admin_headers,
        json={
            "name": "FAA Authorization renewal",
            "entity_type": "other",
            "frequency": "one_time",
        },
    )

    assert resp.status_code == 400, resp.text
    assert "next_due" in resp.json()["detail"]

    db.expire_all()
    assert db.query(MaintenanceSchedule).count() == 0


def test_create_one_time_schedule_stores_due_date_verbatim(client, db, admin_headers):
    """A one-time task stores the user-supplied due date, not a computed one."""
    resp = client.post(
        "/api/maintenance/schedules",
        headers=admin_headers,
        json={
            "name": "FAA Authorization renewal",
            "entity_type": "other",
            "frequency": "one_time",
            "next_due": "2026-09-15",
        },
    )

    assert resp.status_code == 200, resp.text
    schedule_id = resp.json()["id"]

    db.expire_all()
    row = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    assert row.next_due.isoformat() == "2026-09-15"
    assert row.is_active is True


def test_create_recurring_schedule_next_due_override(client, db, admin_headers):
    """An explicit next_due on a recurring schedule overrides auto-calculation."""
    resp = client.post(
        "/api/maintenance/schedules",
        headers=admin_headers,
        json={
            "name": "Quarterly audit",
            "entity_type": "organization",
            "frequency": "quarterly",
            "next_due": "2027-01-01",
        },
    )

    assert resp.status_code == 200, resp.text
    schedule_id = resp.json()["id"]

    db.expire_all()
    row = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    assert row.next_due.isoformat() == "2027-01-01"


def test_complete_one_time_schedule_deactivates(client, db, admin_headers):
    """Completing a one-time task deactivates it (no reschedule) and logs a
    maintenance record with no next_due_date."""
    from app.models.maintenance import MaintenanceRecord

    create = client.post(
        "/api/maintenance/schedules",
        headers=admin_headers,
        json={
            "name": "FAA Authorization renewal",
            "entity_type": "other",
            "frequency": "one_time",
            "next_due": "2026-09-15",
        },
    )
    assert create.status_code == 200, create.text
    schedule_id = create.json()["id"]

    resp = client.post(f"/api/maintenance/schedules/{schedule_id}/complete", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_active"] is False
    # next_due is preserved for history, not recomputed
    assert body["next_due"] == "2026-09-15"

    db.expire_all()
    row = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    assert row.is_active is False
    assert row.last_completed is not None
    assert row.next_due.isoformat() == "2026-09-15"

    record = db.query(MaintenanceRecord).filter(MaintenanceRecord.description == "FAA Authorization renewal").first()
    assert record is not None
    assert record.entity_type == "other"
    assert record.entity_id == 0
    assert record.next_due_date is None


def test_complete_recurring_schedule_still_reschedules(client, db, admin_headers):
    """Completing a recurring schedule keeps it active and advances next_due."""
    create = client.post(
        "/api/maintenance/schedules",
        headers=admin_headers,
        json={
            "name": "Monthly inspection",
            "entity_type": "organization",
            "frequency": "monthly",
        },
    )
    assert create.status_code == 200, create.text
    schedule_id = create.json()["id"]

    resp = client.post(f"/api/maintenance/schedules/{schedule_id}/complete", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_active"] is True
    assert body["next_due"] is not None

    db.expire_all()
    row = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    assert row.is_active is True


def test_update_one_time_schedule_cannot_clear_next_due(client, db, admin_headers):
    """PATCHing next_due to null on a one-time task returns 400."""
    create = client.post(
        "/api/maintenance/schedules",
        headers=admin_headers,
        json={
            "name": "FAA Authorization renewal",
            "entity_type": "other",
            "frequency": "one_time",
            "next_due": "2026-09-15",
        },
    )
    assert create.status_code == 200, create.text
    schedule_id = create.json()["id"]

    resp = client.patch(
        f"/api/maintenance/schedules/{schedule_id}",
        headers=admin_headers,
        json={"next_due": None},
    )

    assert resp.status_code == 400, resp.text

    db.expire_all()
    row = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
    assert row.next_due.isoformat() == "2026-09-15"  # unchanged


def test_create_multi_year_schedule_auto_calcs_next_due(client, db, admin_headers):
    """two_years / three_years frequencies auto-calculate next_due from today
    (not the unknown-frequency 30-day fallback)."""
    from datetime import date, timedelta

    for frequency, days in (("two_years", 730), ("three_years", 1095)):
        resp = client.post(
            "/api/maintenance/schedules",
            headers=admin_headers,
            json={
                "name": f"Airframe overhaul ({frequency})",
                "entity_type": "organization",
                "frequency": frequency,
            },
        )
        assert resp.status_code == 200, resp.text
        schedule_id = resp.json()["id"]

        db.expire_all()
        row = db.query(MaintenanceSchedule).filter(MaintenanceSchedule.id == schedule_id).first()
        assert row.next_due == date.today() + timedelta(days=days)
