"""Rolling requirement lapses: recording, the API, emails, the digest and outputs."""

import json
from datetime import date, datetime, time, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

import app.services.scheduler as sched
from app.models.audit_log import AuditLog
from app.models.flight import Flight
from app.models.flight_requirement import (
    FlightRequirement, FlightRequirementExcusal, FlightRequirementLapse, FlightRequirementNotice,
    FlightRequirementPilot,
)
from app.models.notification_preference import NotificationPreference
from app.models.pilot import Pilot
from app.models.setting import Setting
from app.routers import requirements as requirements_router
from app.services import email_digest, local_time, requirement_notify, requirement_standing
from app.services.email_digest import build_digest
from app.services.requirement_lapses import open_lapses, sync_lapses
from app.services.requirement_notify import notify_lapsed, send_due_reminders

TODAY = date(2026, 11, 20)
LONG_AGO = datetime(2025, 1, 1, tzinfo=timezone.utc)
URL = "/api/requirements"
TODAY_TEXT = "2026-11-20"


@pytest.fixture(autouse=True)
def unit(db, monkeypatch):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()
    monkeypatch.setattr(requirements_router, "local_today", lambda _db: TODAY)
    monkeypatch.setattr(requirement_notify, "local_today", lambda _db: TODAY)
    monkeypatch.setattr(sched, "local_today", lambda _db: TODAY)


@pytest.fixture
def smtp_only(db):
    for key, value in (("smtp_enabled", "true"), ("smtp_host", "mail.example.test"),
                       ("smtp_from_address", "unit@example.test")):
        db.add(Setting(key=key, value=value))
    db.commit()


@pytest.fixture
def smtp(db, smtp_only):
    db.add(Setting(key="requirements_emails_enabled", value="true"))
    db.commit()


@pytest.fixture
def sent(monkeypatch):
    emails = []

    def fake_send(to_address, subject, html_body, db):
        emails.append({"to": to_address, "subject": subject, "html": html_body})
        return True

    monkeypatch.setattr(email_digest, "send_email", fake_send)
    return emails


@pytest.fixture
def managers(db, admin_user, supervisor_user, viewer_user):
    admin_user.email = "admin@example.test"
    supervisor_user.email = "supervisor@example.test"
    viewer_user.email = "viewer@example.test"
    db.commit()


@pytest.fixture
def scheduler_db(_engines, monkeypatch):
    session_factory, _ = _engines
    monkeypatch.setattr(sched, "SessionLocal", session_factory)
    return session_factory


def _to(emails) -> list[str]:
    return sorted(email["to"] for email in emails)


def _pilot(db, email="pilot@example.test", created_at=LONG_AGO):
    pilot = Pilot(first_name="Test", last_name="Pilot", status="active", email=email, created_at=created_at)
    db.add(pilot)
    db.commit()
    return pilot


def _req(db, pilots=(), added_at=LONG_AGO, **extra):
    values = {"name": "Rolling 1 hr", "period_type": "rolling", "start_date": date(2026, 1, 1), "recurring": False,
              "span_length": 30, "span_unit": "days", "model_mode": "all", "time_mode": "any",
              "target_minutes": 60, "reminder_days": 7, "created_at": LONG_AGO}
    values.update(extra)
    req = FlightRequirement(**values, pilots=[FlightRequirementPilot(pilot_id=p.id, added_at=added_at)
                                              for p in pilots])
    db.add(req)
    db.commit()
    return req


def _flight(db, pilot, day, minutes=60):
    db.add(Flight(pilot_id=pilot.id, date=day, duration_seconds=minutes * 60, review_status="reviewed",
                  takeoff_time=datetime.combine(day, time(15, 0))))
    db.commit()


def _lapses(db, req=None):
    db.expire_all()
    query = db.query(FlightRequirementLapse)
    if req is not None:
        query = query.filter_by(requirement_id=req.id)
    return [(row.lapsed_on, row.recovered_on) for row in query.order_by(FlightRequirementLapse.lapsed_on)]


