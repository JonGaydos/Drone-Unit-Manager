"""Fleet equipment CSV exports.

Six of the seven Fleet Management tabs had no export at all; only Vehicles did.
They now share one generic endpoint under /export/fleet/, namespaced on purpose:
a bare /export/{type}/csv would be a catch-all registered ahead of the named CSV
routes and would swallow every one of them. That is pinned by a test here,
because the failure is silent - the named routes simply start 404ing.
"""

import csv
import io
from datetime import date, datetime

from app.models.attachment import Attachment
from app.models.battery import Battery
from app.models.controller import Controller
from app.models.dock import Dock
from app.models.other_equipment import OtherEquipment
from app.models.sensor import SensorPackage
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.flight import Flight
from app.models.incident import Incident
from app.models.flight_approval import FlightPlan
from app.models.equipment_checkout import EquipmentCheckout

FLEET_URL = "/api/export/fleet/{}/csv"


def _rows(resp):
    return list(csv.DictReader(io.StringIO(resp.text)))


def _seed_fleet(db):
    db.add_all([
        Battery(serial_number="k01-1", nickname="X2 Battery 01", manufacturer="Skydio",
                model="SBAR21V1", vehicle_model="Skydio X2E", cycle_count=7, status="active"),
        Battery(serial_number="k01-2", nickname="X2 Battery 02", manufacturer="Skydio",
                model="SBAR21V1", status="retired"),
        Controller(serial_number="ctrl-1", nickname="X10 Controller", manufacturer="Skydio", status="active"),
        Dock(serial_number="dock-1", name="Rooftop Dock", location_name="HQ", status="active"),
        SensorPackage(serial_number="sens-1", name="Thermal", type="thermal", status="active"),
        Attachment(serial_number="att-1", name="Speaker", type="speaker", status="active"),
        OtherEquipment(name="Pelican case", category="case", serial_number="case-1", status="active"),
    ])
    db.commit()


def test_every_fleet_type_exports(client, db, admin_headers):
    _seed_fleet(db)
    expected_first_column = {
        "batteries": "Serial", "controllers": "Serial", "docks": "Serial",
        "sensors": "Serial", "attachments": "Serial", "other-equipment": "Name",
    }
    for kind, first_col in expected_first_column.items():
        resp = client.get(FLEET_URL.format(kind), headers=admin_headers)
        assert resp.status_code == 200, f"{kind}: {resp.text}"
        rows = _rows(resp)
        assert rows, f"{kind} exported no rows"
        assert first_col in rows[0], f"{kind} missing {first_col} column"
        assert f"filename={kind.replace('-', '_')}_export.csv" in resp.headers["content-disposition"]


def test_battery_export_carries_the_columns_the_tab_shows(client, db, admin_headers):
    _seed_fleet(db)

    rows = _rows(client.get(FLEET_URL.format("batteries"), headers=admin_headers))

    row = next(r for r in rows if r["Serial"] == "k01-1")
    assert row["Nickname"] == "X2 Battery 01"
    assert row["Vehicle Model"] == "Skydio X2E"
    assert row["Cycles"] == "7"
    assert row["Status"] == "active"


def test_export_includes_retired_equipment(client, db, admin_headers):
    """The Fleet page hides retired kit by default, but that is a viewing
    convenience. An export quietly missing it would be a poor audit record."""
    _seed_fleet(db)

    serials = {r["Serial"] for r in _rows(client.get(FLEET_URL.format("batteries"), headers=admin_headers))}

    assert serials == {"k01-1", "k01-2"}


def test_export_neutralizes_csv_formula_injection(client, db, admin_headers):
    """A nickname beginning with '=' would execute on open in Excel."""
    db.add(Battery(serial_number="evil-1", nickname="=cmd|'/c calc'!A1", status="active"))
    db.commit()

    row = next(r for r in _rows(client.get(FLEET_URL.format("batteries"), headers=admin_headers))
               if r["Serial"] == "evil-1")

    assert row["Nickname"].startswith("'="), "formula trigger was not neutralized"


def test_unknown_equipment_type_is_rejected(client, admin_headers):
    assert client.get(FLEET_URL.format("wombats"), headers=admin_headers).status_code == 404


def test_the_named_csv_routes_still_resolve(client, admin_headers):
    """Regression guard for route shadowing.

    A bare /export/{equipment_type}/csv sits ahead of these in registration
    order and would capture all of them, so each would 404 with "Unknown
    equipment type" while looking like a routing mystery. Namespacing the
    generic route under /fleet/ is what keeps these reachable.
    """
    for path in ["maintenance", "certifications", "audit", "incidents",
                 "flight-plans", "mission-logs", "training-logs",
                 "checklists", "equipment-checkouts", "pilots", "vehicles"]:
        resp = client.get(f"/api/export/{path}/csv", headers=admin_headers)
        assert resp.status_code == 200, f"/export/{path}/csv returned {resp.status_code}"


