"""Flight requirement emails (assignment, reminder, miss), the digest section and the daily job."""

import json
from datetime import date, datetime, time, timedelta, timezone

import pytest

import app.services.scheduler as sched
from app.models.flight import Flight
from app.models.flight_requirement import (
    FlightRequirement, FlightRequirementNotice, FlightRequirementPilot, FlightRequirementResult,
)
from app.models.notification_preference import NotificationPreference
from app.models.pilot import Pilot
from app.models.role_permission import RolePermission
from app.models.setting import Setting
from app.models.user import User
from app.routers import requirements as requirements_router
from app.services import email_digest, local_time, requirement_notify, requirement_results
from app.services.email_digest import build_digest, render_digest_html
from app.services.requirement_notify import notify_assigned, notify_missed, send_due_reminders
from app.services.requirement_results import close_due_periods

TODAY = date(2026, 11, 19)
LONG_AGO = datetime(2025, 1, 1, tzinfo=timezone.utc)
REMINDER_DAY = date(2026, 11, 23)  # November ends on the 30th; 7 days before
URL = "/api/requirements"
BASE = {"name": "Monthly 1 hr", "period_type": "calendar_month", "start_date": "2026-10-01",
        "recurring": True, "target_minutes": 60}


@pytest.fixture(autouse=True)
def unit(db, monkeypatch):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()
    monkeypatch.setattr(requirement_notify, "local_today", lambda _db: TODAY)
    monkeypatch.setattr(requirements_router, "local_today", lambda _db: TODAY)


@pytest.fixture
def smtp(db):
    for key, value in (("smtp_enabled", "true"), ("smtp_host", "mail.example.test"),
                       ("smtp_from_address", "unit@example.test")):
        db.add(Setting(key=key, value=value))
    db.commit()


@pytest.fixture
def sent(monkeypatch):
    """Capture each email instead of sending it."""
    emails = []

    def fake_send(to_address, subject, html_body, db):
        emails.append({"to": to_address, "subject": subject, "html": html_body})
        return True

    monkeypatch.setattr(email_digest, "send_email", fake_send)
    return emails


def _to(emails) -> list[str]:
    return sorted(email["to"] for email in emails)


def _pilot(db, name="Test", email="pilot@example.test"):
    pilot = Pilot(first_name=name, last_name="Pilot", status="active", email=email, created_at=LONG_AGO)
    db.add(pilot)
    db.commit()
    return pilot


def _req(db, pilots=(), **extra):
    values = {"name": "Monthly 1 hr", "period_type": "calendar_month", "start_date": date(2026, 10, 1),
              "recurring": True, "model_mode": "all", "time_mode": "any", "target_minutes": 60,
              "reminder_days": 7, "created_at": LONG_AGO}
    values.update(extra)
    req = FlightRequirement(**values, pilots=[FlightRequirementPilot(pilot_id=p.id, added_at=LONG_AGO)
                                              for p in pilots])
    db.add(req)
    db.commit()
    return req


def _flight(db, pilot, day, minutes=60, review_status="reviewed"):
    db.add(Flight(pilot_id=pilot.id, date=day, duration_seconds=minutes * 60, review_status=review_status,
                  takeoff_time=datetime.combine(day, time(15, 0))))
    db.commit()


def _notices(db, kind=None):
    query = db.query(FlightRequirementNotice)
    if kind is not None:
        query = query.filter(FlightRequirementNotice.kind == kind)
    return query.all()


# Assignment


def test_assignment_emails_each_pilot_once(db, smtp, sent):
    first, second = _pilot(db, "One", "one@example.test"), _pilot(db, "Two", "two@example.test")
    req = _req(db)
    assert notify_assigned(db, req, [first.id, second.id]) == 2
    assert _to(sent) == ["one@example.test", "two@example.test"]
    assert all("Monthly 1 hr" in email["subject"] for email in sent)
    assert len(_notices(db, "assigned")) == 2
    assert {n.period_start for n in _notices(db)} == {date(2026, 11, 1)}
    assert notify_assigned(db, req, [first.id, second.id]) == 0
    assert len(sent) == 2


def test_assignment_skips_a_blank_address(db, smtp, sent):
    pilot = _pilot(db, email="")
    req = _req(db)
    assert notify_assigned(db, req, [pilot.id]) == 0
    assert sent == []
    assert _notices(db) == []


