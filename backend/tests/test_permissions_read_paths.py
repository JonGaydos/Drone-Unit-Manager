"""Search, dashboard, exports, reports and digests follow the view permissions."""

import csv
import io
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.certification import CertificationType, PilotCertification
from app.models.equipment_checkout import EquipmentCheckout
from app.models.flight import Flight
from app.models.flight_approval import FlightPlan
from app.models.incident import Incident
from app.models.audit_log import AuditLog
from app.models.battery import Battery
from app.models.attachment import Attachment
from app.models.maintenance_schedule import MaintenanceSchedule
from app.models.mission_log import MissionLog
from app.models.notification_preference import NotificationPreference
from app.models.operating_authority import OperatingAuthority
from app.models.pilot import Pilot
from app.models.sensor import SensorPackage
from app.models.telemetry import TelemetryPoint
from app.models.training_log import TrainingLog
from app.models.vehicle import Vehicle
from app.models.vehicle_registration import VehicleRegistration
from app.routers.reports import REPORT_VIEW_KEYS
from app.services import email_digest, scheduler
from app.services.permissions import REGISTRY
from app.services.pilot_contacts import CONTACT_HIDDEN

PERMISSIONS_URL = "/api/permissions"
AUDIT_URL = "/api/audit"
PILOT_ADDRESS = "pilot-record@example.org"
SEARCH_URL = "/api/search"
COMPLIANCE_URL = "/api/dashboard/compliance"
PREFERENCES_URL = "/api/notifications/preferences"
SEND_TEST_URL = "/api/notifications/send-test"
REPORT_URL = "/api/reports/generate"
REPORT_PDF_URL = "/api/reports/generate/pdf"
REPORT_ZIP_URL = "/api/reports/per-pilot/zip"
PILOTS_CSV_URL = "/api/export/pilots/csv"
CALENDAR_URL = "/api/calendar"

FLIGHTS_VIEW = "flights.view"
FLEET_VIEW = "fleet.view"
PILOTS_VIEW = "pilots.view"
LOGS_VIEW = "logs.view"
MAINTENANCE_VIEW = "maintenance.view"
CERTIFICATIONS_VIEW = "certifications.view"
INCIDENTS_VIEW = "incidents.view"
AUTHORITY_VIEW = "authority.view"
REGISTRATIONS_VIEW = "registrations.view"
FLIGHT_PLANS_VIEW = "flight_plans.view"
CHECKLISTS_VIEW = "checklists.view"
REPORTS_EXPORT = "reports.export"
REPORTS_GENERATE = "reports.generate"
DIGEST_REDIRECT = "digest.redirect"
PILOTS_CONTACTS = "pilots.contacts"
PILOTS_MANAGE = "pilots.manage"

PILOT_ROLE = "pilot"
SUPERVISOR_ROLE = "supervisor"
ACCOUNT_ADDRESS = "account@example.com"
OVERRIDE_ADDRESS = "elsewhere@example.org"
SECRET_EMAIL = "secret.pilot@example.com"
SECRET_PHONE = "555-0100"
TODAY = date.today()


def _grid(client, headers, *changes):
    body = {"changes": [{"role": r, "key": k, "value": v} for r, k, v in changes]}
    resp = client.put(PERMISSIONS_URL, headers=headers, json=body)
    assert resp.status_code == 200, resp.text


def _key_off(client, admin_headers, role, key):
    """Turn a key off for a role, along with every key that requires it."""
    changes = [
        (role, dependent, "none" if definition.kind == "level" else "no")
        for dependent, definition in REGISTRY.items()
        if definition.requires == key
    ]
    changes.append((role, key, "no"))
    _grid(client, admin_headers, *changes)


def _add(db, *rows):
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows[0] if len(rows) == 1 else rows


def _pilot(db, **fields):
    defaults = {"first_name": "Findme", "last_name": "Person", "email": SECRET_EMAIL, "phone": SECRET_PHONE}
    return _add(db, Pilot(**{**defaults, **fields}))


def _vehicle(db):
    return _add(db, Vehicle(serial_number="FINDME-1", manufacturer="Skydio", model="X10", status="active"))


def _flight(db, pilot_id=None, vehicle_id=None, **fields):
    defaults = {"date": TODAY, "duration_seconds": 3600, "purpose": "Findme training"}
    return _add(db, Flight(pilot_id=pilot_id, vehicle_id=vehicle_id, **{**defaults, **fields}))


def _cert(db, pilot_id, days=10):
    cert_type = _add(db, CertificationType(name="Part 107", category="faa", has_expiration=True))
    return _add(db, PilotCertification(
        pilot_id=pilot_id, certification_type_id=cert_type.id, status="complete",
        expiration_date=TODAY + timedelta(days=days)))


