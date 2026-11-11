"""Regression tests for the Area 10 staging-test fixes: field clearing and
error mapping (backlog A-F31, B-23, C-F21, B-5, C-F3, D-4)."""

from datetime import date

from app.models import Battery, Dock, Vehicle


# --- A-F31: fleet edits clear a field sent as null ---------------------------

def test_vehicle_patch_null_clears_optional_fields(client, db, admin_headers):
    v = Vehicle(serial_number="AREA10-V1", manufacturer="Acme", model="Quad", nickname="Kite",
                notes="Old note", acquired_date=date(2025, 1, 2))
    db.add(v)
    db.commit()

    resp = client.patch(f"/api/vehicles/{v.id}", headers=admin_headers,
                        json={"nickname": None, "notes": None, "acquired_date": None})

    assert resp.status_code == 200, resp.text
    db.expire_all()
    stored = db.get(Vehicle, v.id)
    assert (stored.nickname, stored.notes, stored.acquired_date) == (None, None, None)


def test_battery_patch_null_clears_health_and_dates(client, db, admin_headers):
    b = Battery(serial_number="AREA10-B1", health_pct=88, acquired_date=date(2025, 1, 2),
                decommissioned_date=date(2026, 1, 2))
    db.add(b)
    db.commit()

    resp = client.patch(f"/api/batteries/{b.id}", headers=admin_headers,
                        json={"health_pct": None, "acquired_date": None, "decommissioned_date": None})

    assert resp.status_code == 200, resp.text
    db.expire_all()
    stored = db.get(Battery, b.id)
    assert (stored.health_pct, stored.acquired_date, stored.decommissioned_date) == (None, None, None)


def test_dock_patch_null_clears_coordinates(client, db, admin_headers):
    d = Dock(serial_number="AREA10-D1", lat=30.1, lon=-85.1)
    db.add(d)
    db.commit()

    resp = client.patch(f"/api/docks/{d.id}", headers=admin_headers, json={"lat": None, "lon": None})

    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert (db.get(Dock, d.id).lat, db.get(Dock, d.id).lon) == (None, None)


# --- B-23: mission and training edits clear a field sent as null -------------

def test_mission_patch_null_clears_optional_fields(client, db, admin_headers):
    v = Vehicle(serial_number="AREA10-V2", manufacturer="Acme", model="Quad")
    db.add(v)
    db.commit()
    created = client.post("/api/mission-logs", headers=admin_headers, json={
        "date": "2026-03-01", "title": "Area 10 mission", "man_hours": 1, "notes": "Old note",
        "location": "Field", "vehicle_id": v.id, "pilots": []})
    assert created.status_code in (200, 201), created.text

    resp = client.patch(f"/api/mission-logs/{created.json()['id']}", headers=admin_headers,
                        json={"notes": None, "location": None, "vehicle_id": None})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["notes"], body["location"], body["vehicle_id"]) == (None, None, None)


def test_training_patch_null_clears_optional_fields(client, admin_headers):
    created = client.post("/api/training-logs", headers=admin_headers, json={
        "date": "2026-03-01", "title": "Area 10 training", "training_type": "Recurrent",
        "man_hours": 1, "notes": "Old note", "instructor": "Coach", "pilots": []})
    assert created.status_code in (200, 201), created.text

    resp = client.patch(f"/api/training-logs/{created.json()['id']}", headers=admin_headers,
                        json={"notes": None, "instructor": None})

    assert resp.status_code == 200, resp.text
    assert (resp.json()["notes"], resp.json()["instructor"]) == (None, None)


# --- C-F21: certification edits clear a field sent as null -------------------

def _cert(db, **fields):
    from app.models import CertificationType, Pilot, PilotCertification
    pilot = Pilot(first_name="Robin", last_name="Area10")
    ct = CertificationType(name="Area 10 Cert", category="training")
    db.add_all([pilot, ct])
    db.flush()
    pc = PilotCertification(pilot_id=pilot.id, certification_type_id=ct.id, status="active", **fields)
    db.add(pc)
    db.commit()
    return pc


def test_certification_patch_null_clears_dates_and_number(client, db, admin_headers):
    pc = _cert(db, issue_date=date(2024, 1, 1), expiration_date=date(2026, 10, 1), certificate_number="CN-1")

    resp = client.patch(f"/api/pilot-certifications/{pc.id}", headers=admin_headers,
                        json={"expiration_date": None, "certificate_number": None})

    assert resp.status_code == 200, resp.text
    assert (resp.json()["expiration_date"], resp.json()["certificate_number"]) == (None, None)
    assert resp.json()["issue_date"] == "2024-01-01"


