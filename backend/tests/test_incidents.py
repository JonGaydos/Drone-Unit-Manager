"""Incident endpoint tests: grounding side effect, edit transition guard, authz.

Covers the real behavior of ``app.routers.incidents``, specifically the
auto-grounding side effect in ``_ground_vehicle_if_needed``:

* POST ``/api/incidents`` with ``equipment_grounded=True`` for an ``active``
  vehicle moves that vehicle to ``maintenance`` (the exact status the code sets).
* PATCH ``/api/incidents/{id}`` on an already-grounding incident does NOT
  re-ground a vehicle a human has manually returned to ``active``. The guard is
  ``was_grounded`` (captured before the update); when the flag was already set,
  the false->true transition never fires, so editing other fields is inert on
  the vehicle.
* Create/edit are pilot-gated (``require_pilot``); a viewer gets 403.

Vehicles are seeded via the ``db`` fixture and re-read after ``expire_all`` since
the app commits on a separate session.
"""

from datetime import date

from app.models.incident import Incident
from app.models.vehicle import Vehicle
from app.routers.auth import create_token
from tests.conftest import _seed_user

INCIDENTS_URL = "/api/incidents"


def _seed_vehicle(db, status="active"):
    vehicle = Vehicle(
        serial_number=f"SN-{status}-{id(object())}",
        manufacturer="Skydio",
        model="X10",
        status=status,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


def _incident_payload(vehicle_id, **overrides):
    payload = {
        "date": "2025-06-01",
        "title": "Hard landing",
        "severity": "major",
        "category": "crash",
        "description": "Airframe damaged on landing",
        "vehicle_id": vehicle_id,
        "equipment_grounded": True,
    }
    payload.update(overrides)
    return payload


# 1. Grounding incident grounds an active vehicle ---------------------------

def test_grounding_incident_sets_vehicle_to_maintenance(client, db, pilot_headers):
    vehicle = _seed_vehicle(db, status="active")

    resp = client.post(INCIDENTS_URL, headers=pilot_headers,
                       json=_incident_payload(vehicle.id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["equipment_grounded"] is True

    db.expire_all()
    assert db.query(Vehicle).filter(Vehicle.id == vehicle.id).one().status == "maintenance"


def test_grounding_incident_leaves_retired_vehicle_alone(client, db, pilot_headers):
    """Only active vehicles are auto-grounded; a retired airframe is untouched."""
    vehicle = _seed_vehicle(db, status="retired")

    resp = client.post(INCIDENTS_URL, headers=pilot_headers,
                       json=_incident_payload(vehicle.id))
    assert resp.status_code == 200, resp.text

    db.expire_all()
    assert db.query(Vehicle).filter(Vehicle.id == vehicle.id).one().status == "retired"


# 2. Edit transition guard --------------------------------------------------

def test_edit_does_not_reground_manually_returned_vehicle(client, db, pilot_headers):
    """A grounding incident grounds the vehicle once. After a human returns the
    vehicle to service, a normal edit of that incident must NOT re-ground it."""
    vehicle = _seed_vehicle(db, status="active")

    create = client.post(INCIDENTS_URL, headers=pilot_headers,
                        json=_incident_payload(vehicle.id))
    assert create.status_code == 200, create.text
    incident_id = create.json()["id"]

    # Vehicle was auto-grounded on create.
    db.expire_all()
    assert db.query(Vehicle).filter(Vehicle.id == vehicle.id).one().status == "maintenance"

    # Human returns the vehicle to service directly.
    v = db.query(Vehicle).filter(Vehicle.id == vehicle.id).one()
    v.status = "active"
    db.commit()

    # Normal edit of the (still grounding) incident: change the description only.
    edit = client.patch(f"{INCIDENTS_URL}/{incident_id}", headers=pilot_headers,
                       json={"description": "Revised after teardown inspection"})
    assert edit.status_code == 200, edit.text
    assert edit.json()["equipment_grounded"] is True

    # Guard holds: the vehicle stays active, not re-grounded.
    db.expire_all()
    assert db.query(Vehicle).filter(Vehicle.id == vehicle.id).one().status == "active"


def test_edit_flipping_flag_to_grounded_grounds_active_vehicle(client, db, pilot_headers):
    """Conversely, a false->true transition on edit DOES ground an active
    vehicle (confirms the guard keys on the prior flag, not on edit-vs-create)."""
    vehicle = _seed_vehicle(db, status="active")

    create = client.post(INCIDENTS_URL, headers=pilot_headers,
                        json=_incident_payload(vehicle.id, equipment_grounded=False))
    assert create.status_code == 200, create.text
    incident_id = create.json()["id"]

    db.expire_all()
    assert db.query(Vehicle).filter(Vehicle.id == vehicle.id).one().status == "active"

    edit = client.patch(f"{INCIDENTS_URL}/{incident_id}", headers=pilot_headers,
                       json={"equipment_grounded": True})
    assert edit.status_code == 200, edit.text

    db.expire_all()
    assert db.query(Vehicle).filter(Vehicle.id == vehicle.id).one().status == "maintenance"


# 3. Role gating ------------------------------------------------------------

def test_create_requires_pilot_viewer_403(client, db):
    viewer = _seed_user(db, username="viewer", role="viewer", password="ViewerPassw0rd!")
    headers = {"Authorization": f"Bearer {create_token(viewer.id)}"}
    vehicle = _seed_vehicle(db, status="active")

    resp = client.post(INCIDENTS_URL, headers=headers, json=_incident_payload(vehicle.id))
    assert resp.status_code == 403, resp.text

    # Side effect did not fire.
    db.expire_all()
    assert db.query(Vehicle).filter(Vehicle.id == vehicle.id).one().status == "active"
    assert db.query(Incident).count() == 0


def test_edit_requires_pilot_viewer_403(client, db, pilot_user):
    viewer = _seed_user(db, username="viewer", role="viewer", password="ViewerPassw0rd!")
    headers = {"Authorization": f"Bearer {create_token(viewer.id)}"}
    incident = Incident(
        date=date(2025, 6, 1), title="I", severity="minor", category="other",
        description="d", reported_by_id=pilot_user.id,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    resp = client.patch(f"{INCIDENTS_URL}/{incident.id}", headers=headers,
                       json={"description": "changed"})
    assert resp.status_code == 403, resp.text
