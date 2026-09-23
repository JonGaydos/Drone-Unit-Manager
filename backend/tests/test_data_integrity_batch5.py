"""Batch 5 sync correctness and data integrity: complete backups, provider
failures that are reported rather than swallowed, one sync at a time, deletes
that only follow a confirmed 404, honest telemetry flags, conservative pilot
matching, complete pilot merges, and 409s for deletes the database refuses."""

import json
import sqlite3
from datetime import date

import httpx
import pytest

from app.database import Base, set_sqlite_pragma
from app.integrations.base import ProviderCredentials
from app.integrations.skydio import SkydioProvider
from app.models.calendar_event import CalendarEvent
from app.models.certification import CertificationType, PilotCertification
from app.models.document import Document
from app.models.flight import Flight
from app.models.incident import Incident
from app.models.pilot import Pilot
from app.models.setting import Setting
from app.models.vehicle import Vehicle
from app.routers.auth import create_token
from app.routers.backup import EXPORT_ORDER
from app.services import sync_manager
from app.services.sync_lock import sync_guard
from app.services.sync_manager import SyncManager, SyncResult

CREDS = ProviderCredentials(api_token="t", token_id="id")
LAST_SYNC = "2026-01-01T00:00:00+00:00"


def _bearer(user):
    return {"Authorization": f"Bearer {create_token(user.id, user.token_version)}"}


def _http_error(status):
    request = httpx.Request("GET", "https://api.skydio.com/api/v0/x")
    return httpx.HTTPStatusError(str(status), request=request, response=httpx.Response(status, request=request))


def _configure_skydio(db):
    for key, value in (("skydio_api_token", "t"), ("skydio_token_id", "id"), ("last_sync_timestamp", LAST_SYNC)):
        db.add(Setting(key=key, value=value))
    db.commit()


def _setting(db, key):
    db.expire_all()
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else None


def _pilot(db, first, last, **kw):
    p = Pilot(first_name=first, last_name=last, status="active", **kw)
    db.add(p)
    db.commit()
    return p


class FakeProvider:
    """Every optional endpoint empty; override what a test needs."""

    def __init__(self, **overrides):
        self.__dict__.update(overrides)

    def sync_users(self, creds): return []
    def sync_vehicles(self, creds): return []
    def sync_flights(self, creds, since=None): return []
    def sync_flights_deep(self, creds): return []
    def sync_batteries(self, creds): return []
    def sync_controllers(self, creds): return []
    def sync_docks(self, creds): return []
    def sync_sensor_packages(self, creds): return []
    def sync_attachments(self, creds): return []
    def sync_media(self, creds, since=None): return []
    def get_flight_detail(self, creds, flight_id): return None
    def get_flight_telemetry(self, creds, flight_id): return []


# 1. Backups hold every table ------------------------------------------------------

def test_backup_exports_every_table():
    assert set(Base.metadata.tables) - {name for name, _ in EXPORT_ORDER} == set()


@pytest.mark.parametrize("table", ["calendar_events", "photo_flights", "photo_incidents"])
def test_new_backup_tables_follow_their_parents(table):
    position = {name: i for i, (name, _) in enumerate(EXPORT_ORDER)}
    for fk in Base.metadata.tables[table].foreign_keys:
        assert position[fk.column.table.name] < position[table]


# 2. A failed provider call is a failed sync --------------------------------------

def test_flight_fetch_error_propagates_from_the_provider():
    provider = SkydioProvider()
    provider._paginate = _failing_request(503)
    with pytest.raises(httpx.HTTPStatusError):
        provider.sync_flights(CREDS)


def test_skydio_outage_leaves_the_sync_mark_and_reports_failure(db, monkeypatch):
    _configure_skydio(db)

    def down(creds, since=None):
        raise _http_error(503)

    monkeypatch.setattr(sync_manager, "get_provider", lambda name: FakeProvider(sync_flights=down))
    result = SyncManager.sync_all("skydio", db)
    assert result.errors
    assert _setting(db, "last_sync_timestamp") == LAST_SYNC
    assert json.loads(_setting(db, "last_sync_result"))["status"] == "failure"


def test_clean_sync_advances_the_mark(db, monkeypatch):
    _configure_skydio(db)
    monkeypatch.setattr(sync_manager, "get_provider", lambda name: FakeProvider())
    assert SyncManager.sync_all("skydio", db).errors == []
    assert _setting(db, "last_sync_timestamp") != LAST_SYNC


def _failing_request(status):
    def request(*a, **k):
        raise _http_error(status)
    return request