def test_assignment_escapes_user_values(db, smtp, sent):
    pilot = _pilot(db, name="<i>Ann</i>")
    req = _req(db, name="<b>Night</b> & day", description="<script>x</script>")
    notify_assigned(db, req, [pilot.id])
    html = sent[0]["html"]
    assert "<b>Night</b>" not in html and "&lt;b&gt;Night&lt;/b&gt; &amp; day" in html
    assert "<script>" not in html and "<i>Ann</i>" not in html


def test_assignment_for_an_inactive_requirement_sends_nothing(db, smtp, sent):
    pilot = _pilot(db)
    req = _req(db, is_active=False)
    assert notify_assigned(db, req, [pilot.id]) == 0
    assert sent == []


def test_a_failed_send_records_nothing(db, smtp, monkeypatch):
    monkeypatch.setattr(email_digest, "send_email", lambda *a, **k: False)
    pilot = _pilot(db)
    assert notify_assigned(db, _req(db), [pilot.id]) == 0
    assert _notices(db) == []


def test_a_notice_written_meanwhile_does_not_raise(db, smtp, monkeypatch, _engines):
    """The scheduler and a request can send the same notice at once; the
    second writer's unique-index clash is swallowed."""
    pilot = _pilot(db)
    req = _req(db)
    session_factory, _ = _engines

    def racing_send(to_address, subject, html_body, _db):
        other = session_factory()
        other.add(FlightRequirementNotice(requirement_id=req.id, pilot_id=pilot.id,
                                          period_start=date(2026, 11, 1), kind="assigned",
                                          sent_at=datetime.now(timezone.utc)))
        other.commit()
        other.close()
        return True

    monkeypatch.setattr(email_digest, "send_email", racing_send)
    assert notify_assigned(db, req, [pilot.id]) == 1
    assert len(_notices(db)) == 1


# Reminders


def test_reminder_goes_out_reminder_days_before_the_end(db, smtp, sent):
    pilot = _pilot(db)
    _req(db, pilots=[pilot])
    assert send_due_reminders(db, REMINDER_DAY - timedelta(days=1)) == 0
    assert send_due_reminders(db, REMINDER_DAY) == 1
    assert _to(sent) == ["pilot@example.test"]
    assert len(_notices(db, "reminder")) == 1
    assert send_due_reminders(db, REMINDER_DAY) == 0
    assert send_due_reminders(db, REMINDER_DAY + timedelta(days=1)) == 0


def test_a_missed_reminder_day_is_caught_up_once(db, smtp, sent):
    pilot = _pilot(db)
    _req(db, pilots=[pilot])
    assert send_due_reminders(db, REMINDER_DAY + timedelta(days=1)) == 1
    assert send_due_reminders(db, REMINDER_DAY + timedelta(days=2)) == 0
    assert _to(sent) == ["pilot@example.test"]


def test_no_reminder_on_the_last_day_of_the_period(db, smtp, sent):
    _pilot(db)
    _req(db)
    assert send_due_reminders(db, date(2026, 11, 30)) == 0
    assert sent == []


def test_reminder_skips_met_and_excused_pilots(db, smtp, sent):
    met = _pilot(db, "Met", "met@example.test")
    excused = _pilot(db, "Excused", "excused@example.test")
    behind = _pilot(db, "Behind", "behind@example.test")
    req = _req(db)
    _flight(db, met, date(2026, 11, 10))
    db.add(FlightRequirementResult(requirement_id=req.id, pilot_id=excused.id, period_start=date(2026, 11, 1),
                                   period_end=date(2026, 11, 30), excused=True, excused_reason="Leave"))
    db.commit()
    assert send_due_reminders(db, REMINDER_DAY) == 1
    assert _to(sent) == ["behind@example.test"]


def test_reminder_days_zero_sends_nothing(db, smtp, sent):
    _pilot(db)
    _req(db, reminder_days=0)
    assert send_due_reminders(db, date(2026, 11, 30)) == 0
    assert sent == []


def test_reminder_skips_an_inactive_requirement(db, smtp, sent):
    _pilot(db)
    _req(db, is_active=False)
    assert send_due_reminders(db, REMINDER_DAY) == 0


# Misses


@pytest.fixture
def managers(db, admin_user, supervisor_user, viewer_user):
    admin_user.email = "admin@example.test"
    supervisor_user.email = "supervisor@example.test"
    viewer_user.email = "viewer@example.test"
    db.add(User(username="former", password_hash="x", display_name="Former", role="supervisor",
                is_active=False, email="former@example.test"))
    db.commit()


