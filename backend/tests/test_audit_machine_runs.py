"""Query-level writes are on the record, and automated work writes one summary."""

import ast
import io
import json
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event

from app.models import (
    Alert, Attachment, AuditLog, Battery, BatteryReading, ChecklistCompletion, ChecklistTemplate,
    Document, EquipmentCheckout, Flight, FlightPlan, FlightPurpose, Folder, Incident,
    MaintenanceSchedule, MediaFile, MissionLog, MissionLogPilot, NotificationPreference, Photo,
    Pilot, SensorPackage, Setting, TrainingLog, TrainingLogPilot, User, Vehicle,
    VehicleRegistration,
)
from app.models.photo import PhotoFlight, PhotoIncident, PhotoPilot
from app.routers import mission_logs, training_logs
from app.routers.sync import _run_sync
from app.services import backup_jobs, battery_dedupe, scheduler, sync_manager
from app.services.audit_capture import machine_run, record_bulk, set_actor
from app.services.sync_manager import SyncManager
from tests.test_brinc_import import _csv as brinc_csv
from tests.test_brinc_import import _row as brinc_row
from tests.test_data_integrity_batch5 import FakeProvider

APP_ROOT = Path(__file__).resolve().parent.parent / "app"
ROWS = 200

# Reasons a query-level write may stay one.
RESTORE = "Backup restore replaces whole tables, and the restore route logs one entry for it."
TELEMETRY = "Telemetry is a separate database and is never recorded in the audit log."
RECORDED = "Goes through record_bulk with the record IDs and values."

ALLOWED_WRITES = {
    ("routers/backup.py", "_restore_main_tables"): RESTORE,
    ("routers/backup.py", "_restore_telemetry"): TELEMETRY,
    ("routers/flights.py", "_refresh_telemetry"): TELEMETRY,
    ("services/flight_delete.py", "purge_flight_telemetry"): TELEMETRY,
    ("services/sync_manager.py", "_store_telemetry_points"): TELEMETRY,
    ("services/audit_capture.py", "update_recorded"): RECORDED,
    ("services/audit_capture.py", "delete_recorded"): RECORDED,
}
_WRITE_METHODS = {"update", "delete"}
_TABLE_WRITE_METHODS = {"insert", "update", "delete"}
_SESSION_BULK_METHODS = {"bulk_insert_mappings", "bulk_update_mappings", "bulk_save_objects"}
_SQL_WRITE_VERBS = ("INSERT", "UPDATE", "DELETE", "REPLACE")


def _reads_a_query(node, query_names) -> bool:
    """Whether an expression is a chain that starts from ``.query(...)``."""
    while isinstance(node, (ast.Call, ast.Attribute)):
        if isinstance(node, ast.Attribute) and node.attr == "query":
            return True
        node = node.func if isinstance(node, ast.Call) else node.value
    return isinstance(node, ast.Name) and node.id in query_names


def _is_sqlalchemy_write(call, core_names) -> bool:
    return isinstance(call.func, ast.Name) and call.func.id in core_names


def _is_text_write(call) -> bool:
    if not (isinstance(call.func, ast.Name) and call.func.id == "text" and call.args):
        return False
    sql = call.args[0]
    return (isinstance(sql, ast.Constant) and isinstance(sql.value, str)
            and sql.value.lstrip().upper().startswith(_SQL_WRITE_VERBS))


def _is_write(call, query_names, core_names) -> bool:
    if _is_sqlalchemy_write(call, core_names) or _is_text_write(call):
        return True
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr in _SESSION_BULK_METHODS:
        return True
    if func.attr in _TABLE_WRITE_METHODS and isinstance(func.value, ast.Attribute) and func.value.attr == "__table__":
        return True
    return func.attr in _WRITE_METHODS and _reads_a_query(func.value, query_names)


def _core_write_names(tree) -> set[str]:
    """Local names for sqlalchemy's ``insert``, ``update`` and ``delete``."""
    return {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy")
        for alias in node.names
        if alias.name in _TABLE_WRITE_METHODS
    }


def _direct_nodes(function):
    """Nodes inside a function, leaving out functions nested in it."""
    stack = list(ast.iter_child_nodes(function))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            stack.extend(ast.iter_child_nodes(node))