def test_flight_detail_is_none_only_for_a_404():
    provider = SkydioProvider()
    provider._request = _failing_request(404)
    assert provider.get_flight_detail(CREDS, "F1") is None
    provider._request = _failing_request(503)
    with pytest.raises(httpx.HTTPStatusError):
        provider.get_flight_detail(CREDS, "F1")


# 3. One sync at a time --------------------------------------------------------------

@pytest.mark.parametrize("path", ["/api/sync/now", "/api/sync/deep", "/api/sync/telemetry", "/api/sync/cleanup"])
def test_second_sync_is_refused_while_one_runs(client, admin_headers, path):
    with sync_guard():
        assert client.post(path, headers=admin_headers).status_code == 409


def test_scheduled_sync_skips_while_one_runs(db, monkeypatch):
    from app.services import scheduler
    _configure_skydio(db)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
    monkeypatch.setattr(scheduler, "check_maintenance_schedules", lambda db: None)

    def must_not_run(*a, **k):
        raise AssertionError("sync ran while another held the lock")

    monkeypatch.setattr(SyncManager, "sync_all", must_not_run)
    with sync_guard():
        scheduler._run_scheduled_sync()


def test_a_flight_listed_twice_in_one_fetch_is_stored_once(db):
    rows = [{"external_id": "abc-123", "date": "2026-09-01"}, {"external_id": "ABC123", "date": "2026-09-01"}]
    result = SyncResult()
    sync_manager._upsert_flights(rows, [], db, result)
    db.commit()
    assert db.query(Flight).count() == 1
    assert (result.flights_new, result.flights_skipped) == (1, 1)


# 4. Deletes follow a confirmed 404, never an outage -----------------------------

def _dateless_flight(db, ext):
    f = Flight(external_id=ext, api_provider="skydio")
    db.add(f)
    db.commit()
    return f


def test_enrich_keeps_flights_it_could_not_look_up(client, db, admin_headers, monkeypatch):
    _configure_skydio(db)
    gone, unreachable = _dateless_flight(db, "GONE"), _dateless_flight(db, "DOWN")
    gone_id, down_id = gone.id, unreachable.id

    def detail(self, creds, flight_id):
        if flight_id == "DOWN":
            raise _http_error(503)
        return None

    monkeypatch.setattr(SkydioProvider, "get_flight_detail", detail)
    resp = client.post("/api/sync/enrich", headers=admin_headers)
    assert resp.status_code == 200
    db.expire_all()
    assert db.get(Flight, gone_id) is None
    assert db.get(Flight, down_id) is not None
    assert any("kept" in e for e in resp.json()["errors"])


def test_ghost_cleanup_deletes_only_confirmed_missing_flights(db):
    gone, unreachable = _dateless_flight(db, "GONE"), _dateless_flight(db, "DOWN")
    gone_id, down_id = gone.id, unreachable.id

    def detail(creds, flight_id):
        if flight_id == "DOWN":
            raise _http_error(503)
        return None

    result = SyncResult()
    sync_manager._enrich_flights(FakeProvider(get_flight_detail=detail), CREDS, db, result)
    db.expire_all()
    assert db.get(Flight, gone_id) is None
    assert db.get(Flight, down_id) is not None
    assert result.errors == []  # housekeeping, not a failure


def test_cleanup_detaches_incidents_instead_of_failing(client, db, admin_headers):
    empty = Flight()
    db.add(empty)
    db.commit()
    incident = Incident(date=date(2026, 9, 1), title="t", severity="minor", category="other",
                        description="d", flight_id=empty.id)
    db.add(incident)
    db.commit()
    resp = client.post("/api/sync/cleanup", headers=admin_headers)
    assert resp.status_code == 200 and resp.json()["deleted"] == 1
    db.expire_all()
    assert db.get(Incident, incident.id).flight_id is None


# 5. Telemetry flags say what was stored ------------------------------------------

@pytest.mark.parametrize("outcome,synced,has", [
    ([{"timestamp_ms": 1, "lat": 1.0, "lon": 2.0, "altitude_m": 10.0}], True, True),
    ([], True, False),
    (_http_error(404), True, False),
    (_http_error(503), False, False),
    (httpx.ConnectError("offline"), False, False),
])
def test_telemetry_flags_follow_what_was_stored(db, monkeypatch, outcome, synced, has):
    _configure_skydio(db)
    flight = Flight(external_id="T1", api_provider="skydio", date=date(2026, 9, 1))
    db.add(flight)
    db.commit()

    def fetch(creds, flight_id):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(sync_manager, "get_provider", lambda name: FakeProvider(get_flight_telemetry=fetch))
    SyncManager.batch_sync_telemetry(db)
    db.expire_all()
    stored = db.get(Flight, flight.id)
    assert (stored.telemetry_synced, stored.has_telemetry) == (synced, has)