def _overdue_schedule(db, vehicle_id=1):
    return _add(db, MaintenanceSchedule(
        name="Motor check", entity_type="vehicle", entity_id=vehicle_id, frequency="monthly",
        is_active=True, next_due=TODAY - timedelta(days=3)))


def _authority(db, days=-5):
    return _add(db, OperatingAuthority(
        authority_type="coa", title="County COA", identifier="COA-1", record_status="active",
        grounds_unit=False, expiry_date=TODAY + timedelta(days=days)))


# Search ----------------------------------------------------------------------

SEARCH_GROUPS = [(PILOTS_VIEW, "pilot"), (FLEET_VIEW, "vehicle"), (FLIGHTS_VIEW, "flight")]


@pytest.mark.parametrize("view_key,result_type", SEARCH_GROUPS)
def test_search_omits_group_when_view_off(client, db, admin_headers, pilot_headers, view_key, result_type):
    pilot = _pilot(db)
    vehicle = _vehicle(db)
    _flight(db, pilot.id, vehicle.id)

    def found():
        resp = client.get(SEARCH_URL, params={"q": "findme"}, headers=pilot_headers)
        assert resp.status_code == 200, resp.text
        return {row["type"] for row in resp.json()["results"]}

    assert found() == {"pilot", "vehicle", "flight"}
    _key_off(client, admin_headers, PILOT_ROLE, view_key)
    assert found() == {"pilot", "vehicle", "flight"} - {result_type}


# Dashboard -------------------------------------------------------------------

DASHBOARD_LISTS = [
    ("/api/dashboard/activity-by-month", FLIGHTS_VIEW),
    ("/api/dashboard/top-pilots-30d", FLIGHTS_VIEW),
    ("/api/dashboard/analytics/flights-by-purpose", FLIGHTS_VIEW),
    ("/api/dashboard/analytics/flights-by-year", FLIGHTS_VIEW),
    ("/api/dashboard/analytics/flights-by-year-purpose", FLIGHTS_VIEW),
    ("/api/dashboard/analytics/flights-by-pilot", FLIGHTS_VIEW),
    ("/api/dashboard/analytics/avg-duration-by-year", FLIGHTS_VIEW),
    ("/api/dashboard/analytics/monthly-flights", FLIGHTS_VIEW),
    ("/api/dashboard/analytics/pilot-hours", FLIGHTS_VIEW),
    ("/api/dashboard/top-vehicles-30d", FLEET_VIEW),
    ("/api/dashboard/analytics/vehicle-hours", FLEET_VIEW),
    ("/api/dashboard/analytics/fleet-health", FLEET_VIEW),
    ("/api/dashboard/maintenance-due", MAINTENANCE_VIEW),
    ("/api/dashboard/upcoming-expirations", CERTIFICATIONS_VIEW),
]


@pytest.mark.parametrize("url,view_key", DASHBOARD_LISTS)
def test_dashboard_lists_follow_view_keys(client, admin_headers, pilot_headers, url, view_key):
    assert client.get(url, headers=pilot_headers).status_code == 200
    _key_off(client, admin_headers, PILOT_ROLE, view_key)
    assert client.get(url, headers=pilot_headers).status_code == 403


def test_pilot_performance_follows_flights_view(client, db, admin_headers, pilot_headers):
    url = f"/api/dashboard/analytics/pilot-performance/{_pilot(db).id}"
    assert client.get(url, headers=pilot_headers).status_code == 200
    _key_off(client, admin_headers, PILOT_ROLE, FLIGHTS_VIEW)
    assert client.get(url, headers=pilot_headers).status_code == 403


def test_pilot_performance_hides_other_features_figures(client, db, admin_headers, pilot_headers):
    pilot = _pilot(db)
    _add(db, Incident(date=TODAY, title="Hard landing", severity="minor", category="other",
                      description="d", pilot_id=pilot.id))
    url = f"/api/dashboard/analytics/pilot-performance/{pilot.id}"
    before = client.get(url, headers=pilot_headers).json()
    assert before["incidents"] == 1
    assert before["training_hours"] == 0
    assert before["mission_hours"] == 0

    _key_off(client, admin_headers, PILOT_ROLE, INCIDENTS_VIEW)
    _key_off(client, admin_headers, PILOT_ROLE, LOGS_VIEW)
    after = client.get(url, headers=pilot_headers).json()
    assert after["incidents"] is None
    assert after["training_hours"] is None
    assert after["mission_hours"] is None
    assert after["total_flights"] == 0