def _lapse(db, req, pilot, lapsed_on, recovered_on=None):
    row = FlightRequirementLapse(requirement_id=req.id, pilot_id=pilot.id, lapsed_on=lapsed_on,
                                 recovered_on=recovered_on)
    db.add(row)
    db.commit()
    return row


def _notices(db, kind):
    db.expire_all()
    return [(n.requirement_id, n.pilot_id, n.period_start)
            for n in db.query(FlightRequirementNotice).filter_by(kind=kind)]


def _excuse(client, headers, req_id, pilot_id, **body):
    return client.post(f"{URL}/{req_id}/excuse", headers=headers, json={"pilot_id": pilot_id, **body})


# Recording lapses


def test_sync_opens_one_lapse_for_a_lapsed_pilot(db):
    pilot = _pilot(db)
    req = _req(db)
    opened, closed = sync_lapses(db, TODAY)
    assert [row.pilot_id for row in opened] == [pilot.id]
    assert closed == []
    assert sync_lapses(db, TODAY) == ([], [])
    assert _lapses(db, req) == [(TODAY, None)]


def test_sync_closes_the_lapse_once_the_pilot_is_current(db):
    pilot = _pilot(db)
    req = _req(db)
    sync_lapses(db, TODAY)
    _flight(db, pilot, date(2026, 11, 22))
    later = date(2026, 11, 23)
    _opened, closed = sync_lapses(db, later)
    assert [row.pilot_id for row in closed] == [pilot.id]
    assert sync_lapses(db, later) == ([], [])
    assert _lapses(db, req) == [(TODAY, later)]


def test_sync_leaves_current_and_not_yet_due_pilots_alone(db):
    current = _pilot(db)
    newcomer = _pilot(db)
    _req(db, pilots=[current])
    _req(db, pilots=[newcomer], added_at=datetime(2026, 11, 10, tzinfo=timezone.utc))
    _flight(db, current, date(2026, 11, 10))
    assert sync_lapses(db, TODAY) == ([], [])
    assert _lapses(db) == []


def test_an_excusal_closes_an_open_lapse(db):
    pilot = _pilot(db)
    req = _req(db)
    sync_lapses(db, TODAY)
    db.add(FlightRequirementExcusal(requirement_id=req.id, pilot_id=pilot.id, excused_until=date(2026, 12, 31)))
    db.commit()
    later = date(2026, 11, 21)
    sync_lapses(db, later)
    assert _lapses(db, req) == [(TODAY, later)]


def test_sync_closes_the_lapse_of_a_pilot_no_longer_assigned(db):
    pilot = _pilot(db)
    req = _req(db)
    sync_lapses(db, TODAY)
    pilot.status = "inactive"
    db.commit()
    later = date(2026, 11, 21)
    sync_lapses(db, later)
    assert _lapses(db, req) == [(TODAY, later)]


def test_sync_keeps_the_earliest_of_two_open_lapses_after_a_merge(db):
    pilot = _pilot(db)
    req = _req(db)
    _lapse(db, req, pilot, date(2026, 11, 1))
    _lapse(db, req, pilot, date(2026, 11, 10))
    assert sync_lapses(db, TODAY) == ([], [])
    assert _lapses(db, req) == [(date(2026, 11, 1), None)]


def test_a_lapse_closed_today_reopens_when_the_pilot_lapses_again(db):
    pilot = _pilot(db)
    req = _req(db)
    _lapse(db, req, pilot, TODAY, recovered_on=TODAY)
    opened, _closed = sync_lapses(db, TODAY)
    assert len(opened) == 1
    assert _lapses(db, req) == [(TODAY, None)]


def test_sync_skips_inactive_and_periodic_requirements(db):
    _pilot(db)
    _req(db, is_active=False)
    _req(db, name="Monthly", period_type="calendar_month", recurring=True, span_length=None, span_unit=None)
    assert sync_lapses(db, TODAY) == ([], [])


def test_switching_a_requirement_off_closes_its_open_lapses(db):
    _pilot(db)
    req = _req(db)
    sync_lapses(db, TODAY)
    req.is_active = False
    db.commit()
    later = date(2026, 11, 21)
    _opened, closed = sync_lapses(db, later)
    assert len(closed) == 1
    assert _lapses(db, req) == [(TODAY, later)]