def test_miss_emails_the_pilot_and_managers_but_not_viewers(db, smtp, sent, managers):
    first, second = _pilot(db, "One", "one@example.test"), _pilot(db, "Two", "two@example.test")
    _req(db)
    rows = close_due_periods(db, TODAY)  # October is saved as missed for both
    assert {row.status for row in rows} == {"missed"}
    assert notify_missed(db, rows) == 4
    assert _to(sent) == ["admin@example.test", "one@example.test", "supervisor@example.test",
                         "two@example.test"]
    manager_email = next(email for email in sent if email["to"] == "supervisor@example.test")
    assert first.full_name in manager_email["html"] and second.full_name in manager_email["html"]
    assert len(_notices(db, "missed")) == 2
    assert notify_missed(db, rows) == 0
    assert len(sent) == 4


def test_miss_ignores_met_and_excused_rows(db, smtp, sent, managers):
    met, excused = _pilot(db, "Met", "met@example.test"), _pilot(db, "Off", "off@example.test")
    req = _req(db)
    _flight(db, met, date(2026, 10, 10))
    db.add(FlightRequirementResult(requirement_id=req.id, pilot_id=excused.id, period_start=date(2026, 10, 1),
                                   period_end=date(2026, 10, 31), excused=True, excused_reason="Leave"))
    db.commit()
    rows = close_due_periods(db, TODAY)
    assert notify_missed(db, rows) == 0
    assert sent == []


def test_miss_escapes_names_for_managers(db, smtp, sent, managers):
    _pilot(db, "<b>Bold</b>", "bold@example.test")
    _req(db, name="<script>alert(1)</script>")
    notify_missed(db, close_due_periods(db, TODAY))
    assert all("<script>" not in email["html"] and "<b>Bold</b>" not in email["html"] for email in sent)


def test_no_smtp_sends_and_records_nothing(db, sent, managers):
    pilot = _pilot(db)
    req = _req(db)
    rows = close_due_periods(db, TODAY)
    assert notify_assigned(db, req, [pilot.id]) == 0
    assert send_due_reminders(db, REMINDER_DAY) == 0
    assert notify_missed(db, rows) == 0
    assert sent == []
    assert _notices(db) == []


def test_smtp_switched_off_sends_nothing(db, smtp, sent):
    db.query(Setting).filter(Setting.key == "smtp_enabled").update({"value": "false"})
    db.commit()
    pilot = _pilot(db)
    assert notify_assigned(db, _req(db), [pilot.id]) == 0
    assert sent == []


# Router wiring


