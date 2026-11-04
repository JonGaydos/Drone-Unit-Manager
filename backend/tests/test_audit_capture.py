"""The session hook that records every data change in the audit log."""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

import app.database as database
from app.database import Base
from app.models import (
    ApiToken, Attachment, AuditLog, Battery, BatteryReading, CalendarEvent, CertificationType,
    ChecklistCompletion, ChecklistTemplate, Component, Controller, CurrencyRule, Dock, Document,
    EquipmentCheckout, Flight, FlightPlan, FlightPurpose, Folder, Geofence, Incident,
    MaintenanceRecord, MaintenanceSchedule, MediaFile, MissionLog, MissionLogPilot,
    NotificationPreference, OperatingAuthority, OtherEquipment, Photo, Pilot, PilotCertification,
    PilotEquipmentQual, SavedReport, SensorPackage, Setting, TrainingLog, TrainingLogPilot, User,
    Vehicle, VehicleRegistration,
)
from app.models.photo import PhotoFlight, PhotoIncident, PhotoPilot
from app.models.role_permission import RolePermission
from app.constants import SECRET_KEYS
from app.services import api_tokens, audit_capture
from app.services.audit import log_action
from app.services.audit_capture import (
    EXCLUDED_FIELDS,
    EXCLUDED_MODELS,
    SYSTEM_STATUS_SETTING_KEYS,
    machine_run,
    set_actor,
)

RAW_SECRET = "raw-secret-value-3f9a"
MARKER = "[changed]"


@pytest.fixture
def session(_engines):
    """A session built the way the app builds one, with capture installed."""
    SessionLocal, _ = _engines
    captured = SessionLocal()
    yield captured
    captured.close()


@pytest.fixture
def parents(db, admin_user):
    """One committed row of each model that other models point at."""
    pilot = Pilot(first_name="Parent", last_name="Pilot")
    vehicle = Vehicle(serial_number="P-1", manufacturer="Acme", model="X")
    battery = Battery(serial_number="B-1")
    template = ChecklistTemplate(name="Preflight", items=[])
    cert_type = CertificationType(name="Part 107", category="faa")
    mission = MissionLog(date=date(2026, 1, 1), title="Mission")
    training = TrainingLog(date=date(2026, 1, 1), title="Training", training_type="sim")
    photo = Photo(filename="a.jpg", original_filename="a.jpg")
    flight = Flight()
    incident = Incident(date=date(2026, 1, 1), title="I", severity="low", category="c", description="d")
    rows = {
        "pilot": pilot, "vehicle": vehicle, "battery": battery, "template": template,
        "cert_type": cert_type, "mission": mission, "training": training, "photo": photo,
        "flight": flight, "incident": incident,
    }
    db.add_all(rows.values())
    db.commit()
    ids = {name: row.id for name, row in rows.items()}
    ids["user"] = admin_user.id
    return ids


def _fixed(cls, **fixed):
    return lambda ids: cls(**fixed)