def test_fleet_health_per_vehicle_overdue_follows_maintenance_view(client, db, admin_headers, pilot_headers):
    vehicle = _vehicle(db)
    _overdue_schedule(db, vehicle.id)
    url = "/api/dashboard/analytics/fleet-health"
    before = client.get(url, headers=pilot_headers).json()
    assert before["vehicles"][0]["overdue_maintenance"] == 1

    _key_off(client, admin_headers, PILOT_ROLE, MAINTENANCE_VIEW)
    after = client.get(url, headers=pilot_headers).json()
    assert after["vehicles"][0]["overdue_maintenance"] is None
    assert after["summary"]["total_overdue_maintenance"] == 1


COMPLIANCE_LISTS = [
    (CERTIFICATIONS_VIEW, "expiring_certifications"),
    (CERTIFICATIONS_VIEW, "pilot_currency_status"),
    (AUTHORITY_VIEW, "expired_authorities"),
    (AUTHORITY_VIEW, "expiring_authorities"),
]


@pytest.mark.parametrize("view_key,field", COMPLIANCE_LISTS)
def test_compliance_named_lists_follow_view_keys(client, db, admin_headers, pilot_headers, view_key, field):
    from app.models.currency_rule import CurrencyRule
    pilot = _pilot(db)
    _cert(db, pilot.id)
    _authority(db, days=-5)
    _authority(db, days=10)
    _add(db, CurrencyRule(name="Rule", required_hours=1, period_days=30, is_active=True))

    before = client.get(COMPLIANCE_URL, headers=pilot_headers).json()
    assert before[field]

    _key_off(client, admin_headers, PILOT_ROLE, view_key)
    after = client.get(COMPLIANCE_URL, headers=pilot_headers)
    assert after.status_code == 200
    assert after.json()[field] == []


def test_unit_totals_stay_visible(client, db, admin_headers, pilot_headers):
    from app.models.currency_rule import CurrencyRule
    pilot = _pilot(db)
    vehicle = _vehicle(db)
    _flight(db, pilot.id, vehicle.id, review_status="reviewed")
    _cert(db, pilot.id)
    _authority(db, days=-5)
    _add(db, CurrencyRule(name="Rule", required_hours=50, period_days=30, is_active=True))
    urls = ["/api/dashboard/stats", "/api/dashboard/trends", COMPLIANCE_URL]
    before = {url: client.get(url, headers=pilot_headers).json() for url in urls}

    for view_key in (FLIGHTS_VIEW, FLEET_VIEW, PILOTS_VIEW, CERTIFICATIONS_VIEW, AUTHORITY_VIEW,
                     MAINTENANCE_VIEW, INCIDENTS_VIEW):
        _key_off(client, admin_headers, PILOT_ROLE, view_key)

    for url in urls[:2]:
        resp = client.get(url, headers=pilot_headers)
        assert resp.status_code == 200
        assert resp.json() == before[url]
    after = client.get(COMPLIANCE_URL, headers=pilot_headers)
    assert after.status_code == 200
    for field in ("total_pilots", "compliance_score", "pilots_lapsed", "pilots_current",
                  "expired_certifications", "operating_authorities_tracked"):
        assert after.json()[field] == before[COMPLIANCE_URL][field]


# Exports ---------------------------------------------------------------------

CSV_ROUTES = [
    ("/api/export/flights/csv", FLIGHTS_VIEW),
    ("/api/export/vehicles/csv", FLEET_VIEW),
    ("/api/export/fleet/batteries/csv", FLEET_VIEW),
    ("/api/export/fleet/other-equipment/csv", FLEET_VIEW),
    ("/api/export/equipment-checkouts/csv", FLEET_VIEW),
    ("/api/export/maintenance/csv", MAINTENANCE_VIEW),
    ("/api/export/checklists/csv", CHECKLISTS_VIEW),
    ("/api/export/certifications/csv", CERTIFICATIONS_VIEW),
    ("/api/export/training-logs/csv", LOGS_VIEW),
    ("/api/export/mission-logs/csv", LOGS_VIEW),
    ("/api/export/incidents/csv", INCIDENTS_VIEW),
    ("/api/export/flight-plans/csv", FLIGHT_PLANS_VIEW),
]


@pytest.mark.parametrize("url,view_key", CSV_ROUTES)
def test_export_needs_both_keys(client, admin_headers, pilot_headers, url, view_key):
    assert client.get(url, headers=pilot_headers).status_code == 200
    _key_off(client, admin_headers, PILOT_ROLE, view_key)
    assert client.get(url, headers=pilot_headers).status_code == 403


