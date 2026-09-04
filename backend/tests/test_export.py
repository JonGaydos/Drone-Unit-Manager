"""Fleet equipment CSV exports.

Six of the seven Fleet Management tabs had no export at all; only Vehicles did.
They now share one generic endpoint under /export/fleet/, namespaced on purpose:
a bare /export/{type}/csv would be a catch-all registered ahead of the named CSV
routes and would swallow every one of them. That is pinned by a test here,
because the failure is silent - the named routes simply start 404ing.
"""

import csv
import io

from app.models.attachment import Attachment
from app.models.battery import Battery
from app.models.controller import Controller
from app.models.dock import Dock
from app.models.other_equipment import OtherEquipment
from app.models.sensor import SensorPackage

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