# model -> (build a row from the parent IDs, field to update, new value)
BUILDERS = {
    ApiToken: (lambda p: ApiToken(name="t", token_hash="h" * 64, token_prefix="dum_", user_id=p["user"]), "name", "t2"),
    Attachment: (_fixed(Attachment, serial_number="A-1"), "serial_number", "A-2"),
    Battery: (_fixed(Battery, serial_number="B-9"), "nickname", "Blue"),
    BatteryReading: (lambda p: BatteryReading(battery_id=p["battery"]), "notes", "ok"),
    CalendarEvent: (_fixed(CalendarEvent, title="E", category="x", start_date=date(2026, 1, 1)), "title", "E2"),
    CertificationType: (_fixed(CertificationType, name="N", category="c"), "name", "N2"),
    ChecklistCompletion: (lambda p: ChecklistCompletion(template_id=p["template"], pilot_id=p["pilot"], responses=[]), "notes", "ok"),
    ChecklistTemplate: (_fixed(ChecklistTemplate, name="T", items=[]), "name", "T2"),
    Component: (_fixed(Component, name="C", component_type="motor"), "name", "C2"),
    Controller: (_fixed(Controller, serial_number="R-1"), "nickname", "Red"),
    CurrencyRule: (_fixed(CurrencyRule, name="R", required_hours=1.0, period_days=30), "name", "R2"),
    Dock: (_fixed(Dock, serial_number="D-1"), "name", "North"),
    Document: (_fixed(Document, entity_type="pilot", document_type="other", title="Doc", filename="d.pdf",
                          file_path="d.pdf", mime_type="application/pdf", file_size_bytes=1), "title", "Doc2"),
    EquipmentCheckout: (lambda p: EquipmentCheckout(entity_type="vehicle", entity_id=p["vehicle"], checked_out_by_id=p["pilot"]), "notes_out", "ok"),
    Flight: (_fixed(Flight), "notes", "ok"),
    FlightPlan: (lambda p: FlightPlan(title="Plan", date_planned=datetime(2026, 1, 1), pilot_id=p["pilot"], submitted_by_id=p["user"]), "title", "Plan2"),
    FlightPurpose: (_fixed(FlightPurpose, name="Purpose"), "name", "Purpose2"),
    Folder: (_fixed(Folder, name="F"), "name", "F2"),
    Geofence: (_fixed(Geofence, name="G", zone_type="z", geometry_type="circle"), "name", "G2"),
    Incident: (_fixed(Incident, date=date(2026, 1, 1), title="I", severity="low", category="c", description="d"), "title", "I2"),
    MaintenanceRecord: (lambda p: MaintenanceRecord(entity_type="vehicle", entity_id=p["vehicle"], maintenance_type="m", description="d"), "description", "d2"),
    MaintenanceSchedule: (_fixed(MaintenanceSchedule, name="S", entity_type="vehicle", frequency="monthly"), "name", "S2"),
    MediaFile: (_fixed(MediaFile, filename="m.jpg", kind="photo"), "filename", "m2.jpg"),
    MissionLog: (_fixed(MissionLog, date=date(2026, 1, 1), title="M"), "title", "M2"),
    MissionLogPilot: (lambda p: MissionLogPilot(mission_log_id=p["mission"], pilot_id=p["pilot"]), "role", "observer"),
    NotificationPreference: (lambda p: NotificationPreference(user_id=p["user"]), "send_time", "09:00"),
    OperatingAuthority: (_fixed(OperatingAuthority, authority_type="cow", title="A"), "title", "A2"),
    OtherEquipment: (_fixed(OtherEquipment, name="O"), "name", "O2"),
    Photo: (_fixed(Photo, filename="p.jpg", original_filename="p.jpg"), "title", "P"),
    PhotoFlight: (lambda p: PhotoFlight(photo_id=p["photo"], flight_id=p["flight"]), "flight_id", None),
    PhotoIncident: (lambda p: PhotoIncident(photo_id=p["photo"], incident_id=p["incident"]), "incident_id", None),
    PhotoPilot: (lambda p: PhotoPilot(photo_id=p["photo"], pilot_id=p["pilot"]), "pilot_id", None),
    Pilot: (_fixed(Pilot, first_name="Ann", last_name="Lee"), "first_name", "Anne"),
    PilotCertification: (lambda p: PilotCertification(pilot_id=p["pilot"], certification_type_id=p["cert_type"]), "notes", "ok"),
    PilotEquipmentQual: (lambda p: PilotEquipmentQual(pilot_id=p["pilot"]), "notes", "ok"),
    RolePermission: (_fixed(RolePermission, role="pilot", permission_key="a.b", value="on"), "value", "off"),
    SavedReport: (_fixed(SavedReport, name="Rep", report_type="flights"), "name", "Rep2"),
    SensorPackage: (_fixed(SensorPackage, serial_number="S-1"), "name", "Thermal"),
    Setting: (_fixed(Setting, key="org_name", value="Unit"), "value", "Unit2"),
    TrainingLog: (_fixed(TrainingLog, date=date(2026, 1, 1), title="Tr", training_type="sim"), "title", "Tr2"),
    TrainingLogPilot: (lambda p: TrainingLogPilot(training_log_id=p["training"], pilot_id=p["pilot"]), "role", "student"),
    User: (_fixed(User, username="newuser", password_hash="x", display_name="New"), "display_name", "Newer"),
    Vehicle: (_fixed(Vehicle, serial_number="V-9", manufacturer="Acme", model="X"), "nickname", "Hawk"),
    VehicleRegistration: (lambda p: VehicleRegistration(vehicle_id=p["vehicle"]), "notes", "ok"),
}
# Link rows have nothing but their foreign keys, so the update repoints one.
REPOINT = {PhotoFlight: "flight", PhotoIncident: "incident", PhotoPilot: "pilot"}


