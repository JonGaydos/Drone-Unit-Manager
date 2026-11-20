"""Flight requirement emails: assignment, reminder and miss, and for rolling
requirements a reminder before the projected lapse and a lapse email.

Each email goes out at most once per requirement, pilot, period start and kind
(for a rolling requirement the period start is the projected lapse date of a
reminder, or the start of a lapse):
a ``FlightRequirementNotice`` row is written after a successful send, and a
pilot with a notice already gets nothing. Nothing is sent, and nothing
recorded, unless the unit switched requirement emails on, while SMTP is not
set up, or when the address is blank. The switch is off by default.
"""

import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from html import escape

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import APP_TITLE
from app.models.flight_requirement import (
    FlightRequirement, FlightRequirementLapse, FlightRequirementNotice, FlightRequirementResult,
)
from app.models.pilot import Pilot
from app.models.setting import Setting
from app.models.user import User
from app.services import email_digest
from app.services.audit_capture import machine_run
from app.services.local_time import local_today
from app.services.permissions import can
from app.services.requirement_eval import (
    ALL_KEY, EXCUSED, MET, MISSED, PilotProgress, evaluate_period, unit_eval_settings,
)
from app.services.requirement_periods import Period, period_containing, periods_between
from app.services.requirement_rolling import CURRENT, RollingProgress, evaluate_rolling

logger = logging.getLogger(__name__)

ASSIGNED, REMINDER, MISSED_NOTICE = "assigned", "reminder", "missed"
# A requirement that starts later is announced for its first period within a year.
ASSIGNMENT_LOOKAHEAD_DAYS = 366
EMAILS_ENABLED_KEY = "requirements_emails_enabled"
NoticeKey = tuple[int, int, date]  # requirement, pilot, period start

_CELL = 'style="padding:6px 12px;border-bottom:1px solid #eee;"'


def _setting(db: Session, key: str) -> str:
    row = db.get(Setting, key)
    return (row.value or "") if row else ""


def smtp_ready(db: Session) -> bool:
    """Whether SMTP is switched on and has a server and a sender."""
    return (_setting(db, "smtp_enabled") == "true"
            and bool(_setting(db, "smtp_host")) and bool(_setting(db, "smtp_from_address")))


def emails_enabled(db: Session) -> bool:
    """Whether the unit switched requirement emails on (off unless set to "true")."""
    return _setting(db, EMAILS_ENABLED_KEY) == "true"


def _can_send(db: Session) -> bool:
    return emails_enabled(db) and smtp_ready(db)


def _org_name(db: Session) -> str:
    return _setting(db, "org_name") or APP_TITLE


def _one_line(text: str) -> str:
    """Collapse whitespace, so a name cannot break a header line."""
    return " ".join(text.split())


def _day(value: date) -> str:
    return f"{value:%b} {value.day}, {value.year}"


def _period_text(period: Period) -> str:
    return f"{_day(period[0])} to {_day(period[1])}"


def _target_text(req: FlightRequirement) -> str:
    parts = []
    if req.target_minutes is not None:
        parts.append(f"{req.target_minutes} minutes")
    if req.target_flights is not None:
        parts.append(f"{req.target_flights} flights")
    return " and ".join(parts)


def _page(org_name: str, title: str, greeting: str, body_html: str) -> str:
    """The shared email frame. ``org_name``, ``title`` and ``greeting`` are
    plain text and escaped here; ``body_html`` must already be escaped."""
    return f"""<html><body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px;margin:0;">
<div style="max-width:600px;margin:0 auto;background:white;border-radius:8px;overflow:hidden;">
  <div style="background:#1a1a2e;color:white;padding:20px;text-align:center;">
    <h1 style="margin:0;font-size:20px;">{escape(org_name)}</h1>
    <p style="margin:4px 0 0;opacity:0.8;font-size:13px;">{escape(title)}</p>
  </div>
  <div style="padding:24px;">
    <p style="margin:0 0 16px;">Hi {escape(greeting)},</p>
    {body_html}
  </div>
</div>
</body></html>"""


def _paragraph(text: str) -> str:
    return f'<p style="margin:0 0 16px;color:#333;">{escape(text)}</p>'


