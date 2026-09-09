"""Report generation tests: filter application in ``app.routers.reports``.

Covers the vehicle filter on the Pilot Hours report, which is built on an outer
join from Pilot to Flight so pilots with no matching flights still appear at 0
hours. Three behaviors are pinned:

* No ``vehicle_ids`` aggregates every vehicle (the pre-existing behavior).
* A ``vehicle_ids`` subset aggregates only flights on those vehicles.
* A pilot who flew nothing on the selected vehicle stays in the report at 0
  hours rather than disappearing, which is what a WHERE clause on the joined
  ``Flight.vehicle_id`` would have caused.
"""

from datetime import date, timedelta

from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.mission_log import MissionLog
from app.models.mission_log_pilot import MissionLogPilot
from app.models.training_log import TrainingLog
from app.models.training_log_pilot import TrainingLogPilot
from app.models.certification import CertificationType, PilotCertification
from app.models.battery import Battery
from app.models.maintenance import MaintenanceRecord
from app.models.incident import Incident
from app.models.operating_authority import OperatingAuthority

GENERATE_URL = "/api/reports/generate"


def _seed_pilot(db, first, last):
    pilot = Pilot(first_name=first, last_name=last, status="active")
    db.add(pilot)
    db.commit()
    db.refresh(pilot)
    return pilot