def _second_parent(db, cls):
    """A second parent row to repoint a link row at."""
    row = {
        PhotoFlight: lambda: Flight(),
        PhotoIncident: lambda: Incident(date=date(2026, 1, 2), title="J", severity="low", category="c", description="d"),
        PhotoPilot: lambda: Pilot(first_name="Other", last_name="Pilot"),
    }[cls]()
    db.add(row)
    db.commit()
    return row.id


def _entries(db, **filters):
    db.expire_all()
    return db.query(AuditLog).filter_by(**filters).order_by(AuditLog.id).all()


def _exercise_model(session, db, cls, parent_ids, admin):
    """Create, update and delete one row of ``cls``, checking each entry."""
    build, field, value = BUILDERS[cls]
    entity_type = audit_capture.entity_type_of(cls)
    if cls in REPOINT:
        value = _second_parent(db, cls)
    before = db.query(AuditLog).count()

    row = build(parent_ids)
    session.add(row)
    session.commit()
    entries = _entries(db)[before:]
    assert [e.action for e in entries] == ["create"], cls.__name__
    assert entries[0].entity_type == entity_type

    old = getattr(row, field)
    setattr(row, field, value)
    session.commit()
    entries = _entries(db)[before + 1:]
    assert [e.action for e in entries] == ["update"], cls.__name__
    assert entries[0].changes[field] == {
        "old": None if old is None else str(old),
        "new": str(value),
    }, cls.__name__

    session.delete(row)
    session.commit()
    entries = _entries(db)[before:]
    assert [e.action for e in entries] == ["create", "update", "delete"], cls.__name__
    for entry in entries:
        assert entry.entity_type == entity_type, cls.__name__
        assert entry.user_id == admin.id, cls.__name__
        assert entry.user_username == admin.username, cls.__name__
        assert entry.user_name == admin.display_name, cls.__name__
    assert entries[2].changes[field]["old"] == str(value), cls.__name__


def test_every_model_is_captured_or_excluded(session, db, parents, admin_user):
    set_actor(session, admin_user)
    mapped = sorted(
        (m.class_ for m in Base.registry.mappers if m.class_.__name__ not in EXCLUDED_MODELS),
        key=lambda cls: cls.__name__,
    )
    missing = [cls.__name__ for cls in mapped if cls not in BUILDERS]
    assert not missing, f"Models with no audit builder: {missing}"
    for cls in mapped:
        _exercise_model(session, db, cls, parents, admin_user)


@pytest.mark.parametrize("model", ["AuditLog", "NotificationLog", "Alert"])
def test_excluded_models_are_named(model):
    assert model in EXCLUDED_MODELS


def test_excluded_models_write_nothing(session, db, admin_user):
    from app.models import Alert, NotificationLog

    session.add(Alert(type="t", severity="low", title="a", message="m"))
    session.add(NotificationLog(user_id=admin_user.id, subject="s", status="sent"))
    session.commit()
    assert _entries(db) == []


def _pilot(session, **fields):
    pilot = Pilot(first_name="Ann", last_name="Lee", **fields)
    session.add(pilot)
    session.commit()
    return pilot


def _clear_audit(db):
    db.query(AuditLog).delete()
    db.commit()


def test_update_records_old_and_new(session, db):
    pilot = _pilot(session, badge_number="100")
    _clear_audit(db)

    pilot.badge_number = "200"
    pilot.notes = "new note"
    session.commit()

    entry = _entries(db)[0]
    assert (entry.action, entry.entity_type, entry.entity_id) == ("update", "pilot", pilot.id)
    assert entry.entity_name == "Ann Lee"
    assert entry.changes == {
        "badge_number": {"old": "100", "new": "200"},
        "notes": {"old": None, "new": "new note"},
    }


def test_update_of_expired_object_still_records_old_value(session, db):
    """After a commit the old value is no longer in memory; it comes from the row."""
    pilot = _pilot(session, badge_number="100")
    _clear_audit(db)
    assert "badge_number" not in pilot.__dict__

    pilot.badge_number = "200"
    session.commit()

    assert _entries(db)[0].changes == {"badge_number": {"old": "100", "new": "200"}}


