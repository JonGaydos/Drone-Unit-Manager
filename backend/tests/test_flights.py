"""Flight endpoint tests: create, delete cascade across two DBs, validation, authz.

Covers the real behavior of ``app.routers.flights``, the most intricate module
because flight deletion spans the MAIN db and the SEPARATE telemetry db:

* POST ``/api/flights`` creates a flight (pilot or higher) and persists it.
* POST ``/api/flights/bulk-delete`` (supervisor/admin) purges telemetry from the
  telemetry db and, in the main db, NULLs the FK refs that ``_purge_flight_references``
  nulls (Incident.flight_id, ChecklistCompletion.flight_id, FlightPlan.linked_flight_id)
  and DELETEs the ones it deletes (MediaFile, PhotoFlight), so the delete commits
  with no IntegrityError.
* DELETE ``/api/flights/{id}`` does the same single-flight purge for a referenced
  flight without IntegrityError.
* PATCH ``/api/flights/{id}`` with an invalid ``review_status`` is rejected by the
  schema validator (422).
* POST ``/api/flights/bulk-update`` is supervisor-gated; a pilot gets 403.

Main-db rows are seeded via the ``db`` fixture; telemetry rows via the
``telemetry_db`` fixture (a Session on the separate telemetry engine). The app
commits, so cross-session reads see committed rows after ``expire_all``.
"""

from datetime import date, datetime

from app.models.flight import Flight
from app.models.telemetry import TelemetryPoint
from app.models.incident import Incident
from app.models.checklist import ChecklistTemplate, ChecklistCompletion
from app.models.flight_approval import FlightPlan
from app.models.media import MediaFile
from app.models.photo import Photo, PhotoFlight
from app.models.pilot import Pilot

FLIGHTS_URL = "/api/flights"
BULK_DELETE_URL = "/api/flights/bulk-delete"
BULK_UPDATE_URL = "/api/flights/bulk-update"


def _seed_flight(db, **kwargs):
    flight = Flight(date=date(2025, 6, 1), **kwargs)
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return flight


def _seed_pilot(db):
    pilot = Pilot(first_name="Test", last_name="Pilot", status="active")
    db.add(pilot)
    db.commit()
    db.refresh(pilot)
    return pilot


def _seed_telemetry(telemetry_db, flight_id, n=3):
    for i in range(n):
        telemetry_db.add(TelemetryPoint(flight_id=flight_id, timestamp_ms=i, altitude_m=10.0 + i))
    telemetry_db.commit()


def _telemetry_count(telemetry_db, flight_id):
    telemetry_db.expire_all()
    return telemetry_db.query(TelemetryPoint).filter(TelemetryPoint.flight_id == flight_id).count()


def _seed_references(db, flight_id, *, pilot_id, user_id):
    """Seed one of each FK-referencing row the delete path must clear."""
    incident = Incident(
        date=date(2025, 6, 1), title="I", severity="minor", category="other",
        description="d", flight_id=flight_id,
    )
    template = ChecklistTemplate(name="T", items=[])
    db.add(template)
    db.flush()
    completion = ChecklistCompletion(
        template_id=template.id, pilot_id=pilot_id, responses=[], flight_id=flight_id,
    )
    plan = FlightPlan(
        title="P", date_planned=datetime(2025, 6, 1, 9, 0), pilot_id=pilot_id,
        submitted_by_id=user_id, linked_flight_id=flight_id,
    )
    media = MediaFile(flight_id=flight_id, filename="m.jpg", kind="photo")
    photo = Photo(filename="p.jpg", original_filename="p.jpg")
    db.add_all([incident, completion, plan, media, photo])
    db.flush()
    photo_flight = PhotoFlight(photo_id=photo.id, flight_id=flight_id)
    db.add(photo_flight)
    db.commit()
    return {
        "incident_id": incident.id, "completion_id": completion.id,
        "plan_id": plan.id, "media_id": media.id, "photo_flight_id": photo_flight.id,
    }


# 1. Create -----------------------------------------------------------------

