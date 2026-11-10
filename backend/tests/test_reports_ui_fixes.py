"""Regression tests for the reports, dashboard and analytics fixes (staging
test 2026-11-08, Area 7)."""

from datetime import date, timedelta

from app.models.battery import Battery
from app.models.maintenance_schedule import MaintenanceSchedule
from app.models.vehicle import Vehicle

FLEET_HEALTH_URL = "/api/dashboard/analytics/fleet-health"
TODAY = date.today()


def _add(db, *rows):
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows[0] if len(rows) == 1 else rows


def _fleet_health(client, headers):
    r = client.get(FLEET_HEALTH_URL, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --- A-F22: average battery health ---


def test_fleet_health_averages_only_in_service_batteries_with_a_reading(client, db, admin_headers):
    _add(db,
         Battery(serial_number="BAT-A", status="active", health_pct=80.0),
         Battery(serial_number="BAT-B", status="charging", health_pct=76.0),
         Battery(serial_number="BAT-C", status="active", health_pct=None),
         Battery(serial_number="BAT-D", status="retired", health_pct=10.0),
         Battery(serial_number="BAT-E", status="damaged", health_pct=None))
    data = _fleet_health(client, admin_headers)
    assert data["summary"]["avg_battery_health"] == 78.0
    assert data["summary"]["total_batteries"] == 3
    assert sorted(b["serial"] for b in data["batteries"]) == ["BAT-A", "BAT-B", "BAT-C"]


def test_fleet_health_battery_average_is_null_without_readings(client, db, admin_headers):
    _add(db, Battery(serial_number="BAT-A", status="active", health_pct=None))
    data = _fleet_health(client, admin_headers)
    assert data["summary"]["avg_battery_health"] is None


# --- A-F42: Fleet Health scope ---


def _overdue(db, entity_type, entity_id):
    return _add(db, MaintenanceSchedule(
        name=f"{entity_type} check", entity_type=entity_type, entity_id=entity_id,
        frequency="monthly", is_active=True, next_due=TODAY - timedelta(days=3)))


def test_fleet_health_lists_every_in_service_vehicle(client, db, admin_headers):
    _add(db,
         Vehicle(serial_number="V-ACTIVE", manufacturer="Make", model="One", status="active"),
         Vehicle(serial_number="V-GROUNDED", manufacturer="Make", model="Two", status="maintenance"),
         Vehicle(serial_number="V-RETIRED", manufacturer="Make", model="Three", status="retired"),
         Vehicle(serial_number="V-DAMAGED", manufacturer="Make", model="Four", status="damaged"))
    data = _fleet_health(client, admin_headers)
    assert sorted(v["serial"] for v in data["vehicles"]) == ["V-ACTIVE", "V-GROUNDED"]
    assert data["summary"]["total_vehicles"] == 2


def test_fleet_health_overdue_total_counts_every_equipment_schedule(client, db, admin_headers):
    vehicle = _add(db, Vehicle(serial_number="V-GROUNDED", manufacturer="Make", model="Two", status="maintenance"))
    battery = _add(db, Battery(serial_number="BAT-A", status="active"))
    _overdue(db, "vehicle", vehicle.id)
    _overdue(db, "battery", battery.id)
    _overdue(db, "dock", 7)
    data = _fleet_health(client, admin_headers)
    assert data["vehicles"][0]["overdue_maintenance"] == 1
    assert data["summary"]["total_overdue_maintenance"] == 3


# --- E-4: vehicle hours carry the vehicle id the cross-filter keys on ---


def test_vehicle_hours_returns_the_vehicle_id(client, db, admin_headers):
    from app.models.flight import Flight
    vehicle = _add(db, Vehicle(serial_number="V-1", manufacturer="Make", model="One", nickname="Hawk", status="active"))
    _add(db, Flight(vehicle_id=vehicle.id, date=TODAY, duration_seconds=7200))
    r = client.get("/api/dashboard/analytics/vehicle-hours", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json() == [{"vehicle_id": vehicle.id, "vehicle_name": "Make One (Hawk)", "hours": 2.0}]


# --- E-7: PDFs with a very long pilot name ---

REPORT_PDF_URL = "/api/reports/generate/pdf"


def _long_name_pilot_with_flight(db):
    from app.models.flight import Flight
    from app.models.pilot import Pilot
    pilot = _add(db, Pilot(first_name="Long", last_name="N" * 10000, status="active"))
    _add(db, Flight(pilot_id=pilot.id, date=TODAY, duration_seconds=3600))
    return pilot


def test_pilot_hours_pdf_renders_with_a_very_long_pilot_name(client, db, admin_headers):
    _long_name_pilot_with_flight(db)
    r = client.post(REPORT_PDF_URL, headers=admin_headers, json={"report_type": "pilot_hours"})
    assert r.status_code == 200, r.text[:300]
    assert r.content.startswith(b"%PDF")


def test_pilot_activity_pdf_renders_with_a_very_long_pilot_name(client, db, admin_headers):
    _long_name_pilot_with_flight(db)
    r = client.post(REPORT_PDF_URL, headers=admin_headers, json={"report_type": "pilot_activity_summary"})
    assert r.status_code == 200, r.text[:300]
    assert r.content.startswith(b"%PDF")


def test_per_pilot_review_pdf_renders_with_a_very_long_pilot_name(client, db, admin_headers):
    pilot = _long_name_pilot_with_flight(db)
    r = client.post(REPORT_PDF_URL, headers=admin_headers, json={
        "report_type": "per_pilot_annual_review", "pilot_ids": [pilot.id]})
    assert r.status_code == 200, r.text[:300]


def test_pdf_chart_clips_a_very_long_pilot_label():
    from PIL import Image
    from app.routers.reports import _generate_chart
    for report_type, row in [
        ("pilot_hours", {"pilot": "N" * 10000, "hours": 1.0}),
        ("pilot_activity_summary", {"pilot": "N" * 10000, "flight_hours": 1.0, "mission_hours": 0, "training_hours": 0}),
    ]:
        buf = _generate_chart(report_type, {"rows": [row]})
        assert buf is not None, report_type
        with Image.open(buf) as img:
            assert img.size[0] < 2000, (report_type, img.size)