def test_delete_records_id_and_key_fields(session, db):
    pilot = _pilot(session, badge_number="100")
    pilot_id = pilot.id
    _clear_audit(db)

    session.delete(pilot)
    session.commit()

    entry = _entries(db)[0]
    assert (entry.action, entry.entity_type, entry.entity_id) == ("delete", "pilot", pilot_id)
    assert entry.entity_name == "Ann Lee"
    assert entry.changes["first_name"] == {"old": "Ann", "new": None}
    assert entry.changes["badge_number"] == {"old": "100", "new": None}
    assert "created_at" not in entry.changes


def test_orphan_removed_from_its_parent_records_a_delete(session, db, parents):
    mission = session.get(MissionLog, parents["mission"])
    link = MissionLogPilot(mission_log_id=mission.id, pilot_id=parents["pilot"], role="pic")
    mission.pilots.append(link)
    session.commit()
    link_id = link.id
    _clear_audit(db)

    mission.pilots.remove(link)
    session.commit()

    entry = _entries(db, entity_type="mission_log_pilot")[0]
    assert (entry.action, entry.entity_id) == ("delete", link_id)
    assert entry.changes["role"] == {"old": "pic", "new": None}


def test_unchanged_update_writes_nothing(session, db):
    pilot = _pilot(session, badge_number="100")
    _clear_audit(db)

    pilot.badge_number = "100"
    session.commit()
    pilot.badge_number = "100"  # with the attribute loaded this time
    session.commit()

    assert _entries(db) == []


def _secret_row(session, parents_user_id, field):
    if field == "password_hash":
        row = User(username="u1", password_hash=RAW_SECRET, display_name="U")
        session.add(row)
    elif field == "token_hash":
        row = ApiToken(name="t", token_hash=RAW_SECRET, token_prefix="dum_", user_id=parents_user_id)
        session.add(row)
    else:
        row = Setting(key=field, value=RAW_SECRET)
        session.add(row)
    session.commit()
    return row


def _set_secret(row, field, value):
    setattr(row, "value" if isinstance(row, Setting) else field, value)


@pytest.mark.parametrize("field", ["password_hash", "token_hash", *sorted(SECRET_KEYS)])
def test_secret_fields_never_stored(session, db, admin_user, field):
    """On create, on update and on delete the raw values never reach an entry."""
    row = _secret_row(session, admin_user.id, field)
    _set_secret(row, field, RAW_SECRET + "-new")
    session.commit()
    session.delete(row)
    session.commit()

    entries = _entries(db)
    assert [e.action for e in entries] == ["create", "update", "delete"]
    key = "value" if isinstance(row, Setting) else field
    for entry in entries:
        assert RAW_SECRET not in str(
            (entry.changes, entry.details, entry.entity_name, entry.user_name, entry.user_username))
        assert entry.changes[key] == {"old": MARKER, "new": MARKER}


def test_excluded_fields_alone_write_nothing(session, db, admin_user):
    token = ApiToken(name="t", token_hash="h" * 64, token_prefix="dum_", user_id=admin_user.id)
    flight = Flight()
    session.add_all([token, flight])
    session.commit()
    user = session.get(User, admin_user.id)
    _clear_audit(db)
    assert {"created_at", "updated_at", "last_used_at", "token_version", "modified_by_id"} <= EXCLUDED_FIELDS

    token.last_used_at = datetime.now(timezone.utc)
    user.token_version = 7
    flight.modified_by_id = user.id
    flight.updated_at = datetime.now(timezone.utc)
    session.commit()

    assert _entries(db) == []


@pytest.mark.parametrize("key", sorted(SYSTEM_STATUS_SETTING_KEYS))
def test_system_status_settings_write_nothing(session, db, key):
    row = Setting(key=key, value="a")
    session.add(row)
    session.commit()
    row.value = "b"
    session.commit()
    session.delete(row)
    session.commit()

    assert _entries(db) == []


def test_rollback_leaves_no_entry(session, db):
    pilot = _pilot(session)
    _clear_audit(db)

    pilot.notes = "flushed"
    session.flush()
    session.flush()  # the queued entry reaches the database too
    session.rollback()
    session.commit()

    assert _entries(db) == []
    pilot.notes = "kept"
    session.commit()
    assert _entries(db)[0].changes == {"notes": {"old": None, "new": "kept"}}


