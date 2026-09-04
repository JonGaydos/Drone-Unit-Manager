"""FAA-registration scoping tests for GET /api/dashboard/compliance.

Expired registrations must only count vehicles in the ACTIVE fleet: keeping
historical (now-expired) registrations on retired vehicles must not appear as
a compliance problem or drag down the compliance score.
"""

from datetime import date, timedelta

from app.models.vehicle import Vehicle
from app.models.vehicle_registration import VehicleRegistration


def _seed_vehicle(db, *, serial, status):
    v = Vehicle(serial_number=serial, manufacturer="Skydio", model="X2E", status=status)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _seed_expired_registration(db, vehicle_id):
    reg = VehicleRegistration(
        vehicle_id=vehicle_id,
        registration_number=f"FA-{vehicle_id}",
        expiry_date=date.today() - timedelta(days=30),
        is_current=True,
    )
    db.add(reg)
    db.commit()


def test_expired_registrations_exclude_retired_vehicles(client, db, admin_headers):
    """An expired registration on a retired vehicle is ignored; one on an
    active vehicle still counts."""
    active = _seed_vehicle(db, serial="COMP-ACTIVE", status="active")
    retired = _seed_vehicle(db, serial="COMP-RETIRED", status="retired")
    _seed_expired_registration(db, active.id)
    _seed_expired_registration(db, retired.id)

    resp = client.get("/api/dashboard/compliance", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_vehicles"] == 1  # active fleet only
    assert body["expired_registrations"] == 1  # retired vehicle's expired reg ignored


def test_expired_registration_only_on_retired_vehicle_is_clean(client, db, admin_headers):
    """A fleet whose only expired registrations sit on retired vehicles shows
    zero expired registrations and no score deduction for registrations."""
    _seed_vehicle(db, serial="COMP-ACTIVE-2", status="active")
    retired = _seed_vehicle(db, serial="COMP-RETIRED-2", status="retired")
    _seed_expired_registration(db, retired.id)

    resp = client.get("/api/dashboard/compliance", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["expired_registrations"] == 0
    assert body["compliance_score"] == 100
