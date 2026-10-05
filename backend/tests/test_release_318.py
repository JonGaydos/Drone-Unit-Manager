"""3.1.8: a clear error when a data folder is not writable, local dates for
spreadsheet imports, pilot contact details kept from viewers, and the smaller
fixes found testing 3.1.7 on staging."""

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest
from alembic import command
from PIL import Image

import app.config
import app.main
from app.routers.auth import create_token
from app.config import settings
from app.models.certification import CertificationType, PilotCertification
from app.models.flight import Flight
from app.models.mission_log import MissionLog
from app.models.mission_log_pilot import MissionLogPilot
from app.models.pilot import Pilot
from app.models.setting import Setting
from app.services.excel_import import import_skydio_csv
from tests.conftest import _seed_user
from tests.test_maintenance_batch8 import _alembic, _insert


@pytest.fixture
def upload_root(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", root)
    return root


@pytest.fixture
def central(db):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()


@pytest.fixture
def pilot_record(db):
    p = Pilot(first_name="Kim", last_name="Ray", email="kim@example.org", phone="555-111-2222",
              phone_type="personal", phone_work="555-333-4444", status="active")
    db.add(p)
    db.commit()
    return p


@pytest.fixture
def viewer_headers(db):
    viewer = _seed_user(db, username="viewer", role="viewer", password="ViewerPassw0rd!")
    return {"Authorization": f"Bearer {create_token(viewer.id)}"}


def _upload(client, headers, entity_type, entity_id):
    return client.post("/api/documents/upload", headers=headers,
                       data={"entity_type": entity_type, "entity_id": str(entity_id),
                             "document_type": "other", "title": "Doc"},
                       files={"file": ("doc.pdf", b"%PDF-1.4 test", "application/pdf")})


# 1. A folder the app cannot write to -------------------------------------------------

def test_an_unwritable_folder_is_named_not_a_bare_500(client, admin_headers, upload_root, monkeypatch):
    def refuse(self, data):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "write_bytes", refuse)
    resp = _upload(client, admin_headers, "general", 1)
    assert resp.status_code == 500
    assert "not writable" in resp.json()["detail"]


def test_health_warns_about_unwritable_upload_folders(client, upload_root, monkeypatch):
    (upload_root / "documents" / "vehicle").mkdir(parents=True)
    locked = str(upload_root / "documents" / "vehicle")
    real_access = os.access
    monkeypatch.setattr(app.main.os, "access", lambda path, mode: path != locked and real_access(path, mode))
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "1 upload folder(s) are not writable by the app; uploads into them will fail" in body["warnings"]


# 2. Spreadsheet imports dated by the local day ---------------------------------------

def test_skydio_takeoff_is_utc_and_the_date_is_local(db, central):
    csv_text = "Flight ID,Vehicle,Pilot,Takeoff,Duration (seconds)\nabc-1,X10-1,Jane Doe,2026-01-01 03:30:00,600\n"
    import_skydio_csv(db, csv_text.encode())
    flight = db.query(Flight).one()
    assert flight.takeoff_time == datetime(2026, 1, 1, 3, 30)
    assert flight.date == date(2025, 12, 31)


def test_a_local_takeoff_time_is_stored_as_utc(db, central):
    csv_text = "Flight ID,Vehicle,Pilot,Local Takeoff Time,Duration (seconds)\nabc-2,X10-1,Jane Doe,2025-12-31 21:30:00,600\n"
    import_skydio_csv(db, csv_text.encode())
    flight = db.query(Flight).one()
    assert flight.takeoff_time == datetime(2026, 1, 1, 3, 30)
    assert flight.date == date(2025, 12, 31)


def test_migration_redates_spreadsheet_imports_only(tmp_path, monkeypatch):
    path = tmp_path / "m.db"
    url = f"sqlite:///{path.as_posix()}"
    monkeypatch.setattr(app.config.settings, "DATABASE_URL", url)
    command.upgrade(_alembic(url), "0009_end_schedules_for_retired_equipment")

    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO settings (key, value) VALUES ('display_timezone', 'America/Chicago')")
    rows = {
        "excel": ("excel_import", "2026-01-01", "2026-01-01 03:30:00"),
        "csv": ("skydio_csv", "2026-01-01", "2026-01-01 03:30:00"),
        "corrected": ("excel_import", "2025-12-30", "2026-01-01 03:30:00"),
        "daytime": ("excel_import", "2026-01-01", "2026-01-01 18:00:00"),
        "manual": ("manual", "2026-01-01", "2026-01-01 03:30:00"),
    }
    for fid, (source, day, takeoff) in enumerate(rows.values(), start=1):
        _insert(conn, "flights", id=fid, data_source=source, date=day, takeoff_time=takeoff)
    conn.commit()
    conn.close()

    command.upgrade(_alembic(url), "head")
    conn = sqlite3.connect(path)
    dates = {name: conn.execute("SELECT date FROM flights WHERE id = ?", (i,)).fetchone()[0]
             for i, name in enumerate(rows, start=1)}
    conn.close()
    assert dates == {"excel": "2025-12-31", "csv": "2025-12-31", "corrected": "2025-12-30",
                     "daytime": "2026-01-01", "manual": "2026-01-01"}


# 3. Pilot contact details kept from viewers -----------------------------------------

