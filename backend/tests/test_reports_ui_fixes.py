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


# --- E-3: upcoming expirations start today ---


def test_upcoming_expirations_leave_out_certs_that_already_expired(client, db, admin_headers):
    from app.models.certification import CertificationType, PilotCertification
    from app.models.pilot import Pilot
    pilot = _add(db, Pilot(first_name="Robin", last_name="Vale", status="active"))
    ct = _add(db, CertificationType(name="Part 107", category="faa"))
    soon = _add(db, PilotCertification(pilot_id=pilot.id, certification_type_id=ct.id, status="active",
                                       expiration_date=TODAY + timedelta(days=10)))
    _add(db, PilotCertification(pilot_id=pilot.id, certification_type_id=ct.id, status="active",
                                expiration_date=date(2019, 1, 1)))
    today = _add(db, PilotCertification(pilot_id=pilot.id, certification_type_id=ct.id, status="active",
                                        expiration_date=TODAY))
    r = client.get("/api/dashboard/upcoming-expirations", headers=admin_headers)
    assert r.status_code == 200
    assert [row["expiration_date"] for row in r.json()] == [str(today.expiration_date), str(soon.expiration_date)]


# --- E-8: Pilot Hours totals include pilots who flew and later left ---


def test_pilot_hours_report_keeps_inactive_pilots_who_flew_in_the_period(client, db, admin_headers):
    from app.models.flight import Flight
    from app.models.pilot import Pilot
    active, left, never = _add(db,
                               Pilot(first_name="Robin", last_name="Vale", status="active"),
                               Pilot(first_name="Casey", last_name="Moor", status="inactive"),
                               Pilot(first_name="Avery", last_name="Stone", status="inactive"))
    _add(db, Flight(pilot_id=active.id, date=date(2024, 3, 1), duration_seconds=3600),
         Flight(pilot_id=left.id, date=date(2024, 4, 1), duration_seconds=7200))
    body = {"report_type": "pilot_hours", "date_from": "2024-01-01", "date_to": "2024-12-31"}
    data = client.post("/api/reports/generate", headers=admin_headers, json=body).json()
    assert sorted(r["pilot"] for r in data["rows"]) == ["Casey Moor", "Robin Vale"]
    assert data["summary"]["total_hours"] == 3.0
    summary = client.post("/api/reports/generate", headers=admin_headers,
                          json={**body, "report_type": "flight_summary"}).json()["summary"]
    assert data["summary"]["total_hours"] == summary["total_hours"]


# --- E-9: PDF charts keep their aspect ratio ---


def test_pdf_chart_image_keeps_the_chart_aspect_ratio():
    from PIL import Image
    from app.routers.reports import _chart_image, _generate_chart
    buf = _generate_chart("battery_status", {"rows": [{"status": "active"}, {"status": "retired"}]})
    with Image.open(buf) as img:
        ratio = img.size[0] / img.size[1]
    buf.seek(0)
    flowable = _chart_image(buf, max_width=468, max_height=216)
    assert flowable.drawWidth <= 468 and flowable.drawHeight <= 216
    assert abs(flowable.drawWidth / flowable.drawHeight - ratio) < 0.01


# --- E-10: point-in-time reports do not claim a date range ---


def test_dateless_report_masthead_reads_as_of_today_not_the_date_range():
    from app.routers.reports import ReportConfig, _pdf_masthead, _pdf_theme
    for report_type in ("battery_status", "pilot_certifications"):
        config = ReportConfig(report_type=report_type, date_from=date(2026, 1, 1))
        texts = [p.text for p in _pdf_masthead({"title": "Report", "summary": {}}, config, "Unit", None, _pdf_theme())]
        assert not any("Date Range" in t for t in texts), (report_type, texts)
        assert any(f"As of {TODAY}" in t for t in texts), (report_type, texts)
    config = ReportConfig(report_type="flight_summary", date_from=date(2026, 1, 1))
    texts = [p.text for p in _pdf_masthead({"title": "Report", "summary": {}}, config, "Unit", None, _pdf_theme())]
    assert any("Date Range: 2026-01-01 to Present" in t for t in texts)
