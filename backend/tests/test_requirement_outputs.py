"""Requirement misses in Needs Attention, deadlines on the calendar, the CSV export and the PDF report."""

from datetime import date, datetime, timezone

import pytest

from app.models.flight_requirement import FlightRequirement, FlightRequirementResult
from app.models.pilot import Pilot
from app.models.role_permission import RolePermission

LONG_AGO = datetime(2025, 1, 1, tzinfo=timezone.utc)
OCT = (date(2026, 10, 1), date(2026, 10, 31))
SEP = (date(2026, 9, 1), date(2026, 9, 30))
REPORT_URL = "/api/reports/generate"
REPORT_PDF_URL = "/api/reports/generate/pdf"
CSV_HEADER = "Requirement,Period start,Period end,Pilot,Status,Minutes,Flights,Per model,Excused reason"


def _pilot(db):
    pilot = Pilot(first_name="Test", last_name="Pilot", status="active", created_at=LONG_AGO)
    db.add(pilot)
    db.commit()
    return pilot


def _req(db, **extra):
    values = {"name": "Monthly 1 hr", "period_type": "calendar_month", "start_date": SEP[0],
              "recurring": True, "model_mode": "all", "time_mode": "any", "target_minutes": 60,
              "created_at": LONG_AGO}
    values.update(extra)
    req = FlightRequirement(**values)
    db.add(req)
    db.commit()
    return req


def _saved(db, req, pilot, period, status, totals=None, excused=None, reason=None):
    row = FlightRequirementResult(
        requirement_id=req.id, pilot_id=pilot.id, period_start=period[0], period_end=period[1],
        status=status, totals=totals if totals is not None else {"*": {"minutes": 0, "flights": 0}},
        target_snapshot={}, excused=excused, excused_reason=reason, saved_at=LONG_AGO)
    db.add(row)
    db.commit()
    return row


def _deny(db, role, key):
    db.add(RolePermission(role=role, permission_key=key, value="no"))
    db.commit()


def _attention(client, headers, pilot):
    return client.get(f"/api/pilots/{pilot.id}/needs-attention", headers=headers).json()


# Needs Attention


def test_missed_requirement_is_listed_and_cleared_by_excusal(client, db, admin_headers):
    pilot = _pilot(db)
    req = _req(db)
    row = _saved(db, req, pilot, OCT, "missed")
    items = [i for i in _attention(client, admin_headers, pilot)["items"] if i["category"] == "requirement"]
    assert items == [{"level": "red", "category": "requirement",
                      "text": "Missed requirement: Monthly 1 hr (2026-10-01 to 2026-10-31)"}]
    row.excused = True
    db.commit()
    body = _attention(client, admin_headers, pilot)
    assert body["count"] == 0


def test_missed_requirement_is_hidden_without_requirements_view(client, db, supervisor_headers):
    pilot = _pilot(db)
    _saved(db, _req(db), pilot, OCT, "missed")
    _deny(db, "supervisor", "requirements.view")
    assert _attention(client, supervisor_headers, pilot)["count"] == 0


# Calendar


def _calendar(client, headers, start, end):
    return client.get("/api/calendar", headers=headers, params={"start": start, "end": end}).json()["events"]


def test_calendar_has_one_deadline_per_period_end_in_range(client, db, admin_headers):
    _req(db)
    events = [e for e in _calendar(client, admin_headers, "2026-10-01", "2026-11-30") if e["source"] == "requirement"]
    assert [(e["start"], e["title"]) for e in events] == [
        ("2026-10-31", "Due: Monthly 1 hr"), ("2026-11-30", "Due: Monthly 1 hr")]
    assert events[0]["category"] == "requirement"
    assert events[0]["all_day"] is True
    assert events[0]["link"] == "/settings?tab=requirements"


def test_calendar_skips_inactive_requirements(client, db, admin_headers):
    _req(db, is_active=False)
    events = _calendar(client, admin_headers, "2026-10-01", "2026-11-30")
    assert [e for e in events if e["source"] == "requirement"] == []


def test_calendar_hides_deadlines_without_requirements_view(client, db, supervisor_headers):
    _req(db)
    _deny(db, "supervisor", "requirements.view")
    events = _calendar(client, supervisor_headers, "2026-10-01", "2026-11-30")
    assert [e for e in events if e["source"] == "requirement"] == []


# CSV