# --- B-5, C-F3, D-4: integrity errors name the field -------------------------

CONFLICT = "conflicts with other records"


def _flight_id(client, admin_headers):
    resp = client.post("/api/flights", headers=admin_headers, json={"date": "2026-03-01", "duration_seconds": 60})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _assert_names(resp, *words):
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and CONFLICT not in detail
    for word in words:
        assert word in detail


def test_flight_create_with_unknown_pilot_is_422_naming_it(client, admin_headers):
    resp = client.post("/api/flights", headers=admin_headers,
                       json={"pilot_id": 999999, "date": "2026-03-01", "duration_seconds": 60})
    _assert_names(resp, "pilot_id", "999999")


def test_flight_create_with_unknown_vehicle_is_422_naming_it(client, admin_headers):
    resp = client.post("/api/flights", headers=admin_headers,
                       json={"vehicle_id": 888888, "date": "2026-03-01", "duration_seconds": 60})
    _assert_names(resp, "vehicle_id", "888888")


def test_flight_patch_and_bulk_with_unknown_pilot_are_422(client, admin_headers):
    fid = _flight_id(client, admin_headers)
    _assert_names(client.patch(f"/api/flights/{fid}", headers=admin_headers, json={"pilot_id": 999999}),
                  "pilot_id")
    _assert_names(client.post("/api/flights/bulk-update", headers=admin_headers,
                              json={"flight_ids": [fid], "pilot_id": 999999}), "pilot_id")


def test_flight_patch_null_required_field_is_422_naming_it(client, admin_headers):
    fid = _flight_id(client, admin_headers)
    _assert_names(client.patch(f"/api/flights/{fid}", headers=admin_headers, json={"review_status": None}),
                  "review_status")
    _assert_names(client.patch(f"/api/flights/{fid}", headers=admin_headers, json={"pilot_confirmed": None}),
                  "pilot_confirmed")


def test_certification_assign_with_unknown_pilot_is_422(client, db, admin_headers):
    from app.models import CertificationType
    ct = CertificationType(name="Area 10 FK", category="training")
    db.add(ct)
    db.commit()
    resp = client.post("/api/pilot-certifications", headers=admin_headers,
                       json={"pilot_id": 999999, "certification_type_id": ct.id})
    _assert_names(resp, "pilot_id", "999999")


def test_certification_assign_with_unknown_type_is_422(client, db, admin_headers):
    from app.models import Pilot
    pilot = Pilot(first_name="Robin", last_name="Area10")
    db.add(pilot)
    db.commit()
    resp = client.post("/api/pilot-certifications", headers=admin_headers,
                       json={"pilot_id": pilot.id, "certification_type_id": 777777})
    _assert_names(resp, "certification_type_id")


def test_incident_with_unknown_pilot_is_422(client, admin_headers):
    resp = client.post("/api/incidents", headers=admin_headers, json={
        "date": "2026-03-01", "title": "Area 10", "description": "Made-up report",
        "severity": "minor", "category": "other", "pilot_id": 99999})
    _assert_names(resp, "pilot_id", "99999")


def test_uniqueness_and_delete_conflicts_stay_409():
    import asyncio
    from sqlalchemy.exc import IntegrityError
    from app.main import integrity_conflict

    class _Req:
        method, url = "POST", type("U", (), {"path": "/api/x"})()

    for message, statement, params in [
        ("UNIQUE constraint failed: vehicles.serial_number",
         "INSERT INTO vehicles (serial_number) VALUES (?)", ("SN-1",)),
        ("FOREIGN KEY constraint failed", "DELETE FROM pilots WHERE pilots.id = ?", (5,)),
    ]:
        resp = asyncio.run(integrity_conflict(_Req(), IntegrityError(statement, params, Exception(message))))
        assert resp.status_code == 409
        assert CONFLICT in resp.body.decode()


def test_clearing_a_required_fleet_column_is_422_naming_it(client, db, admin_headers):
    b = Battery(serial_number="AREA10-B2", cycle_count=33)
    db.add(b)
    db.commit()
    _assert_names(client.patch(f"/api/batteries/{b.id}", headers=admin_headers, json={"cycle_count": None}),
                  "cycle_count")