def test_changing_a_requirement_to_periodic_closes_its_open_lapses(db):
    _pilot(db)
    req = _req(db)
    sync_lapses(db, TODAY)
    req.period_type = "calendar_month"
    req.recurring = True
    db.commit()
    later = date(2026, 11, 21)
    sync_lapses(db, later)
    assert _lapses(db, req) == [(TODAY, later)]


def test_switching_back_on_opens_a_new_lapse_for_a_pilot_still_lapsed(db):
    _pilot(db)
    req = _req(db)
    sync_lapses(db, TODAY)
    req.is_active = False
    db.commit()
    sync_lapses(db, date(2026, 11, 21))
    req.is_active = True
    db.commit()
    back_on = date(2026, 11, 25)
    opened, _closed = sync_lapses(db, back_on)
    assert len(opened) == 1
    assert _lapses(db, req) == [(TODAY, date(2026, 11, 21)), (back_on, None)]


def test_open_lapses_leave_out_inactive_requirements(db):
    pilot = _pilot(db)
    active = _req(db)
    off = _req(db, name="Off", is_active=False)
    _lapse(db, active, pilot, TODAY)
    _lapse(db, off, pilot, TODAY)
    assert [(row.requirement_id, name) for row, name in open_lapses(db)] == [(active.id, "Rolling 1 hr")]


# API


def test_status_shows_the_rolling_window_and_each_pilot(client, db, viewer_headers):
    current, lapsed = _pilot(db), _pilot(db)
    req = _req(db)
    _flight(db, current, date(2026, 11, 10))
    body = client.get(f"{URL}/status", headers=viewer_headers).json()
    row = next(r for r in body["requirements"] if r["requirement_id"] == req.id)
    assert row["period_type"] == "rolling"
    assert row["current_period"] is None
    assert row["pending_periods"] == []
    assert (row["rolling"]["window_start"], row["rolling"]["window_end"]) == ("2026-10-22", TODAY_TEXT)
    pilots = {p["pilot_id"]: p for p in row["rolling"]["pilots"]}
    assert pilots[current.id]["status"] == "current"
    assert pilots[current.id]["lapse_date"] == "2026-12-10"
    assert pilots[current.id]["pilot_name"] == "Test Pilot"
    assert pilots[lapsed.id]["status"] == "lapsed"


def test_status_rows_of_periodic_requirements_carry_their_type(client, db, viewer_headers):
    _req(db, name="Monthly", period_type="calendar_month", recurring=True, span_length=None, span_unit=None)
    row = client.get(f"{URL}/status", headers=viewer_headers).json()["requirements"][0]
    assert row["period_type"] == "calendar_month"
    assert row["rolling"] is None


def test_a_page_load_records_the_lapse(client, db, viewer_headers):
    _pilot(db)
    req = _req(db)
    assert client.get(f"{URL}/status", headers=viewer_headers).status_code == 200
    assert _lapses(db, req) == [(TODAY, None)]


def test_pilot_page_lists_rolling_progress_and_lapses(client, db, viewer_headers):
    pilot = _pilot(db)
    req = _req(db)
    _lapse(db, req, pilot, date(2026, 6, 1), recovered_on=date(2026, 6, 20))
    body = client.get(f"{URL}/pilots/{pilot.id}", headers=viewer_headers).json()
    assert [(row["requirement_id"], row["status"]) for row in body["rolling"]] == [(req.id, "lapsed")]
    assert body["rolling"][0]["window_start"] == "2026-10-22"
    assert [(row["lapsed_on"], row["recovered_on"]) for row in body["lapses"]] == [
        (TODAY_TEXT, None), ("2026-06-01", "2026-06-20")]
    assert body["lapses"][0]["name"] == "Rolling 1 hr"
    assert body["current"] == []