def _table(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    head = "".join(f'<th style="padding:8px 12px;text-align:left;">{escape(h)}</th>' for h in header)
    body = "".join("<tr>" + "".join(f"<td {_CELL}>{escape(cell)}</td>" for cell in row) + "</tr>"
                   for row in rows)
    return (f'<table style="border-collapse:collapse;width:100%;margin:8px 0 24px;border:1px solid #eee;">'
            f'<thead><tr style="background:#fafafa;">{head}</tr></thead><tbody>{body}</tbody></table>')


def _requirement_html(req: FlightRequirement, period: Period | None) -> str:
    """The requirement as a table; for a rolling one, its window length instead of a period."""
    when = ("Window", f"Last {req.span_length} {req.span_unit}") if req.period_type == "rolling" else (
        "Period", _period_text(period))
    rows = [("Requirement", req.name), ("Target", _target_text(req)), when]
    if req.description:
        rows.append(("Details", req.description))
    return _table(("", ""), rows)


# Notices


def _sent_before(db: Session, key: NoticeKey, kind: str) -> bool:
    return db.query(FlightRequirementNotice.id).filter_by(
        requirement_id=key[0], pilot_id=key[1], period_start=key[2], kind=kind).first() is not None


def _record(db: Session, key: NoticeKey, kind: str) -> None:
    """Write the notice. When another run wrote it meanwhile, the unique index
    refuses this one; only this insert is rolled back."""
    try:
        with db.begin_nested():
            db.add(FlightRequirementNotice(requirement_id=key[0], pilot_id=key[1], period_start=key[2],
                                           kind=kind, sent_at=datetime.now(timezone.utc)))
    except IntegrityError:
        logger.info("Requirement notice %s for %s was already recorded", kind, key)
    db.commit()


@contextmanager
def notice_run(db: Session, details: str):
    """Record the notices written in this block as one audit entry, then commit it."""
    completed = False
    try:
        with machine_run(db, "send_notices", "flight_requirement_notice", details=details):
            yield
        completed = True
    finally:
        if completed:
            db.commit()


def _send_once(db: Session, key: NoticeKey, kind: str, address: str | None, subject: str, html: str) -> bool:
    """Send unless the address is blank or the notice exists, and record it after a successful send."""
    if not (address or "").strip() or _sent_before(db, key, kind):
        return False
    if not email_digest.send_email(address, _one_line(subject), html, db):
        return False
    _record(db, key, kind)
    return True


def _pilots(db: Session, pilot_ids) -> dict[int, Pilot]:
    return {pilot.id: pilot for pilot in db.query(Pilot).filter(Pilot.id.in_(list(pilot_ids)))}


def _greeting(pilot: Pilot) -> str:
    return pilot.first_name or pilot.full_name


# Assignment


def _assignment_period(req: FlightRequirement, fiscal_start_month: int, today: date) -> Period | None:
    """The period running today, else the next one to start."""
    spec = req.to_period_spec(fiscal_start_month)
    upcoming = periods_between(spec, today, today + timedelta(days=ASSIGNMENT_LOOKAHEAD_DAYS))
    return upcoming[0] if upcoming else None


def notify_assigned(db: Session, req: FlightRequirement, pilot_ids: list[int]) -> int:
    """Email each pilot that they now have ``req`` to meet, for the period
    running today or the next one. Returns the number sent."""
    if not req.is_active or not pilot_ids or not _can_send(db):
        return 0
    period = _assignment_period(req, unit_eval_settings(db).fiscal_start_month, local_today(db))
    if period is None:
        return 0
    org_name = _org_name(db)
    body = _paragraph("You have been assigned a flight requirement:") + _requirement_html(req, period)
    sent = 0
    with notice_run(db, "Flight requirement assignment emails"):
        for pilot in sorted(_pilots(db, pilot_ids).values(), key=lambda p: p.id):
            html = _page(org_name, "Flight Requirement Assigned", _greeting(pilot), body)
            sent += _send_once(db, (req.id, pilot.id, period[0]), ASSIGNED, pilot.email,
                               f"Flight requirement assigned: {req.name}", html)
    return sent


def notify_joined(db: Session, pilot_id: int) -> int:
    """Email a pilot who has just become active about each active requirement
    that applies to every active pilot. Returns the number sent."""
    requirements = db.query(FlightRequirement).filter(
        FlightRequirement.is_active.is_(True), ~FlightRequirement.pilots.any(),
    ).order_by(FlightRequirement.id).all()
    return sum(notify_assigned(db, req, [pilot_id]) for req in requirements)


# Reminders


def _totals_rows(progress: PilotProgress | RollingProgress) -> list[tuple[str, ...]]:
    return [("Any aircraft" if key == ALL_KEY else key, f"{int(total['minutes'])} minutes",
             f"{total['flights']} flights") for key, total in progress.totals.items()]


def _remind(db: Session, req: FlightRequirement, period: Period, today: date, grace_days: int,
            org_name: str) -> int:
    progress = evaluate_period(db, req, period, today, grace_days)
    behind = [p for p in progress.values() if p.status not in (MET, EXCUSED)]
    pilots = _pilots(db, (p.pilot_id for p in behind))
    sent = 0
    for pilot_progress in behind:
        pilot = pilots[pilot_progress.pilot_id]
        body = (_paragraph(f"This period ends on {_day(period[1])} and you have not met this requirement yet.")
                + _requirement_html(req, period)
                + _paragraph("Your reviewed flights so far:")
                + _table(("Aircraft", "Time", "Flights"), _totals_rows(pilot_progress)))
        html = _page(org_name, "Flight Requirement Reminder", _greeting(pilot), body)
        sent += _send_once(db, (req.id, pilot.id, period[0]), REMINDER, pilot.email,
                           f"Flight requirement reminder: {req.name}", html)
    return sent


def _rolling_due(req: FlightRequirement, progress: RollingProgress, today: date) -> bool:
    return (progress.status == CURRENT and progress.lapse_date is not None
            and 0 < (progress.lapse_date - today).days <= req.reminder_days)


def _remind_rolling(db: Session, req: FlightRequirement, today: date, org_name: str) -> int:
    """Remind each current pilot whose projected lapse is ``reminder_days`` or
    fewer days away, once per projected lapse date."""
    due = [p for p in evaluate_rolling(db, req, today).values() if _rolling_due(req, p, today)]
    pilots = _pilots(db, (p.pilot_id for p in due))
    sent = 0
    for progress in due:
        pilot = pilots[progress.pilot_id]
        body = (_paragraph(f"You lapse on {_day(progress.lapse_date)} unless you fly again before then.")
                + _requirement_html(req, None)
                + _paragraph("Your reviewed flights in the window:")
                + _table(("Aircraft", "Time", "Flights"), _totals_rows(progress)))
        html = _page(org_name, "Flight Requirement Reminder", _greeting(pilot), body)
        sent += _send_once(db, (req.id, pilot.id, progress.lapse_date), REMINDER, pilot.email,
                           f"Flight requirement reminder: {req.name}", html)
    return sent


def _remind_periodic(db: Session, req: FlightRequirement, settings, today: date, org_name: str) -> int:
    period = period_containing(req.to_period_spec(settings.fiscal_start_month), today)
    if period is None or not 0 < (period[1] - today).days <= req.reminder_days:
        return 0
    return _remind(db, req, period, today, settings.grace_days, org_name)


def send_due_reminders(db: Session, today: date) -> int:
    """Remind each assigned pilot who has not met an active requirement, and is
    not excused, once its period ends ``reminder_days`` or fewer days after
    ``today`` (and not today), so a missed run is caught up the next day. The
    reminder notice keeps it to one per pilot per period. On a rolling
    requirement, remind each current pilot ``reminder_days`` or fewer days
    before their projected lapse, once per lapse date. Returns the number sent."""
    if not _can_send(db):
        return 0
    settings = unit_eval_settings(db)
    org_name = _org_name(db)
    sent = 0
    reqs = db.query(FlightRequirement).filter(
        FlightRequirement.is_active.is_(True), FlightRequirement.reminder_days > 0,
    ).order_by(FlightRequirement.id).all()
    for req in reqs:
        if req.period_type == "rolling":
            sent += _remind_rolling(db, req, today, org_name)
        else:
            sent += _remind_periodic(db, req, settings, today, org_name)
    return sent


# Misses


def _key(row: FlightRequirementResult) -> NoticeKey:
    return row.requirement_id, row.pilot_id, row.period_start


def _manager_addresses(db: Session) -> list[str]:
    """Each active user whose role holds requirements.manage, by address, once."""
    users = db.query(User).filter(User.is_active.is_(True)).order_by(User.id).all()
    addresses: dict[str, str] = {}
    for user in users:
        address = (user.email or "").strip()
        if address and can(db, user, "requirements.manage"):
            addresses.setdefault(address.casefold(), address)
    return list(addresses.values())


def _send_managers(db: Session, title: str, subject: str, body: str, org_name: str) -> int:
    html = _page(org_name, title, "there", body)
    return sum(email_digest.send_email(address, subject, html, db) for address in _manager_addresses(db))


def _pilot_name(pilots: dict[int, Pilot], pilot_id: int) -> str:
    return pilots[pilot_id].full_name if pilot_id in pilots else ""


def _email_managers(db: Session, misses: list[FlightRequirementResult], reqs: dict[int, FlightRequirement],
                    pilots: dict[int, Pilot], org_name: str) -> int:
    rows = [(_pilot_name(pilots, row.pilot_id), reqs[row.requirement_id].name,
             _period_text((row.period_start, row.period_end))) for row in misses]
    body = (_paragraph(f"{len(misses)} flight requirement results were saved as missed:")
            + _table(("Pilot", "Requirement", "Period"), rows))
    return _send_managers(db, "Flight Requirements Missed", f"Flight requirements missed ({len(misses)})", body,
                          org_name)


def _email_missed_pilot(db: Session, row: FlightRequirementResult, req: FlightRequirement, pilot: Pilot | None,
                        org_name: str) -> bool:
    if pilot is None or not (pilot.email or "").strip():
        return False
    period = (row.period_start, row.period_end)
    body = (_paragraph(f"The period {_period_text(period)} has closed and this requirement was not met.")
            + _requirement_html(req, period))
    html = _page(org_name, "Flight Requirement Missed", _greeting(pilot), body)
    return email_digest.send_email(pilot.email, _one_line(f"Flight requirement missed: {req.name}"), html, db)


def notify_missed(db: Session, results: list[FlightRequirementResult]) -> int:
    """Email each pilot whose saved result in ``results`` is missed, and send
    every active user with requirements.manage one email listing them all.
    A miss is announced once: its notice is written when an email about it got
    through, and a miss with a notice is left out. Returns the number sent."""
    if not _can_send(db):
        return 0
    misses = [row for row in results if row.status == MISSED and not _sent_before(db, _key(row), MISSED_NOTICE)]
    if not misses:
        return 0
    org_name = _org_name(db)
    reqs = {req.id: req for req in db.query(FlightRequirement).filter(
        FlightRequirement.id.in_({row.requirement_id for row in misses}))}
    pilots = _pilots(db, {row.pilot_id for row in misses})
    told = [_email_missed_pilot(db, row, reqs[row.requirement_id], pilots.get(row.pilot_id), org_name)
            for row in misses]
    managers_told = _email_managers(db, misses, reqs, pilots, org_name)
    # One "missed" notice covers both the pilot and the managers: once a
    # manager email went out, a failed pilot send is not retried.
    for row, pilot_told in zip(misses, told):
        if pilot_told or managers_told:
            _record(db, _key(row), MISSED_NOTICE)
    return sum(told) + managers_told


# Lapses


def _lapse_key(row: FlightRequirementLapse) -> NoticeKey:
    return row.requirement_id, row.pilot_id, row.lapsed_on


def _email_lapsed_pilot(db: Session, row: FlightRequirementLapse, req: FlightRequirement, pilot: Pilot | None,
                        org_name: str) -> bool:
    if pilot is None or not (pilot.email or "").strip():
        return False
    body = (_paragraph(f"As of {_day(row.lapsed_on)} you no longer meet this requirement. "
                       "Fly the target within the window to be current again.")
            + _requirement_html(req, None))
    html = _page(org_name, "Flight Requirement Lapsed", _greeting(pilot), body)
    return email_digest.send_email(pilot.email, _one_line(f"Flight requirement lapsed: {req.name}"), html, db)


def notify_lapsed(db: Session, lapses: list[FlightRequirementLapse]) -> int:
    """Email each pilot whose lapse in ``lapses`` started, and send every
    active user with requirements.manage one email listing them all. A lapse
    is announced once, as a "missed" notice keyed by its start, as for
    ``notify_missed``. Returns the number sent."""
    if not _can_send(db):
        return 0
    fresh = [row for row in lapses if not _sent_before(db, _lapse_key(row), MISSED_NOTICE)]
    if not fresh:
        return 0
    org_name = _org_name(db)
    reqs = {req.id: req for req in db.query(FlightRequirement).filter(
        FlightRequirement.id.in_({row.requirement_id for row in fresh}))}
    pilots = _pilots(db, {row.pilot_id for row in fresh})
    told = [_email_lapsed_pilot(db, row, reqs[row.requirement_id], pilots.get(row.pilot_id), org_name)
            for row in fresh]
    rows = [(_pilot_name(pilots, row.pilot_id), reqs[row.requirement_id].name, _day(row.lapsed_on))
            for row in fresh]
    body = (_paragraph(f"{len(fresh)} pilots lapsed on a rolling flight requirement:")
            + _table(("Pilot", "Requirement", "Lapsed on"), rows))
    managers_told = _send_managers(db, "Flight Requirements Lapsed", f"Flight requirements lapsed ({len(fresh)})",
                                   body, org_name)
    for row, pilot_told in zip(fresh, told):
        if pilot_told or managers_told:
            _record(db, _lapse_key(row), MISSED_NOTICE)
    return sum(told) + managers_told