def test_create_flight_persists(client, db, pilot_headers):
    resp = client.post(FLIGHTS_URL, headers=pilot_headers, json={
        "date": "2025-06-01", "purpose": "patrol", "case_number": "C-1",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["purpose"] == "patrol"
    # Created flights default to needs_review / manual source.
    assert body["review_status"] == "needs_review"

    db.expire_all()
    flight = db.query(Flight).filter(Flight.id == body["id"]).first()
    assert flight is not None
    assert flight.case_number == "C-1"
    assert flight.data_source == "manual"


# 2. Bulk-delete purges telemetry + clears FK refs --------------------------

def test_bulk_delete_purges_telemetry_and_clears_fk_refs(client, db, telemetry_db, admin_headers, admin_user):
    pilot = _seed_pilot(db)
    flight = _seed_flight(db, purpose="patrol")
    _seed_telemetry(telemetry_db, flight.id, n=4)
    refs = _seed_references(db, flight.id, pilot_id=pilot.id, user_id=admin_user.id)

    assert _telemetry_count(telemetry_db, flight.id) == 4

    resp = client.post(BULK_DELETE_URL, headers=admin_headers, json={"flight_ids": [flight.id]})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "deleted": 1}

    db.expunge_all()
    # Flight gone.
    assert db.query(Flight).filter(Flight.id == flight.id).first() is None
    # Telemetry purged from the SEPARATE db.
    assert _telemetry_count(telemetry_db, flight.id) == 0
    # NULLed refs survive with flight_id cleared.
    assert db.query(Incident).filter(Incident.id == refs["incident_id"]).one().flight_id is None
    assert db.query(ChecklistCompletion).filter(ChecklistCompletion.id == refs["completion_id"]).one().flight_id is None
    assert db.query(FlightPlan).filter(FlightPlan.id == refs["plan_id"]).one().linked_flight_id is None
    # DELETEd refs are gone.
    assert db.query(MediaFile).filter(MediaFile.id == refs["media_id"]).first() is None
    assert db.query(PhotoFlight).filter(PhotoFlight.id == refs["photo_flight_id"]).first() is None


# 3. Single delete of a referenced flight -----------------------------------

def test_single_delete_referenced_flight(client, db, telemetry_db, admin_headers, admin_user):
    pilot = _seed_pilot(db)
    flight = _seed_flight(db, purpose="patrol")
    _seed_telemetry(telemetry_db, flight.id, n=2)
    refs = _seed_references(db, flight.id, pilot_id=pilot.id, user_id=admin_user.id)

    resp = client.delete(f"{FLIGHTS_URL}/{flight.id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    db.expunge_all()
    assert db.query(Flight).filter(Flight.id == flight.id).first() is None
    assert _telemetry_count(telemetry_db, flight.id) == 0
    assert db.query(Incident).filter(Incident.id == refs["incident_id"]).one().flight_id is None
    assert db.query(MediaFile).filter(MediaFile.id == refs["media_id"]).first() is None


# 4. Invalid review_status -> 422 -------------------------------------------

def test_update_invalid_review_status_422(client, db, admin_headers):
    flight = _seed_flight(db)
    resp = client.patch(f"{FLIGHTS_URL}/{flight.id}", headers=admin_headers,
                        json={"review_status": "bogus"})
    assert resp.status_code == 422, resp.text


def test_bulk_update_invalid_review_status_422(client, db, admin_headers):
    flight = _seed_flight(db)
    resp = client.post(BULK_UPDATE_URL, headers=admin_headers,
                       json={"flight_ids": [flight.id], "review_status": "bogus"})
    assert resp.status_code == 422, resp.text


# 5. Bulk-update authz -------------------------------------------------------

def test_bulk_update_supervisor_gated_pilot_403(client, db, pilot_headers):
    flight = _seed_flight(db, purpose="patrol")
    resp = client.post(BULK_UPDATE_URL, headers=pilot_headers,
                       json={"flight_ids": [flight.id], "purpose": "changed"})
    assert resp.status_code == 403, resp.text

    db.expire_all()
    assert db.query(Flight).filter(Flight.id == flight.id).one().purpose == "patrol"