def test_flags_include_an_open_lapse(client, db, viewer_headers):
    pilot = _pilot(db)
    req = _req(db)
    flags = client.get(f"{URL}/flags", headers=viewer_headers).json()[str(pilot.id)]
    lapse_id = db.query(FlightRequirementLapse.id).scalar()
    assert flags == [{"kind": "lapsed", "result_id": None, "lapse_id": lapse_id, "requirement_id": req.id,
                      "name": "Rolling 1 hr", "period_start": TODAY_TEXT, "period_end": None,
                      "pilot_name": "Test Pilot"}]


def test_a_racing_lapse_sync_does_not_fail_a_page_load(client, db, admin_headers, monkeypatch):
    pilot = _pilot(db)
    _req(db)

    def racing(*_args):
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))

    monkeypatch.setattr(requirement_standing, "sync_lapses", racing)
    for path in ("status", f"pilots/{pilot.id}", "flags"):
        assert client.get(f"{URL}/{path}", headers=admin_headers).status_code == 200, path


def test_a_lapse_changed_meanwhile_does_not_fail_a_page_load(client, db, admin_headers, monkeypatch):
    _pilot(db)
    _req(db)

    def stale(*_args):
        raise StaleDataError("UPDATE statement on table 'flight_requirement_lapses' expected to update 1 row")

    monkeypatch.setattr(requirement_standing, "sync_lapses", stale)
    assert client.get(f"{URL}/status", headers=admin_headers).status_code == 200


def test_excusing_a_rolling_pilot_until_a_date(client, db, admin_headers, supervisor_headers, supervisor_user):
    pilot = _pilot(db)
    req = _req(db)
    client.get(f"{URL}/status", headers=admin_headers)
    response = _excuse(client, supervisor_headers, req.id, pilot.id, excused_until="2026-12-31", reason="Leave")
    assert response.status_code == 200, response.text
    excusal = db.query(FlightRequirementExcusal).one()
    assert (excusal.excused_until, excusal.reason, excusal.excused_by_id) == (
        date(2026, 12, 31), "Leave", supervisor_user.id)
    row = client.get(f"{URL}/status", headers=admin_headers).json()["requirements"][0]
    assert row["rolling"]["pilots"][0]["status"] == "excused"
    assert row["rolling"]["pilots"][0]["excused_until"] == "2026-12-31"
    assert _lapses(db, req) == [(TODAY, TODAY)]


def test_a_rolling_excusal_closes_the_open_lapse_at_once(client, db, admin_headers):
    pilot = _pilot(db)
    req = _req(db)
    sync_lapses(db, TODAY)
    assert _excuse(client, admin_headers, req.id, pilot.id, excused_until="2026-12-31").status_code == 200
    assert _lapses(db, req) == [(TODAY, TODAY)]


def test_removing_a_rolling_excusal(client, db, admin_headers):
    pilot = _pilot(db)
    req = _req(db)
    _excuse(client, admin_headers, req.id, pilot.id, excused_until="2026-12-31")
    assert _excuse(client, admin_headers, req.id, pilot.id, excused_until=None).status_code == 200
    assert db.query(FlightRequirementExcusal).count() == 0
    row = client.get(f"{URL}/status", headers=admin_headers).json()["requirements"][0]
    assert row["rolling"]["pilots"][0]["status"] == "lapsed"


@pytest.mark.parametrize("body", [{"excused_until": "2026-11-19"}, {}, {"period_start": "2026-11-01", "excused": True}])
def test_a_rolling_excusal_needs_a_date_from_today(client, db, admin_headers, body):
    pilot = _pilot(db)
    req = _req(db)
    assert _excuse(client, admin_headers, req.id, pilot.id, **body).status_code == 422


def test_a_rolling_excusal_from_today_is_accepted(client, db, admin_headers):
    pilot = _pilot(db)
    req = _req(db)
    assert _excuse(client, admin_headers, req.id, pilot.id, excused_until=TODAY_TEXT).status_code == 200


def test_a_rolling_excusal_needs_an_assigned_pilot(client, db, admin_headers):
    assigned, other = _pilot(db), _pilot(db)
    req = _req(db, pilots=[assigned])
    assert _excuse(client, admin_headers, req.id, other.id, excused_until="2026-12-31").status_code == 422


