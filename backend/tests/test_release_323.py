"""3.2.3: CSV exports show server-stamped times in local time, and date filters
on those times use local days. Chicago is UTC-5 in October, so 01:27 UTC on
Oct 8 is 8:27 PM on Oct 7."""

import csv
import io
from datetime import date, datetime

import pytest

from app.models.audit_log import AuditLog
from app.models.checklist import ChecklistCompletion, ChecklistTemplate
from app.models.equipment_checkout import EquipmentCheckout
from app.models.pilot import Pilot
from app.models.setting import Setting

EVENING_UTC = datetime(2026, 10, 8, 1, 27, 43)    # Oct 7, 8:27:43 PM in Chicago
MORNING_UTC = datetime(2026, 10, 8, 14, 0, 0)     # Oct 8, 9:00 AM in Chicago


@pytest.fixture(autouse=True)
def chicago(db):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()


@pytest.fixture
def pilot(db):
    p = Pilot(first_name="Ann", last_name="Smith", status="active")
    db.add(p)
    db.commit()
    return p


def _rows(resp):
    assert resp.status_code == 200, resp.text
    return list(csv.reader(io.StringIO(resp.text)))[1:]


def _audit(db, when, name):
    db.add(AuditLog(user_id=None, user_name="x", action="create", entity_type="t",
                    entity_name=name, created_at=when))


# ── Local times in exports ───────────────────────────────────────────────────

def test_audit_export_shows_local_time(client, db, admin_headers):
    _audit(db, EVENING_UTC, "evening")
    db.commit()
    rows = _rows(client.get("/api/export/audit/csv", headers=admin_headers))
    assert rows[0][0] == "2026-10-07 20:27:43"


def test_checkout_export_shows_local_time_and_keeps_typed_return(client, db, admin_headers, pilot):
    db.add(EquipmentCheckout(entity_type="vehicle", entity_id=1, entity_name="Eagle",
                             checked_out_by_id=pilot.id, checked_out_at=EVENING_UTC,
                             checked_in_at=MORNING_UTC, expected_return=datetime(2026, 10, 8, 9, 30)))
    db.commit()
    row = _rows(client.get("/api/export/equipment-checkouts/csv", headers=admin_headers))[0]
    assert row[3] == "2026-10-07 20:27"   # checked out, converted
    assert row[4] == "2026-10-08 09:30"   # expected return, typed in, unchanged
    assert row[5] == "2026-10-08 09:00"   # checked in, converted


def test_checklist_export_shows_local_time(client, db, admin_headers, pilot):
    template = ChecklistTemplate(name="Preflight", items=[])
    db.add(template)
    db.flush()
    db.add(ChecklistCompletion(template_id=template.id, pilot_id=pilot.id, responses=[],
                               all_passed=True, completed_at=EVENING_UTC))
    db.commit()
    assert _rows(client.get("/api/export/checklists/csv", headers=admin_headers))[0][0] == "2026-10-07 20:27"


# ── Date filters use local days ──────────────────────────────────────────────

def test_audit_export_filters_by_local_day(client, db, admin_headers):
    _audit(db, EVENING_UTC, "evening")
    _audit(db, MORNING_UTC, "morning")
    db.commit()
    oct7 = _rows(client.get("/api/export/audit/csv", params={"date_from": "2026-10-07", "date_to": "2026-10-07"},
                            headers=admin_headers))
    oct8 = _rows(client.get("/api/export/audit/csv", params={"date_from": "2026-10-08", "date_to": "2026-10-08"},
                            headers=admin_headers))
    assert [r[5] for r in oct7] == ["evening"]
    assert [r[5] for r in oct8] == ["morning"]


def test_checkout_export_filters_by_local_day(client, db, admin_headers, pilot):
    db.add(EquipmentCheckout(entity_type="vehicle", entity_id=1, entity_name="Eagle",
                             checked_out_by_id=pilot.id, checked_out_at=EVENING_UTC))
    db.commit()
    params = {"date_from": "2026-10-07", "date_to": "2026-10-07"}
    assert len(_rows(client.get("/api/export/equipment-checkouts/csv", params=params, headers=admin_headers))) == 1
    params = {"date_from": "2026-10-08"}
    assert _rows(client.get("/api/export/equipment-checkouts/csv", params=params, headers=admin_headers)) == []


def test_checklist_list_filters_by_local_day(client, db, admin_headers, pilot):
    template = ChecklistTemplate(name="Preflight", items=[])
    db.add(template)
    db.flush()
    db.add(ChecklistCompletion(template_id=template.id, pilot_id=pilot.id, responses=[],
                               all_passed=True, completed_at=EVENING_UTC))
    db.commit()

    def count(**params):
        resp = client.get("/api/checklists/completions", params=params, headers=admin_headers)
        assert resp.status_code == 200, resp.text
        return len(resp.json())

    assert count(date_from="2026-10-07", date_to="2026-10-07") == 1
    assert count(date_from="2026-10-08") == 0
    assert count(date_to="2026-10-06") == 0


def test_local_day_start_follows_daylight_saving():
    from zoneinfo import ZoneInfo

    from app.services.local_time import local_day_start
    zone = ZoneInfo("America/Chicago")
    assert local_day_start(date(2026, 7, 1), zone).hour == 5    # CDT, UTC-5
    assert local_day_start(date(2026, 1, 15), zone).hour == 6   # CST, UTC-6