def _api_create(client, headers, **changes):
    response = client.post(URL, headers=headers, json={**BASE, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def test_creating_a_requirement_emails_its_pilots(client, db, admin_headers, smtp, sent):
    _pilot(db, "One", "one@example.test")
    _pilot(db, "Two", "two@example.test")
    _api_create(client, admin_headers)
    assert _to(sent) == ["one@example.test", "two@example.test"]


def test_creating_an_inactive_requirement_emails_nobody(client, db, admin_headers, smtp, sent):
    _pilot(db)
    _api_create(client, admin_headers, is_active=False)
    assert sent == []


def test_switching_on_emails_every_assigned_pilot(client, db, admin_headers, smtp, sent):
    _pilot(db, "One", "one@example.test")
    _pilot(db, "Two", "two@example.test")
    created = _api_create(client, admin_headers, is_active=False)
    response = client.patch(f"{URL}/{created['id']}", headers=admin_headers, json={"is_active": True})
    assert response.status_code == 200, response.text
    assert _to(sent) == ["one@example.test", "two@example.test"]


def test_adding_a_pilot_emails_only_the_new_one(client, db, admin_headers, smtp, sent):
    first = _pilot(db, "One", "one@example.test")
    second = _pilot(db, "Two", "two@example.test")
    created = _api_create(client, admin_headers, pilot_ids=[first.id])
    assert _to(sent) == ["one@example.test"]
    response = client.patch(f"{URL}/{created['id']}", headers=admin_headers,
                            json={"pilot_ids": [first.id, second.id]})
    assert response.status_code == 200, response.text
    assert _to(sent) == ["one@example.test", "two@example.test"]


def test_narrowing_from_all_pilots_emails_nobody(client, db, admin_headers, smtp, sent):
    first = _pilot(db, "One", "one@example.test")
    _pilot(db, "Two", "two@example.test")
    created = _api_create(client, admin_headers)
    sent.clear()
    db.query(FlightRequirementNotice).delete()
    db.commit()
    response = client.patch(f"{URL}/{created['id']}", headers=admin_headers, json={"pilot_ids": [first.id]})
    assert response.status_code == 200, response.text
    assert sent == []


def test_an_email_error_never_fails_the_request(client, db, admin_headers, smtp, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("mail server exploded")

    monkeypatch.setattr(email_digest, "send_email", broken)
    _pilot(db)
    created = _api_create(client, admin_headers, is_active=False)
    response = client.patch(f"{URL}/{created['id']}", headers=admin_headers, json={"is_active": True})
    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is True


# Digest


@pytest.fixture
def digest_day(monkeypatch):
    def set_day(day):
        monkeypatch.setattr(local_time, "local_today", lambda _db: day)
    return set_day


def _section(db, user):
    return (build_digest(db, user) or {}).get("requirements")


def test_digest_lists_periods_ending_soon_with_pilots_not_met(db, viewer_user, digest_day):
    _pilot(db)
    _req(db)
    digest_day(date(2026, 11, 25))
    section = _section(db, viewer_user)
    assert section and "1 of 1 pilots not met" in json.dumps(section)


def test_digest_leaves_out_a_period_far_from_its_end(db, viewer_user, digest_day):
    _pilot(db)
    _req(db, start_date=date(2026, 11, 1))
    digest_day(date(2026, 11, 10))
    assert _section(db, viewer_user) is None


def test_digest_lists_periods_pending_review_with_unreviewed_flights(db, viewer_user, digest_day):
    pilot = _pilot(db)
    _req(db)
    _flight(db, pilot, date(2026, 10, 20), review_status="needs_review")
    digest_day(date(2026, 11, 5))
    text = json.dumps(_section(db, viewer_user))
    assert "Pending review" in text and "1 of 1 pilots not met, 1 unreviewed flight" in text


def test_digest_leaves_out_a_pending_period_every_pilot_met(db, viewer_user, digest_day):
    pilot = _pilot(db)
    _req(db)
    _flight(db, pilot, date(2026, 10, 20))
    digest_day(date(2026, 11, 5))
    assert _section(db, viewer_user) is None


def test_digest_lists_misses_saved_in_the_last_week(db, viewer_user, digest_day):
    pilot = _pilot(db, "Recent")
    old = _pilot(db, "Older")
    req = _req(db, pilots=[pilot, old])
    now = datetime.now(timezone.utc)
    for who, saved_at in ((pilot, now - timedelta(days=2)), (old, now - timedelta(days=10))):
        db.add(FlightRequirementResult(requirement_id=req.id, pilot_id=who.id, period_start=date(2026, 10, 1),
                                       period_end=date(2026, 10, 31), status="missed", totals={},
                                       target_snapshot={}, saved_at=saved_at))
    db.commit()
    digest_day(date(2026, 11, 10))
    text = json.dumps(_section(db, viewer_user))
    assert "Recent Pilot" in text and "Older Pilot" not in text


def test_digest_leaves_the_section_out_when_the_category_is_off(db, viewer_user, digest_day):
    _pilot(db)
    _req(db)
    db.add(NotificationPreference(user_id=viewer_user.id, categories=json.dumps(["needs_review"])))
    db.commit()
    digest_day(date(2026, 11, 25))
    assert _section(db, viewer_user) is None


def test_digest_leaves_the_section_out_without_view(db, viewer_user, digest_day):
    _pilot(db)
    _req(db)
    db.add(RolePermission(role="viewer", permission_key="requirements.view", value="no"))
    db.commit()
    digest_day(date(2026, 11, 25))
    assert _section(db, viewer_user) is None


def test_new_preferences_include_the_requirements_category(db, viewer_user):
    pref = NotificationPreference(user_id=viewer_user.id)
    db.add(pref)
    db.commit()
    assert "requirements" in json.loads(pref.categories)


def test_digest_renders_the_section_escaped(viewer_user):
    html = render_digest_html({"requirements": [{"requirement": "<b>X</b>", "status": "Ends soon"}]},
                              viewer_user, "Unit")
    assert "Flight Requirements" in html and "<b>X</b>" not in html


# Daily job


@pytest.fixture
def scheduler_db(_engines, monkeypatch):
    session_factory, _ = _engines
    monkeypatch.setattr(sched, "SessionLocal", session_factory)
    return session_factory


def test_daily_job_runs_the_three_steps_in_order(db, scheduler_db, monkeypatch):
    pilot = _pilot(db)
    req = _req(db)
    row = FlightRequirementResult(requirement_id=req.id, pilot_id=pilot.id, period_start=date(2026, 10, 1),
                                  period_end=date(2026, 10, 31), status="missed",
                                  saved_at=datetime.now(timezone.utc))
    db.add(row)
    db.commit()
    calls = []
    monkeypatch.setattr(sched, "local_today", lambda _db: TODAY)
    monkeypatch.setattr(requirement_results, "close_due_periods",
                        lambda _db, today: calls.append(("close", today)) or [])
    monkeypatch.setattr(requirement_notify, "notify_missed",
                        lambda _db, rows: calls.append(("missed", [r.id for r in rows])) or 0)
    monkeypatch.setattr(requirement_notify, "send_due_reminders",
                        lambda _db, today: calls.append(("remind", today)) or 0)
    sched._run_requirements_daily()
    assert calls == [("close", TODAY), ("missed", [row.id]), ("remind", TODAY)]


def _fail(*_args):
    raise RuntimeError("step failed")


def test_daily_job_carries_on_after_saving_fails(db, scheduler_db, monkeypatch):
    calls = []
    monkeypatch.setattr(sched, "local_today", lambda _db: TODAY)
    monkeypatch.setattr(requirement_results, "close_due_periods", _fail)
    monkeypatch.setattr(requirement_notify, "notify_missed", lambda *_a: calls.append("missed") or 0)
    monkeypatch.setattr(requirement_notify, "send_due_reminders",
                        lambda _db, today: calls.append(today) or 0)
    sched._run_requirements_daily()
    assert calls == [TODAY]


def test_daily_job_carries_on_after_miss_emails_fail(db, scheduler_db, monkeypatch):
    pilot = _pilot(db)
    _req(db)
    calls = []
    monkeypatch.setattr(sched, "local_today", lambda _db: TODAY)
    monkeypatch.setattr(requirement_notify, "notify_missed", _fail)
    monkeypatch.setattr(requirement_notify, "send_due_reminders",
                        lambda _db, today: calls.append(today) or 0)
    sched._run_requirements_daily()
    assert calls == [TODAY]
    db.expire_all()
    assert db.query(FlightRequirementResult).filter_by(pilot_id=pilot.id, status="missed").count() == 1


def test_daily_job_sends_real_emails_end_to_end(db, scheduler_db, monkeypatch, smtp, sent, managers):
    _pilot(db)
    _req(db)
    monkeypatch.setattr(sched, "local_today", lambda _db: TODAY)
    sched._run_requirements_daily()
    assert _to(sent) == ["admin@example.test", "pilot@example.test", "supervisor@example.test"]
    assert len(_notices(db, "missed")) == 1


def test_scheduler_registers_the_daily_job(scheduler_db, monkeypatch):
    monkeypatch.setattr(sched, "_scheduler", None)
    sched.start_scheduler()
    try:
        job = sched._scheduler.get_job(sched.REQUIREMENTS_DAILY_JOB_ID)
        assert job is not None and sched.REQUIREMENTS_DAILY_JOB_ID == "requirements_daily"
        hour = next(field for field in job.trigger.fields if field.name == "hour")
        assert str(hour) == str(sched.MAINTENANCE_ALERT_HOUR)
    finally:
        sched.stop_scheduler()


def test_daily_job_emails_a_miss_a_page_load_saved(client, db, admin_headers, scheduler_db, monkeypatch, smtp,
                                                   sent, managers):
    pilot = _pilot(db)
    monthly = _req(db)
    older = _req(db, name="Old quarterly", is_active=False)
    db.add(FlightRequirementResult(requirement_id=older.id, pilot_id=pilot.id, period_start=date(2026, 7, 1),
                                   period_end=date(2026, 9, 30), status="missed", totals={}, target_snapshot={},
                                   saved_at=datetime.now(timezone.utc) - timedelta(days=20)))
    db.commit()
    assert client.get(f"{URL}/status", headers=admin_headers).status_code == 200  # saves October as missed
    monkeypatch.setattr(sched, "local_today", lambda _db: TODAY)
    sched._run_requirements_daily()
    assert _to(sent) == ["admin@example.test", "pilot@example.test", "supervisor@example.test"]
    assert all("Old quarterly" not in email["html"] for email in sent)
    db.expire_all()
    assert [(n.requirement_id, n.kind) for n in _notices(db)] == [(monthly.id, "missed")]
    sched._run_requirements_daily()
    assert len(sent) == 3
