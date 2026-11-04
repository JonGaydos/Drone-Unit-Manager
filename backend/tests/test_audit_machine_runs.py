"""Query-level writes are on the record, and automated work writes one summary."""

import ast
import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone
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
from app.schemas.mission_log import MissionLogPilotIn
from app.schemas.training_log import TrainingLogPilotIn
from app.routers.sync import _run_sync
from app.services import audit_capture, backup_jobs, battery_dedupe, scheduler, sync_manager
from app.services.audit_capture import (
    delete_links, delete_recorded, machine_run, record_bulk, set_actor, update_recorded,
)
from app.services.sync_manager import SyncManager
from tests.test_brinc_import import _csv as brinc_csv
from tests.test_brinc_import import _row as brinc_row
from tests.test_data_integrity_batch5 import FakeProvider
from tests.test_jobs_batch7 import _wait_for

APP_ROOT = Path(__file__).resolve().parent.parent / "app"
ROWS = 200

RAW_SECRET = "raw-secret-value-3f9a"
PASSWORD_HASH = "password_hash"
TRUE_TEXT = "True"
FALSE_TEXT = "False"
SYSTEM_USER = "System"
PILOT_ROLE = "pilot"
TITLE = "title"
MARKER = "[changed]"
FLIGHT = "flight"
FLIGHT_MODEL = "Flight"
PILOT_MODEL = "Pilot"
COUNTS = "counts"
RECORDS = "records"
IDS = "ids"
TOTAL_IDS = "total_ids"
DELETED = "deleted"
CREATE = "create"
UPDATE = "update"
DELETE = "delete"
IMPORT = "import"
BACKUP = "backup"
SYNC = "sync"
SYNC_RUN = "sync_run"
TELEMETRY_RUN = "telemetry_sync"
SKYDIO = "skydio"
PURPOSE = "purpose"
PATROL = "Patrol"
ALERT = "alert"
INCIDENT = "incident"
PHOTO_FILE = "a.jpg"
PHOTO_FLIGHT = "photo_flight"
PHOTO_INCIDENT = "photo_incident"
PHOTO_PILOT = "photo_pilot"
DUPLICATE = "DUP"
KEEPER = "KEEP"
SECOND_ATTACHMENT = "A2"
LOW = "low"
SESSION_LOCAL = "SessionLocal"
CSV_NAME = "f.csv"
LOG_IMPORT_URL = "/api/export/flights/import/log"
FLIGHTS_IMPORT_URL = "/api/export/flights/import"

# Reasons a query-level write may stay one.
RESTORE = "Backup restore replaces whole tables, and the restore route logs one entry for it."
TELEMETRY = "Telemetry is a separate database and is never recorded in the audit log."
RECORDED = "Goes through record_bulk with the record IDs and values."
LINKS = "Hands the deleted rows' IDs and values to record_bulk, or to the route's own entry."

ALLOWED_WRITES = {
    ("routers/backup.py", "_restore_main_tables"): RESTORE,
    ("routers/backup.py", "_restore_telemetry"): TELEMETRY,
    ("routers/flights.py", "_refresh_telemetry"): TELEMETRY,
    ("services/flight_delete.py", "purge_flight_telemetry"): TELEMETRY,
    ("services/sync_manager.py", "_store_telemetry_points"): TELEMETRY,
    ("services/audit_capture.py", "update_recorded"): RECORDED,
    ("services/audit_capture.py", "_delete_rows"): LINKS,
}
_WRITE_METHODS = {UPDATE, DELETE}
_TABLE_WRITE_METHODS = {"insert", UPDATE, DELETE}
_SESSION_BULK_METHODS = {"bulk_insert_mappings", "bulk_update_mappings", "bulk_save_objects"}
_SQL_WRITE_VERBS = ("INSERT", "UPDATE", "DELETE", "REPLACE")


def _change(old, new) -> dict:
    return {"old": old, "new": new}


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


def _photo(**kwargs):
    return Photo(filename=PHOTO_FILE, original_filename=PHOTO_FILE, **kwargs)


def _incident(**kwargs):
    return Incident(date=date(2026, 1, 1), title="I", severity=LOW, category="c", description="d", **kwargs)


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

    record_bulk(session, UPDATE, FLIGHT, [3, 1, 2], {PURPOSE: _change("A", None)})
    session.commit()

    entry = _entries(db)[0]
    assert (entry.action, entry.entity_type, entry.user_username) == (UPDATE, FLIGHT, admin_user.username)
    assert entry.changes[RECORDS][IDS] == [1, 2, 3]
    assert entry.changes[RECORDS][TOTAL_IDS] == 3
    assert entry.changes[PURPOSE] == _change("A", None)


def test_record_bulk_keeps_every_id_outside_a_run(session, db):
    record_bulk(session, UPDATE, FLIGHT, list(range(1, 702)), None)
    session.commit()

    assert len(_entries(db)[0].changes[RECORDS][IDS]) == 701


def test_record_bulk_masks_secret_fields(session, db):
    record_bulk(session, UPDATE, "user", [1], {PASSWORD_HASH: _change(RAW_SECRET, RAW_SECRET)})
    session.commit()

    entry = _entries(db)[0]
    assert entry.changes[PASSWORD_HASH] == _change(MARKER, MARKER)
    assert RAW_SECRET not in json.dumps(entry.changes)


def test_update_recorded_masks_secret_fields(session, db):
    user, = _seed(db, User(username="u", display_name="U", password_hash=RAW_SECRET, role=PILOT_ROLE))
    user_id = user.id

    update_recorded(session, session.query(User).filter(User.id == user_id), {User.password_hash: (RAW_SECRET, "next")})
    session.commit()

    entry = _entries(db)[0]
    assert entry.changes[PASSWORD_HASH] == _change(MARKER, MARKER)
    assert RAW_SECRET not in json.dumps(entry.changes)


def test_delete_recorded_masks_secret_fields(session, db):
    user, = _seed(db, User(username="u", display_name="U", password_hash=RAW_SECRET, role=PILOT_ROLE))
    user_id = user.id

    delete_recorded(session, session.query(User).filter(User.id == user_id))
    session.commit()

    changes = _entries(db)[0].changes
    assert f"{PASSWORD_HASH}={MARKER}" in changes[DELETED]["old"]
    assert RAW_SECRET not in json.dumps(changes)