@pytest.mark.parametrize("url,view_key", CSV_ROUTES)
def test_export_refused_without_export_key(client, admin_headers, pilot_headers, url, view_key):
    _key_off(client, admin_headers, PILOT_ROLE, REPORTS_EXPORT)
    assert client.get(url, headers=pilot_headers).status_code == 403


@pytest.fixture
def flight_with_track(db, telemetry_db):
    flight = _flight(db)
    telemetry_db.add(TelemetryPoint(flight_id=flight.id, timestamp_ms=1000, lat=30.0, lon=-90.0, altitude_m=10.0))
    telemetry_db.commit()
    return flight


@pytest.mark.parametrize("fmt", ["gpx", "kml"])
def test_track_export_needs_both_keys(client, admin_headers, pilot_headers, flight_with_track, fmt):
    url = f"/api/export/flights/{flight_with_track.id}/{fmt}"
    assert client.get(url, headers=pilot_headers).status_code == 200
    _key_off(client, admin_headers, PILOT_ROLE, REPORTS_EXPORT)
    assert client.get(url, headers=pilot_headers).status_code == 403
    _grid(client, admin_headers, (PILOT_ROLE, REPORTS_EXPORT, "yes"))
    assert client.get(url, headers=pilot_headers).status_code == 200
    _key_off(client, admin_headers, PILOT_ROLE, FLIGHTS_VIEW)
    assert client.get(url, headers=pilot_headers).status_code == 403


def test_pilots_csv_stays_supervisor_level(client, admin_headers, supervisor_headers, pilot_headers):
    assert client.get(PILOTS_CSV_URL, headers=pilot_headers).status_code == 403
    assert client.get(PILOTS_CSV_URL, headers=supervisor_headers).status_code == 200

    _key_off(client, admin_headers, SUPERVISOR_ROLE, REPORTS_EXPORT)
    assert client.get(PILOTS_CSV_URL, headers=supervisor_headers).status_code == 403
    _grid(client, admin_headers, (SUPERVISOR_ROLE, REPORTS_EXPORT, "yes"), (SUPERVISOR_ROLE, PILOTS_MANAGE, "no"))
    assert client.get(PILOTS_CSV_URL, headers=supervisor_headers).status_code == 403

    _grid(client, admin_headers, (PILOT_ROLE, PILOTS_MANAGE, "yes"))
    assert client.get(PILOTS_CSV_URL, headers=pilot_headers).status_code == 200


def test_pilots_csv_blanks_contacts_without_contacts_key(client, db, admin_headers, supervisor_headers):
    _pilot(db)
    assert SECRET_EMAIL in client.get(PILOTS_CSV_URL, headers=supervisor_headers).text
    _grid(client, admin_headers, (SUPERVISOR_ROLE, PILOTS_CONTACTS, "no"))
    body = client.get(PILOTS_CSV_URL, headers=supervisor_headers).text
    rows = list(csv.DictReader(io.StringIO(body)))
    assert rows[0]["First Name"] == "Findme"
    assert SECRET_EMAIL not in body
    assert SECRET_PHONE not in body


# Reports ---------------------------------------------------------------------

EXPECTED_REPORT_KEYS = {
    "flight_summary": {FLIGHTS_VIEW},
    "pilot_hours": {FLIGHTS_VIEW},
    "equipment_utilization": {FLEET_VIEW, FLIGHTS_VIEW},
    "pilot_certifications": {CERTIFICATIONS_VIEW, AUTHORITY_VIEW},
    "battery_status": {FLEET_VIEW},
    "maintenance_history": {MAINTENANCE_VIEW},
    "pilot_activity_summary": {FLIGHTS_VIEW, LOGS_VIEW},
    "annual_unit_report": {FLIGHTS_VIEW, LOGS_VIEW, FLEET_VIEW, CERTIFICATIONS_VIEW, AUTHORITY_VIEW,
                           MAINTENANCE_VIEW, INCIDENTS_VIEW},
    "per_pilot_annual_review": {FLIGHTS_VIEW, LOGS_VIEW, CERTIFICATIONS_VIEW},
}
REPORT_CASES = [(rtype, key) for rtype, keys in EXPECTED_REPORT_KEYS.items() for key in sorted(keys)]


def test_report_view_keys_cover_every_report_type():
    assert {rtype: set(keys) for rtype, keys in REPORT_VIEW_KEYS.items()} == EXPECTED_REPORT_KEYS


