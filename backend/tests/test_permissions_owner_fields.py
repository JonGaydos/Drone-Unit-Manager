"""Record responses carry the owner field the frontend needs for its Own checks."""

from app.models.document import Document
from app.models.flight import Flight
from app.models.photo import Photo

PNG_NAME = "a.png"


def test_flight_response_has_created_by(client, pilot_headers, pilot_user, linked_pilot):
    created = client.post("/api/flights", headers=pilot_headers, json={"pilot_id": linked_pilot.id, "date": "2026-03-01"})
    assert created.status_code == 200, created.text
    assert created.json()["created_by_id"] == pilot_user.id
    listed = client.get("/api/flights", headers=pilot_headers).json()["flights"]
    assert listed[0]["created_by_id"] == pilot_user.id


def test_synced_flight_has_no_creator(client, db, pilot_headers):
    db.add(Flight(external_id="ext-1"))
    db.commit()
    listed = client.get("/api/flights", headers=pilot_headers).json()["flights"]
    assert listed[0]["created_by_id"] is None


def test_mission_log_response_has_created_by(client, pilot_headers, pilot_user):
    created = client.post("/api/mission-logs", headers=pilot_headers, json={"date": "2026-03-01", "title": "M"})
    assert created.status_code in (200, 201), created.text
    assert created.json()["created_by_id"] == pilot_user.id
    assert client.get("/api/mission-logs", headers=pilot_headers).json()[0]["created_by_id"] == pilot_user.id


def test_training_log_response_has_created_by(client, pilot_headers, pilot_user):
    body = {"date": "2026-03-01", "title": "T", "training_type": "recurrent"}
    created = client.post("/api/training-logs", headers=pilot_headers, json=body)
    assert created.status_code in (200, 201), created.text
    assert created.json()["created_by_id"] == pilot_user.id


def test_maintenance_response_has_created_by(client, pilot_headers, pilot_user):
    body = {"entity_type": "organization", "entity_id": 0, "maintenance_type": "scheduled", "description": "Check"}
    created = client.post("/api/maintenance", headers=pilot_headers, json=body)
    assert created.status_code in (200, 201), created.text
    assert created.json()["created_by_id"] == pilot_user.id
    assert client.get("/api/maintenance", headers=pilot_headers).json()[0]["created_by_id"] == pilot_user.id


def test_document_response_has_uploaded_by(client, db, pilot_headers, pilot_user):
    db.add(Document(entity_type="general", document_type="other", title="D", filename="d.pdf",
                    file_path="/nonexistent/d.pdf", mime_type="application/pdf", file_size_bytes=1,
                    uploaded_by_id=pilot_user.id))
    db.commit()
    rows = client.get("/api/documents", headers=pilot_headers).json()
    assert rows[0]["uploaded_by_id"] == pilot_user.id


def test_photo_response_has_uploaded_by(client, db, pilot_headers, pilot_user):
    db.add(Photo(filename=PNG_NAME, original_filename=PNG_NAME, mime_type="image/png", uploaded_by_id=pilot_user.id))
    db.commit()
    rows = client.get("/api/photos", headers=pilot_headers).json()
    assert rows[0]["uploaded_by_id"] == pilot_user.id
