"""Batch 8 maintenance and compliance correctness: completed tasks stop
showing as overdue, retired equipment stops counting, alerts are per aircraft,
currency reads only the flights that can count, a fuller health check, and
the small fixes that came with them."""

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

import app.config
from app.models.alert import Alert
from app.models.battery import Battery
from app.models.controller import Controller
from app.models.currency_rule import CurrencyRule
from app.models.flight import Flight
from app.models.maintenance import MaintenanceRecord
from app.models.maintenance_schedule import MaintenanceSchedule
from app.models.pilot import Pilot
from app.models.telemetry import TelemetryPoint
from app.models.vehicle import Vehicle
from app.routers.currency import flights_by_pilot
from app.services.scheduler import check_maintenance_schedules
from app.services.sync_manager import _find_equipment_by_serial

SCHEDULES = "/api/maintenance/schedules"


def _vehicle(db, serial="V-1", status="active"):
    v = Vehicle(serial_number=serial, manufacturer="Skydio", model="X10", status=status)
    db.add(v)
    db.commit()
    return v


def _schedule(db, entity_type, entity_id, name="Monthly check", days_ago=3):
    s = MaintenanceSchedule(name=name, entity_type=entity_type, entity_id=entity_id, frequency="monthly",
                            next_due=date.today() - timedelta(days=days_ago), is_active=True)
    db.add(s)
    db.commit()
    return s


# 1. A task done on time is not overdue ---------------------------------------------

def test_completing_a_schedule_twice_leaves_one_current_due_date(client, db, admin_headers):
    v = _vehicle(db)
    sid = _schedule(db, "vehicle", v.id).id
    client.post(f"{SCHEDULES}/{sid}/complete", headers=admin_headers)
    # The first completion's record now carries a due date in the past.
    first = db.query(MaintenanceRecord).one()
    first.next_due_date = date.today() - timedelta(days=5)
    first.performed_date = date.today() - timedelta(days=35)
    db.commit()
    client.post(f"{SCHEDULES}/{sid}/complete", headers=admin_headers)

    due = client.get("/api/dashboard/maintenance-due", headers=admin_headers).json()
    assert all(item["days_remaining"] >= 0 for item in due)
    upcoming = client.get("/api/maintenance?upcoming=true", headers=admin_headers).json()
    assert len(upcoming) == 1
    assert upcoming[0]["next_due_date"] >= date.today().isoformat()


def test_an_ad_hoc_due_date_for_a_different_task_still_shows(client, db, admin_headers):
    db.add_all([
        MaintenanceRecord(entity_type="vehicle", entity_id=1, maintenance_type="inspection", description="Gimbal",
                          performed_date=date(2026, 1, 1), next_due_date=date.today() + timedelta(days=10)),
        MaintenanceRecord(entity_type="vehicle", entity_id=1, maintenance_type="repair", description="Arm swap",
                          performed_date=date(2026, 2, 1)),
    ])
    db.commit()
    upcoming = client.get("/api/maintenance?upcoming=true", headers=admin_headers).json()
    assert [r["description"] for r in upcoming] == ["Gimbal"]


# 2. Equipment leaving service takes its schedules with it --------------------------

def test_retiring_a_vehicle_ends_its_schedules(client, db, admin_headers):
    v = _vehicle(db)
    s = _schedule(db, "vehicle", v.id)
    assert client.delete(f"/api/vehicles/{v.id}", headers=admin_headers).status_code == 200
    db.expire_all()
    assert db.get(MaintenanceSchedule, s.id).is_active is False


def test_marking_equipment_retired_ends_its_schedules(client, db, admin_headers):
    b = Battery(serial_number="B-1", status="active")
    db.add(b)
    db.commit()
    s = _schedule(db, "battery", b.id)
    client.patch(f"/api/batteries/{b.id}", headers=admin_headers, json={"status": "retired"})
    db.expire_all()
    assert db.get(MaintenanceSchedule, s.id).is_active is False


def test_deleting_equipment_ends_its_schedules(client, db, admin_headers):
    c = Controller(serial_number="C-1", status="active")
    db.add(c)
    db.commit()
    s = _schedule(db, "controller", c.id)
    assert client.delete(f"/api/controllers/{c.id}", headers=admin_headers).status_code == 200
    db.expire_all()
    assert db.get(MaintenanceSchedule, s.id).is_active is False


def test_an_edit_that_keeps_equipment_in_service_leaves_schedules_alone(client, db, admin_headers):
    b = Battery(serial_number="B-2", status="active")
    db.add(b)
    db.commit()
    s = _schedule(db, "battery", b.id)
    client.patch(f"/api/batteries/{b.id}", headers=admin_headers, json={"notes": "cycled"})
    db.expire_all()
    assert db.get(MaintenanceSchedule, s.id).is_active is True


MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def _alembic(url):
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _insert(conn, table, **values):
    """Insert a row, giving every other required column a plain value."""
    for _, name, col_type, notnull, default, pk in conn.execute(f"PRAGMA table_info({table})"):
        if notnull and default is None and not pk and name not in values:
            numeric = any(t in (col_type or "").upper() for t in ("INT", "BOOL", "FLOAT", "NUM", "REAL"))
            values[name] = 0 if numeric else "x"
    cols = ", ".join(values)
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({', '.join('?' * len(values))})", list(values.values()))