def test_delete_links_masks_secret_fields(db):
    user, = _seed(db, User(username="u", display_name="U", password_hash=RAW_SECRET, role=PILOT_ROLE))

    changes = delete_links(db.query(User).filter(User.id == user.id))
    db.rollback()

    assert RAW_SECRET not in json.dumps(changes)


def test_record_bulk_with_no_ids_writes_nothing(session, db):
    record_bulk(session, UPDATE, FLIGHT, [], None)
    session.commit()

    assert _entries(db) == []


def test_record_bulk_rolls_back_with_its_change(session, db):
    record_bulk(session, UPDATE, FLIGHT, [1], None)
    session.rollback()

    assert _entries(db) == []


def test_record_bulk_counts_toward_a_run_under_the_model_name(session, db):
    with machine_run(session, SYNC, FLIGHT):
        record_bulk(session, UPDATE, FLIGHT, [1, 2], {PURPOSE: _change("A", None)})
        record_bulk(session, DELETE, PHOTO_FLIGHT, [9], None)
    session.commit()

    entry = _only_summary(db, SYNC)
    assert entry.changes[FLIGHT_MODEL][COUNTS] == {CREATE: 0, UPDATE: 2, DELETE: 0}
    assert entry.changes["PhotoFlight"][COUNTS] == {CREATE: 0, UPDATE: 0, DELETE: 1}


def test_record_bulk_in_a_failed_savepoint_is_not_counted(session, db):
    with machine_run(session, IMPORT, FLIGHT):
        nested = session.begin_nested()
        record_bulk(session, UPDATE, FLIGHT, [1], None)
        nested.rollback()
    session.commit()

    assert _entries(db) == []


# Query-level writes by a person ---------------------------------------------------