@pytest.mark.parametrize("report_type,view_key", REPORT_CASES)
def test_report_refused_when_view_off(client, admin_headers, pilot_headers, report_type, view_key):
    body = {"report_type": report_type}
    assert client.post(REPORT_URL, json=body, headers=pilot_headers).status_code == 200
    _key_off(client, admin_headers, PILOT_ROLE, view_key)
    assert client.post(REPORT_URL, json=body, headers=pilot_headers).status_code == 403
    assert client.post(REPORT_PDF_URL, json=body, headers=pilot_headers).status_code == 403


@pytest.mark.parametrize("url", [REPORT_URL, REPORT_PDF_URL])
def test_unknown_report_type_refused(client, admin_headers, url):
    resp = client.post(url, json={"report_type": "does_not_exist"}, headers=admin_headers)
    assert resp.status_code == 400


@pytest.mark.parametrize("url", [REPORT_URL, REPORT_PDF_URL, REPORT_ZIP_URL])
def test_reports_need_generate_key(client, viewer_headers, admin_headers, pilot_headers, url):
    body = {"report_type": "battery_status"}
    assert client.post(url, json=body, headers=viewer_headers).status_code == 403
    _grid(client, admin_headers, (PILOT_ROLE, REPORTS_GENERATE, "no"))
    assert client.post(url, json=body, headers=pilot_headers).status_code == 403


def test_per_pilot_zip_ignores_the_type_in_the_body(client, db, admin_headers, pilot_headers):
    """The zip always renders the annual review, so that is the type that decides."""
    _pilot(db)
    body = {"report_type": "battery_status"}
    assert client.post(REPORT_ZIP_URL, json=body, headers=pilot_headers).status_code == 200
    _key_off(client, admin_headers, PILOT_ROLE, CERTIFICATIONS_VIEW)
    assert client.post(REPORT_ZIP_URL, json=body, headers=pilot_headers).status_code == 403


# Digest ----------------------------------------------------------------------

def _seed_digest_data(db, user):
    pilot = _pilot(db)
    vehicle = _vehicle(db)
    _add(db, FlightPlan(title="Plan", date_planned=datetime(2026, 12, 1), pilot_id=pilot.id,
                        submitted_by_id=user.id, status="pending"))
    _flight(db, pilot.id, vehicle.id, review_status="needs_review")
    _cert(db, pilot.id)
    _add(db, VehicleRegistration(vehicle_id=vehicle.id, registration_number="FA-1", is_current=True,
                                 expiry_date=TODAY + timedelta(days=10)))
    _overdue_schedule(db, vehicle.id)
    _add(db, EquipmentCheckout(entity_type="vehicle", entity_id=vehicle.id, entity_name="X10",
                               checked_out_by_id=pilot.id, expected_return=datetime(2020, 1, 1)))
    _add(db, Incident(date=TODAY, title="Hard landing", severity="minor", category="other", description="d",
                      created_at=datetime.now(timezone.utc)))


DIGEST_SECTIONS = [
    ("pending_approvals", "flight_plans.approve"),
    ("needs_review", "flights.review"),
    ("expiring_certs", CERTIFICATIONS_VIEW),
    ("expiring_registrations", REGISTRATIONS_VIEW),
    ("overdue_maintenance", MAINTENANCE_VIEW),
    ("overdue_checkouts", FLEET_VIEW),
    ("recent_incidents", INCIDENTS_VIEW),
]


@pytest.mark.parametrize("section,key", DIGEST_SECTIONS)
def test_digest_sections_follow_view_keys(client, db, admin_headers, supervisor_user, admin_user, section, key):
    _seed_digest_data(db, admin_user)
    assert section in email_digest.build_digest(db, admin_user)
    assert section in email_digest.build_digest(db, supervisor_user)
    _key_off(client, admin_headers, SUPERVISOR_ROLE, key)
    db.expire_all()
    supervisor_user._resolved_permissions = None
    digest = email_digest.build_digest(db, supervisor_user) or {}
    assert section not in digest
    assert section in email_digest.build_digest(db, admin_user)


def test_digest_supervisor_sections_follow_permission_not_role(client, db, admin_headers, admin_user, pilot_user):
    _seed_digest_data(db, admin_user)
    assert "needs_review" not in email_digest.build_digest(db, pilot_user)
    assert "pending_approvals" not in email_digest.build_digest(db, pilot_user)
    _grid(client, admin_headers, (PILOT_ROLE, "flights.review", "yes"), (PILOT_ROLE, "flight_plans.approve", "yes"))
    pilot_user._resolved_permissions = None
    digest = email_digest.build_digest(db, pilot_user)
    assert "needs_review" in digest
    assert "pending_approvals" in digest