# ---------------------------------------------------------------------------
# Characterization coverage for the four complex CSV exports before they are
# refactored: flights, incidents, flight-plans, equipment-checkouts. Each pins
# the header row and a populated data row (including the optional-field and
# lookup branches), so a later refactor of these builders cannot change the
# output unnoticed.
# ---------------------------------------------------------------------------

def _seed_export_pilot(db, first="Ana", last="Alvarez", email=None):
    p = Pilot(first_name=first, last_name=last, status="active", email=email)
    db.add(p); db.commit(); db.refresh(p)
    return p


def _seed_export_vehicle(db, serial="SN-1", model="X10"):
    v = Vehicle(serial_number=serial, manufacturer="Skydio", model=model, status="active")
    db.add(v); db.commit(); db.refresh(v)
    return v


def test_flights_csv_headers_and_row(client, db, admin_headers):
    p = _seed_export_pilot(db, "Ana", "Alvarez", email="ana@example.gov")
    v = _seed_export_vehicle(db, "SN-1", "X10")
    db.add(Flight(date=date(2025, 6, 1), pilot_id=p.id, vehicle_id=v.id, duration_seconds=600,
                  external_id="F-1", purpose="Patrol", takeoff_address="Main St"))
    db.commit()

    resp = client.get("/api/export/flights/csv", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    rows = _rows(resp)
    assert rows
    assert "Purpose" in rows[0]
    r = rows[0]
    assert r["Pilot"] == "ana@example.gov"   # email preferred over the name
    assert r["Vehicle"] == "SN-1"
    assert r["Purpose"] == "Patrol"
    assert r["Battery"] == "N/A"             # empty equipment slot -> N/A
    assert "filename=flights_export.csv" in resp.headers["content-disposition"]


def test_flights_csv_date_filter(client, db, admin_headers):
    p = _seed_export_pilot(db)
    db.add_all([
        Flight(date=date(2025, 1, 1), pilot_id=p.id, duration_seconds=60, external_id="A"),
        Flight(date=date(2025, 6, 1), pilot_id=p.id, duration_seconds=60, external_id="B"),
    ])
    db.commit()

    rows = _rows(client.get("/api/export/flights/csv?date_from=2025-06-01", headers=admin_headers))
    assert len(rows) == 1


def test_incidents_csv_headers_and_row(client, db, admin_headers):
    p = _seed_export_pilot(db, "Bo", "Reed")
    db.add(Incident(date=date(2025, 5, 1), title="Bird strike", severity="minor",
                    category="near_miss", description="d", status="open",
                    report_type="incident", pilot_id=p.id, equipment_grounded=True))
    db.commit()

    rows = _rows(client.get("/api/export/incidents/csv", headers=admin_headers))
    assert rows
    assert "Report Type" in rows[0]
    r = rows[0]
    assert r["Title"] == "Bird strike"
    assert r["Pilot"] == "Bo Reed"
    assert r["Report Type"] == "incident"
    assert r["Equipment Grounded"] == "Yes"


def test_flight_plans_csv_headers_and_row(client, db, admin_user, admin_headers):
    p = _seed_export_pilot(db, "Cy", "Lang")
    v = _seed_export_vehicle(db, "V-9", "X2E")
    db.add(FlightPlan(title="Overwatch", date_planned=datetime(2025, 7, 1, 9, 0),
                      pilot_id=p.id, vehicle_id=v.id, location="Park", purpose="Event",
                      case_number="25-100", status="approved", submitted_by_id=admin_user.id))
    db.commit()

    rows = _rows(client.get("/api/export/flight-plans/csv", headers=admin_headers))
    assert rows
    assert "Date Planned" in rows[0]
    r = rows[0]
    assert r["Title"] == "Overwatch"
    assert r["Pilot"] == "Cy Lang"
    assert r["Vehicle"] == "Skydio X2E"
    assert r["Status"] == "approved"


def test_equipment_checkouts_csv_headers_and_row(client, db, admin_headers):
    p = _seed_export_pilot(db, "Di", "Vance")
    db.add(EquipmentCheckout(entity_type="vehicle", entity_id=1, entity_name="X10-1",
                             checked_out_by_id=p.id, checked_out_at=datetime(2025, 8, 1, 10, 0),
                             condition_out="good"))
    db.commit()

    rows = _rows(client.get("/api/export/equipment-checkouts/csv", headers=admin_headers))
    assert rows
    assert "Checked Out By" in rows[0]
    r = rows[0]
    assert r["Entity Name"] == "X10-1"
    assert r["Checked Out By"] == "Di Vance"
    assert r["Condition Out"] == "good"
    assert r["Checked In At"] == ""          # not returned yet -> empty