def _query_variables(function) -> set[str]:
    assigned = {
        target.id
        for node in _direct_nodes(function)
        if isinstance(node, ast.Assign) and _reads_a_query(node.value, set())
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    parameters = {arg.arg for arg in function.args.args if arg.arg == "query"}
    return assigned | parameters


def _functions(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _writes_in(source: str) -> set[str]:
    """Names of the functions in ``source`` holding a query-level write."""
    tree = ast.parse(source)
    core_names = _core_write_names(tree)
    return {
        function.name
        for function in _functions(tree)
        if any(isinstance(node, ast.Call) and _is_write(node, _query_variables(function), core_names)
               for node in _direct_nodes(function))
    }


def _app_writes() -> set[tuple[str, str]]:
    return {
        (path.relative_to(APP_ROOT).as_posix(), name)
        for path in APP_ROOT.rglob("*.py")
        for name in _writes_in(path.read_text(encoding="utf-8"))
    }


@pytest.mark.parametrize("source", [
    "def f(db):\n    db.query(A).filter(A.x == 1).update({'x': 2})\n",
    "def f(db):\n    db.query(A).delete()\n",
    "def f(db):\n    rows = db.query(A).filter(A.x == 1)\n    rows.update({'x': 2})\n",
    "def f(query):\n    query.delete()\n",
    "def f(db):\n    db.execute(A.__table__.insert(), [])\n",
    "def f(db):\n    db.execute(A.__table__.delete())\n",
    "from sqlalchemy import update\ndef f(db):\n    db.execute(update(A).values(x=1))\n",
    "from sqlalchemy import text\ndef f(db):\n    db.execute(text('DELETE FROM a'))\n",
    "def f(db):\n    db.bulk_save_objects([])\n",
])
def test_the_scan_finds_each_shape_of_write(source):
    assert _writes_in(source) == {"f"}


@pytest.mark.parametrize("source", [
    "def f(values):\n    values.update({'x': 2})\n",
    "def f(db, row):\n    db.delete(row)\n",
    "def f(db):\n    db.query(A).filter(A.x == 1).first()\n",
    "from sqlalchemy import text\ndef f(db):\n    db.execute(text('SELECT 1'))\n",
])
def test_the_scan_leaves_other_calls_alone(source):
    assert _writes_in(source) == set()


def test_no_unrecorded_bulk_writes():
    assert _app_writes() - set(ALLOWED_WRITES) == set()


def test_the_allowlist_names_only_writes_that_exist():
    assert set(ALLOWED_WRITES) - _app_writes() == set()


def test_helpers_on_the_allowlist_call_record_bulk():
    for (relative, name), reason in ALLOWED_WRITES.items():
        if reason != RECORDED:
            continue
        tree = ast.parse((APP_ROOT / relative).read_text(encoding="utf-8"))
        function = next(f for f in _functions(tree) if f.name == name)
        assert any(isinstance(node, ast.Call) and getattr(node.func, "id", None) == "record_bulk"
                   for node in _direct_nodes(function)), name


# Helpers --------------------------------------------------------------------------

@pytest.fixture
def session(_engines):
    SessionLocal, _ = _engines
    captured = SessionLocal()
    yield captured
    captured.close()


def _entries(db, **filters):
    db.expire_all()
    return db.query(AuditLog).filter_by(**filters).order_by(AuditLog.id).all()


def _clear_audit(db):
    db.query(AuditLog).delete()
    db.commit()


def _seed(db, *rows):
    db.add_all(rows)
    db.commit()
    return rows


def _skydio_settings(db):
    _seed(db, Setting(key="skydio_api_token", value="t"), Setting(key="skydio_token_id", value="id"))


def _provider_flights(count=ROWS):
    return [{"external_id": f"EXT{i}", "date": "2026-01-01", "duration_seconds": 60, "max_altitude_m": 10.0}
            for i in range(count)]


def _use_provider(monkeypatch, **overrides):
    overrides.setdefault("get_flight_detail", lambda creds, flight_id: {})
    monkeypatch.setattr(sync_manager, "get_provider", lambda name: FakeProvider(**overrides))


def _document(**kwargs):
    return Document(entity_type="general", document_type="other", title="D", filename="d.pdf",
                    file_path="d.pdf", mime_type="application/pdf", file_size_bytes=1, **kwargs)


def _only_summary(db, action):
    entries = _entries(db)
    assert [e.action for e in entries] == [action]
    return entries[0]


# record_bulk ----------------------------------------------------------------------

def test_record_bulk_writes_ids_and_values(session, db, admin_user):
    set_actor(session, admin_user)

    record_bulk(session, "update", "flight", [3, 1, 2], {"purpose": {"old": "A", "new": None}})
    session.commit()

    entry = _entries(db)[0]
    assert (entry.action, entry.entity_type, entry.user_username) == ("update", "flight", admin_user.username)
    assert entry.changes["records"]["ids"] == [1, 2, 3]
    assert entry.changes["records"]["total_ids"] == 3
    assert entry.changes["purpose"] == {"old": "A", "new": None}


def test_record_bulk_keeps_every_id_outside_a_run(session, db):
    record_bulk(session, "update", "flight", list(range(1, 702)), None)
    session.commit()

    assert len(_entries(db)[0].changes["records"]["ids"]) == 701


def test_record_bulk_with_no_ids_writes_nothing(session, db):
    record_bulk(session, "update", "flight", [], None)
    session.commit()

    assert _entries(db) == []


def test_record_bulk_rolls_back_with_its_change(session, db):
    record_bulk(session, "update", "flight", [1], None)
    session.rollback()

    assert _entries(db) == []


def test_record_bulk_counts_toward_a_run_under_the_model_name(session, db):
    with machine_run(session, "sync", "flight"):
        record_bulk(session, "update", "flight", [1, 2], {"purpose": {"old": "A", "new": None}})
        record_bulk(session, "delete", "photo_flight", [9], None)
    session.commit()

    entry = _only_summary(db, "sync")
    assert entry.changes["Flight"]["counts"] == {"create": 0, "update": 2, "delete": 0}
    assert entry.changes["PhotoFlight"]["counts"] == {"create": 0, "update": 0, "delete": 1}


def test_record_bulk_in_a_failed_savepoint_is_not_counted(session, db):
    with machine_run(session, "import", "flight"):
        nested = session.begin_nested()
        record_bulk(session, "update", "flight", [1], None)
        nested.rollback()
    session.commit()

    assert _only_summary(db, "import").changes == {}


# Query-level writes by a person ---------------------------------------------------

def test_folder_delete_moves_are_recorded(client, db, admin_headers):
    folder, _ = _seed(db, Folder(name="Old"), Folder(name="Parent"))
    child, doc = _seed(db, Folder(name="Child", parent_id=folder.id),
                       _document(folder_id=folder.id))
    folder_id, child_id, doc_id = folder.id, child.id, doc.id

    resp = client.delete(f"/api/folders/{folder_id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    moved_doc = _entries(db, entity_type="document", entity_id=doc_id)
    assert moved_doc[0].changes["folder_id"] == {"old": str(folder_id), "new": None}
    moved_child = _entries(db, entity_type="folder", entity_id=child_id)
    assert moved_child[0].changes["parent_id"] == {"old": str(folder_id), "new": None}
    assert db.get(Document, doc_id).folder_id is None


def test_vehicle_registration_replacement_is_recorded(client, db, admin_headers):
    vehicle, = _seed(db, Vehicle(serial_number="V", manufacturer="A", model="B"))
    old, = _seed(db, VehicleRegistration(vehicle_id=vehicle.id, registration_number="R1", is_current=True))
    old_id = old.id

    resp = client.post(f"/api/vehicles/{vehicle.id}/registrations", headers=admin_headers,
                       json={"registration_number": "R2"})
    assert resp.status_code in (200, 201), resp.text

    entries = _entries(db, entity_type="vehicle_registration", entity_id=old_id)
    assert entries[0].changes["is_current"] == {"old": "True", "new": "False"}


def test_equipment_leaving_service_records_its_schedules(client, db, admin_headers):
    battery, = _seed(db, Battery(serial_number="B"))
    schedule, = _seed(db, MaintenanceSchedule(
        name="Check", entity_type="battery", entity_id=battery.id, frequency="monthly", is_active=True))
    schedule_id = schedule.id

    assert client.delete(f"/api/batteries/{battery.id}", headers=admin_headers).status_code == 200

    entries = _entries(db, entity_type="maintenance_schedule", entity_id=schedule_id)
    assert entries[0].changes["is_active"] == {"old": "True", "new": "False"}


def _merged_entry(db, entity_type):
    entries = [e for e in _entries(db, entity_type=entity_type) if e.changes and "records" in e.changes]
    assert len(entries) == 1
    return entries[0]


def test_merge_reassignments_are_recorded_for_batteries(client, db, admin_headers):
    target, source = _seed(db, Battery(serial_number="KEEP"), Battery(serial_number="DUP"))
    pilot, = _seed(db, Pilot(first_name="A", last_name="B"))
    flight, reading, checkout = _seed(
        db, Flight(battery_serial="DUP"), BatteryReading(battery_id=source.id, health_pct=90),
        EquipmentCheckout(entity_type="battery", entity_id=source.id, checked_out_by_id=pilot.id))
    source_id, target_id, flight_id, reading_id, checkout_id = (
        source.id, target.id, flight.id, reading.id, checkout.id)

    resp = client.post(f"/api/batteries/{target_id}/merge?merge_from_id={source_id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["flights_updated"] == 1

    flights = _merged_entry(db, "flight").changes
    assert flights["records"]["ids"] == [flight_id]
    assert flights["battery_serial"] == {"old": "DUP", "new": "KEEP"}
    readings = _merged_entry(db, "battery_reading").changes
    assert readings["records"]["ids"] == [reading_id]
    assert readings["battery_id"] == {"old": str(source_id), "new": str(target_id)}
    checkouts = _merged_entry(db, "equipment").changes
    assert checkouts["records"]["ids"] == [checkout_id]


def test_merge_reassignments_are_recorded_for_vehicles(client, db, admin_headers):
    target, source = _seed(db, Vehicle(serial_number="KEEP", manufacturer="A", model="B"),
                           Vehicle(serial_number="DUP", manufacturer="A", model="B"))
    target_id, source_id = target.id, source.id
    flight, alert = _seed(db, Flight(vehicle_id=source_id),
                          Alert(type="t", severity="low", title="a", message="m",
                                entity_type="vehicle", entity_id=source_id))
    flight_id, alert_id = flight.id, alert.id

    resp = client.post(f"/api/vehicles/{target_id}/merge?merge_from_id={source_id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["references_moved"] == 2

    flights = _merged_entry(db, "flight").changes
    assert flights["records"]["ids"] == [flight_id]
    assert flights["vehicle_id"] == {"old": str(source_id), "new": str(target_id)}
    assert _merged_entry(db, "alert").changes["records"]["ids"] == [alert_id]


def test_merge_reassignments_are_recorded_for_sensors_and_attachments(client, db, admin_headers):
    sensor_keep, sensor_dup = _seed(db, SensorPackage(serial_number="S1"), SensorPackage(serial_number="S2"))
    attach_keep, attach_dup = _seed(db, Attachment(serial_number="A1"), Attachment(serial_number="A2"))
    flight, = _seed(db, Flight(sensor_package="S2", attachment_top="A2", attachment_left="A2"))
    flight_id = flight.id

    assert client.post(f"/api/sensors/{sensor_keep.id}/merge?merge_from_id={sensor_dup.id}",
                       headers=admin_headers).status_code == 200
    assert client.post(f"/api/attachments/{attach_keep.id}/merge?merge_from_id={attach_dup.id}",
                       headers=admin_headers).status_code == 200

    bulk = [e.changes for e in _entries(db, entity_type="flight") if e.changes and "records" in e.changes]
    assert {"sensor_package", "attachment_top", "attachment_left"} == {
        key for changes in bulk for key in changes if key != "records"}
    assert all(changes["records"]["ids"] == [flight_id] for changes in bulk)


def test_purpose_delete_records_the_flights_it_cleared(client, db, admin_headers):
    purpose, flight = _seed(db, FlightPurpose(name="Patrol"), Flight(purpose="Patrol"))
    flight_id = flight.id

    assert client.delete(f"/api/flights/purposes/{purpose.id}", headers=admin_headers).status_code == 200

    changes = _merged_entry(db, "flight").changes
    assert changes["records"]["ids"] == [flight_id]
    assert changes["purpose"] == {"old": "Patrol", "new": None}


def test_pilot_merge_records_moved_certification_references(client, db, admin_headers):
    from app.models import CertificationType, PilotCertification

    keep, dup = _seed(db, Pilot(first_name="Keep", last_name="X"), Pilot(first_name="Dup", last_name="X"))
    cert_type, = _seed(db, CertificationType(name="Part 107", category="faa"))
    kept, dropped = _seed(
        db, PilotCertification(pilot_id=keep.id, certification_type_id=cert_type.id, expiration_date=date(2030, 1, 1)),
        PilotCertification(pilot_id=dup.id, certification_type_id=cert_type.id, expiration_date=date(2027, 1, 1)))
    doc, = _seed(db, _document(certification_id=dropped.id))
    doc_id, kept_id, dropped_id = doc.id, kept.id, dropped.id

    resp = client.post(f"/api/pilots/{keep.id}/merge", headers=admin_headers, json={"source_id": dup.id})
    assert resp.status_code == 200, resp.text

    changes = _merged_entry(db, "document").changes
    assert changes["records"]["ids"] == [doc_id]
    assert changes["certification_id"] == {"old": str(dropped_id), "new": str(kept_id)}


def test_permission_reset_records_the_rows_it_removed(client, db, admin_headers):
    from app.models.role_permission import RolePermission

    row, = _seed(db, RolePermission(role="pilot", permission_key="a.a", value="on"))
    row_id = row.id

    assert client.post("/api/permissions/reset", headers=admin_headers).status_code == 200

    entry = _entries(db, entity_type="role_permission")[0]
    assert entry.action == "delete"
    assert entry.changes["records"]["ids"] == [row_id]
    assert "a.a" in entry.changes["deleted"]["old"]


# Link rows ------------------------------------------------------------------------

def _deleted_link(db, entity_type):
    entry = _merged_entry(db, entity_type)
    assert entry.action == "delete"
    return entry.changes


def test_photo_unlinks_record_the_link_rows(client, db, admin_headers):
    photo, flight = _seed(db, Photo(filename="a.jpg", original_filename="a.jpg"), Flight())
    incident, = _seed(db, Incident(date=date(2026, 1, 1), title="I", severity="low", category="c", description="d"))
    to_flight, to_incident = _seed(db, PhotoFlight(photo_id=photo.id, flight_id=flight.id),
                                   PhotoIncident(photo_id=photo.id, incident_id=incident.id))
    link_ids = to_flight.id, to_incident.id

    assert client.delete(f"/api/photos/{photo.id}/flight/{flight.id}", headers=admin_headers).status_code == 200
    assert client.delete(f"/api/photos/{photo.id}/incident/{incident.id}", headers=admin_headers).status_code == 200

    assert _deleted_link(db, "photo_flight")["records"]["ids"] == [link_ids[0]]
    assert _deleted_link(db, "photo_incident")["records"]["ids"] == [link_ids[1]]


def test_photo_pilot_replacement_records_the_old_links(client, db, admin_headers):
    photo, pilot, other = _seed(db, Photo(filename="a.jpg", original_filename="a.jpg"),
                                Pilot(first_name="A", last_name="B"), Pilot(first_name="C", last_name="D"))
    link, = _seed(db, PhotoPilot(photo_id=photo.id, pilot_id=pilot.id))
    link_id, pilot_id = link.id, pilot.id

    resp = client.patch(f"/api/photos/{photo.id}", headers=admin_headers, data={"pilot_ids": str(other.id)})
    assert resp.status_code == 200, resp.text

    changes = _deleted_link(db, "photo_pilot")
    assert changes["records"]["ids"] == [link_id]
    assert f"pilot_id={pilot_id}" in changes["deleted"]["old"]


def test_photo_purge_records_every_link(client, db, admin_headers, monkeypatch):
    from datetime import datetime, timezone

    pilot, flight = _seed(db, Pilot(first_name="A", last_name="B"), Flight())
    incident, = _seed(db, Incident(date=date(2026, 1, 1), title="I", severity="low", category="c", description="d"))
    photo, = _seed(db, Photo(filename="a.jpg", original_filename="a.jpg", deleted_at=datetime.now(timezone.utc)))
    _seed(db, PhotoPilot(photo_id=photo.id, pilot_id=pilot.id),
          PhotoFlight(photo_id=photo.id, flight_id=flight.id),
          PhotoIncident(photo_id=photo.id, incident_id=incident.id))

    resp = client.delete(f"/api/photos/{photo.id}/purge", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    for entity_type in ("photo_pilot", "photo_flight", "photo_incident"):
        assert len(_deleted_link(db, entity_type)["records"]["ids"]) == 1


def test_incident_delete_records_its_photo_links(client, db, admin_headers):
    photo, = _seed(db, Photo(filename="a.jpg", original_filename="a.jpg"))
    incident, = _seed(db, Incident(date=date(2026, 1, 1), title="I", severity="low", category="c", description="d"))
    link, = _seed(db, PhotoIncident(photo_id=photo.id, incident_id=incident.id))
    link_id = link.id

    assert client.delete(f"/api/incidents/{incident.id}", headers=admin_headers).status_code == 200

    assert _deleted_link(db, "photo_incident")["records"]["ids"] == [link_id]


@pytest.mark.parametrize("module, parent_model, link_model, link_field, entity_type", [
    (mission_logs, MissionLog, MissionLogPilot, "mission_log_id", "mission_log_pilot"),
    (training_logs, TrainingLog, TrainingLogPilot, "training_log_id", "training_log_pilot"),
])
def test_roster_rebuild_records_the_old_links(session, db, module, parent_model, link_model, link_field, entity_type):
    extra = {"training_type": "sim"} if parent_model is TrainingLog else {}
    parent, pilot = _seed(db, parent_model(date=date(2026, 1, 1), title="T", **extra),
                          Pilot(first_name="A", last_name="B"))
    link, = _seed(db, link_model(pilot_id=pilot.id, hours=2.5, **{link_field: parent.id}))
    link_id, parent_id = link.id, parent.id

    module._sync_pilots(session, session.get(parent_model, parent_id), [])
    session.commit()

    changes = _deleted_link(db, entity_type)
    assert changes["records"]["ids"] == [link_id]
    assert "hours=2.5" in changes["deleted"]["old"]


def _flight_with_references(db, submitter):
    photo, template, pilot = _seed(db, Photo(filename="a.jpg", original_filename="a.jpg"),
                                   ChecklistTemplate(name="T", items=[]), Pilot(first_name="A", last_name="B"))
    flight, = _seed(db, Flight(purpose="Patrol"))
    incident, completion, plan, media, link = _seed(
        db,
        Incident(date=date(2026, 1, 1), title="I", severity="low", category="c", description="d", flight_id=flight.id),
        ChecklistCompletion(template_id=template.id, pilot_id=pilot.id, flight_id=flight.id, responses=[]),
        FlightPlan(title="P", date_planned=date(2026, 1, 1), pilot_id=pilot.id, submitted_by_id=submitter.id,
                   linked_flight_id=flight.id),
        MediaFile(filename="m.jpg", kind="photo", flight_id=flight.id),
        PhotoFlight(photo_id=photo.id, flight_id=flight.id),
    )
    return {"flight": flight.id, "incident": incident.id, "completion": completion.id,
            "plan": plan.id, "media": media.id, "link": link.id}


def test_bulk_flight_delete_records_each_flight_and_reference(client, db, admin_user, admin_headers):
    ids = _flight_with_references(db, admin_user)

    resp = client.post("/api/flights/bulk-delete", headers=admin_headers, json={"flight_ids": [ids["flight"]]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == 1

    deleted = [e for e in _entries(db, entity_type="flight", entity_id=ids["flight"]) if e.action == "delete"]
    assert deleted[0].changes["purpose"] == {"old": "Patrol", "new": None}
    assert [e.action for e in _entries(db, action="bulk_delete")] == ["bulk_delete"]
    old_flight = {"old": str(ids["flight"]), "new": None}
    assert _entries(db, entity_type="incident", entity_id=ids["incident"])[0].changes["flight_id"] == old_flight
    assert _entries(db, entity_type="checklist_completion", entity_id=ids["completion"])[0].changes["flight_id"] == old_flight
    assert _entries(db, entity_type="flight_plan", entity_id=ids["plan"])[0].changes["linked_flight_id"] == old_flight
    assert _entries(db, entity_type="media_file", entity_id=ids["media"])[0].action == "delete"
    assert _deleted_link(db, "photo_flight")["records"]["ids"] == [ids["link"]]
    assert not [e for e in _entries(db) if e.changes and "Flight" in e.changes]


def test_single_flight_delete_writes_one_entry_with_values(client, db, admin_user, admin_headers):
    ids = _flight_with_references(db, admin_user)

    assert client.delete(f"/api/flights/{ids['flight']}", headers=admin_headers).status_code == 200

    entry, = [e for e in _entries(db, entity_type="flight", entity_id=ids["flight"]) if e.action == "delete"]
    assert entry.changes["purpose"] == {"old": "Patrol", "new": None}
    assert entry.entity_name == f"Flight {ids['flight']}"


def test_bulk_flight_update_records_each_flight_with_values(client, db, admin_headers):
    first, second = _seed(db, Flight(purpose="A"), Flight(purpose="B"))
    first_id, second_id = first.id, second.id

    resp = client.post("/api/flights/bulk-update", headers=admin_headers,
                       json={"flight_ids": [first_id, second_id], "purpose": "C"})
    assert resp.status_code == 200, resp.text

    assert _entries(db, entity_id=first_id, entity_type="flight")[0].changes["purpose"] == {"old": "A", "new": "C"}
    assert _entries(db, entity_id=second_id, entity_type="flight")[0].changes["purpose"] == {"old": "B", "new": "C"}


# A person's alert actions ---------------------------------------------------------

def _alert(db, **kwargs):
    alert, = _seed(db, Alert(type="t", severity="low", title="Check", message="m", **kwargs))
    return alert.id


def test_person_alert_read_is_logged(client, db, admin_user, admin_headers):
    alert_id = _alert(db)

    assert client.patch(f"/api/alerts/{alert_id}/read", headers=admin_headers).status_code == 200
    assert client.patch(f"/api/alerts/{alert_id}/read", headers=admin_headers).status_code == 200

    entries = _entries(db, entity_type="alert")
    assert [(e.action, e.entity_id, e.user_username) for e in entries] == [("read", alert_id, admin_user.username)]
    assert entries[0].changes["is_read"] == {"old": "False", "new": "True"}


def test_person_alert_dismiss_is_logged(client, db, admin_user, admin_headers):
    alert_id = _alert(db)

    assert client.patch(f"/api/alerts/{alert_id}/dismiss", headers=admin_headers).status_code == 200

    entries = _entries(db, entity_type="alert")
    assert [(e.action, e.entity_id, e.user_username) for e in entries] == [("dismiss", alert_id, admin_user.username)]
    assert entries[0].changes["is_dismissed"] == {"old": "False", "new": "True"}


def test_person_alert_dismiss_all_is_logged(client, db, admin_user, admin_headers):
    open_ids = sorted([_alert(db), _alert(db)])
    _alert(db, is_dismissed=True)

    assert client.post("/api/alerts/dismiss-all", headers=admin_headers).status_code == 200

    entry, = _entries(db, entity_type="alert")
    assert (entry.action, entry.user_username) == ("dismiss_all", admin_user.username)
    assert entry.changes["records"]["ids"] == open_ids
    assert entry.changes["is_dismissed"] == {"old": "False", "new": "True"}


def test_alert_is_still_left_out_of_automatic_capture(session, db):
    session.add(Alert(type="t", severity="low", title="a", message="m"))
    session.commit()

    assert _entries(db) == []


def test_generated_alerts_write_one_summary(session, db):
    _seed(db, *[MaintenanceSchedule(name=f"S{i}", entity_type="vehicle", entity_id=1, frequency="monthly",
                                    is_active=True, next_due=date.today() - timedelta(days=1))
                for i in range(ROWS)])

    scheduler.check_maintenance_schedules(session)

    entry = _only_summary(db, "alert_check")
    assert (entry.entity_type, entry.user_name) == ("alert", "System")
    assert entry.changes["Alert"]["counts"]["create"] == ROWS


# Sync -----------------------------------------------------------------------------

def test_sync_run_writes_one_summary(session, db, monkeypatch):
    _skydio_settings(db)
    _clear_audit(db)
    _use_provider(monkeypatch, sync_flights=lambda creds, since=None: _provider_flights())

    result = SyncManager.sync_all("skydio", session)

    assert result.flights_new == ROWS
    entry = _only_summary(db, "sync_run")
    assert entry.changes["Flight"]["counts"]["create"] == ROWS
    assert entry.changes["Flight"]["total_ids"] == ROWS


def test_sync_with_nothing_new_still_writes_its_summary(session, db, monkeypatch):
    _skydio_settings(db)
    _use_provider(monkeypatch)

    SyncManager.sync_all("skydio", session)

    assert _only_summary(db, "sync_run").changes == {}


def test_deep_sync_writes_one_summary(session, db, monkeypatch):
    _skydio_settings(db)
    _use_provider(monkeypatch, sync_flights_deep=lambda creds: _provider_flights())

    SyncManager.sync_all_deep("skydio", session)

    assert _only_summary(db, "sync_run").changes["Flight"]["counts"]["create"] == ROWS


def test_sync_failure_keeps_its_earlier_batches_on_record(session, db, monkeypatch):
    _skydio_settings(db)

    def down(creds):
        raise RuntimeError("provider went away")

    vehicles = [{"serial_number": "V1", "manufacturer": "A", "model": "B"}]
    _use_provider(monkeypatch, sync_vehicles=lambda creds: vehicles, sync_batteries=down)

    result = SyncManager.sync_all("skydio", session)

    assert result.errors
    assert _only_summary(db, "sync_run").changes["Vehicle"]["counts"]["create"] == 1


def test_manual_sync_writes_one_summary_and_names_the_admin(session, db, admin_user, monkeypatch):
    _skydio_settings(db)
    _seed(db, Flight(external_id="BLANK"), Flight(external_id="TODO", telemetry_synced=False, date=date(2026, 1, 1)))
    _use_provider(monkeypatch, sync_flights=lambda creds, since=None: _provider_flights(3))

    _run_sync(session, True, True, admin_user.id, admin_user.display_name)

    entries = _entries(db)
    assert sorted(e.action for e in entries) == ["sync", "sync_run"]
    named = next(e for e in entries if e.action == "sync")
    assert named.user_id == admin_user.id
    summary = next(e for e in entries if e.action == "sync_run").changes["Flight"]
    assert summary["counts"]["create"] == 3
    assert summary["counts"]["delete"] == 1
    assert summary["counts"]["update"] >= 1


def test_ghost_flights_removed_by_sync_only_add_to_the_summary(session, db, monkeypatch):
    _skydio_settings(db)
    photo, = _seed(db, Photo(filename="a.jpg", original_filename="a.jpg"))
    ghost, = _seed(db, Flight(external_id="GHOST", api_provider="skydio"))
    _seed(db, PhotoFlight(photo_id=photo.id, flight_id=ghost.id),
          Incident(date=date(2026, 1, 1), title="I", severity="low", category="c", description="d", flight_id=ghost.id))
    _use_provider(monkeypatch, get_flight_detail=lambda creds, flight_id: None)

    SyncManager.sync_all("skydio", session)

    entry = _only_summary(db, "sync_run")
    assert entry.changes["Flight"]["counts"]["delete"] == 1
    assert entry.changes["Incident"]["counts"]["update"] == 1
    assert entry.changes["PhotoFlight"]["counts"]["delete"] == 1


def test_person_edit_during_sync_logged_in_full(session, db, _engines, monkeypatch):
    SessionLocal, _ = _engines
    _skydio_settings(db)
    pilot, = _seed(db, Pilot(first_name="A", last_name="B", notes="before"))
    pilot_id = pilot.id

    def edit_then_list(creds, since=None):
        other = SessionLocal()
        try:
            other.get(Pilot, pilot_id).notes = "by hand"
            other.commit()
        finally:
            other.close()
        return _provider_flights(3)

    _use_provider(monkeypatch, sync_flights=edit_then_list)

    SyncManager.sync_all("skydio", session)

    entry, = _entries(db, entity_type="pilot", entity_id=pilot_id)
    assert entry.changes["notes"] == {"old": "before", "new": "by hand"}
    assert "Pilot" not in _entries(db, action="sync_run")[0].changes


def test_telemetry_sync_writes_one_summary(session, db, monkeypatch):
    _skydio_settings(db)
    _seed(db, *[Flight(external_id=f"T{i}", telemetry_synced=False) for i in range(5)])
    _use_provider(monkeypatch, get_flight_telemetry=lambda creds, flight_id: [])

    assert SyncManager.batch_sync_telemetry(session, limit=10) == 5

    entry = _only_summary(db, "telemetry_sync")
    assert entry.changes["Flight"]["counts"]["update"] == 5


def test_enrich_route_writes_one_summary(client, db, admin_headers, monkeypatch):
    from app.integrations import skydio

    _skydio_settings(db)
    _seed(db, Flight(external_id="E1", api_provider="skydio"), Flight(external_id="E2", api_provider="skydio"))
    details = {"E1": {"duration_seconds": 60}, "E2": None}
    monkeypatch.setattr(skydio.SkydioProvider, "get_flight_detail",
                        lambda self, creds, flight_id: details[flight_id])

    assert client.post("/api/sync/enrich", headers=admin_headers).status_code == 200

    entries = _entries(db)
    assert sorted(e.action for e in entries) == ["enrich_flights", "enrich_run"]
    summary = next(e for e in entries if e.action == "enrich_run").changes["Flight"]
    assert summary["counts"] == {"create": 0, "update": 1, "delete": 1}


def test_cleanup_route_is_a_person_action_with_full_entries(client, db, admin_headers):
    flight, = _seed(db, Flight(external_id="BLANK"))
    flight_id = flight.id

    assert client.post("/api/sync/cleanup", headers=admin_headers).status_code == 200

    assert _entries(db, entity_type="flight", entity_id=flight_id)[0].action == "delete"
    assert not _entries(db, action="sync_run")


# Imports --------------------------------------------------------------------------

def _upload(client, headers, url, name, content):
    resp = client.post(url, headers=headers, files={"file": (name, content)})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_flight_import_writes_one_summary(client, db, admin_user, admin_headers):
    rows = "".join(f"2026-01-01,P{i}\n" for i in range(ROWS))

    body = _upload(client, admin_headers, "/api/export/flights/import", "f.csv", ("Date,Purpose\n" + rows).encode())

    assert body["imported"] == ROWS
    entry = _only_summary(db, "import")
    assert entry.user_username == admin_user.username
    assert entry.changes["Flight"]["counts"]["create"] == ROWS


def test_skydio_csv_import_writes_one_summary(client, db, admin_headers):
    rows = "".join(f"id-{i},X10-1,Jane Doe,2026-01-01 03:30:00,600\n" for i in range(ROWS))
    csv_text = "Flight ID,Vehicle,Pilot,Takeoff,Duration (seconds)\n" + rows

    _upload(client, admin_headers, "/api/export/excel/import", "f.csv", csv_text.encode())

    assert _only_summary(db, "import").changes["Flight"]["counts"]["create"] == ROWS


def test_brinc_import_writes_one_summary(client, db, admin_headers):
    _seed(db, Vehicle(serial_number="B1", provider_serial="l2d-0001-00001", manufacturer="Brinc", model="LEMUR 2"))
    rows = [brinc_row(flight_id=f"id-{i}", start=f"2026-09-02 11:{i // 60:02d}:{i % 60:02d}", address="")
            for i in range(ROWS)]

    _upload(client, admin_headers, "/api/export/flights/import/log", "f.csv", brinc_csv(rows))

    entry = _only_summary(db, "import")
    assert entry.changes["Flight"]["counts"]["create"] == ROWS
    assert entry.changes["Pilot"]["counts"]["create"] == 1


def _airdata_log(flight_id):
    return json.dumps({
        "id": flight_id, "time": "2026-01-01 10:00:00", "duration": 60,
        "gps": [[30.0, -85.0]], "gps_timestamps": [0],
    }).encode()


def test_flight_log_zip_import_writes_one_summary(client, db, admin_headers, monkeypatch):
    from app.services import flight_log_import

    monkeypatch.setattr(flight_log_import, "_parse_for_format", lambda text, fmt: ({
        "metadata": {"date": date(2026, 1, 1), "external_id": text}, "telemetry": [],
    }, "airdata"))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        for i in range(5):
            zf.writestr(f"f{i}.json", f"LOG{i}")

    body = _upload(client, admin_headers, "/api/export/flights/import/log", "logs.zip", archive.getvalue())

    assert body["imported"] == 5
    assert _only_summary(db, "import").changes["Flight"]["counts"]["create"] == 5


def test_mission_import_savepoints_sit_inside_one_summary(client, db, admin_headers, monkeypatch):
    from app.routers import import_router

    real_attach = import_router._attach_pilots

    def fail_on_one_row(db_, link_model, link_col, parent_id, members, per_pilot, unknown_id, unmatched):
        if members == "boom":
            raise ValueError("bad row")
        real_attach(db_, link_model, link_col, parent_id, members, per_pilot, unknown_id, unmatched)

    monkeypatch.setattr(import_router, "_attach_pilots", fail_on_one_row)
    rows = "".join(f"2026-01-01,Mission {i},{'boom' if i == 3 else ''}\n" for i in range(10))
    mapping = json.dumps({"date": "Date", "title": "Title", "members": "Members"})

    resp = client.post(f"/api/import/commit?entity=missions&mapping={mapping}", headers=admin_headers,
                       files={"file": ("m.csv", ("Date,Title,Members\n" + rows).encode())})
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 9

    summary = _only_summary(db, "import").changes["MissionLog"]
    assert summary["counts"]["create"] == 9
    assert summary["total_ids"] == 9


def test_maintenance_import_writes_one_summary(client, db, admin_headers):
    _seed(db, Vehicle(serial_number="V1", manufacturer="A", model="B", nickname="V1"))
    rows = "".join(f"2026-01-01,Work {i},V1\n" for i in range(5))
    mapping = json.dumps({"performed_date": "Date", "description": "Description", "drones": "Drone"})

    resp = client.post(f"/api/import/commit?entity=maintenance&mapping={mapping}", headers=admin_headers,
                       files={"file": ("m.csv", ("Date,Description,Drone\n" + rows).encode())})
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 5

    assert _only_summary(db, "import").changes["MaintenanceRecord"]["counts"]["create"] == 5


# Other jobs -----------------------------------------------------------------------

def test_backup_job_writes_one_summary(db, _engines, tmp_path, monkeypatch):
    monkeypatch.setattr(backup_jobs, "SessionLocal", _engines[0])
    monkeypatch.setattr(backup_jobs, "backup_dir", lambda: str(tmp_path))
    monkeypatch.setattr(backup_jobs, "build_backup_archive", lambda db, include_telemetry: (io.BytesIO(b"zip"), {}))

    backup_jobs.run_scheduled_backup()

    entry = _only_summary(db, "backup")
    assert entry.changes == {}
    assert "dum-backup-" in entry.details


def test_failed_backup_job_writes_one_summary(db, _engines, tmp_path, monkeypatch):
    def broken(db, include_telemetry):
        raise OSError("disk full")

    monkeypatch.setattr(backup_jobs, "SessionLocal", _engines[0])
    monkeypatch.setattr(backup_jobs, "backup_dir", lambda: str(tmp_path))
    monkeypatch.setattr(backup_jobs, "build_backup_archive", broken)

    backup_jobs.run_scheduled_backup()

    assert "failed" in _only_summary(db, "backup").details
    assert db.query(Setting).filter_by(key="last_backup_at").count() == 1


def _digest_user(db, username):
    user, = _seed(db, User(username=username, display_name=username, password_hash="x",
                           email=f"{username}@example.com", role="admin"))
    _seed(db, NotificationPreference(user_id=user.id, enabled=True, frequency="daily"))
    return user


def test_digest_job_writes_one_summary(db, _engines, monkeypatch):
    from app.services import email_digest

    monkeypatch.setattr(scheduler, "SessionLocal", _engines[0])
    monkeypatch.setattr(scheduler, "_is_pref_due_now", lambda pref, now, hour, session: True)
    monkeypatch.setattr(email_digest, "build_digest", lambda session, user: None)
    monkeypatch.setattr(email_digest, "digest_address", lambda session, user, pref: "x@example.com")
    _seed(db, Setting(key="smtp_enabled", value="true"))
    _digest_user(db, "one")
    _digest_user(db, "two")
    _clear_audit(db)

    scheduler._run_digest_job()

    entry = _only_summary(db, "digest")
    assert entry.changes["NotificationLog"]["counts"]["create"] == 2


def test_digest_job_with_nothing_due_writes_nothing(db, _engines, monkeypatch):
    monkeypatch.setattr(scheduler, "SessionLocal", _engines[0])
    monkeypatch.setattr(scheduler, "_is_pref_due_now", lambda pref, now, hour, session: False)
    _seed(db, Setting(key="smtp_enabled", value="true"))
    _digest_user(db, "one")

    scheduler._run_digest_job()

    assert _entries(db) == []


def test_battery_repair_writes_one_summary(session, db):
    canonical, duplicate = _seed(db, Battery(serial_number="k01-231117-1-00061"),
                                 Battery(serial_number="-k01-231117-1-00061"))
    flight, = _seed(db, Flight(battery_serial="-k01-231117-1-00061"))
    flight_id, duplicate_id = flight.id, duplicate.id
    assert canonical.id

    assert battery_dedupe.merge_duplicate_batteries(session) == 1

    entry = _only_summary(db, "battery_repair")
    assert entry.changes["Flight"]["ids"] == [flight_id]
    assert duplicate_id in entry.changes["Battery"]["ids"]


# What a run costs -----------------------------------------------------------------

@pytest.fixture
def statements(_engines):
    """Every SQL statement sent to the main database while a test runs."""
    engine = _engines[0].kw["bind"]
    seen: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    yield seen
    event.remove(engine, "before_cursor_execute", record)


def _audit_statements(seen):
    return [s for s in seen if "audit_logs" in s]


def test_a_run_writes_no_audit_rows_per_flush(session, db, statements):
    with machine_run(session, "import", "flight"):
        for i in range(ROWS):
            session.add(Flight(external_id=f"F{i}"))
            session.flush()
    session.commit()

    assert len(_audit_statements(statements)) == 1
    assert _only_summary(db, "import").changes["Flight"]["counts"]["create"] == ROWS


def test_a_run_writes_no_audit_rows_per_savepoint(session, db, statements):
    with machine_run(session, "import", "flight"):
        for i in range(ROWS):
            with session.begin_nested():
                session.add(Flight(external_id=f"F{i}"))
                session.flush()
    session.commit()

    assert len(_audit_statements(statements)) == 1
    assert _only_summary(db, "import").changes["Flight"]["counts"]["create"] == ROWS


def test_a_run_reads_no_old_values(session, db, statements):
    """A value set on an expired object has no old value in memory. Capture
    reads it from the row, which a run must not pay for on every row."""
    def set_purpose(target, purpose):
        flights = target.query(Flight).all()
        target.commit()
        statements.clear()
        for flight in flights:
            flight.purpose = purpose
        target.flush()

    _seed(db, *[Flight(purpose="A") for _ in range(ROWS)])
    set_purpose(db, "B")
    db.commit()
    without_capture = len(statements)

    with machine_run(session, "sync", "flight"):
        set_purpose(session, "C")
    in_a_run = len(statements)
    session.commit()

    # Entering the run commits nothing, and the run adds its one row at exit.
    assert in_a_run == without_capture + 1
    assert _only_summary(db, "sync").changes["Flight"]["counts"]["update"] == ROWS


def test_a_run_counts_each_commit_with_one_audit_write(session, db, statements):
    with machine_run(session, "import", "flight"):
        for i in range(3):
            session.add(Flight(external_id=f"F{i}"))
            session.commit()
    session.commit()

    assert len(_audit_statements(statements)) == 3
    assert _only_summary(db, "import").changes["Flight"]["total_ids"] == 3


def test_flushed_work_is_reported_when_a_run_raises_and_the_caller_commits(session, db):
    with pytest.raises(RuntimeError):
        with machine_run(session, "sync", "pilot"):
            session.add(Pilot(first_name="Flushed", last_name="X"))
            session.flush()
            raise RuntimeError("provider went away")
    session.commit()

    assert db.query(Pilot).count() == 1
    assert _only_summary(db, "sync").changes["Pilot"]["counts"]["create"] == 1