def test_digest_preview_follows_view_keys(client, db, admin_headers, admin_user, pilot_headers):
    _seed_digest_data(db, admin_user)
    url = "/api/notifications/preview"
    assert "recent_incidents" in client.get(url, headers=pilot_headers).json()["sections"]
    _key_off(client, admin_headers, PILOT_ROLE, INCIDENTS_VIEW)
    assert "recent_incidents" not in client.get(url, headers=pilot_headers).json()["sections"]


# Digest override -------------------------------------------------------------

def _stored_override(db, user):
    db.expire_all()
    return db.query(NotificationPreference).filter(NotificationPreference.user_id == user.id).one().email_override


def test_redirect_refused_on_save_without_permission(client, db, pilot_user, pilot_headers):
    resp = client.put(PREFERENCES_URL, json={"email_override": OVERRIDE_ADDRESS}, headers=pilot_headers)
    assert resp.status_code == 403
    assert _stored_override(db, pilot_user) is None


def test_redirect_allowed_with_permission(client, db, admin_headers, pilot_user, pilot_headers):
    _grid(client, admin_headers, (PILOT_ROLE, DIGEST_REDIRECT, "yes"))
    resp = client.put(PREFERENCES_URL, json={"email_override": OVERRIDE_ADDRESS}, headers=pilot_headers)
    assert resp.status_code == 200
    assert _stored_override(db, pilot_user) == OVERRIDE_ADDRESS


@pytest.mark.parametrize("cleared", ["", "   "])
def test_clearing_override_needs_no_permission(client, db, pilot_user, pilot_headers, cleared):
    _add(db, NotificationPreference(user_id=pilot_user.id, email_override=OVERRIDE_ADDRESS))
    resp = client.put(PREFERENCES_URL, json={"email_override": cleared}, headers=pilot_headers)
    assert resp.status_code == 200
    assert _stored_override(db, pilot_user) is None


@pytest.fixture
def sent(monkeypatch):
    """Capture the recipient of each digest email instead of sending it."""
    recipients = []

    def fake_send(to_address, subject, html_body, db):
        recipients.append(to_address)
        return True

    monkeypatch.setattr(email_digest, "send_email", fake_send)
    return recipients


def _with_account_and_override(db, user, account=ACCOUNT_ADDRESS):
    user.email = account
    db.commit()
    pref = _add(db, NotificationPreference(user_id=user.id, email_override=OVERRIDE_ADDRESS))
    _seed_digest_data(db, user)
    return pref


def test_scheduled_digest_ignores_override_without_permission(db, pilot_user, sent):
    pref = _with_account_and_override(db, pilot_user)
    scheduler._send_user_digest(pref, db)
    assert sent == [ACCOUNT_ADDRESS]
    assert _stored_override(db, pilot_user) == OVERRIDE_ADDRESS


def test_scheduled_digest_honors_override_with_permission(db, supervisor_user, sent):
    pref = _with_account_and_override(db, supervisor_user)
    scheduler._send_user_digest(pref, db)
    assert sent == [OVERRIDE_ADDRESS]


def test_scheduled_digest_with_no_permitted_address_is_not_sent(db, pilot_user, sent):
    pref = _with_account_and_override(db, pilot_user, account=None)
    scheduler._send_user_digest(pref, db)
    assert sent == []
    assert _stored_override(db, pilot_user) == OVERRIDE_ADDRESS


def test_scheduled_digest_falls_back_to_the_linked_pilot_email(db, pilot_user, linked_pilot, sent):
    linked_pilot.email = PILOT_ADDRESS
    pref = _with_account_and_override(db, pilot_user, account=None)
    scheduler._send_user_digest(pref, db)
    assert sent == [PILOT_ADDRESS]
    assert _stored_override(db, pilot_user) == OVERRIDE_ADDRESS


def test_scheduled_digest_prefers_the_account_address_to_the_pilot_email(db, pilot_user, linked_pilot, sent):
    linked_pilot.email = PILOT_ADDRESS
    pref = _with_account_and_override(db, pilot_user)
    scheduler._send_user_digest(pref, db)
    assert sent == [ACCOUNT_ADDRESS]


def test_send_test_uses_the_same_fallback_and_never_the_override(client, db, pilot_user, linked_pilot, pilot_headers, sent):
    linked_pilot.email = PILOT_ADDRESS
    _with_account_and_override(db, pilot_user, account=None)
    resp = client.post(SEND_TEST_URL, headers=pilot_headers)
    assert resp.status_code == 200, resp.text
    assert sent == [PILOT_ADDRESS]