def test_a_periodic_excuse_still_needs_a_period_start(client, db, admin_headers):
    pilot = _pilot(db)
    req = _req(db, name="Monthly", period_type="calendar_month", recurring=True, span_length=None, span_unit=None)
    assert _excuse(client, admin_headers, req.id, pilot.id, excused=True).status_code == 422


def test_deleting_a_lapse_is_for_admins_and_audited(client, db, admin_headers, supervisor_headers, admin_user):
    pilot = _pilot(db)
    req = _req(db)
    lapse = _lapse(db, req, pilot, date(2026, 6, 1), recovered_on=date(2026, 6, 20))
    path = f"{URL}/{req.id}/lapses/{lapse.id}"
    assert client.delete(path, headers=supervisor_headers).status_code == 403
    assert client.delete(f"{URL}/{req.id + 1}/lapses/{lapse.id}", headers=admin_headers).status_code == 404
    assert client.delete(path, headers=admin_headers).status_code == 200
    assert db.query(FlightRequirementLapse).filter_by(id=lapse.id).count() == 0
    entry = db.query(AuditLog).filter_by(entity_type="flight_requirement_lapse", entity_id=lapse.id).one()
    assert (entry.action, entry.user_id) == ("delete", admin_user.id)


PERIODIC = {"name": "Monthly 1 hr", "period_type": "calendar_month", "start_date": "2026-11-01",
            "recurring": True, "target_minutes": 60}