def _seed_vehicle(db, serial, nickname):
    vehicle = Vehicle(
        serial_number=serial,
        manufacturer="Skydio",
        model="X2E",
        nickname=nickname,
        status="active",
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


def _seed_flight(db, pilot_id, vehicle_id, duration_seconds, flight_date=date(2025, 6, 1)):
    flight = Flight(
        date=flight_date,
        pilot_id=pilot_id,
        vehicle_id=vehicle_id,
        duration_seconds=duration_seconds,
    )
    db.add(flight)
    db.commit()
    return flight


def _fleet(db):
    """Two pilots, two vehicles. Ana flies both; Ben flies only vehicle two."""
    ana = _seed_pilot(db, "Ana", "Alvarez")
    ben = _seed_pilot(db, "Ben", "Boyd")
    one = _seed_vehicle(db, "SN-ONE", "Vehicle One")
    two = _seed_vehicle(db, "SN-TWO", "Vehicle Two")

    _seed_flight(db, ana.id, one.id, 3600)   # 1.0 h on vehicle one
    _seed_flight(db, ana.id, two.id, 1800)   # 0.5 h on vehicle two
    _seed_flight(db, ben.id, two.id, 7200)   # 2.0 h on vehicle two

    return ana, ben, one, two


def _generate(client, headers, report_type, **config):
    """POST a report config and return the payload. One helper for every report
    type; the only thing that ever varied was the report_type string."""
    body = {"report_type": report_type, **config}
    resp = client.post(GENERATE_URL, headers=headers, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _rows_by(payload, key):
    """Index a report's rows by one of their columns."""
    return {row[key]: row for row in payload["rows"]}


def _rows_by_pilot(payload):
    return _rows_by(payload, "pilot")


def _rows_by_vehicle(payload):
    return _rows_by(payload, "vehicle")




def test_pilot_hours_without_vehicle_filter_covers_every_vehicle(client, db, pilot_headers):
    _fleet(db)

    resp = client.post(GENERATE_URL, json={"report_type": "pilot_hours"}, headers=pilot_headers)

    assert resp.status_code == 200
    payload = resp.json()
    rows = _rows_by_pilot(payload)
    assert rows["Ana Alvarez"]["hours"] == 1.5
    assert rows["Ana Alvarez"]["flights"] == 2
    assert rows["Ben Boyd"]["hours"] == 2.0
    assert payload["summary"]["total_hours"] == 3.5


def test_pilot_hours_honors_vehicle_filter(client, db, pilot_headers):
    _fleet(db)
    one = db.query(Vehicle).filter_by(serial_number="SN-ONE").one()

    resp = client.post(
        GENERATE_URL,
        json={"report_type": "pilot_hours", "vehicle_ids": [one.id]},
        headers=pilot_headers,
    )

    assert resp.status_code == 200
    payload = resp.json()
    rows = _rows_by_pilot(payload)
    assert rows["Ana Alvarez"]["hours"] == 1.0
    assert rows["Ana Alvarez"]["flights"] == 1
    assert payload["summary"]["total_hours"] == 1.0


def test_pilot_hours_keeps_pilots_with_no_flights_on_the_selected_vehicle(client, db, pilot_headers):
    _fleet(db)
    one = db.query(Vehicle).filter_by(serial_number="SN-ONE").one()

    resp = client.post(
        GENERATE_URL,
        json={"report_type": "pilot_hours", "vehicle_ids": [one.id]},
        headers=pilot_headers,
    )

    rows = _rows_by_pilot(resp.json())
    assert "Ben Boyd" in rows
    assert rows["Ben Boyd"]["hours"] == 0
    assert rows["Ben Boyd"]["flights"] == 0


# --- Pilot Activity Summary -------------------------------------------------
#
# Same defect class as the Pilot Hours vehicle filter: the UI always sends
# pilot_ids and vehicle_ids for every report type, and this generator read
# neither, so selecting one pilot silently returned the whole roster.




# --- Per-Pilot Annual Review: aircraft breakdown + service history -----------
#
# "Time in service" is derived from flights, because a pilot record carries no
# hire date and its created_at is when the row entered the app.




def test_activity_summary_without_pilot_filter_covers_the_active_roster(client, db, pilot_headers):
    _fleet(db)

    payload = _generate(client, pilot_headers, "pilot_activity_summary")

    assert set(_rows_by_pilot(payload)) == {"Ana Alvarez", "Ben Boyd"}
    assert payload["summary"]["total_pilots"] == 2


def test_activity_summary_honors_the_pilot_filter(client, db, pilot_headers):
    ana, _ben, _one, _two = _fleet(db)

    payload = _generate(client, pilot_headers, "pilot_activity_summary", pilot_ids=[ana.id])

    rows = _rows_by_pilot(payload)
    assert set(rows) == {"Ana Alvarez"}
    assert payload["summary"]["total_pilots"] == 1
    assert rows["Ana Alvarez"]["flight_hours"] == 1.5  # both her vehicles


def test_activity_summary_includes_an_explicitly_selected_inactive_pilot(client, db, pilot_headers):
    """Naming a pilot overrides the active-only default, matching Pilot Hours."""
    ana, _ben, one, _two = _fleet(db)
    ana.status = "inactive"
    db.commit()

    assert set(_rows_by_pilot(_generate(client, pilot_headers, "pilot_activity_summary"))) == {"Ben Boyd"}

    payload = _generate(client, pilot_headers, "pilot_activity_summary", pilot_ids=[ana.id])
    assert set(_rows_by_pilot(payload)) == {"Ana Alvarez"}


def test_activity_summary_scopes_flight_hours_to_the_selected_vehicles(client, db, pilot_headers):
    ana, _ben, one, _two = _fleet(db)

    payload = _generate(client, pilot_headers, "pilot_activity_summary", pilot_ids=[ana.id], vehicle_ids=[one.id])

    rows = _rows_by_pilot(payload)
    assert rows["Ana Alvarez"]["flight_hours"] == 1.0  # 0.5 h on vehicle two excluded
    # The mixed total is called out rather than left to read as fully scoped.
    assert "not aircraft-scoped" in payload["summary"]["flight_hours_scope"]


def test_activity_summary_keeps_a_pilot_who_flew_none_of_the_selected_vehicles(client, db, pilot_headers):
    """Ben flew only vehicle two, so filtering to vehicle one must leave him in
    the report at 0 flight hours rather than dropping him."""
    _ana, _ben, one, _two = _fleet(db)

    rows = _rows_by_pilot(_generate(client, pilot_headers, "pilot_activity_summary", vehicle_ids=[one.id]))

    assert "Ben Boyd" in rows
    assert rows["Ben Boyd"]["flight_hours"] == 0


def test_activity_summary_omits_the_scope_note_when_no_vehicle_filter(client, db, pilot_headers):
    _fleet(db)

    assert "flight_hours_scope" not in _generate(client, pilot_headers, "pilot_activity_summary")["summary"]


def _section(payload, needle):
    return next(s for s in payload["sections"] if needle in s["title"])


def test_review_breaks_flight_hours_down_per_aircraft(client, db, pilot_headers):
    ana, _ben, _one, _two = _fleet(db)

    payload = _generate(client, pilot_headers, "per_pilot_annual_review", pilot_ids=[ana.id],
                      date_from="2025-01-01", date_to="2025-12-31")

    sec = _section(payload, "Aircraft Flown")
    rows = {r["vehicle"]: r for r in sec["rows"]}
    assert set(rows) == {"Skydio X2E (Vehicle One)", "Skydio X2E (Vehicle Two)"}
    assert rows["Skydio X2E (Vehicle One)"]["hours"] == 1.0
    assert rows["Skydio X2E (Vehicle Two)"]["hours"] == 0.5
    # The breakdown must reconcile with the pilot's own flight-hours figure.
    assert sec["summary"]["flight_hours"] == _section(payload, "Ana Alvarez")["summary"]["flight_hours"]


def test_review_keeps_flights_with_no_aircraft_so_the_breakdown_adds_up(client, db, pilot_headers):
    """A flight with no vehicle would otherwise be dropped by the join and make
    the per-aircraft table silently fail to match the total."""
    ana, _ben, _one, _two = _fleet(db)
    _seed_flight(db, ana.id, None, 1800)  # 0.5 h, no aircraft recorded

    payload = _generate(client, pilot_headers, "per_pilot_annual_review", pilot_ids=[ana.id],
                      date_from="2025-01-01", date_to="2025-12-31")

    sec = _section(payload, "Aircraft Flown")
    rows = {r["vehicle"]: r for r in sec["rows"]}
    assert rows["Unassigned"]["hours"] == 0.5
    assert sec["summary"]["flight_hours"] == 2.0
    assert sec["summary"]["flight_hours"] == _section(payload, "Ana Alvarez")["summary"]["flight_hours"]


def test_review_derives_time_in_service_from_flights(client, db, pilot_headers):
    ana, _ben, _one, two = _fleet(db)
    _seed_flight(db, ana.id, two.id, 3600, flight_date=date(2024, 3, 15))

    payload = _generate(client, pilot_headers, "per_pilot_annual_review", pilot_ids=[ana.id],
                      date_from="2025-01-01", date_to="2025-12-31")
    summary = _section(payload, "Ana Alvarez")["summary"]

    # Career figures span the earlier flight even though it is outside the period.
    assert summary["in_service_since"] == "2024-03-15"
    assert summary["last_flight"] == "2025-06-01"
    assert summary["career_flights"] == 3
    assert summary["career_flight_hours"] == 2.5
    # The period-scoped figure stays scoped.
    assert summary["flight_hours"] == 1.5


def test_review_monthly_activity_spans_the_whole_service_history(client, db, pilot_headers):
    ana, _ben, _one, two = _fleet(db)
    _seed_flight(db, ana.id, two.id, 3600, flight_date=date(2024, 3, 15))

    sec = _section(_generate(client, pilot_headers, "per_pilot_annual_review", pilot_ids=[ana.id],
                           date_from="2025-01-01", date_to="2025-12-31"),
                   "Monthly Activity")

    months = [r["month"] for r in sec["rows"]]
    assert months == ["2024-03", "2025-06"]
    assert sec["summary"]["first_flight"] == "2024-03"
    assert sec["summary"]["latest_activity"] == "2025-06"


def test_review_handles_a_pilot_who_has_never_flown(client, db, pilot_headers):
    nobody = _seed_pilot(db, "New", "Recruit")

    payload = _generate(client, pilot_headers, "per_pilot_annual_review", pilot_ids=[nobody.id])

    assert _section(payload, "New Recruit")["summary"]["in_service_since"] == "no flights on record"
    assert _section(payload, "Aircraft Flown")["rows"] == []
    assert _section(payload, "Monthly Activity")["rows"] == []


# --- Equipment Utilization --------------------------------------------------
#
# Third report in the family that accepted pilot_ids and vehicle_ids and read
# neither. The axis here is aircraft rather than pilots, so the outer-join rule
# from the Pilot Hours fix applies to the vehicle side instead.






def test_equipment_unfiltered_lists_only_aircraft_that_flew(client, db, pilot_headers):
    """Historical shape preserved: a vehicle nobody flew is not padded in."""
    _fleet(db)
    _seed_vehicle(db, "SN-IDLE", "Never Flown")

    rows = _rows_by_vehicle(_generate(client, pilot_headers, "equipment_utilization"))

    assert set(rows) == {"Skydio X2E (Vehicle One)", "Skydio X2E (Vehicle Two)"}
    assert rows["Skydio X2E (Vehicle One)"]["hours"] == 1.0   # Ana only
    assert rows["Skydio X2E (Vehicle Two)"]["hours"] == 2.5   # Ana 0.5 + Ben 2.0


def test_equipment_honors_the_vehicle_filter(client, db, pilot_headers):
    _ana, _ben, one, _two = _fleet(db)

    rows = _rows_by_vehicle(_generate(client, pilot_headers, "equipment_utilization", vehicle_ids=[one.id]))

    assert set(rows) == {"Skydio X2E (Vehicle One)"}
    assert rows["Skydio X2E (Vehicle One)"]["hours"] == 1.0


def test_equipment_honors_the_pilot_filter(client, db, pilot_headers):
    """Ben's 2.0 h on vehicle two must not be counted when filtering to Ana."""
    ana, _ben, _one, _two = _fleet(db)

    rows = _rows_by_vehicle(_generate(client, pilot_headers, "equipment_utilization", pilot_ids=[ana.id]))

    assert rows["Skydio X2E (Vehicle One)"]["hours"] == 1.0
    assert rows["Skydio X2E (Vehicle Two)"]["hours"] == 0.5
    assert rows["Skydio X2E (Vehicle Two)"]["flights"] == 1


def test_equipment_keeps_a_selected_aircraft_the_pilot_never_flew(client, db, pilot_headers):
    """Ben never flew vehicle one. Selecting both him and it must show the
    aircraft at 0 rather than dropping it, which a WHERE on the joined
    Flight.pilot_id would have done."""
    _ana, ben, one, two = _fleet(db)

    rows = _rows_by_vehicle(
        _generate(client, pilot_headers, "equipment_utilization", pilot_ids=[ben.id], vehicle_ids=[one.id, two.id])
    )

    assert set(rows) == {"Skydio X2E (Vehicle One)", "Skydio X2E (Vehicle Two)"}
    assert rows["Skydio X2E (Vehicle One)"]["flights"] == 0
    assert rows["Skydio X2E (Vehicle One)"]["hours"] == 0
    assert rows["Skydio X2E (Vehicle Two)"]["hours"] == 2.0


def test_equipment_selected_aircraft_with_no_flights_at_all_still_listed(client, db, pilot_headers):
    _fleet(db)
    idle = _seed_vehicle(db, "SN-IDLE", "Never Flown")

    rows = _rows_by_vehicle(_generate(client, pilot_headers, "equipment_utilization", vehicle_ids=[idle.id]))

    assert set(rows) == {"Skydio X2E (Never Flown)"}
    assert rows["Skydio X2E (Never Flown)"]["flights"] == 0


def test_equipment_date_range_still_applies_alongside_the_new_filters(client, db, pilot_headers):
    ana, _ben, one, _two = _fleet(db)
    _seed_flight(db, ana.id, one.id, 3600, flight_date=date(2024, 1, 15))

    rows = _rows_by_vehicle(_generate(
        client, pilot_headers, "equipment_utilization",
        pilot_ids=[ana.id], vehicle_ids=[one.id],
        date_from="2025-01-01", date_to="2025-12-31",
    ))

    # The 2024 flight is outside the range, so only the 1.0 h from 2025 counts.
    assert rows["Skydio X2E (Vehicle One)"]["hours"] == 1.0


# --- PDF layout -------------------------------------------------------------
#
# The summary strip divided the page width by the number of fields, so a
# thirteen-field summary got 0.56in columns and every heading wrapped onto three
# or four lines. The masthead also stacked the logo on its own line above
# centred text rather than setting it beside the titles.

def _styles():
    from reportlab.lib.styles import getSampleStyleSheet
    return getSampleStyleSheet()


def _avail_width():
    from reportlab.lib.units import inch
    return 8.5 * inch - 1.2 * inch


def _summary_grid(summary):
    from reportlab.lib.colors import HexColor
    from app.routers.reports import _build_pdf_summary_table
    els = _build_pdf_summary_table(summary, _styles(), HexColor("#dbeafe"), _avail_width())
    return els[0] if els else None


WIDE_SUMMARY = {
    "total_hours": 85.7, "flight_hours": 15.4, "mission_hours": 39.0,
    "training_hours": 31.2, "flights": 59, "missions_participated": 11,
    "trainings_attended": 14, "certifications_expired": 0,
    "certifications_expiring_90d": 0, "in_service_since": "2025-11-05",
    "last_flight": "2026-08-08", "career_flights": 60, "career_flight_hours": 15.6,
}


def test_summary_wraps_into_a_grid_instead_of_one_long_row():
    from app.routers.reports import SUMMARY_COLUMNS

    table = _summary_grid(WIDE_SUMMARY)

    rows = table._cellvalues
    assert len(rows[0]) == SUMMARY_COLUMNS, "summary should cap its row width"
    # Label row + value row per chunk.
    assert len(rows) == 2 * -(-len(WIDE_SUMMARY) // SUMMARY_COLUMNS)


def test_summary_labels_fit_on_one_line():
    """The actual complaint: headings broken across three or four lines."""
    from reportlab.platypus import Paragraph

    table = _summary_grid(WIDE_SUMMARY)
    col_w = table._colWidths[0]

    for row in table._cellvalues[::2]:          # label rows only
        for cell in row:
            if isinstance(cell, Paragraph):
                _, height = cell.wrap(col_w - 16, 1000)
                assert height <= 22, f"{cell.text!r} still wraps at {col_w/72:.2f}in"


def test_a_short_summary_is_not_padded_out():
    table = _summary_grid({"period": "2026", "pilots_reviewed": 1})

    assert len(table._cellvalues[0]) == 2


def test_summary_with_no_fields_renders_nothing():
    from reportlab.lib.colors import HexColor
    from app.routers.reports import _build_pdf_summary_table

    assert _build_pdf_summary_table({}, _styles(), HexColor("#dbeafe"), _avail_width()) == []


def test_pdf_renders_end_to_end_without_a_logo():
    """No logo configured must still produce a document, with the titles stacked
    directly rather than inside a masthead table."""
    from app.routers.reports import ReportConfig, _render_report_pdf

    data = {
        "report_type": "pilot_hours", "title": "Pilot Hours Report",
        "summary": WIDE_SUMMARY,
        "columns": ["Pilot", "Hours"], "rows": [{"pilot": "Ana", "hours": 1.5}],
    }
    buf = _render_report_pdf(data, ReportConfig(report_type="pilot_hours"),
                             "Example County Sheriff's Office", None)
    body = buf.read()
    assert body.startswith(b"%PDF"), "did not produce a PDF"
    assert len(body) > 1000


# ---------------------------------------------------------------------------
# Coverage for the previously untested report types: flight_summary,
# pilot_certifications, battery_status, maintenance_history, and the annual
# unit report. Characterization tests: they pin the CURRENT output so a later
# refactor of these (complex, compliance-critical) builders cannot change it
# unnoticed.
# ---------------------------------------------------------------------------

def _seed_mission(db, when, man_hours, reason="Search", pilots=None):
    m = MissionLog(date=when, title="Mission", reason=reason, man_hours=man_hours)
    db.add(m); db.commit(); db.refresh(m)
    for pid, hrs in (pilots or []):
        db.add(MissionLogPilot(mission_log_id=m.id, pilot_id=pid, hours=hrs))
    db.commit()
    return m


def _seed_training(db, when, man_hours, ttype="Recurrent", pilots=None):
    t = TrainingLog(date=when, title="Training", training_type=ttype, man_hours=man_hours)
    db.add(t); db.commit(); db.refresh(t)
    for pid, hrs in (pilots or []):
        db.add(TrainingLogPilot(training_log_id=t.id, pilot_id=pid, hours=hrs))
    db.commit()
    return t


def _seed_cert(db, pilot_id, name, status, issue=None, expires=None, sort_order=0):
    ct = db.query(CertificationType).filter(CertificationType.name == name).first()
    if not ct:
        ct = CertificationType(name=name, category="faa", sort_order=sort_order)
        db.add(ct); db.commit(); db.refresh(ct)
    pc = PilotCertification(pilot_id=pilot_id, certification_type_id=ct.id, status=status,
                            issue_date=issue, expiration_date=expires)
    db.add(pc); db.commit(); db.refresh(pc)
    return pc


def _seed_battery(db, serial, status="active", health=None, cycles=0):
    b = Battery(serial_number=serial, status=status, health_pct=health, cycle_count=cycles,
                manufacturer="Skydio", model="X10", vehicle_model="X10")
    db.add(b); db.commit(); db.refresh(b)
    return b


def _seed_maint(db, when, mtype, cost, entity_type="vehicle", entity_id=1, desc="work"):
    r = MaintenanceRecord(entity_type=entity_type, entity_id=entity_id, maintenance_type=mtype,
                          description=desc, performed_date=when, cost=cost, performed_by="Tech")
    db.add(r); db.commit(); db.refresh(r)
    return r


def _seed_incident(db, when, severity="minor", category="near_miss", status="open"):
    i = Incident(date=when, title="Inc", severity=severity, category=category,
                 description="d", status=status, report_type="incident")
    db.add(i); db.commit(); db.refresh(i)
    return i


def _seed_authority(db, identifier="COA-1", issue=None, expiry=None, record_status="active"):
    a = OperatingAuthority(authority_type="coa", identifier=identifier, title="Statewide COA",
                           issue_date=issue, expiry_date=expiry, record_status=record_status)
    db.add(a); db.commit(); db.refresh(a)
    return a


def _mark_uncounted(db, flight):
    flight.counts_toward_totals = False
    db.commit()


# --- flight_summary --------------------------------------------------------

def test_flight_summary_counts_only_unit_flights_by_default(client, db, pilot_headers):
    ana = _seed_pilot(db, "Ana", "Alvarez")
    one = _seed_vehicle(db, "SN-1", "One")
    _seed_flight(db, ana.id, one.id, 3600)
    _mark_uncounted(db, _seed_flight(db, ana.id, one.id, 1800))

    payload = _generate(client, pilot_headers, "flight_summary")

    assert payload["summary"]["total_flights"] == 1
    assert payload["summary"]["total_hours"] == 1.0
    assert payload["columns"][0] == "Date"
    row = payload["rows"][0]
    assert row["pilot"] == "Ana Alvarez"
    assert row["vehicle"] == "Skydio X2E"
    assert row["duration_min"] == 60.0


def test_flight_summary_include_non_unit_adds_them_back(client, db, pilot_headers):
    ana = _seed_pilot(db, "Ana", "Alvarez")
    one = _seed_vehicle(db, "SN-1", "One")
    _seed_flight(db, ana.id, one.id, 3600)
    _mark_uncounted(db, _seed_flight(db, ana.id, one.id, 1800))

    payload = _generate(client, pilot_headers, "flight_summary", include_non_unit=True)

    assert payload["summary"]["total_flights"] == 2
    assert payload["summary"]["total_hours"] == 1.5


def test_flight_summary_date_range_filters(client, db, pilot_headers):
    ana = _seed_pilot(db, "Ana", "Alvarez")
    one = _seed_vehicle(db, "SN-1", "One")
    _seed_flight(db, ana.id, one.id, 3600, flight_date=date(2025, 1, 10))
    _seed_flight(db, ana.id, one.id, 3600, flight_date=date(2025, 6, 10))

    payload = _generate(client, pilot_headers, "flight_summary",
                        date_from="2025-06-01", date_to="2025-06-30")

    assert payload["summary"]["total_flights"] == 1


# --- pilot_certifications --------------------------------------------------

def test_pilot_certifications_counts_and_appends_authorities(client, db, pilot_headers):
    ana = _seed_pilot(db, "Ana", "Alvarez")
    _seed_cert(db, ana.id, "Part 107", "active", expires=date.today() + timedelta(days=200), sort_order=1)
    _seed_cert(db, ana.id, "Night Waiver", "expired", expires=date.today() - timedelta(days=5), sort_order=2)
    _seed_cert(db, ana.id, "Recurrent", "pending", sort_order=3)
    _seed_authority(db)

    payload = _generate(client, pilot_headers, "pilot_certifications")

    s = payload["summary"]
    assert s["total_pilots"] == 1
    assert s["total_active"] == 1
    assert s["total_expired"] == 1
    assert s["total_pending"] == 1
    assert [sec["title"] for sec in payload["sections"]] == ["Pilot Certifications", "Operating Authorities"]


def test_pilot_certifications_days_until_expiry(client, db, pilot_headers):
    ana = _seed_pilot(db, "Ana", "Alvarez")
    _seed_cert(db, ana.id, "Part 107", "active", expires=date.today() + timedelta(days=30))

    payload = _generate(client, pilot_headers, "pilot_certifications")

    assert _rows_by(payload, "cert_name")["Part 107"]["days_until_expiry"] == 30


# --- battery_status --------------------------------------------------------

def test_battery_status_averages_exclude_unknown_health(client, db, pilot_headers):
    _seed_battery(db, "B-1", status="active", health=90.0, cycles=100)
    _seed_battery(db, "B-2", status="retired", health=70.0, cycles=200)
    _seed_battery(db, "B-3", status="active", health=None, cycles=0)

    payload = _generate(client, pilot_headers, "battery_status")

    s = payload["summary"]
    assert s["total_batteries"] == 3
    assert s["active"] == 2
    assert s["avg_health_pct"] == 80.0     # (90 + 70) / 2; the None is skipped
    assert s["avg_cycles"] == 100.0        # (100 + 200 + 0) / 3


# --- maintenance_history ---------------------------------------------------

def test_maintenance_history_totals_and_by_type(client, db, pilot_headers):
    _seed_maint(db, date(2025, 3, 1), "scheduled", 100.0)
    _seed_maint(db, date(2025, 4, 1), "scheduled", 50.0)
    _seed_maint(db, date(2025, 5, 1), "inspection", 0)

    payload = _generate(client, pilot_headers, "maintenance_history")

    s = payload["summary"]
    assert s["total_records"] == 3
    assert s["total_cost"] == "$150.00"
    assert "scheduled: 2" in s["records_by_type"]
    assert "inspection: 1" in s["records_by_type"]


def test_maintenance_history_date_filter(client, db, pilot_headers):
    _seed_maint(db, date(2025, 1, 1), "scheduled", 100.0)
    _seed_maint(db, date(2025, 6, 1), "scheduled", 50.0)

    payload = _generate(client, pilot_headers, "maintenance_history", date_from="2025-06-01")

    assert payload["summary"]["total_records"] == 1


# --- annual_unit_report ----------------------------------------------------

def _seed_annual_year(db, year=2025):
    ana = _seed_pilot(db, "Ana", "Alvarez")
    ben = _seed_pilot(db, "Ben", "Boyd")
    one = _seed_vehicle(db, "SN-1", "One")
    _seed_flight(db, ana.id, one.id, 3600, flight_date=date(year, 2, 1))
    _seed_flight(db, ben.id, one.id, 1800, flight_date=date(year, 3, 1))
    _seed_mission(db, date(year, 2, 15), 5.0, reason="Search", pilots=[(ana.id, 2.5), (ben.id, 2.5)])
    _seed_training(db, date(year, 4, 1), 4.0, ttype="Recurrent", pilots=[(ana.id, 4.0)])
    _seed_incident(db, date(year, 5, 1), severity="minor", category="near_miss", status="open")
    _seed_maint(db, date(year, 6, 1), "scheduled", 200.0)
    _seed_authority(db, issue=date(year - 1, 1, 1), expiry=date(year + 1, 1, 1))
    return ana, ben, one


def _annual(client, headers, year=2025):
    return _generate(client, headers, "annual_unit_report",
                     date_from=f"{year}-01-01", date_to=f"{year}-12-31")


def test_annual_report_has_all_sections_in_order(client, db, pilot_headers):
    _seed_annual_year(db, 2025)
    payload = _annual(client, pilot_headers, 2025)

    assert [s["title"] for s in payload["sections"]] == [
        "Executive Summary", "Operational Tempo", "Personnel Activity",
        "Fleet Utilization", "Mission Activity", "Training Activity",
        "Operating Authorities", "Compliance & Certifications",
        "Maintenance Summary", "Incidents & Safety", "Year-over-Year Comparison",
    ]


def test_annual_report_headline_totals(client, db, pilot_headers):
    _seed_annual_year(db, 2025)
    s = _annual(client, pilot_headers, 2025)["summary"]

    assert s["total_flights"] == 2
    assert s["total_flight_hours"] == 1.5        # (3600 + 1800) / 3600
    assert s["total_missions"] == 1
    assert s["total_training_hours"] == 4.0
    assert s["incidents_reported"] == 1


def test_annual_report_personnel_activity_uses_per_pilot_hours(client, db, pilot_headers):
    _seed_annual_year(db, 2025)
    personnel = _section(_annual(client, pilot_headers, 2025), "Personnel Activity")

    by = {r["pilot"]: r for r in personnel["rows"]}
    assert by["Ana Alvarez"]["flight_hours"] == 1.0
    assert by["Ana Alvarez"]["mission_hours"] == 2.5
    assert by["Ana Alvarez"]["training_hours"] == 4.0
    assert by["Ana Alvarez"]["total_hours"] == 7.5


def test_annual_report_yoy_spans_five_years(client, db, pilot_headers):
    _seed_annual_year(db, 2025)
    yoy = _annual(client, pilot_headers, 2025)["rows"]

    assert [r["year"] for r in yoy] == [2021, 2022, 2023, 2024, 2025]
    y25 = next(r for r in yoy if r["year"] == 2025)
    assert y25["flights"] == 2
    assert y25["flight_hours"] == 1.5


def test_annual_yoy_vehicle_count_respects_the_unit_filter(client, db, pilot_headers):
    """A vehicle that only flew a non-counted flight is left out of the
    Year-over-Year unique-vehicles count, consistent with the flight, hour and
    pilot totals in the same row. Previously the flight-based columns applied
    the counted-unit rule but the vehicle count did not, so a vendor-only
    aircraft inflated the year's fleet count."""
    ana = _seed_pilot(db, "Ana", "Alvarez")
    one = _seed_vehicle(db, "SN-1", "One")
    _mark_uncounted(db, _seed_flight(db, ana.id, one.id, 3600, flight_date=date(2025, 2, 1)))

    y25 = next(r for r in _annual(client, pilot_headers, 2025)["rows"] if r["year"] == 2025)

    assert y25["flights"] == 0            # excluded by the unit filter
    assert y25["unique_vehicles"] == 0    # its vehicle is excluded too, consistently


def test_annual_personnel_and_tempo_measure_mission_hours_differently(client, db, pilot_headers):
    """By design the two sections report different mission-hour measures:
    Operational Tempo sums log-level man_hours (total person-hours logged),
    while Personnel Activity attributes per-pilot link hours. They can differ,
    and this pins that intended distinction so a later change does not silently
    conflate them."""
    ana = _seed_pilot(db, "Ana", "Alvarez")
    ben = _seed_pilot(db, "Ben", "Boyd")
    _seed_mission(db, date(2025, 2, 1), man_hours=10.0, pilots=[(ana.id, 2.0), (ben.id, 3.0)])

    payload = _annual(client, pilot_headers, 2025)
    tempo_mission = sum(r["mission_hours"] for r in _section(payload, "Operational Tempo")["rows"])
    personnel_mission = sum(r["mission_hours"] for r in _section(payload, "Personnel Activity")["rows"])

    assert tempo_mission == 10.0          # log man_hours
    assert personnel_mission == 5.0       # sum of per-pilot hours
    assert tempo_mission != personnel_mission


# --- export endpoints: PDF and per-pilot ZIP -------------------------------

def test_generate_pdf_endpoint_returns_a_pdf(client, db, pilot_headers):
    _fleet(db)
    resp = client.post("/api/reports/generate/pdf",
                       json={"report_type": "pilot_hours"}, headers=pilot_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


def test_generate_pdf_endpoint_renders_the_annual_report_with_charts(client, db, pilot_headers):
    """The annual report drives the chart path (matplotlib) inside the PDF."""
    _seed_annual_year(db, 2025)
    resp = client.post("/api/reports/generate/pdf",
                       json={"report_type": "annual_unit_report",
                             "date_from": "2025-01-01", "date_to": "2025-12-31"},
                       headers=pilot_headers)
    assert resp.status_code == 200, resp.text
    assert resp.content.startswith(b"%PDF")
    assert len(resp.content) > 1000


def test_generate_pdf_endpoint_tolerates_an_unknown_report_type(client, db, pilot_headers):
    """An unknown type still produces a (blank) PDF rather than erroring."""
    resp = client.post("/api/reports/generate/pdf",
                       json={"report_type": "does_not_exist"}, headers=pilot_headers)
    assert resp.status_code == 200, resp.text
    assert resp.content.startswith(b"%PDF")


def test_per_pilot_zip_returns_one_pdf_per_pilot(client, db, pilot_headers):
    import io
    import zipfile

    ana = _seed_pilot(db, "Ana", "Alvarez")
    one = _seed_vehicle(db, "SN-1", "One")
    _seed_flight(db, ana.id, one.id, 3600, flight_date=date(2025, 2, 1))

    resp = client.post("/api/reports/per-pilot/zip",
                       json={"report_type": "per_pilot_annual_review",
                             "date_from": "2025-01-01", "date_to": "2025-12-31",
                             "pilot_ids": [ana.id]},
                       headers=pilot_headers)

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert names[0].endswith(".pdf")
        assert "Ana_Alvarez" in names[0]
        assert zf.read(names[0]).startswith(b"%PDF")