# 6. Matching and merging --------------------------------------------------------------

def test_enrichment_does_not_overwrite_equipment_a_user_set(db):
    flight = Flight(battery_serial="MINE", sensor_package="SENSOR-MINE", attachment_top="Spotlight (1)")
    sync_manager._enrich_flight_equipment(flight, {
        "battery_serial": "-OTHER",
        "sensor_package": {"sensor_package_serial": "SENSOR-OTHER"},
        "attachments": [{"mount_point": "top", "attachment_type": "Speaker", "attachment_serial": "2"},
                        {"mount_point": "bottom", "attachment_type": "Light", "attachment_serial": "3"}],
    })
    assert (flight.battery_serial, flight.sensor_package, flight.attachment_top) == ("MINE", "SENSOR-MINE", "Spotlight (1)")
    assert flight.attachment_bottom == "Light (3)"


def test_ambiguous_pilot_names_match_no_one(db):
    _pilot(db, "John", "Smith")
    _pilot(db, "John", "Smith")
    only = _pilot(db, "Avery", "Stone")
    assert sync_manager._match_pilot(db, "John Smith") is None
    assert sync_manager._match_pilot(db, "John") is None
    assert sync_manager._match_pilot(db, "Avery") == only.id
    assert sync_manager._match_pilot(db, "Avery Stone") == only.id


def test_email_pattern_needs_a_single_candidate(db):
    _pilot(db, "Dana", "Smith")
    _pilot(db, "Drew", "Smith")
    assert sync_manager._find_pilot_by_email_pattern(db, "dsmith@agency.gov") is None
    only = _pilot(db, "Riley", "Quinn")
    assert sync_manager._find_pilot_by_email_pattern(db, "rquinn@agency.gov").id == only.id


def test_pilot_merge_moves_calendar_and_vehicle_links_and_keeps_the_later_certificate(client, db, admin_user):
    keeper, duplicate = _pilot(db, "Pat", "Lee"), _pilot(db, "Pat", "Lee")
    ctype = CertificationType(name="Part 107", category="faa")
    db.add(ctype)
    db.commit()
    older = PilotCertification(pilot_id=keeper.id, certification_type_id=ctype.id, expiration_date=date(2026, 1, 1))
    newer = PilotCertification(pilot_id=duplicate.id, certification_type_id=ctype.id, expiration_date=date(2028, 1, 1))
    db.add_all([older, newer])
    db.commit()
    doc = Document(entity_type="certification", entity_id=older.id, certification_id=older.id, pilot_id=keeper.id,
                   document_type="part_107", title="card", filename="c.pdf", file_path="/x/c.pdf",
                   mime_type="application/pdf", file_size_bytes=1)
    event = CalendarEvent(title="Leave", category="leave", start_date=date(2026, 10, 1), pilot_id=duplicate.id)
    vehicle = Vehicle(serial_number="V1", manufacturer="Skydio", model="X10", manual_location_pilot_id=duplicate.id)
    db.add_all([doc, event, vehicle])
    db.commit()
    newer_id, older_id = newer.id, older.id

    resp = client.post(f"/api/pilots/{keeper.id}/merge", headers=_bearer(admin_user), json={"source_id": duplicate.id})
    assert resp.status_code == 200
    db.expire_all()
    certs = db.query(PilotCertification).filter(PilotCertification.pilot_id == keeper.id).all()
    assert [c.id for c in certs] == [newer_id]
    assert db.get(PilotCertification, older_id) is None
    assert db.get(Document, doc.id).certification_id == newer_id
    assert db.get(CalendarEvent, event.id).pilot_id == keeper.id
    assert db.get(Vehicle, vehicle.id).manual_location_pilot_id == keeper.id


# 7. The database refusing a delete is a conflict, not a crash ---------------------

def test_deleting_a_certification_type_still_in_use_is_a_409(client, db, admin_headers):
    pilot = _pilot(db, "Sam", "Ortiz")
    ctype = CertificationType(name="Night ops", category="training")
    db.add(ctype)
    db.commit()
    db.add(PilotCertification(pilot_id=pilot.id, certification_type_id=ctype.id))
    db.commit()
    resp = client.delete(f"/api/certification-types/{ctype.id}", headers=admin_headers)
    assert resp.status_code == 409


def test_connections_wait_for_the_write_lock():
    conn = sqlite3.connect(":memory:")
    set_sqlite_pragma(conn, None)
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