def test_an_open_lapse_cannot_be_deleted(client, db, admin_headers):
    pilot = _pilot(db)
    req = _req(db)
    lapse = _lapse(db, req, pilot, date(2026, 11, 2))
    response = client.delete(f"{URL}/{req.id}/lapses/{lapse.id}", headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["detail"] == "Only a closed lapse can be deleted"


def test_a_rolling_requirement_with_lapses_cannot_be_deleted(client, db, admin_headers):
    pilot = _pilot(db)
    req = _req(db)
    _lapse(db, req, pilot, date(2026, 6, 1), recovered_on=date(2026, 6, 20))
    response = client.delete(f"{URL}/{req.id}", headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "This requirement has saved results. Switch it off instead."


def test_a_rolling_requirement_without_lapses_can_be_deleted(client, db, admin_headers):
    req = _req(db)
    assert client.delete(f"{URL}/{req.id}", headers=admin_headers).status_code == 200


def test_patch_to_rolling_clears_recurring_and_end_date(client, admin_headers):
    req_id = client.post(URL, headers=admin_headers, json={**PERIODIC, "end_date": "2027-06-30"}).json()["id"]
    response = client.patch(f"{URL}/{req_id}", headers=admin_headers,
                            json={"period_type": "rolling", "span_length": 30, "span_unit": "days"})
    assert response.status_code == 200, response.text
    assert (response.json()["recurring"], response.json()["end_date"]) == (False, None)


def test_patch_from_rolling_to_periodic_recurs_again(client, admin_headers):
    rolling = {**PERIODIC, "period_type": "rolling", "recurring": False, "span_length": 30, "span_unit": "days"}
    req_id = client.post(URL, headers=admin_headers, json=rolling).json()["id"]
    response = client.patch(f"{URL}/{req_id}", headers=admin_headers, json={"period_type": "calendar_month"})
    assert response.status_code == 200, response.text
    assert response.json()["recurring"] is True


# Emails


def test_reminder_goes_out_reminder_days_before_the_lapse(db, smtp, sent):
    pilot = _pilot(db)
    req = _req(db)
    _flight(db, pilot, date(2026, 10, 25))  # ages out on November 24
    assert send_due_reminders(db, TODAY) == 1
    assert _to(sent) == ["pilot@example.test"]
    assert "Rolling 1 hr" in sent[0]["subject"]
    assert _notices(db, "reminder") == [(req.id, pilot.id, date(2026, 11, 24))]
    assert send_due_reminders(db, TODAY) == 0


def test_no_reminder_far_from_the_lapse(db, smtp, sent):
    pilot = _pilot(db)
    _req(db)
    _flight(db, pilot, date(2026, 11, 10))  # ages out on December 10
    assert send_due_reminders(db, TODAY) == 0
    assert sent == []


LATE_ADDED = datetime(2026, 11, 1, 18, 0, tzinfo=timezone.utc)  # November 1 locally; due December 1


@pytest.mark.parametrize(("day", "count"), [(date(2026, 11, 23), 0), (date(2026, 11, 24), 1),
                                            (date(2026, 12, 1), 0)])
def test_a_pilot_not_yet_due_is_reminded_before_becoming_due(db, smtp, sent, day, count):
    pilot = _pilot(db)
    _req(db, pilots=[pilot], added_at=LATE_ADDED)
    assert send_due_reminders(db, day) == count


def test_the_not_yet_due_reminder_is_keyed_by_the_due_date(db, smtp, sent):
    pilot = _pilot(db)
    req = _req(db, pilots=[pilot], added_at=LATE_ADDED)
    send_due_reminders(db, date(2026, 11, 28))
    assert _notices(db, "reminder") == [(req.id, pilot.id, date(2026, 12, 1))]


def test_rolling_status_of_a_pilot_not_yet_due_is_unchanged_by_reminders(client, db, admin_headers, smtp, sent):
    pilot = _pilot(db)
    _req(db, pilots=[pilot], added_at=LATE_ADDED)
    send_due_reminders(db, TODAY)
    row = client.get(f"{URL}/status", headers=admin_headers).json()["requirements"][0]
    assert row["rolling"]["pilots"][0]["status"] == "not_yet_due"


ROLLING_API = {"name": "Rolling 1 hr", "period_type": "rolling", "start_date": "2026-01-01",
               "span_length": 30, "span_unit": "days", "target_minutes": 60}


def test_creating_a_rolling_requirement_emails_its_pilots(client, db, admin_headers, smtp, sent):
    pilot = _pilot(db)
    response = client.post(URL, headers=admin_headers, json={**ROLLING_API, "pilot_ids": [pilot.id]})
    assert response.status_code == 201, response.text
    assert _to(sent) == ["pilot@example.test"]
    assert "Last 30 days" in sent[0]["html"]
    assert _notices(db, "assigned") == [(response.json()["id"], pilot.id, date(2026, 1, 1))]


def test_switching_a_rolling_requirement_on_emails_its_pilots(client, db, admin_headers, smtp, sent):
    _pilot(db)
    req_id = client.post(URL, headers=admin_headers, json={**ROLLING_API, "is_active": False}).json()["id"]
    assert sent == []
    client.patch(f"{URL}/{req_id}", headers=admin_headers, json={"is_active": True})
    assert _to(sent) == ["pilot@example.test"]


def test_adding_a_pilot_to_a_rolling_requirement_emails_only_the_new_one(client, db, admin_headers, smtp, sent):
    first = _pilot(db, email="one@example.test")
    second = _pilot(db, email="two@example.test")
    req_id = client.post(URL, headers=admin_headers, json={**ROLLING_API, "pilot_ids": [first.id]}).json()["id"]
    client.patch(f"{URL}/{req_id}", headers=admin_headers, json={"pilot_ids": [first.id, second.id]})
    assert _to(sent) == ["one@example.test", "two@example.test"]


def test_lapse_email_goes_to_the_pilot_and_managers_once(db, smtp, sent, managers):
    pilot = _pilot(db)
    req = _req(db)
    opened, _closed = sync_lapses(db, TODAY)
    assert notify_lapsed(db, opened) == 3
    assert _to(sent) == ["admin@example.test", "pilot@example.test", "supervisor@example.test"]
    assert _notices(db, "missed") == [(req.id, pilot.id, TODAY)]
    assert notify_lapsed(db, opened) == 0


def test_emails_off_send_nothing_for_rolling_requirements(db, smtp_only, sent, managers):
    pilot = _pilot(db)
    _req(db)
    _flight(db, pilot, date(2026, 10, 25))
    second = _pilot(db, email="two@example.test")
    assert send_due_reminders(db, TODAY) == 0
    opened, _closed = sync_lapses(db, TODAY)
    assert [row.pilot_id for row in opened] == [second.id]
    assert notify_lapsed(db, opened) == 0
    assert sent == []
    assert _notices(db, "missed") == []


def test_a_page_load_and_the_daily_job_open_one_lapse_and_email_once(client, db, admin_headers, scheduler_db,
                                                                     smtp, sent, managers):
    _pilot(db)
    req = _req(db)
    client.get(f"{URL}/status", headers=admin_headers)
    sched._run_requirements_daily()
    sched._run_requirements_daily()
    assert _lapses(db, req) == [(TODAY, None)]
    assert _to(sent) == ["admin@example.test", "pilot@example.test", "supervisor@example.test"]


def test_an_excused_pilot_gets_no_lapse_email(client, db, admin_headers, scheduler_db, smtp, sent, managers):
    pilot = _pilot(db)
    req = _req(db)
    client.get(f"{URL}/status", headers=admin_headers)
    _excuse(client, admin_headers, req.id, pilot.id, excused_until="2026-12-31")
    sched._run_requirements_daily()
    assert sent == []
    assert _lapses(db, req) == [(TODAY, TODAY)]


def test_daily_job_audits_lapses_and_their_emails_as_one_entry_each(db, scheduler_db, smtp, sent, managers):
    _pilot(db)
    _pilot(db, email="two@example.test")
    _req(db)
    sched._run_requirements_daily()
    db.expire_all()
    entries = sorted((entry.action, entry.entity_type, entry.details) for entry in db.query(AuditLog))
    assert entries == [
        ("send_notices", "flight_requirement_notice", "Flight requirement lapse emails"),
        ("sync_lapses", "flight_requirement_lapse", "Recorded rolling requirement lapses"),
    ]


# Digest and outputs


def test_digest_lists_lapsed_pilots(db, viewer_user, monkeypatch):
    pilot = _pilot(db)
    req = _req(db)
    _lapse(db, req, pilot, date(2026, 11, 2))
    db.add(NotificationPreference(user_id=viewer_user.id, categories=json.dumps(["requirements"])))
    db.commit()
    monkeypatch.setattr(local_time, "local_today", lambda _db: TODAY)
    section = build_digest(db, viewer_user)["requirements"]
    assert {"requirement": "Rolling 1 hr", "pilot": "Test Pilot", "status": "Lapsed since 2026-11-02"} in section


def test_needs_attention_lists_an_open_lapse(client, db, admin_headers):
    pilot = _pilot(db)
    req = _req(db)
    _lapse(db, req, pilot, date(2026, 11, 2))
    _lapse(db, req, pilot, date(2026, 6, 1), recovered_on=date(2026, 6, 20))
    items = client.get(f"/api/pilots/{pilot.id}/needs-attention", headers=admin_headers).json()["items"]
    assert items == [{"level": "red", "category": "requirement", "text": "Lapsed: Rolling 1 hr since 2026-11-02"}]


def test_csv_lists_lapse_rows(client, db, admin_headers):
    pilot = _pilot(db)
    req = _req(db)
    _lapse(db, req, pilot, date(2026, 6, 1), recovered_on=date(2026, 6, 20))
    _lapse(db, req, pilot, date(2026, 11, 2))
    lines = client.get(f"/api/export/requirements/{req.id}/csv", headers=admin_headers).text.strip().splitlines()
    assert lines[1:] == ["Rolling 1 hr,2026-06-01,2026-06-20,Test Pilot,lapsed,,,,",
                         "Rolling 1 hr,2026-11-02,,Test Pilot,lapsed,,,,"]


def test_report_lists_lapses_in_the_date_range(client, db, admin_headers):
    pilot = _pilot(db)
    req = _req(db)
    _lapse(db, req, pilot, date(2026, 6, 1), recovered_on=date(2026, 6, 20))
    _lapse(db, req, pilot, date(2026, 11, 2))
    body = client.post("/api/reports/generate", headers=admin_headers,
                       json={"report_type": "flight_requirements", "date_from": "2026-10-01"}).json()
    assert [(row["period"], row["status"]) for row in body["rows"]] == [("Since 2026-11-02", "lapsed")]
    assert body["summary"]["lapsed"] == 1

