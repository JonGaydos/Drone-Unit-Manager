"""Flights that are not the unit's own activity must not reach its numbers.

pilot.status answers "is this person on the roster" and nothing else. A pilot
who leaves keeps counting, because they flew those flights for the unit; a
vendor rep with a live account never counted, because they never did. In one
observed import a single vendor rep held 27% of the period's flights.

The sweep at the bottom is the point of this file: it drives every dashboard
endpoint and every report type through one excluded pilot and one excluded
flight, so a new aggregate that forgets the rule fails here rather than shipping
a wrong number.
"""

from datetime import date, timedelta

import pytest

from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle

TODAY = date.today()
RECENT = TODAY - timedelta(days=3)

# Durations chosen so any leak is unmistakable in a total: the unit flew one
# hour, the excluded pair two more.
UNIT_SECONDS = 3600
VENDOR_SECONDS = 3600
ONE_OFF_SECONDS = 3600


@pytest.fixture
def scoped(db):
    """One counted flight, one flown by a vendor, one excluded on its own."""
    vehicle = Vehicle(serial_number="AIRFRAME-1", manufacturer="Brinc",
                      model="LEMUR 2", nickname="Lemur #2", status="active")
    unit_pilot = Pilot(first_name="Alex", last_name="Rivera", status="active")
    # Live account, real sorties, but never the unit's own activity.
    vendor = Pilot(first_name="Vendor", last_name="Rep", status="active",
                   counts_toward_totals=False)
    # Left the unit. Their flights are still the unit's and must keep counting.
    departed = Pilot(first_name="Jamie", last_name="Cole", status="inactive")
    db.add_all([vehicle, unit_pilot, vendor, departed])
    db.flush()

    db.add_all([
        Flight(external_id="unit-1", date=RECENT, duration_seconds=UNIT_SECONDS,
               pilot_id=unit_pilot.id, vehicle_id=vehicle.id, purpose="Patrol"),
        Flight(external_id="vendor-1", date=RECENT, duration_seconds=VENDOR_SECONDS,
               pilot_id=vendor.id, vehicle_id=vehicle.id, purpose="Vendor Demo"),
        Flight(external_id="oneoff-1", date=RECENT, duration_seconds=ONE_OFF_SECONDS,
               pilot_id=unit_pilot.id, vehicle_id=vehicle.id, purpose="Vendor Demo",
               counts_toward_totals=False),
    ])
    db.commit()
    return {"vehicle": vehicle, "unit_pilot": unit_pilot,
            "vendor": vendor, "departed": departed}


# --- The rule itself --------------------------------------------------------


def test_a_flight_counts_by_default(client, db, scoped):
    assert db.query(Flight).filter(Flight.external_id == "unit-1").one().counts_toward_totals


def test_a_pilot_counts_by_default(client, db, scoped):
    assert db.query(Pilot).filter(Pilot.first_name == "Alex").one().counts_toward_totals


def test_leaving_the_unit_does_not_stop_a_pilot_counting(client, db, scoped):
    """The whole reason this is separate from status. Jamie Cole resigned;
    the flights he flew were still the unit's work."""
    departed = db.query(Pilot).filter(Pilot.first_name == "Jamie").one()
    assert departed.status == "inactive"
    assert departed.counts_toward_totals is True


# --- Dashboard --------------------------------------------------------------


def test_dashboard_totals_exclude_both_kinds(client, db, scoped, admin_headers):
    """Three flights of an hour each are in the database; one is the unit's."""
    stats = client.get("/api/dashboard/stats", headers=admin_headers).json()

    assert stats["total_flights"] == 1
    assert stats["total_flight_hours"] == pytest.approx(1.0)


def test_a_departed_pilot_still_shows_in_the_dashboard_totals(client, db, scoped, admin_headers):
    departed = db.query(Pilot).filter(Pilot.first_name == "Jamie").one()
    db.add(Flight(external_id="departed-1", date=RECENT, duration_seconds=3600,
                  pilot_id=departed.id))
    db.commit()

    stats = client.get("/api/dashboard/stats", headers=admin_headers).json()

    assert stats["total_flights"] == 2
    assert stats["total_flight_hours"] == pytest.approx(2.0)


def test_the_vendor_never_appears_in_pilot_analytics(client, db, scoped, admin_headers):
    by_pilot = client.get("/api/dashboard/analytics/flights-by-pilot", headers=admin_headers).json()
    hours = client.get("/api/dashboard/analytics/pilot-hours", headers=admin_headers).json()

    assert "Vendor Rep" not in [r["pilot_name"] for r in by_pilot]
    assert "Vendor Rep" not in [r["pilot_name"] for r in hours]