CONTACTS = ("email", "phone", "phone_type", "phone_work")


def test_viewers_get_pilots_without_contact_details(client, viewer_headers, pilot_record):
    listed = client.get("/api/pilots", headers=viewer_headers).json()[0]
    single = client.get(f"/api/pilots/{pilot_record.id}", headers=viewer_headers).json()
    assert [listed[f] for f in CONTACTS] == [None] * 4
    assert [single[f] for f in CONTACTS] == [None] * 4
    assert single["full_name"] == "Kim Ray"


def test_other_roles_still_see_contact_details(client, pilot_headers, pilot_record):
    single = client.get(f"/api/pilots/{pilot_record.id}", headers=pilot_headers).json()
    assert single["email"] == "kim@example.org"
    assert single["phone_work"] == "555-333-4444"


def test_viewer_search_neither_shows_nor_matches_email(client, viewer_headers, admin_headers, pilot_record):
    by_name = client.get("/api/search?q=Kim", headers=viewer_headers).json()["results"]
    by_email = client.get("/api/search?q=example.org", headers=viewer_headers).json()["results"]
    admin_by_email = client.get("/api/search?q=example.org", headers=admin_headers).json()["results"]
    assert [r["subtitle"] for r in by_name if r["type"] == "pilot"] == ["active"]
    assert [r for r in by_email if r["type"] == "pilot"] == []
    assert admin_by_email[0]["subtitle"] == "kim@example.org"


def test_viewer_flights_csv_names_the_pilot_without_email(client, db, viewer_headers, pilot_record):
    db.add(Flight(pilot_id=pilot_record.id, date=date(2026, 9, 1)))
    db.commit()
    text = client.get("/api/export/flights/csv", headers=viewer_headers).text
    assert "Kim Ray" in text
    assert "kim@example.org" not in text


def test_viewer_compliance_currency_list_has_no_email(client, db, viewer_headers, pilot_record):
    from app.models.currency_rule import CurrencyRule
    db.add(CurrencyRule(name="90-day", required_hours=1, period_days=90))
    db.commit()
    entries = client.get("/api/dashboard/compliance", headers=viewer_headers).json()["pilot_currency_status"]
    assert [e["email"] for e in entries] == [None]


# Smaller fixes ---------------------------------------------------------------------

def test_mission_search_runs_in_the_database(client, db, admin_headers, pilot_record):
    old = MissionLog(date=date(2020, 1, 1), title="Old search", case_number="2020-0001", man_hours=1, status="completed")
    db.add(old)
    db.add(MissionLog(date=date(2026, 1, 1), title="100% coverage", man_hours=1, status="completed"))
    db.commit()
    db.add(MissionLogPilot(mission_log_id=old.id, pilot_id=pilot_record.id, hours=1))
    db.commit()

    def titles(text):
        resp = client.get("/api/mission-logs", headers=admin_headers, params={"search": text, "limit": 1})
        return [m["title"] for m in resp.json()]

    assert titles("2020-0001") == ["Old search"]
    assert titles("kim ray") == ["Old search"]
    assert titles("100%") == ["100% coverage"]
    assert titles("0%c") == []


def test_deleting_a_cert_type_in_use_says_how_to_keep_it(client, db, admin_headers, pilot_record):
    ct = CertificationType(name="Night ops", category="custom")
    db.add(ct)
    db.commit()
    db.add(PilotCertification(pilot_id=pilot_record.id, certification_type_id=ct.id, status="complete"))
    db.commit()
    resp = client.delete(f"/api/certification-types/{ct.id}", headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"].startswith("In use by 1 pilot certification record(s). Hide it instead")


def test_report_logo_is_scaled_before_it_is_embedded(client, db, admin_headers, upload_root):
    (upload_root / "org").mkdir()
    noise = Image.frombytes("RGB", (1600, 1600), os.urandom(1600 * 1600 * 3))
    noise.save(upload_root / "org" / "logo.png")
    assert (upload_root / "org" / "logo.png").stat().st_size > 5_000_000
    db.add(Setting(key="org_logo", value="/api/settings/logo"))
    db.commit()
    resp = client.post("/api/reports/generate/pdf", headers=admin_headers,
                       json={"report_type": "flight_summary"})
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
    assert len(resp.content) < 3_000_000


def test_a_pilot_attaches_documents_to_their_own_record_only(client, db, pilot_user, pilot_headers, upload_root):
    own = Pilot(first_name="Pat", last_name="Own", status="active")
    other = Pilot(first_name="Sam", last_name="Other", status="active")
    db.add_all([own, other])
    db.commit()
    pilot_user.pilot_id = own.id
    db.commit()
    cert_type = CertificationType(name="Part 107", category="faa")
    db.add(cert_type)
    db.commit()
    other_cert = PilotCertification(pilot_id=other.id, certification_type_id=cert_type.id, status="complete")
    db.add(other_cert)
    db.commit()

    assert _upload(client, pilot_headers, "pilot", own.id).status_code == 200
    assert _upload(client, pilot_headers, "pilot", other.id).status_code == 403
    assert _upload(client, pilot_headers, "certification", other_cert.id).status_code == 403
    assert _upload(client, pilot_headers, "maintenance", 42).status_code == 200