def test_audit_write_failure_fails_the_save(session, db):
    pilot = _pilot(session)
    pilot_id = pilot.id
    _clear_audit(db)
    bind = database.engine
    with bind.begin() as conn:
        conn.execute(text(
            "CREATE TRIGGER block_audit BEFORE INSERT ON audit_logs "
            "BEGIN SELECT RAISE(ABORT, 'audit write refused'); END"))

    pilot.notes = "must not save"
    with pytest.raises(Exception, match="audit write refused"):
        session.commit()
    session.rollback()

    with bind.begin() as conn:
        conn.execute(text("DROP TRIGGER block_audit"))
    db.expire_all()
    assert db.get(Pilot, pilot_id).notes is None
    assert _entries(db) == []


def test_log_action_absorbs_automatic_entry(session, db, admin_user):
    """Called before the flush: one row, with the meaning and the values."""
    set_actor(session, admin_user)
    pilot = _pilot(session)
    _clear_audit(db)

    pilot.notes = "changed"
    log_action(session, admin_user.id, "Admin", "deactivate", "pilot", pilot.id, "Ann Lee",
               changes={"reason": {"old": None, "new": "left the unit"}}, details="Left")
    session.commit()

    entries = _entries(db)
    assert len(entries) == 1
    assert entries[0].action == "deactivate"
    assert entries[0].details == "Left"
    assert entries[0].changes == {
        "notes": {"old": None, "new": "changed"},
        "reason": {"old": None, "new": "left the unit"},
    }


def test_log_action_after_flush_absorbs_automatic_entry(session, db, admin_user):
    """The usual create route: flush for the ID, then log, then commit."""
    set_actor(session, admin_user)
    pilot = Pilot(first_name="Ann", last_name="Lee")
    session.add(pilot)
    session.flush()
    log_action(session, admin_user.id, admin_user.display_name, "create", "pilot", pilot.id, "Ann Lee",
               ip_address="10.0.0.1")
    session.commit()

    entries = _entries(db)
    assert len(entries) == 1
    assert entries[0].action == "create"
    assert entries[0].ip_address == "10.0.0.1"
    assert entries[0].changes["first_name"] == {"old": None, "new": "Ann"}


def test_log_action_absorbs_delete(session, db, admin_user):
    pilot = _pilot(session)
    pilot_id = pilot.id
    _clear_audit(db)

    session.delete(pilot)
    log_action(session, admin_user.id, "Admin", "delete", "pilot", pilot_id, "Ann Lee")
    session.commit()

    entries = _entries(db)
    assert len(entries) == 1
    assert entries[0].changes["first_name"] == {"old": "Ann", "new": None}


def test_log_action_for_another_record_absorbs_nothing(session, db, admin_user):
    pilot = _pilot(session)
    _clear_audit(db)

    pilot.notes = "changed"
    log_action(session, admin_user.id, "Admin", "update", "pilot", pilot.id + 1, "Other")
    session.commit()

    assert len(_entries(db)) == 2


def test_log_action_fills_username_from_actor(session, db, admin_user):
    set_actor(session, admin_user)
    log_action(session, admin_user.id, admin_user.display_name, "export", "backup")
    session.commit()

    assert _entries(db)[0].user_username == admin_user.username


def test_log_action_without_actor_leaves_username_empty(session, db):
    log_action(session, None, None, "export", "backup")
    session.commit()

    entry = _entries(db)[0]
    assert entry.user_username is None
    assert entry.user_name == "System"


def test_two_flushes_of_one_record_write_one_entry(session, db):
    pilot = _pilot(session, badge_number="1")
    _clear_audit(db)

    pilot.badge_number = "2"
    session.flush()
    pilot.badge_number = "3"
    session.commit()

    entries = _entries(db)
    assert len(entries) == 1
    assert entries[0].changes == {"badge_number": {"old": "1", "new": "3"}}


def test_no_actor_records_system(session, db):
    pilot = _pilot(session)

    entry = _entries(db, entity_id=pilot.id, entity_type="pilot")[0]
    assert entry.user_id is None
    assert entry.user_name == "System"
    assert entry.user_username is None


def test_set_actor_stores_identity(session, admin_user):
    set_actor(session, admin_user)

    assert session.info["audit_actor"] == {
        "id": admin_user.id, "name": admin_user.display_name, "username": admin_user.username,
    }


def _three_pilots(session):
    pilots = [Pilot(first_name=f"P{i}", last_name="X") for i in range(3)]
    session.add_all(pilots)
    session.commit()
    return pilots