def test_migration_ends_schedules_on_equipment_already_out_of_service(tmp_path, monkeypatch):
    path = tmp_path / "m.db"
    url = f"sqlite:///{path.as_posix()}"
    monkeypatch.setattr(app.config.settings, "DATABASE_URL", url)
    command.upgrade(_alembic(url), "0008_local_flight_dates")

    conn = sqlite3.connect(path)
    for vid, status in ((1, "active"), (2, "retired"), (3, "damaged")):
        _insert(conn, "vehicles", id=vid, serial_number=f"V{vid}", status=status)
    schedules = {"live": ("vehicle", 1), "retired": ("vehicle", 2), "damaged": ("vehicle", 3),
                 "deleted": ("vehicle", 99), "org": ("organization", None)}
    ids = {}
    for name, (etype, eid) in schedules.items():
        ids[name] = conn.execute(
            "INSERT INTO maintenance_schedules (name, entity_type, entity_id, frequency, is_active) "
            "VALUES (?, ?, ?, 'monthly', 1)", (name, etype, eid)).lastrowid
    conn.commit()
    conn.close()

    command.upgrade(_alembic(url), "head")
    conn = sqlite3.connect(path)
    active = {name: conn.execute("SELECT is_active FROM maintenance_schedules WHERE id = ?", (i,)).fetchone()[0]
              for name, i in ids.items()}
    conn.close()
    assert active == {"live": 1, "retired": 0, "damaged": 0, "deleted": 0, "org": 1}


# 3. One alert per aircraft ----------------------------------------------------------

def test_same_task_on_a_second_aircraft_still_raises_its_alert(db):
    """Alerts were matched on the task name alone, so while aircraft A had an
    open "Monthly check" alert, B's overdue "Monthly check" raised nothing."""
    a, b = _vehicle(db, "V-A"), _vehicle(db, "V-B")
    _schedule(db, "vehicle", a.id)
    check_maintenance_schedules(db)
    _schedule(db, "vehicle", b.id)
    check_maintenance_schedules(db)
    check_maintenance_schedules(db)
    alerts = db.query(Alert).filter(Alert.type == "maintenance_due").all()
    assert sorted(x.entity_id for x in alerts) == sorted([a.id, b.id])


# 4. Currency reads only flights that can count ------------------------------------

def test_currency_loads_only_flights_inside_the_longest_period(db):
    pilot = Pilot(first_name="Kim", last_name="Ray", status="active")
    db.add(pilot)
    db.commit()
    db.add_all([
        Flight(pilot_id=pilot.id, date=date.today() - timedelta(days=10), duration_seconds=600),
        Flight(pilot_id=pilot.id, date=date.today() - timedelta(days=400), duration_seconds=600),
    ])
    rules = [CurrencyRule(name="90-day", required_hours=1, period_days=90),
             CurrencyRule(name="180-day", required_hours=1, period_days=180)]
    db.add_all(rules)
    db.commit()
    loaded = flights_by_pilot(db, [pilot.id], rules)
    assert [f.date for f in loaded[pilot.id]] == [date.today() - timedelta(days=10)]
    assert flights_by_pilot(db, [pilot.id], []) == {}


# 5. Health ------------------------------------------------------------------------------

def test_health_checks_both_databases_and_lists_warnings(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["telemetry_database"] == "connected"
    assert "The background scheduler is not running" in body["warnings"]
    assert "No backup in the last 26 hours" in body["warnings"]


# 6. Small fixes -----------------------------------------------------------------------

def test_the_apps_own_flights_csv_imports_back(client, db, admin_headers):
    csv_text = "Date,Pilot,Purpose,Duration (s)\n2026-09-01,,Training,600\n"
    resp = client.post("/api/export/flights/import", headers=admin_headers,
                       files={"file": ("flights.csv", csv_text.encode(), "text/csv")})
    assert resp.json()["imported"] == 1, resp.json()
    assert db.query(Flight).one().date == date(2026, 9, 1)


def test_refresh_reads_the_short_metric_names():
    from app.routers.flights import _refresh_location_and_metrics
    flight = Flight()
    _refresh_location_and_metrics(flight, {"max_speed": 12.5, "max_altitude": 90, "distance": 800}, [])
    assert (flight.max_speed_mps, flight.max_altitude_m, flight.distance_m) == (12.5, 90, 800)


def test_zero_readings_stay_zero(client, db, telemetry_db, admin_headers):
    flight = Flight(date=date(2026, 9, 1))
    db.add(flight)
    db.commit()
    telemetry_db.add(TelemetryPoint(flight_id=flight.id, timestamp_ms=0, altitude_m=0.0, speed_mps=0.0,
                                    heading_deg=0.0, battery_pct=97.0))
    telemetry_db.commit()
    point = client.get(f"/api/telemetry/flight/{flight.id}", headers=admin_headers).json()[0]
    assert (point["altitude_m"], point["speed_mps"], point["heading_deg"]) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize("lookup,expected", [
    ("K01-231117-1-00061", "k01-231117-1-00061"),   # exact, any case
    ("-231117-1-00061", "k01-231117-1-00061"),      # unique short form
    ("-00099", None),                               # fits two batteries
    ("_1-0", None),                                 # an underscore is a character, not a wildcard
])
def test_serial_lookup(db, lookup, expected):
    db.add_all([Battery(serial_number="k01-231117-1-00061"), Battery(serial_number="k01-111111-1-00099"),
                Battery(serial_number="k01-222222-2-00099")])
    db.commit()
    found = _find_equipment_by_serial(db, Battery, lookup)
    assert (found.serial_number if found else None) == expected