def test_send_test_ignores_override_without_permission(client, db, pilot_user, pilot_headers, sent):
    _with_account_and_override(db, pilot_user)
    resp = client.post(SEND_TEST_URL, headers=pilot_headers)
    assert resp.status_code == 200, resp.text
    assert sent == [ACCOUNT_ADDRESS]
    assert _stored_override(db, pilot_user) == OVERRIDE_ADDRESS


def test_send_test_honors_override_with_permission(client, db, supervisor_user, supervisor_headers, sent):
    _with_account_and_override(db, supervisor_user)
    resp = client.post(SEND_TEST_URL, headers=supervisor_headers)
    assert resp.status_code == 200, resp.text
    assert sent == [OVERRIDE_ADDRESS]


def test_send_test_with_no_permitted_address_keeps_no_address_error(client, db, pilot_user, pilot_headers, sent):
    _with_account_and_override(db, pilot_user, account=None)
    resp = client.post(SEND_TEST_URL, headers=pilot_headers)
    assert resp.status_code == 400
    assert sent == []


def test_send_test_falls_back_to_linked_pilot_address(client, db, pilot_user, pilot_headers, sent):
    _with_account_and_override(db, pilot_user, account=None)
    linked = _pilot(db, first_name="Linked", email="linked@example.com")
    pilot_user.pilot_id = linked.id
    db.commit()
    resp = client.post(SEND_TEST_URL, headers=pilot_headers)
    assert resp.status_code == 200, resp.text
    assert sent == ["linked@example.com"]


# Read paths the route mapping does not list ----------------------------------

def _seed_equipment(db):
    battery, sensor, attachment = _add(
        db,
        Battery(serial_number="B-1", status="active"),
        SensorPackage(serial_number="S-1", status="active"),
        Attachment(serial_number="A-1", status="active"),
    )
    return battery, sensor, attachment


@pytest.mark.parametrize("path", ["stats", "flights", "pilots"])
@pytest.mark.parametrize("kind,index", [("batteries", 0), ("sensors", 1), ("attachments", 2)])
def test_equipment_flight_reads_follow_flights_view(client, db, admin_headers, pilot_headers, kind, index, path):
    url = f"/api/{kind}/{_seed_equipment(db)[index].id}/{path}"
    assert client.get(url, headers=pilot_headers).status_code == 200
    _key_off(client, admin_headers, PILOT_ROLE, FLIGHTS_VIEW)
    assert client.get(url, headers=pilot_headers).status_code == 403


def test_pilot_stats_follow_flights_view(client, db, admin_headers, pilot_headers):
    url = f"/api/pilots/{_pilot(db).id}/stats"
    assert client.get(url, headers=pilot_headers).status_code == 200
    _key_off(client, admin_headers, PILOT_ROLE, FLIGHTS_VIEW)
    assert client.get(url, headers=pilot_headers).status_code == 403


def test_vehicle_stats_follow_flights_view(client, db, admin_headers, pilot_headers):
    url = f"/api/vehicles/{_vehicle(db).id}/stats"
    assert client.get(url, headers=pilot_headers).status_code == 200
    _key_off(client, admin_headers, PILOT_ROLE, FLIGHTS_VIEW)
    assert client.get(url, headers=pilot_headers).status_code == 403


def test_needs_attention_follows_certifications_view(client, db, admin_headers, pilot_headers):
    url = f"/api/pilots/{_pilot(db).id}/needs-attention"
    assert client.get(url, headers=pilot_headers).status_code == 200
    _key_off(client, admin_headers, PILOT_ROLE, CERTIFICATIONS_VIEW)
    assert client.get(url, headers=pilot_headers).status_code == 403


def test_calendar_sources_follow_view_keys(client, db, admin_headers, pilot_headers):
    pilot = _pilot(db)
    _cert(db, pilot.id)
    _overdue_schedule(db)
    _add(db, TrainingLog(date=TODAY, title="Drill", training_type="scenario"),
         MissionLog(date=TODAY, title="Search"))
    params = {"start": str(TODAY - timedelta(days=30)), "end": str(TODAY + timedelta(days=30))}

    def categories():
        resp = client.get(CALENDAR_URL, params=params, headers=pilot_headers)
        assert resp.status_code == 200, resp.text
        return {event["category"] for event in resp.json()["events"]}

    assert categories() == {"training_day", "mission", "maintenance_due", "cert_expiration"}
    _key_off(client, admin_headers, PILOT_ROLE, LOGS_VIEW)
    assert categories() == {"maintenance_due", "cert_expiration"}
    _key_off(client, admin_headers, PILOT_ROLE, MAINTENANCE_VIEW)
    assert categories() == {"cert_expiration"}
    _key_off(client, admin_headers, PILOT_ROLE, CERTIFICATIONS_VIEW)
    assert categories() == set()