def test_machine_run_writes_one_summary(session, db, admin_user):
    set_actor(session, admin_user)
    pilots = _three_pilots(session)
    _clear_audit(db)

    with machine_run(session, "sync", "pilot", details="Nightly"):
        for pilot in pilots:
            pilot.notes = "synced"
        session.flush()
    session.commit()

    entries = _entries(db)
    assert len(entries) == 1
    entry = entries[0]
    assert (entry.action, entry.entity_type, entry.details) == ("sync", "pilot", "Nightly")
    assert entry.user_username == admin_user.username
    summary = entry.changes["Pilot"]
    assert summary["counts"] == {"create": 0, "update": 3, "delete": 0}
    assert summary["ids"] == sorted(p.id for p in pilots)
    assert summary["total_ids"] == 3


def test_machine_run_counts_creates_and_deletes_across_commits(session, db):
    pilots = _three_pilots(session)
    doomed_id = pilots[0].id
    _clear_audit(db)

    with machine_run(session, "import", "pilot"):
        added = Pilot(first_name="New", last_name="X")
        session.add(added)
        session.commit()
        session.delete(pilots[0])
        session.commit()
    session.commit()

    entries = _entries(db)
    assert len(entries) == 1
    summary = entries[0].changes["Pilot"]
    assert summary["counts"] == {"create": 1, "update": 0, "delete": 1}
    assert summary["ids"] == sorted([added.id, doomed_id])


def test_machine_run_row_commits_with_each_batch(session, db):
    """A run that dies later still has its earlier batches on record."""
    with pytest.raises(RuntimeError):
        with machine_run(session, "sync", "pilot"):
            session.add(Pilot(first_name="Batch", last_name="One"))
            session.commit()
            raise RuntimeError("provider went away")
    session.rollback()

    entries = _entries(db)
    assert len(entries) == 1
    assert entries[0].changes["Pilot"]["counts"]["create"] == 1


def test_machine_run_rollback_drops_uncommitted_counts(session, db):
    with machine_run(session, "sync", "pilot"):
        session.add(Pilot(first_name="Kept", last_name="X"))
        session.commit()
        session.add(Pilot(first_name="Lost", last_name="X"))
        session.flush()
        session.rollback()
    session.commit()

    entries = _entries(db)
    assert len(entries) == 1
    assert entries[0].changes["Pilot"]["counts"]["create"] == 1
    assert entries[0].changes["Pilot"]["total_ids"] == 1


def test_machine_run_failed_savepoint_drops_its_counts(session, db):
    with machine_run(session, "import", "pilot"):
        session.add(Pilot(first_name="Kept", last_name="X"))
        session.flush()
        nested = session.begin_nested()
        session.add(Pilot(first_name="Lost", last_name="X"))
        session.flush()
        nested.rollback()
        with session.begin_nested():
            session.add(Pilot(first_name="Also", last_name="Kept"))
    session.commit()

    assert _entries(db)[0].changes["Pilot"]["counts"]["create"] == 2
    assert db.query(Pilot).count() == 2


def test_machine_run_caps_ids_and_states_total(session, db):
    with machine_run(session, "import", "pilot"):
        session.add_all(Pilot(first_name=f"P{i}", last_name="X") for i in range(505))
        session.flush()
    session.commit()

    summary = _entries(db)[0].changes["Pilot"]
    assert len(summary["ids"]) == 500
    assert summary["total_ids"] == 505
    assert summary["counts"]["create"] == 505


def test_machine_run_with_no_writes_still_writes_summary(session, db):
    with machine_run(session, "sync", "flight"):
        pass
    session.commit()

    entries = _entries(db)
    assert len(entries) == 1
    assert entries[0].changes == {}


def test_machine_run_counts_alerts_and_skips_status_settings(session, db):
    from app.models import Alert

    with machine_run(session, "alerts", "alert"):
        session.add(Alert(type="t", severity="low", title="a", message="m"))
        session.add(Setting(key="last_sync_result", value="{}"))
        session.flush()
    session.commit()

    entries = _entries(db)
    assert len(entries) == 1
    assert set(entries[0].changes) == {"Alert"}


