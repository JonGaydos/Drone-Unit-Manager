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
