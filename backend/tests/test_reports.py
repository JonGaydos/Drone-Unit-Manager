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

from datetime import date

from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle

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