def test_nested_machine_run_joins_the_outer_one(session, db):
    with machine_run(session, "sync", "pilot"):
        with machine_run(session, "import", "pilot"):
            session.add(Pilot(first_name="A", last_name="B"))
            session.flush()
    session.commit()

    entries = _entries(db)
    assert len(entries) == 1
    assert entries[0].action == "sync"


def test_capture_resumes_after_machine_run(session, db):
    with machine_run(session, "sync", "pilot"):
        pass
    _pilot(session)

    assert [e.action for e in _entries(db)] == ["sync", "create"]


def test_person_edit_in_another_session_during_run_is_logged_in_full(session, db, _engines):
    SessionLocal, _ = _engines
    pilot = _pilot(session)
    _clear_audit(db)
    other = SessionLocal()
    try:
        with machine_run(session, "sync", "pilot"):
            person_pilot = other.get(Pilot, pilot.id)
            person_pilot.notes = "by hand"
            other.commit()
        session.commit()
    finally:
        other.close()

    assert sorted(e.action for e in _entries(db)) == ["sync", "update"]


def test_login_token_actor_is_recorded(client, db, admin_user, admin_headers):
    resp = client.post("/api/pilots", headers=admin_headers, json={"first_name": "Ann", "last_name": "Lee"})
    assert resp.status_code in (200, 201)

    entries = _entries(db, entity_type="pilot")
    assert len(entries) == 1
    assert entries[0].user_username == admin_user.username
    assert entries[0].changes["first_name"] == {"old": None, "new": "Ann"}


def test_api_token_actor_is_recorded(client, db, admin_user):
    raw = api_tokens.generate_token()
    db.add(ApiToken(name="ha", token_hash=api_tokens.hash_token(raw), token_prefix=raw[:8],
                    user_id=admin_user.id, read_only=False))
    db.commit()

    resp = client.post("/api/pilots", headers={"Authorization": f"Bearer {raw}"},
                       json={"first_name": "Ann", "last_name": "Lee"})
    assert resp.status_code in (200, 201)

    entries = _entries(db, entity_type="pilot")
    assert len(entries) == 1
    assert entries[0].user_id == admin_user.id
    assert entries[0].user_username == admin_user.username


def test_login_records_the_username(client, db, admin_user):
    from tests.conftest import ADMIN_PASSWORD

    resp = client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert resp.status_code == 200

    assert _entries(db, action="login")[0].user_username == "admin"


def test_setting_route_writes_one_entry_with_values(client, db, admin_headers):
    db.add(Setting(key="org_name", value="Old"))
    db.commit()

    resp = client.put("/api/settings", headers=admin_headers, json={"key": "org_name", "value": "New"})
    assert resp.status_code == 200

    entries = _entries(db, entity_type="setting")
    assert len(entries) == 1
    assert entries[0].entity_name == "org_name"
    assert entries[0].changes == {"value": {"old": "Old", "new": "New"}}


def test_secret_setting_route_hides_the_value(client, db, admin_headers):
    resp = client.put("/api/settings", headers=admin_headers,
                      json={"key": "smtp_password", "value": RAW_SECRET})
    assert resp.status_code == 200

    entries = _entries(db, entity_type="setting")
    assert len(entries) == 1
    assert RAW_SECRET not in str(entries[0].changes)
    assert entries[0].changes == {"value": {"old": MARKER, "new": MARKER}}


def test_route_that_logged_after_commit_writes_one_entry(client, db, admin_headers):
    resp = client.post("/api/operating-authorities", headers=admin_headers,
                       json={"authority_type": "part_107_waiver", "title": "Waiver"})
    assert resp.status_code == 201

    assert len(_entries(db, entity_type="operating_authority")) == 1


def test_person_bulk_edit_logs_each_flight_with_values(client, db, admin_headers):
    flights = [Flight(purpose="Patrol"), Flight(purpose="Training")]
    db.add_all(flights)
    db.commit()

    resp = client.post("/api/flights/bulk-update", headers=admin_headers, json={
        "flight_ids": [f.id for f in flights], "purpose": "Mapping"})
    assert resp.status_code == 200

    entries = _entries(db, entity_type="flight")
    assert [e.action for e in entries] == ["bulk_update", "update", "update"]
    by_flight = {e.entity_id: e.changes for e in entries[1:]}
    assert by_flight == {
        flights[0].id: {"purpose": {"old": "Patrol", "new": "Mapping"}},
        flights[1].id: {"purpose": {"old": "Training", "new": "Mapping"}},
    }
