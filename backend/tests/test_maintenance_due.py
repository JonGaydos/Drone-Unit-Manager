"""The dashboard's maintenance tile: what is due, most overdue first.

Maintenance is tracked in two places. Schedules are the recurring plan; records
are the log of work performed, each carrying its own next-due date. The tile
used to read records only, so a schedule nobody had completed yet had no record
behind it and never appeared -- and that is exactly the case most likely to be
overdue. On the instance this was found on, a Monthly Inspection thirty-one
days past due was counted in the compliance header and absent from the tile
named after it.
"""

from datetime import date, timedelta

from app.models.maintenance import MaintenanceRecord
from app.models.maintenance_schedule import MaintenanceSchedule

URL = "/api/dashboard/maintenance-due"


def _in_days(n):
    return date.today() + timedelta(days=n)


def _schedule(db, name, days, entity_id=1, active=True, entity_type="vehicle"):
    row = MaintenanceSchedule(
        name=name, entity_type=entity_type, entity_id=entity_id,
        frequency="monthly", next_due=_in_days(days) if days is not None else None,
        is_active=active)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _record(db, description, days, entity_id=1, entity_type="vehicle"):
    row = MaintenanceRecord(
        entity_type=entity_type, entity_id=entity_id, maintenance_type="inspection",
        description=description,
        next_due_date=_in_days(days) if days is not None else None)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _names(client, headers, **params):
    resp = client.get(URL, headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return [i["name"] for i in resp.json()]


# 1. Both sources ------------------------------------------------------------

def test_a_schedule_nobody_has_completed_still_appears(client, db, admin_headers):
    """The case that went missing. A recurring task with no completion has no
    record behind it, so a records-only tile never showed it."""
    _schedule(db, "Monthly Inspection", -31)

    assert _names(client, admin_headers) == ["Monthly Inspection"]


def test_an_ad_hoc_record_with_a_due_date_appears(client, db, admin_headers):
    """Not everything with a due date comes from a schedule."""
    _record(db, "RMA for Gimbal", 14)

    assert _names(client, admin_headers) == ["RMA for Gimbal"]


def test_both_are_listed_together(client, db, admin_headers):
    _schedule(db, "Monthly Inspection", -31)
    _record(db, "RMA for Gimbal", 14, entity_id=2)

    assert _names(client, admin_headers) == ["Monthly Inspection", "RMA for Gimbal"]


# 2. Ordering ----------------------------------------------------------------

def test_the_most_overdue_comes_first(client, db, admin_headers):
    """Days remaining ascending, so overdue sorts above anything in the future.
    The point of the tile is what needs attention, not what is coming up."""
    _schedule(db, "Due in twenty", 20, entity_id=1)
    _schedule(db, "Overdue by five", -5, entity_id=2)
    _schedule(db, "Overdue by thirty", -30, entity_id=3)
    _schedule(db, "Due in eighty-six", 86, entity_id=4)

    assert _names(client, admin_headers) == [
        "Overdue by thirty", "Overdue by five", "Due in twenty", "Due in eighty-six"]


def test_two_items_due_the_same_day_are_ordered_by_name(client, db, admin_headers):
    """Otherwise the tile reshuffles itself between loads."""
    _schedule(db, "Brinc Lemur #2 Inspection", 20, entity_id=2)
    _schedule(db, "Brinc Lemur #1 Inspection", 20, entity_id=1)

    assert _names(client, admin_headers) == [
        "Brinc Lemur #1 Inspection", "Brinc Lemur #2 Inspection"]


def test_days_remaining_is_negative_when_overdue(client, db, admin_headers):
    _schedule(db, "Monthly Inspection", -31)

    item = client.get(URL, headers=admin_headers).json()[0]

    assert item["days_remaining"] == -31
    assert item["due_date"] == _in_days(-31).isoformat()


def test_something_due_today_is_zero_not_overdue(client, db, admin_headers):
    _schedule(db, "Due today", 0)

    assert client.get(URL, headers=admin_headers).json()[0]["days_remaining"] == 0


# 3. The duplicate a completed schedule leaves behind -------------------------

def test_a_schedule_and_its_generated_record_appear_once(client, db, admin_headers):
    """Completing a schedule auto-creates a record carrying the schedule's new
    due date, so every recurring task done once exists in both tables. Listed
    twice, the tile is half padding."""
    _schedule(db, "Brinc Lemur #1 Inspection", 20, entity_id=7)
    _record(db, "Brinc Lemur #1 Inspection", 20, entity_id=7)

    items = client.get(URL, headers=admin_headers).json()

    assert len(items) == 1
    assert items[0]["source"] == "schedule", "the schedule is the thing that recurs"


def test_a_record_for_the_same_equipment_on_a_different_date_is_kept(client, db, admin_headers):
    """Matching is on the equipment and the date. A second, genuinely different
    piece of work on the same airframe is not a duplicate."""
    _schedule(db, "Brinc Lemur #1 Inspection", 20, entity_id=7)
    _record(db, "Battery replacement", 45, entity_id=7)

    assert _names(client, admin_headers) == ["Brinc Lemur #1 Inspection", "Battery replacement"]


def test_a_record_for_different_equipment_on_the_same_date_is_kept(client, db, admin_headers):
    _schedule(db, "Lemur #1 Inspection", 20, entity_id=1)
    _record(db, "Lemur #2 Inspection", 20, entity_id=2)

    assert len(client.get(URL, headers=admin_headers).json()) == 2


# 4. What is left out --------------------------------------------------------

def test_an_inactive_schedule_is_left_out(client, db, admin_headers):
    """A paused schedule should not nag."""
    _schedule(db, "Retired check", -50, active=False)

    assert _names(client, admin_headers) == []


def test_anything_without_a_due_date_is_left_out(client, db, admin_headers):
    """There is no countdown to show and nothing to sort it by."""
    _schedule(db, "Undated schedule", None)
    _record(db, "Undated record", None)

    assert _names(client, admin_headers) == []


def test_nothing_due_returns_an_empty_list(client, db, admin_headers):
    assert client.get(URL, headers=admin_headers).json() == []


# 5. The limit ---------------------------------------------------------------

def test_only_the_first_five_are_returned(client, db, admin_headers):
    """The tile is a summary. Five covers everything overdue on a unit this
    size without becoming the page."""
    for i in range(8):
        _schedule(db, f"Task {i}", i, entity_id=i)

    assert _names(client, admin_headers) == ["Task 0", "Task 1", "Task 2", "Task 3", "Task 4"]


def test_the_limit_is_adjustable(client, db, admin_headers):
    for i in range(4):
        _schedule(db, f"Task {i}", i, entity_id=i)

    assert len(_names(client, admin_headers, limit=2)) == 2


def test_a_nonsense_limit_returns_nothing_rather_than_everything(client, db, admin_headers):
    _schedule(db, "Task", 1)

    assert _names(client, admin_headers, limit=-1) == []


# 6. Access ------------------------------------------------------------------

def test_the_endpoint_requires_a_login(client, db):
    _schedule(db, "Monthly Inspection", -31)

    assert client.get(URL).status_code == 401