def test_preflight_warnings_follow_view_keys(client, db, admin_headers, pilot_headers):
    vehicle = _vehicle(db)
    _overdue_schedule(db, vehicle.id)
    _add(db, VehicleRegistration(vehicle_id=vehicle.id, registration_number="FA-1", is_current=True,
                                 expiry_date=TODAY - timedelta(days=1)))
    url = "/api/flights/preflight-check"

    def warnings():
        resp = client.get(url, params={"vehicle_id": vehicle.id}, headers=pilot_headers)
        assert resp.status_code == 200, resp.text
        return " ".join(resp.json()["warnings"])

    assert "Overdue maintenance" in warnings()
    assert "registration expired" in warnings()
    _key_off(client, admin_headers, PILOT_ROLE, MAINTENANCE_VIEW)
    assert "Overdue maintenance" not in warnings()
    assert "registration expired" in warnings()
    _key_off(client, admin_headers, PILOT_ROLE, REGISTRATIONS_VIEW)
    assert warnings() == ""


# The audit log follows pilots.contacts -----------------------------------------

AUDIT_PHONE = "555-0100"
AUDIT_EMAIL = "jane@example.org"


def _seed_contact_audit(db):
    db.add(AuditLog(user_name="Admin", action="update", entity_type="pilot", entity_id=1, entity_name="Jane Doe",
                    changes={"email": {"old": None, "new": AUDIT_EMAIL}, "phone": {"old": AUDIT_PHONE, "new": None},
                             "first_name": {"old": "Jan", "new": "Jane"}}))
    db.add(AuditLog(user_name="Admin", action="send_reminders", entity_type="currency",
                    details=f"sent=1, failed=0; recipients=Jane Doe <{AUDIT_EMAIL}>; Bob Roy <bob@example.org>"))
    db.add(AuditLog(user_name="Admin", action="send_test", entity_type="notification",
                    details=f"to={AUDIT_EMAIL}, sent=True"))
    db.commit()


def _hide_contacts_with_audit(client, admin_headers, role="pilot"):
    _grid(client, admin_headers, (role, "audit.view", "yes"), (role, "pilots.contacts", "no"))


def test_audit_api_redacts_contacts_without_the_permission(client, db, admin_headers, pilot_headers):
    _seed_contact_audit(db)
    _hide_contacts_with_audit(client, admin_headers)

    resp = client.get(AUDIT_URL, headers=pilot_headers)

    assert resp.status_code == 200, resp.text
    assert AUDIT_EMAIL not in resp.text
    assert AUDIT_PHONE not in resp.text
    assert "bob@example.org" not in resp.text
    logs = {entry["action"]: entry for entry in resp.json()["logs"]}
    assert logs["update"]["changes"]["first_name"] == {"old": "Jan", "new": "Jane"}
    assert logs["update"]["changes"]["email"] == {"old": CONTACT_HIDDEN, "new": CONTACT_HIDDEN}
    assert logs["send_reminders"]["details"] == (
        f"sent=1, failed=0; recipients=Jane Doe <{CONTACT_HIDDEN}>; Bob Roy <{CONTACT_HIDDEN}>")
    assert logs["send_test"]["details"] == f"to={CONTACT_HIDDEN}, sent=True"


def test_audit_csv_redacts_recipients_without_the_permission(client, db, admin_headers, pilot_headers):
    _seed_contact_audit(db)
    _hide_contacts_with_audit(client, admin_headers)

    resp = client.get("/api/export/audit/csv", headers=pilot_headers)

    assert resp.status_code == 200, resp.text
    assert AUDIT_EMAIL not in resp.text
    assert "bob@example.org" not in resp.text
    assert "Jane Doe" in resp.text


def test_audit_keeps_contacts_with_the_permission_and_stored_rows_intact(client, db, admin_headers, pilot_headers):
    _seed_contact_audit(db)
    _grid(client, admin_headers, ("pilot", "audit.view", "yes"))

    assert AUDIT_EMAIL in client.get(AUDIT_URL, headers=pilot_headers).text
    assert AUDIT_EMAIL in client.get("/api/export/audit/csv", headers=pilot_headers).text
    assert AUDIT_EMAIL in client.get(AUDIT_URL, headers=admin_headers).text

    _hide_contacts_with_audit(client, admin_headers)
    client.get(AUDIT_URL, headers=pilot_headers)
    db.expire_all()
    stored = db.query(AuditLog).filter(AuditLog.action == "update", AuditLog.entity_type == "pilot").first()
    assert stored.changes["email"]["new"] == AUDIT_EMAIL