def test_aircraft_hours_exclude_them_too(client, db, scoped, admin_headers):
    """Chosen deliberately: aircraft hour totals follow the same rule as
    everything else, so a report and the fleet view never disagree."""
    rows = client.get("/api/dashboard/analytics/vehicle-hours", headers=admin_headers).json()

    assert len(rows) == 1
    assert rows[0]["hours"] == pytest.approx(1.0)


# --- Reports ----------------------------------------------------------------


def _generate(client, headers, report_type, **extra):
    body = {"report_type": report_type, **extra}
    resp = client.post("/api/reports/generate", headers=headers, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_flight_summary_counts_only_unit_activity(client, db, scoped, admin_headers):
    report = _generate(client, admin_headers, "flight_summary")

    assert report["summary"]["total_flights"] == 1
    assert report["summary"]["total_hours"] == pytest.approx(1.0)


def test_the_option_brings_everything_back(client, db, scoped, admin_headers):
    """The escape hatch behind "Include non-unit flights"."""
    report = _generate(client, admin_headers, "flight_summary", include_non_unit=True)

    assert report["summary"]["total_flights"] == 3
    assert report["summary"]["total_hours"] == pytest.approx(3.0)


def test_a_vendor_is_not_listed_at_zero_hours(client, db, scoped, admin_headers):
    """Filtering their flights but leaving the row reads as a unit pilot who
    did not fly, which is worse than not listing them."""
    report = _generate(client, admin_headers, "pilot_hours")

    assert "Vendor Rep" not in [r["pilot"] for r in report["rows"]]


def test_equipment_utilization_excludes_them(client, db, scoped, admin_headers):
    report = _generate(client, admin_headers, "equipment_utilization")

    lemur = next(r for r in report["rows"] if "Lemur" in r["vehicle"])
    assert lemur["flights"] == 1
    assert lemur["hours"] == pytest.approx(1.0)


def test_pilot_activity_summary_excludes_them(client, db, scoped, admin_headers):
    report = _generate(client, admin_headers, "pilot_activity_summary")

    assert "Vendor Rep" not in [r["pilot"] for r in report["rows"]]
    assert report["summary"]["total_flight_hours"] == pytest.approx(1.0)


def test_the_annual_unit_report_headline_excludes_them(client, db, scoped, admin_headers):
    report = _generate(client, admin_headers, "annual_unit_report",
                       date_from=str(date(TODAY.year, 1, 1)),
                       date_to=str(date(TODAY.year, 12, 31)))

    narrative = next(s for s in report["sections"] if s["type"] == "narrative")["narrative"]
    assert "1 flight(s)" in narrative, narrative
    assert "3 flight(s)" not in narrative


def test_the_per_pilot_review_has_no_section_for_a_vendor(client, db, scoped, admin_headers):
    report = _generate(client, admin_headers, "per_pilot_annual_review")

    titles = " ".join(s.get("title", "") for s in report["sections"])
    assert "Vendor Rep" not in titles


# --- The sweep --------------------------------------------------------------

# Every report that totals flights. Listed explicitly so adding a report type
# without deciding how it treats non-unit activity shows up as a failure here.
FLIGHT_REPORTS = [
    "flight_summary",
    "pilot_hours",
    "equipment_utilization",
    "pilot_activity_summary",
    "annual_unit_report",
    "per_pilot_annual_review",
]

DASHBOARD_ENDPOINTS = [
    "/api/dashboard/stats",
    "/api/dashboard/trends",
    "/api/dashboard/activity-by-month",
    "/api/dashboard/top-pilots-30d",
    "/api/dashboard/top-vehicles-30d",
    "/api/dashboard/analytics/flights-by-purpose",
    "/api/dashboard/analytics/flights-by-year",
    "/api/dashboard/analytics/flights-by-year-purpose",
    "/api/dashboard/analytics/flights-by-pilot",
    "/api/dashboard/analytics/avg-duration-by-year",
    "/api/dashboard/analytics/monthly-flights",
    "/api/dashboard/analytics/vehicle-hours",
    "/api/dashboard/analytics/pilot-hours",
    "/api/dashboard/analytics/fleet-health",
]


# Keys whose value is a count of flights or an amount of flight time. Roster
# figures like active_pilots are legitimately 2 here (the unit pilot and the
# vendor are both on the roster), so the sweep must not read those as a leak.
FLIGHT_KEYS = ("flight", "hour", "sec", "duration")


def _flight_numbers(node, key="", out=None):
    """Every flight-count or flight-time number in a JSON response."""
    out = [] if out is None else out
    if isinstance(node, bool):
        return out
    if isinstance(node, (int, float)):
        if any(k in key.lower() for k in FLIGHT_KEYS):
            out.append(float(node))
    elif isinstance(node, dict):
        for k, v in node.items():
            _flight_numbers(v, k, out)
    elif isinstance(node, list):
        for v in node:
            _flight_numbers(v, key, out)
    return out


@pytest.mark.parametrize("endpoint", DASHBOARD_ENDPOINTS)
def test_no_dashboard_endpoint_leaks_a_non_unit_flight(client, db, scoped, admin_headers, endpoint):
    """The unit flew one flight of one hour. Any 2 or 3 in a response is two or
    three flights, or two or three hours, and means an aggregate somewhere is
    still counting the vendor.
    """
    body = client.get(endpoint, headers=admin_headers).json()

    leaked = [n for n in _flight_numbers(body) if n in (2.0, 3.0)]
    assert not leaked, f"{endpoint} reported {leaked}, which can only include excluded flights"
    assert "Vendor Rep" not in str(body)


@pytest.mark.parametrize("report_type", FLIGHT_REPORTS)
def test_no_report_leaks_a_non_unit_flight(client, db, scoped, admin_headers, report_type):
    body = _generate(client, admin_headers, report_type)

    assert "Vendor Rep" not in str(body)
    assert "Vendor Demo" not in str(body), "a purpose only the excluded flights used"


@pytest.mark.parametrize("report_type", FLIGHT_REPORTS)
def test_every_flight_report_honours_the_include_option(client, db, scoped, admin_headers,
                                                        report_type):
    """Whatever a report shows by default, asking for everything must widen it."""
    default = _generate(client, admin_headers, report_type)
    everything = _generate(client, admin_headers, report_type, include_non_unit=True)

    # Not every report prints a purpose or a pilot name, so the universal
    # assertion is that the flag changes the answer at all.
    assert str(default) != str(everything), f"{report_type} ignored include_non_unit"


# --- Certification labels in the per-pilot review ---------------------------

# Not about flight scope, but the same report, and nothing covered these labels
# or their counts before the surrounding function was split up.


def test_the_per_pilot_review_labels_and_counts_certifications(client, db, scoped, admin_headers):
    """Expired, expiring inside 90 days, and everything else showing its own
    status. The two counts drive the summary tiles."""
    from app.models.certification import CertificationType, PilotCertification

    pilot = scoped["unit_pilot"]
    types = {}
    for name in ("Lapsed Cert", "Soon Cert", "Good Cert", "Undated Cert"):
        ct = CertificationType(name=name, category="custom", has_expiration=True)
        db.add(ct)
        db.flush()
        types[name] = ct

    db.add_all([
        PilotCertification(pilot_id=pilot.id, certification_type_id=types["Lapsed Cert"].id,
                           status="complete", expiration_date=TODAY - timedelta(days=1)),
        PilotCertification(pilot_id=pilot.id, certification_type_id=types["Soon Cert"].id,
                           status="complete", expiration_date=TODAY + timedelta(days=30)),
        PilotCertification(pilot_id=pilot.id, certification_type_id=types["Good Cert"].id,
                           status="complete", expiration_date=TODAY + timedelta(days=400)),
        PilotCertification(pilot_id=pilot.id, certification_type_id=types["Undated Cert"].id,
                           status="in_progress", expiration_date=None),
    ])
    db.commit()

    report = _generate(client, admin_headers, "per_pilot_annual_review")
    section = next(s for s in report["sections"] if s["title"].startswith("Alex"))
    by_cert = {r["certification"]: r["status"] for r in section["rows"]}

    assert by_cert["Lapsed Cert"] == "Expired"
    assert by_cert["Soon Cert"] == "Expiring Soon"
    # Far-future and undated fall through to the record's own status.
    assert by_cert["Good Cert"] == "Complete"
    assert by_cert["Undated Cert"] == "In Progress"

    assert section["summary"]["certifications_expired"] == 1
    assert section["summary"]["certifications_expiring_90d"] == 1


def test_a_certification_with_no_type_does_not_break_the_review(client, db, scoped, admin_headers):
    """The row renders an em dash rather than raising on a missing relation."""
    from app.models.certification import CertificationType, PilotCertification

    ct = CertificationType(name="Doomed Type", category="custom", has_expiration=True)
    db.add(ct)
    db.flush()
    db.add(PilotCertification(pilot_id=scoped["unit_pilot"].id, certification_type_id=ct.id,
                              status="complete", expiration_date=None))
    db.commit()

    report = _generate(client, admin_headers, "per_pilot_annual_review")
    section = next(s for s in report["sections"] if s["title"].startswith("Alex"))

    assert section["rows"][0]["issue_date"] == "—"