def test_folder_delete_moves_are_recorded(client, db, admin_headers):
    folder, _ = _seed(db, Folder(name="Old"), Folder(name="Parent"))
    child, doc = _seed(db, Folder(name="Child", parent_id=folder.id),
                       _document(folder_id=folder.id))
    folder_id, child_id, doc_id = folder.id, child.id, doc.id

    resp = client.delete(f"/api/folders/{folder_id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    moved_doc = _entries(db, entity_type="document", entity_id=doc_id)
    assert moved_doc[0].changes["folder_id"] == _change(str(folder_id), None)
    moved_child = _entries(db, entity_type="folder", entity_id=child_id)
    assert moved_child[0].changes["parent_id"] == _change(str(folder_id), None)
    assert db.get(Document, doc_id).folder_id is None


def test_vehicle_registration_replacement_is_recorded(client, db, admin_headers):
    vehicle, = _seed(db, Vehicle(serial_number="V", manufacturer="A", model="B"))
    old, = _seed(db, VehicleRegistration(vehicle_id=vehicle.id, registration_number="R1", is_current=True))
    old_id = old.id

    resp = client.post(f"/api/vehicles/{vehicle.id}/registrations", headers=admin_headers,
                       json={"registration_number": "R2"})
    assert resp.status_code in (200, 201), resp.text

    entries = _entries(db, entity_type="vehicle_registration", entity_id=old_id)
    assert entries[0].changes["is_current"] == _change(TRUE_TEXT, FALSE_TEXT)


def test_equipment_leaving_service_records_its_schedules(client, db, admin_headers):
    battery, = _seed(db, Battery(serial_number="B"))
    schedule, = _seed(db, MaintenanceSchedule(
        name="Check", entity_type="battery", entity_id=battery.id, frequency="monthly", is_active=True))
    schedule_id = schedule.id

    assert client.delete(f"/api/batteries/{battery.id}", headers=admin_headers).status_code == 200

    entries = _entries(db, entity_type="maintenance_schedule", entity_id=schedule_id)
    assert entries[0].changes["is_active"] == _change(TRUE_TEXT, FALSE_TEXT)


def _merged_entry(db, entity_type):
    entries = [e for e in _entries(db, entity_type=entity_type) if e.changes and RECORDS in e.changes]
    assert len(entries) == 1
    return entries[0]


def test_merge_reassignments_are_recorded_for_batteries(client, db, admin_headers):
    target, source = _seed(db, Battery(serial_number=KEEPER), Battery(serial_number=DUPLICATE))
    pilot, = _seed(db, Pilot(first_name="A", last_name="B"))
    flight, reading, checkout = _seed(
        db, Flight(battery_serial=DUPLICATE), BatteryReading(battery_id=source.id, health_pct=90),
        EquipmentCheckout(entity_type="battery", entity_id=source.id, checked_out_by_id=pilot.id))
    source_id, target_id, flight_id, reading_id, checkout_id = (
        source.id, target.id, flight.id, reading.id, checkout.id)

    resp = client.post(f"/api/batteries/{target_id}/merge?merge_from_id={source_id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["flights_updated"] == 1

    flights = _merged_entry(db, FLIGHT).changes
    assert flights[RECORDS][IDS] == [flight_id]
    assert flights["battery_serial"] == _change(DUPLICATE, KEEPER)
    readings = _merged_entry(db, "battery_reading").changes
    assert readings[RECORDS][IDS] == [reading_id]
    assert readings["battery_id"] == _change(str(source_id), str(target_id))
    checkouts = _merged_entry(db, "equipment").changes
    assert checkouts[RECORDS][IDS] == [checkout_id]


def test_merge_reassignments_are_recorded_for_vehicles(client, db, admin_headers):
    target, source = _seed(db, Vehicle(serial_number=KEEPER, manufacturer="A", model="B"),
                           Vehicle(serial_number=DUPLICATE, manufacturer="A", model="B"))
    target_id, source_id = target.id, source.id
    flight, alert = _seed(db, Flight(vehicle_id=source_id),
                          Alert(type="t", severity=LOW, title="a", message="m",
                                entity_type="vehicle", entity_id=source_id))
    flight_id, alert_id = flight.id, alert.id

    resp = client.post(f"/api/vehicles/{target_id}/merge?merge_from_id={source_id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["references_moved"] == 2

    flights = _merged_entry(db, FLIGHT).changes
    assert flights[RECORDS][IDS] == [flight_id]
    assert flights["vehicle_id"] == _change(str(source_id), str(target_id))
    assert _merged_entry(db, ALERT).changes[RECORDS][IDS] == [alert_id]


def test_merge_reassignments_are_recorded_for_sensors_and_attachments(client, db, admin_headers):
    sensor_keep, sensor_dup = _seed(db, SensorPackage(serial_number="S1"), SensorPackage(serial_number="S2"))
    attach_keep, attach_dup = _seed(db, Attachment(serial_number="A1"), Attachment(serial_number=SECOND_ATTACHMENT))
    flight, = _seed(db, Flight(sensor_package="S2", attachment_top=SECOND_ATTACHMENT,
                               attachment_left=SECOND_ATTACHMENT))
    flight_id = flight.id

    assert client.post(f"/api/sensors/{sensor_keep.id}/merge?merge_from_id={sensor_dup.id}",
                       headers=admin_headers).status_code == 200
    assert client.post(f"/api/attachments/{attach_keep.id}/merge?merge_from_id={attach_dup.id}",
                       headers=admin_headers).status_code == 200

    bulk = [e.changes for e in _entries(db, entity_type=FLIGHT) if e.changes and RECORDS in e.changes]
    assert {"sensor_package", "attachment_top", "attachment_left"} == {
        key for changes in bulk for key in changes if key != RECORDS}
    assert all(changes[RECORDS][IDS] == [flight_id] for changes in bulk)


def test_purpose_delete_records_the_flights_it_cleared(client, db, admin_headers):
    purpose, flight = _seed(db, FlightPurpose(name=PATROL), Flight(purpose=PATROL))
    flight_id = flight.id

    assert client.delete(f"/api/flights/purposes/{purpose.id}", headers=admin_headers).status_code == 200

    changes = _merged_entry(db, FLIGHT).changes
    assert changes[RECORDS][IDS] == [flight_id]
    assert changes[PURPOSE] == _change(PATROL, None)


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
    assert changes[RECORDS][IDS] == [doc_id]
    assert changes["certification_id"] == _change(str(dropped_id), str(kept_id))


def test_permission_reset_records_the_rows_it_removed(client, db, admin_headers):
    from app.models.role_permission import RolePermission

    row, = _seed(db, RolePermission(role=PILOT_ROLE, permission_key="a.a", value="on"))
    row_id = row.id

    assert client.post("/api/permissions/reset", headers=admin_headers).status_code == 200

    entry = _entries(db, entity_type="role_permission")[0]
    assert entry.action == DELETE
    assert entry.changes[RECORDS][IDS] == [row_id]
    assert "a.a" in entry.changes[DELETED]["old"]


# Link rows ------------------------------------------------------------------------

def _deleted_link(db, entity_type):
    entry = _merged_entry(db, entity_type)
    assert entry.action == DELETE
    return entry.changes


def test_photo_unlinks_fold_the_link_into_one_entry(client, db, admin_headers):
    photo, flight = _seed(db, _photo(), Flight())
    incident, = _seed(db, _incident())
    to_flight, to_incident = _seed(db, PhotoFlight(photo_id=photo.id, flight_id=flight.id),
                                   PhotoIncident(photo_id=photo.id, incident_id=incident.id))
    flight_link, incident_link = to_flight.id, to_incident.id

    assert client.delete(f"/api/photos/{photo.id}/flight/{flight.id}", headers=admin_headers).status_code == 200
    assert client.delete(f"/api/photos/{photo.id}/incident/{incident.id}", headers=admin_headers).status_code == 200

    first, second = _entries(db)
    assert (first.action, second.action) == ("unlink", "unlink")
    assert first.changes[PHOTO_FLIGHT][IDS] == [flight_link]
    assert second.changes[PHOTO_INCIDENT][IDS] == [incident_link]


def test_photo_pilot_replacement_folds_into_one_entry(client, db, admin_headers):
    photo, pilot, other = _seed(db, _photo(), Pilot(first_name="A", last_name="B"),
                                Pilot(first_name="C", last_name="D"))
    link, = _seed(db, PhotoPilot(photo_id=photo.id, pilot_id=pilot.id))
    link_id, pilot_id, other_id, photo_id = link.id, pilot.id, other.id, photo.id

    resp = client.patch(f"/api/photos/{photo_id}", headers=admin_headers,
                        data={TITLE: "New", "pilot_ids": str(other_id)})
    assert resp.status_code == 200, resp.text

    entry, = _entries(db)
    assert (entry.action, entry.entity_type, entry.entity_id) == (UPDATE, "photo", photo_id)
    assert entry.changes[TITLE]["new"] == "New"
    assert entry.changes[PHOTO_PILOT][IDS] == [link_id]
    assert f"pilot_id={pilot_id}" in entry.changes[PHOTO_PILOT]["old"]
    new_link = db.query(PhotoPilot).filter_by(photo_id=photo_id).one()
    assert entry.changes["photo_pilot_added"][IDS] == [new_link.id]
    assert new_link.pilot_id == other_id


def test_photo_purge_folds_every_link_into_one_entry(client, db, admin_headers):
    pilot, flight = _seed(db, Pilot(first_name="A", last_name="B"), Flight())
    incident, = _seed(db, _incident())
    photo, = _seed(db, _photo(deleted_at=datetime.now(timezone.utc)))
    photo_id = photo.id
    _seed(db, PhotoPilot(photo_id=photo_id, pilot_id=pilot.id),
          PhotoFlight(photo_id=photo_id, flight_id=flight.id),
          PhotoIncident(photo_id=photo_id, incident_id=incident.id))

    resp = client.delete(f"/api/photos/{photo_id}/purge", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    entry, = _entries(db)
    assert (entry.action, entry.entity_id) == ("purge", photo_id)
    for entity_type in (PHOTO_PILOT, PHOTO_FLIGHT, PHOTO_INCIDENT):
        assert len(entry.changes[entity_type][IDS]) == 1


def test_incident_delete_folds_its_photo_links_into_one_entry(client, db, admin_headers):
    photo, = _seed(db, _photo())
    incident, = _seed(db, _incident())
    link, = _seed(db, PhotoIncident(photo_id=photo.id, incident_id=incident.id))
    link_id, incident_id = link.id, incident.id

    assert client.delete(f"/api/incidents/{incident_id}", headers=admin_headers).status_code == 200

    entry, = _entries(db)
    assert (entry.action, entry.entity_id) == (DELETE, incident_id)
    assert entry.changes[PHOTO_INCIDENT][IDS] == [link_id]


ROSTERS = [
    (mission_logs, MissionLog, MissionLogPilot, "mission_log_id", MissionLogPilotIn, "mission_log_pilot"),
    (training_logs, TrainingLog, TrainingLogPilot, "training_log_id", TrainingLogPilotIn, "training_log_pilot"),
]


def _roster(db, parent_model, link_model, link_field):
    extra = {"training_type": "sim"} if parent_model is TrainingLog else {}
    parent, pilot = _seed(db, parent_model(date=date(2026, 1, 1), title="T", **extra),
                          Pilot(first_name="A", last_name="B"))
    link, = _seed(db, link_model(pilot_id=pilot.id, hours=2.5, **{link_field: parent.id}))
    return parent.id, pilot.id, link.id


@pytest.mark.parametrize("module, parent_model, link_model, link_field, schema, entity_type", ROSTERS)
def test_roster_rebuild_records_the_old_links(session, db, module, parent_model, link_model, link_field, schema,
                                              entity_type):
    parent_id, _, link_id = _roster(db, parent_model, link_model, link_field)

    module._sync_pilots(session, session.get(parent_model, parent_id), [])
    session.commit()

    changes = _deleted_link(db, entity_type)
    assert changes[RECORDS][IDS] == [link_id]
    assert "hours=2.5" in changes[DELETED]["old"]


@pytest.mark.parametrize("module, parent_model, link_model, link_field, schema, entity_type", ROSTERS)
def test_unchanged_roster_is_left_alone(session, db, module, parent_model, link_model, link_field, schema,
                                        entity_type):
    parent_id, pilot_id, link_id = _roster(db, parent_model, link_model, link_field)

    module._sync_pilots(session, session.get(parent_model, parent_id), [schema(pilot_id=pilot_id, hours=2.5)])
    session.commit()

    assert _entries(db) == []
    assert db.query(link_model).one().id == link_id


@pytest.mark.parametrize("module, parent_model, link_model, link_field, schema, entity_type", ROSTERS)
def test_changed_hours_rebuild_the_roster(session, db, module, parent_model, link_model, link_field, schema,
                                          entity_type):
    parent_id, pilot_id, _ = _roster(db, parent_model, link_model, link_field)

    module._sync_pilots(session, session.get(parent_model, parent_id), [schema(pilot_id=pilot_id, hours=3.0)])
    session.commit()

    assert sorted(e.action for e in _entries(db, entity_type=entity_type)) == [CREATE, DELETE]
    assert db.query(link_model).one().hours == 3.0


def _flight_with_references(db, submitter):
    photo, template, pilot = _seed(db, _photo(),
                                   ChecklistTemplate(name="T", items=[]), Pilot(first_name="A", last_name="B"))
    flight, = _seed(db, Flight(purpose=PATROL))
    incident, completion, plan, media, link = _seed(
        db,
        _incident(flight_id=flight.id),
        ChecklistCompletion(template_id=template.id, pilot_id=pilot.id, flight_id=flight.id, responses=[]),
        FlightPlan(title="P", date_planned=date(2026, 1, 1), pilot_id=pilot.id, submitted_by_id=submitter.id,
                   linked_flight_id=flight.id),
        MediaFile(filename="m.jpg", kind="photo", flight_id=flight.id),
        PhotoFlight(photo_id=photo.id, flight_id=flight.id),
    )
    return {FLIGHT: flight.id, INCIDENT: incident.id, "completion": completion.id,
            "plan": plan.id, "media": media.id, "link": link.id}


def test_bulk_flight_delete_records_each_flight_and_reference(client, db, admin_user, admin_headers):
    ids = _flight_with_references(db, admin_user)

    resp = client.post("/api/flights/bulk-delete", headers=admin_headers, json={"flight_ids": [ids[FLIGHT]]})
    assert resp.status_code == 200, resp.text
    assert resp.json()[DELETED] == 1

    deleted = [e for e in _entries(db, entity_type=FLIGHT, entity_id=ids[FLIGHT]) if e.action == DELETE]
    assert deleted[0].changes[PURPOSE] == _change(PATROL, None)
    assert [e.action for e in _entries(db, action="bulk_delete")] == ["bulk_delete"]
    old_flight = _change(str(ids[FLIGHT]), None)
    assert _entries(db, entity_type=INCIDENT, entity_id=ids[INCIDENT])[0].changes["flight_id"] == old_flight
    completion = _entries(db, entity_type="checklist_completion", entity_id=ids["completion"])[0]
    assert completion.changes["flight_id"] == old_flight
    assert _entries(db, entity_type="flight_plan", entity_id=ids["plan"])[0].changes["linked_flight_id"] == old_flight
    assert _entries(db, entity_type="media_file", entity_id=ids["media"])[0].action == DELETE
    assert _deleted_link(db, PHOTO_FLIGHT)[RECORDS][IDS] == [ids["link"]]
    assert not [e for e in _entries(db) if e.changes and FLIGHT_MODEL in e.changes]


def test_single_flight_delete_writes_one_entry_with_values(client, db, admin_user, admin_headers):
    ids = _flight_with_references(db, admin_user)

    assert client.delete(f"/api/flights/{ids['flight']}", headers=admin_headers).status_code == 200

    entry, = [e for e in _entries(db, entity_type=FLIGHT, entity_id=ids[FLIGHT]) if e.action == DELETE]
    assert entry.changes[PURPOSE] == _change(PATROL, None)
    assert entry.entity_name == f"Flight {ids['flight']}"


def test_bulk_flight_update_records_each_flight_with_values(client, db, admin_headers):
    first, second = _seed(db, Flight(purpose="A"), Flight(purpose="B"))
    first_id, second_id = first.id, second.id

    resp = client.post("/api/flights/bulk-update", headers=admin_headers,
                       json={"flight_ids": [first_id, second_id], PURPOSE: "C"})
    assert resp.status_code == 200, resp.text

    assert _entries(db, entity_id=first_id, entity_type=FLIGHT)[0].changes[PURPOSE] == _change("A", "C")
    assert _entries(db, entity_id=second_id, entity_type=FLIGHT)[0].changes[PURPOSE] == _change("B", "C")


# A person's alert actions ---------------------------------------------------------

def _alert(db, **kwargs):
    alert, = _seed(db, Alert(type="t", severity=LOW, title="Check", message="m", **kwargs))
    return alert.id


def test_person_alert_read_is_logged(client, db, admin_user, admin_headers):
    alert_id = _alert(db)

    assert client.patch(f"/api/alerts/{alert_id}/read", headers=admin_headers).status_code == 200
    assert client.patch(f"/api/alerts/{alert_id}/read", headers=admin_headers).status_code == 200

    entries = _entries(db, entity_type=ALERT)
    assert [(e.action, e.entity_id, e.user_username) for e in entries] == [("read", alert_id, admin_user.username)]
    assert entries[0].changes["is_read"] == _change(FALSE_TEXT, TRUE_TEXT)


def test_person_alert_dismiss_is_logged(client, db, admin_user, admin_headers):
    alert_id = _alert(db)

    assert client.patch(f"/api/alerts/{alert_id}/dismiss", headers=admin_headers).status_code == 200

    entries = _entries(db, entity_type=ALERT)
    assert [(e.action, e.entity_id, e.user_username) for e in entries] == [("dismiss", alert_id, admin_user.username)]
    assert entries[0].changes["is_dismissed"] == _change(FALSE_TEXT, TRUE_TEXT)


def test_person_alert_dismiss_all_is_logged(client, db, admin_user, admin_headers):
    open_ids = sorted([_alert(db), _alert(db)])
    _alert(db, is_dismissed=True)

    assert client.post("/api/alerts/dismiss-all", headers=admin_headers).status_code == 200

    entry, = _entries(db, entity_type=ALERT)
    assert (entry.action, entry.user_username) == ("dismiss_all", admin_user.username)
    assert entry.changes[RECORDS][IDS] == open_ids
    assert entry.changes["is_dismissed"] == _change(FALSE_TEXT, TRUE_TEXT)


def test_alert_is_still_left_out_of_automatic_capture(session, db):
    session.add(Alert(type="t", severity=LOW, title="a", message="m"))
    session.commit()

    assert _entries(db) == []


def test_generated_alerts_write_one_summary(session, db):
    _seed(db, *[MaintenanceSchedule(name=f"S{i}", entity_type="vehicle", entity_id=1, frequency="monthly",
                                    is_active=True, next_due=date.today() - timedelta(days=1))
                for i in range(ROWS)])

    scheduler.check_maintenance_schedules(session)

    entry = _only_summary(db, "alert_check")
    assert (entry.entity_type, entry.user_name) == (ALERT, SYSTEM_USER)
    assert entry.changes["Alert"][COUNTS][CREATE] == ROWS


# Sync -----------------------------------------------------------------------------

def test_sync_run_writes_one_summary(session, db, monkeypatch):
    _skydio_settings(db)
    _clear_audit(db)
    _use_provider(monkeypatch, sync_flights=lambda creds, since=None: _provider_flights())

    result = SyncManager.sync_all(SKYDIO, session)

    assert result.flights_new == ROWS
    entry = _only_summary(db, SYNC_RUN)
    assert entry.changes[FLIGHT_MODEL][COUNTS][CREATE] == ROWS
    assert entry.changes[FLIGHT_MODEL][TOTAL_IDS] == ROWS


def test_sync_tick_with_no_changes_writes_no_row(session, db, monkeypatch):
    _skydio_settings(db)
    _use_provider(monkeypatch)

    SyncManager.sync_all(SKYDIO, session)

    assert _entries(db) == []
    assert session.query(Setting).filter_by(key="last_sync_result").count() == 1


def test_telemetry_tick_with_no_changes_writes_no_row(session, db, monkeypatch):
    _skydio_settings(db)
    _use_provider(monkeypatch)

    assert SyncManager.batch_sync_telemetry(session, limit=10) == 0

    assert _entries(db) == []


def test_alert_check_with_nothing_overdue_writes_no_row(session, db):
    scheduler.check_maintenance_schedules(session)

    assert _entries(db) == []


def test_battery_repair_with_nothing_to_repair_writes_no_row(session, db):
    _seed(db, Battery(serial_number="k01-231117-1-00061"))

    assert battery_dedupe.merge_duplicate_batteries(session) == 0

    assert _entries(db) == []


def test_import_with_no_rows_writes_no_row(client, db, admin_headers):
    _upload(client, admin_headers, FLIGHTS_IMPORT_URL, CSV_NAME, b"Date,Purpose\n")

    assert _entries(db) == []


def _job_result(client, headers, url):
    resp = client.post(url, headers=headers)
    assert resp.status_code == 200, resp.text
    job = _wait_for(client, headers, resp.json()["job_id"])
    assert job["status"] == "done", job


def test_background_sync_names_who_started_it(client, db, admin_user, admin_headers, monkeypatch):
    _skydio_settings(db)
    _use_provider(monkeypatch, sync_flights=lambda creds, since=None: _provider_flights(3))

    _job_result(client, admin_headers, "/api/sync/now/start")

    entry, = _entries(db, action=SYNC_RUN)
    assert (entry.user_id, entry.user_username) == (admin_user.id, admin_user.username)
    assert entry.user_name == admin_user.display_name


def test_background_telemetry_names_who_started_it(client, db, admin_user, admin_headers, monkeypatch):
    _skydio_settings(db)
    _seed(db, Flight(external_id="T1", telemetry_synced=False))
    _use_provider(monkeypatch, get_flight_telemetry=lambda creds, flight_id: [])

    _job_result(client, admin_headers, "/api/sync/telemetry/start")

    entry = _only_summary(db, TELEMETRY_RUN)
    assert (entry.user_id, entry.user_username) == (admin_user.id, admin_user.username)


def test_scheduled_sync_stays_system(db, _engines, monkeypatch):
    monkeypatch.setattr(scheduler, SESSION_LOCAL, _engines[0])
    _skydio_settings(db)
    _use_provider(monkeypatch, sync_flights=lambda creds, since=None: _provider_flights(3))

    scheduler._run_scheduled_sync()

    entry = _only_summary(db, SYNC_RUN)
    assert (entry.user_id, entry.user_name, entry.user_username) == (None, SYSTEM_USER, None)


def test_deep_sync_writes_one_summary(session, db, monkeypatch):
    _skydio_settings(db)
    _use_provider(monkeypatch, sync_flights_deep=lambda creds: _provider_flights())

    SyncManager.sync_all_deep(SKYDIO, session)

    assert _only_summary(db, SYNC_RUN).changes[FLIGHT_MODEL][COUNTS][CREATE] == ROWS


def test_sync_failure_keeps_its_earlier_batches_on_record(session, db, monkeypatch):
    _skydio_settings(db)

    def down(creds):
        raise RuntimeError("provider went away")

    vehicles = [{"serial_number": "V1", "manufacturer": "A", "model": "B"}]
    _use_provider(monkeypatch, sync_vehicles=lambda creds: vehicles, sync_batteries=down)

    result = SyncManager.sync_all(SKYDIO, session)

    assert result.errors
    assert _only_summary(db, SYNC_RUN).changes["Vehicle"][COUNTS][CREATE] == 1


def test_manual_sync_writes_one_summary_and_names_the_admin(session, db, admin_user, monkeypatch):
    _skydio_settings(db)
    _seed(db, Flight(external_id="BLANK"), Flight(external_id="TODO", telemetry_synced=False, date=date(2026, 1, 1)))
    _use_provider(monkeypatch, sync_flights=lambda creds, since=None: _provider_flights(3))

    _run_sync(session, True, True, admin_user.id, admin_user.display_name)

    entries = _entries(db)
    assert sorted(e.action for e in entries) == [SYNC, SYNC_RUN]
    named = next(e for e in entries if e.action == SYNC)
    assert named.user_id == admin_user.id
    summary = next(e for e in entries if e.action == SYNC_RUN).changes[FLIGHT_MODEL]
    assert summary[COUNTS][CREATE] == 3
    assert summary[COUNTS][DELETE] == 1
    assert summary[COUNTS][UPDATE] >= 1


def test_ghost_flights_removed_by_sync_only_add_to_the_summary(session, db, monkeypatch):
    _skydio_settings(db)
    photo, = _seed(db, _photo())
    ghost, = _seed(db, Flight(external_id="GHOST", api_provider=SKYDIO))
    _seed(db, PhotoFlight(photo_id=photo.id, flight_id=ghost.id),
          _incident(flight_id=ghost.id))
    _use_provider(monkeypatch, get_flight_detail=lambda creds, flight_id: None)

    SyncManager.sync_all(SKYDIO, session)

    entry = _only_summary(db, SYNC_RUN)
    assert entry.changes[FLIGHT_MODEL][COUNTS][DELETE] == 1
    assert entry.changes["Incident"][COUNTS][UPDATE] == 1
    assert entry.changes["PhotoFlight"][COUNTS][DELETE] == 1


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

    SyncManager.sync_all(SKYDIO, session)

    entry, = _entries(db, entity_type=PILOT_ROLE, entity_id=pilot_id)
    assert entry.changes["notes"] == _change("before", "by hand")
    assert PILOT_MODEL not in _entries(db, action=SYNC_RUN)[0].changes


def test_telemetry_sync_writes_one_summary(session, db, monkeypatch):
    _skydio_settings(db)
    _seed(db, *[Flight(external_id=f"T{i}", telemetry_synced=False) for i in range(5)])
    _use_provider(monkeypatch, get_flight_telemetry=lambda creds, flight_id: [])

    assert SyncManager.batch_sync_telemetry(session, limit=10) == 5

    entry = _only_summary(db, TELEMETRY_RUN)
    assert entry.changes[FLIGHT_MODEL][COUNTS][UPDATE] == 5


def test_enrich_route_writes_one_summary(client, db, admin_headers, monkeypatch):
    from app.integrations import skydio

    _skydio_settings(db)
    _seed(db, Flight(external_id="E1", api_provider=SKYDIO), Flight(external_id="E2", api_provider=SKYDIO))
    details = {"E1": {"duration_seconds": 60}, "E2": None}
    monkeypatch.setattr(skydio.SkydioProvider, "get_flight_detail",
                        lambda self, creds, flight_id: details[flight_id])

    assert client.post("/api/sync/enrich", headers=admin_headers).status_code == 200

    entries = _entries(db)
    assert sorted(e.action for e in entries) == ["enrich_flights", "enrich_run"]
    summary = next(e for e in entries if e.action == "enrich_run").changes[FLIGHT_MODEL]
    assert summary[COUNTS] == {CREATE: 0, UPDATE: 1, DELETE: 1}


def test_cleanup_route_is_a_person_action_with_full_entries(client, db, admin_headers):
    flight, = _seed(db, Flight(external_id="BLANK"))
    flight_id = flight.id

    assert client.post("/api/sync/cleanup", headers=admin_headers).status_code == 200

    assert _entries(db, entity_type=FLIGHT, entity_id=flight_id)[0].action == DELETE
    assert not _entries(db, action=SYNC_RUN)


# Imports --------------------------------------------------------------------------

def _upload(client, headers, url, name, content):
    resp = client.post(url, headers=headers, files={"file": (name, content)})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_flight_import_writes_one_summary(client, db, admin_user, admin_headers):
    rows = "".join(f"2026-01-01,P{i}\n" for i in range(ROWS))

    body = _upload(client, admin_headers, FLIGHTS_IMPORT_URL, CSV_NAME, ("Date,Purpose\n" + rows).encode())

    assert body["imported"] == ROWS
    entry = _only_summary(db, IMPORT)
    assert entry.user_username == admin_user.username
    assert entry.changes[FLIGHT_MODEL][COUNTS][CREATE] == ROWS


def test_skydio_csv_import_writes_one_summary(client, db, admin_headers):
    rows = "".join(f"id-{i},X10-1,Jane Doe,2026-01-01 03:30:00,600\n" for i in range(ROWS))
    csv_text = "Flight ID,Vehicle,Pilot,Takeoff,Duration (seconds)\n" + rows

    _upload(client, admin_headers, "/api/export/excel/import", CSV_NAME, csv_text.encode())

    assert _only_summary(db, IMPORT).changes[FLIGHT_MODEL][COUNTS][CREATE] == ROWS


def test_brinc_import_writes_one_summary(client, db, admin_headers):
    _seed(db, Vehicle(serial_number="B1", provider_serial="l2d-0001-00001", manufacturer="Brinc", model="LEMUR 2"))
    rows = [brinc_row(flight_id=f"id-{i}", start=f"2026-09-02 11:{i // 60:02d}:{i % 60:02d}", address="")
            for i in range(ROWS)]

    _upload(client, admin_headers, LOG_IMPORT_URL, CSV_NAME, brinc_csv(rows))

    entry = _only_summary(db, IMPORT)
    assert entry.changes[FLIGHT_MODEL][COUNTS][CREATE] == ROWS
    assert entry.changes[PILOT_MODEL][COUNTS][CREATE] == 1


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

    body = _upload(client, admin_headers, LOG_IMPORT_URL, "logs.zip", archive.getvalue())

    assert body["imported"] == 5
    assert _only_summary(db, IMPORT).changes[FLIGHT_MODEL][COUNTS][CREATE] == 5


def test_mission_import_savepoints_sit_inside_one_summary(client, db, admin_headers, monkeypatch):
    from app.routers import import_router

    real_attach = import_router._attach_pilots

    def fail_on_one_row(db_, link_model, link_col, parent_id, members, per_pilot, unknown_id, unmatched):
        if members == "boom":
            raise ValueError("bad row")
        real_attach(db_, link_model, link_col, parent_id, members, per_pilot, unknown_id, unmatched)

    monkeypatch.setattr(import_router, "_attach_pilots", fail_on_one_row)
    rows = "".join(f"2026-01-01,Mission {i},{'boom' if i == 3 else ''}\n" for i in range(10))
    mapping = json.dumps({"date": "Date", TITLE: "Title", "members": "Members"})

    resp = client.post(f"/api/import/commit?entity=missions&mapping={mapping}", headers=admin_headers,
                       files={"file": ("m.csv", ("Date,Title,Members\n" + rows).encode())})
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 9

    summary = _only_summary(db, IMPORT).changes["MissionLog"]
    assert summary[COUNTS][CREATE] == 9
    assert summary[TOTAL_IDS] == 9


def test_maintenance_import_writes_one_summary(client, db, admin_headers):
    _seed(db, Vehicle(serial_number="V1", manufacturer="A", model="B", nickname="V1"))
    rows = "".join(f"2026-01-01,Work {i},V1\n" for i in range(5))
    mapping = json.dumps({"performed_date": "Date", "description": "Description", "drones": "Drone"})

    resp = client.post(f"/api/import/commit?entity=maintenance&mapping={mapping}", headers=admin_headers,
                       files={"file": ("m.csv", ("Date,Description,Drone\n" + rows).encode())})
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 5

    assert _only_summary(db, IMPORT).changes["MaintenanceRecord"][COUNTS][CREATE] == 5


# Other jobs -----------------------------------------------------------------------

def test_backup_job_writes_one_summary(db, _engines, tmp_path, monkeypatch):
    monkeypatch.setattr(backup_jobs, SESSION_LOCAL, _engines[0])
    monkeypatch.setattr(backup_jobs, "backup_dir", lambda: str(tmp_path))
    monkeypatch.setattr(backup_jobs, "build_backup_archive", lambda db, include_telemetry: (io.BytesIO(b"zip"), {}))

    backup_jobs.run_scheduled_backup()

    entry = _only_summary(db, BACKUP)
    assert entry.user_name == SYSTEM_USER
    assert "dum-backup-" in entry.details


def test_failed_backup_job_writes_one_summary(db, _engines, tmp_path, monkeypatch):
    def broken(db, include_telemetry):
        raise OSError("disk full")

    monkeypatch.setattr(backup_jobs, SESSION_LOCAL, _engines[0])
    monkeypatch.setattr(backup_jobs, "backup_dir", lambda: str(tmp_path))
    monkeypatch.setattr(backup_jobs, "build_backup_archive", broken)

    backup_jobs.run_scheduled_backup()

    assert "failed" in _only_summary(db, BACKUP).details
    assert db.query(Setting).filter_by(key="last_backup_at").count() == 1


def _digest_user(db, username):
    user, = _seed(db, User(username=username, display_name=username, password_hash="x",
                           email=f"{username}@example.com", role="admin"))
    _seed(db, NotificationPreference(user_id=user.id, enabled=True, frequency="daily"))
    return user


def test_digest_job_writes_one_summary(db, _engines, monkeypatch):
    from app.services import email_digest

    monkeypatch.setattr(scheduler, SESSION_LOCAL, _engines[0])
    monkeypatch.setattr(scheduler, "_is_pref_due_now", lambda pref, now, hour, session: True)
    monkeypatch.setattr(email_digest, "build_digest", lambda session, user: None)
    monkeypatch.setattr(email_digest, "digest_address", lambda session, user, pref: "x@example.com")
    _seed(db, Setting(key="smtp_enabled", value="true"))
    _digest_user(db, "one")
    _digest_user(db, "two")
    _clear_audit(db)

    scheduler._run_digest_job()

    entry = _only_summary(db, "digest")
    assert entry.changes["NotificationLog"][COUNTS][CREATE] == 2


def test_digest_job_with_nothing_due_writes_nothing(db, _engines, monkeypatch):
    monkeypatch.setattr(scheduler, SESSION_LOCAL, _engines[0])
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
    assert entry.changes[FLIGHT_MODEL][IDS] == [flight_id]
    assert duplicate_id in entry.changes["Battery"][IDS]


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
    with machine_run(session, IMPORT, FLIGHT):
        for i in range(ROWS):
            session.add(Flight(external_id=f"F{i}"))
            session.flush()
    session.commit()

    assert len(_audit_statements(statements)) == 1
    assert _only_summary(db, IMPORT).changes[FLIGHT_MODEL][COUNTS][CREATE] == ROWS


def test_a_run_writes_no_audit_rows_per_savepoint(session, db, statements):
    with machine_run(session, IMPORT, FLIGHT):
        for i in range(ROWS):
            with session.begin_nested():
                session.add(Flight(external_id=f"F{i}"))
                session.flush()
    session.commit()

    assert len(_audit_statements(statements)) == 1
    assert _only_summary(db, IMPORT).changes[FLIGHT_MODEL][COUNTS][CREATE] == ROWS


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

    with machine_run(session, SYNC, FLIGHT):
        set_purpose(session, "C")
    in_a_run = len(statements)
    session.commit()

    # Entering the run commits nothing, and the run adds its one row at exit.
    assert in_a_run == without_capture + 1
    assert _only_summary(db, SYNC).changes[FLIGHT_MODEL][COUNTS][UPDATE] == ROWS


def test_a_run_counts_each_commit_with_one_audit_write(session, db, statements):
    with machine_run(session, IMPORT, FLIGHT):
        for i in range(3):
            session.add(Flight(external_id=f"F{i}"))
            session.commit()
    session.commit()

    assert len(_audit_statements(statements)) == 3
    assert _only_summary(db, IMPORT).changes[FLIGHT_MODEL][TOTAL_IDS] == 3


def test_flushed_work_is_reported_when_a_run_raises_and_the_caller_commits(session, db):
    with pytest.raises(RuntimeError):
        with machine_run(session, SYNC, PILOT_ROLE):
            session.add(Pilot(first_name="Flushed", last_name="X"))
            session.flush()
            raise RuntimeError("provider went away")
    session.commit()

    assert db.query(Pilot).count() == 1
    assert _only_summary(db, SYNC).changes[PILOT_MODEL][COUNTS][CREATE] == 1


# A summary write that fails ---------------------------------------------------------

def _fail_summary_writes(monkeypatch, times=1):
    """Make the next ``times`` writes of a run's summary raise."""
    left = [times]

    def failing(real):
        def write(*args):
            if left[0]:
                left[0] -= 1
                raise RuntimeError("audit write refused")
            return real(*args)
        return write

    for name in ("_insert_row", "_update_row"):
        monkeypatch.setattr(audit_capture, name, failing(getattr(audit_capture, name)))


def test_the_next_commit_retries_a_failed_summary_write(session, db, monkeypatch):
    with machine_run(session, SYNC, PILOT_ROLE):
        session.add(Pilot(first_name="Kept", last_name="X"))
        session.flush()
        _fail_summary_writes(monkeypatch)
        with pytest.raises(RuntimeError):
            session.commit()
        session.commit()

    assert db.query(Pilot).count() == 1
    assert _only_summary(db, SYNC).changes[PILOT_MODEL][COUNTS][CREATE] == 1


def test_a_summary_write_failing_as_a_run_ends_is_retried(session, db, monkeypatch):
    with pytest.raises(RuntimeError):
        with machine_run(session, SYNC, PILOT_ROLE):
            session.add(Pilot(first_name="Kept", last_name="X"))
            session.flush()
            _fail_summary_writes(monkeypatch)
    session.commit()

    assert db.query(Pilot).count() == 1
    assert _only_summary(db, SYNC).changes[PILOT_MODEL][COUNTS][CREATE] == 1


def test_a_run_that_cannot_write_its_summary_leaves_nothing_to_commit(session, db, monkeypatch):
    with pytest.raises(RuntimeError):
        with machine_run(session, SYNC, PILOT_ROLE):
            session.add(Pilot(first_name="Dropped", last_name="X"))
            session.flush()
            _fail_summary_writes(monkeypatch, times=2)
    session.commit()

    assert db.query(Pilot).count() == 0
    assert _entries(db) == []


def test_media_step_drops_its_rows_when_their_summary_fails(session, db, monkeypatch):
    _skydio_settings(db)

    def media(creds, since=None):
        _fail_summary_writes(monkeypatch)
        return [{"external_uuid": "M1", "filename": PHOTO_FILE}]

    _use_provider(monkeypatch, sync_media=media)

    result = SyncManager.sync_all(SKYDIO, session)

    assert db.query(MediaFile).count() == 0
    assert result.media_synced == 0


def test_telemetry_step_drops_its_changes_when_their_summary_fails(session, db, admin_user, monkeypatch):
    _skydio_settings(db)
    flight = _seed(db, Flight(external_id="TODO", telemetry_synced=False, date=date(2026, 1, 1)))[0]

    def telemetry(creds, flight_id):
        _fail_summary_writes(monkeypatch)
        return []

    _use_provider(monkeypatch, get_flight_telemetry=telemetry)

    _run_sync(session, False, True, admin_user.id, admin_user.display_name)

    db.expire_all()
    assert db.get(Flight, flight.id).telemetry_synced is False
    assert len(_entries(db, action=SYNC)) == 1


def test_zip_entry_is_dropped_when_its_summary_fails(client, db, admin_headers, monkeypatch):
    from app.services import flight_log_import

    def parse(text, fmt):
        if text == "LOG2":
            _fail_summary_writes(monkeypatch)
        return {"metadata": {"date": date(2026, 1, 1), "external_id": text}, "telemetry": []}, "airdata"

    monkeypatch.setattr(flight_log_import, "_parse_for_format", parse)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        for i in range(3):
            zf.writestr(f"f{i}.json", f"LOG{i}")

    body = _upload(client, admin_headers, LOG_IMPORT_URL, "logs.zip", archive.getvalue())

    assert body["imported"] == 2 and len(body["errors"]) == 1
    assert db.query(Flight).count() == 2
    assert _only_summary(db, IMPORT).changes[FLIGHT_MODEL][COUNTS][CREATE] == 2