def test_csv_has_header_and_a_row_per_saved_result(client, db, admin_headers):
    pilot = _pilot(db)
    req = _req(db)
    totals = {"*": {"minutes": 45, "flights": 2}, "ModelA": {"minutes": 30, "flights": 1},
              "ModelB": {"minutes": 15, "flights": 1}}
    _saved(db, req, pilot, SEP, "met", totals=totals)
    _saved(db, req, pilot, OCT, "excused", excused=True, reason="On leave")
    response = client.get(f"/api/export/requirements/{req.id}/csv", headers=admin_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0] == CSV_HEADER
    assert len(lines) == 3
    assert lines[1] == "Monthly 1 hr,2026-09-01,2026-09-30,Test Pilot,met,45,2,ModelA: 30 min / 1; ModelB: 15 min / 1,"
    assert lines[2].endswith(",excused,0,0,,On leave")


def test_csv_escapes_a_name_starting_with_a_formula_character(client, db, admin_headers):
    pilot = _pilot(db)
    req = _req(db, name="=SUM(A1)")
    _saved(db, req, pilot, OCT, "missed")
    response = client.get(f"/api/export/requirements/{req.id}/csv", headers=admin_headers)
    assert response.text.splitlines()[1].startswith("'=SUM(A1),")


def test_csv_needs_both_keys(client, db, supervisor_headers):
    req = _req(db)
    _deny(db, "supervisor", "requirements.view")
    assert client.get(f"/api/export/requirements/{req.id}/csv", headers=supervisor_headers).status_code == 403


def test_csv_filters_to_one_pilot(client, db, admin_headers):
    pilot = _pilot(db)
    other = Pilot(first_name="Other", last_name="Flyer", status="active", created_at=LONG_AGO)
    db.add(other)
    db.commit()
    req = _req(db)
    _saved(db, req, pilot, SEP, "met")
    _saved(db, req, other, SEP, "missed")
    response = client.get(f"/api/export/requirements/{req.id}/csv?pilot_id={pilot.id}", headers=admin_headers)
    assert response.status_code == 200
    lines = response.text.strip().splitlines()
    assert lines[0] == CSV_HEADER
    assert len(lines) == 2
    assert ",Test Pilot,met," in lines[1]
    assert f"pilot_{pilot.id}" in response.headers["content-disposition"]


def test_csv_for_a_pilot_without_results_has_only_the_header(client, db, admin_headers):
    req = _req(db)
    _saved(db, req, _pilot(db), SEP, "met")
    response = client.get(f"/api/export/requirements/{req.id}/csv?pilot_id=999", headers=admin_headers)
    assert response.status_code == 200
    assert response.text.strip().splitlines() == [CSV_HEADER]


def test_csv_refuses_a_pilot_id_that_is_not_a_number(client, db, admin_headers):
    req = _req(db)
    assert client.get(f"/api/export/requirements/{req.id}/csv?pilot_id=abc", headers=admin_headers).status_code == 422


def test_csv_unknown_requirement_is_404(client, admin_headers):
    assert client.get("/api/export/requirements/999/csv", headers=admin_headers).status_code == 404


# Report


def _config(**extra):
    return {"report_type": "flight_requirements", **extra}


def test_report_has_summary_and_a_row_per_result(client, db, admin_headers):
    pilot = _pilot(db)
    req = _req(db)
    _saved(db, req, pilot, SEP, "met")
    _saved(db, req, pilot, OCT, "missed")
    body = client.post(REPORT_URL, headers=admin_headers, json=_config()).json()
    assert body["summary"] == {"requirements": 1, "results": 2, "met": 1, "missed": 1, "excused": 0, "score": "50%"}
    assert len(body["rows"]) == 2
    assert len(body["columns"]) == len(body["rows"][0])


def test_report_filters_by_date_range(client, db, admin_headers):
    pilot = _pilot(db)
    req = _req(db)
    _saved(db, req, pilot, SEP, "met")
    _saved(db, req, pilot, OCT, "missed")
    body = client.post(REPORT_URL, headers=admin_headers,
                       json=_config(date_from="2026-10-01", date_to="2026-10-31")).json()
    assert body["summary"]["results"] == 1
    assert body["summary"]["score"] == "0%"


def test_report_renders_as_pdf(client, db, admin_headers):
    _saved(db, _req(db), _pilot(db), OCT, "missed")
    response = client.post(REPORT_PDF_URL, headers=admin_headers, json=_config())
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


@pytest.mark.parametrize("key", ["requirements.view", "flights.view"])
def test_report_is_refused_without_a_view_key(client, db, supervisor_headers, key):
    _deny(db, "supervisor", key)
    assert client.post(REPORT_URL, headers=supervisor_headers, json=_config()).status_code == 403
