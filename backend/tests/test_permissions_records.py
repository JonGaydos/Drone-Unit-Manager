"""Operational record routes enforce the role permission grid, including ownership."""

from datetime import date

import pytest

from app.models.alert import Alert
from app.models.calendar_event import CalendarEvent
from app.models.incident import Incident
from app.models.maintenance import MaintenanceRecord
from app.models.maintenance_schedule import MaintenanceSchedule
from app.models.pilot import Pilot

PERMISSIONS_URL = "/api/permissions"
PLANS_URL = "/api/flight-plans"
INCIDENTS_URL = "/api/incidents"
MISSIONS_URL = "/api/mission-logs"
TRAININGS_URL = "/api/training-logs"
MAINTENANCE_URL = "/api/maintenance"
SCHEDULES_URL = "/api/maintenance/schedules"
CALENDAR_URL = "/api/calendar"
EVENTS_URL = "/api/calendar/events"
CHECKLISTS_URL = "/api/checklists/templates"
CHECKOUTS_URL = "/api/equipment-checkouts"
ALERTS_URL = "/api/alerts"
RESOLVED = "resolved"


def _grid(client, headers, *changes):
    body = {"changes": [{"role": r, "key": k, "value": v} for r, k, v in changes]}
    resp = client.put(PERMISSIONS_URL, headers=headers, json=body)
    assert resp.status_code == 200, resp.text


def _other_pilot(db):
    pilot = Pilot(first_name="Other", last_name="Pilot")
    db.add(pilot)
    db.commit()
    db.refresh(pilot)
    return pilot


def _plan_body(pilot_id):
    return {"title": "Plan", "date_planned": "2026-03-01T10:00:00", "pilot_id": pilot_id}


def _incident_body():
    return {"date": "2026-03-01", "title": "Hard landing", "severity": "minor",
            "category": "other", "description": "Bumped"}


def _log_body():
    return {"date": "2026-03-01", "title": "Log", "training_type": "drill"}


def _schedule(db):
    schedule = MaintenanceSchedule(name="Check", entity_type="other", entity_id=0,
                                   frequency="monthly", is_active=True)
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def test_self_approval_blocked_even_when_granted(client, admin_headers, pilot_headers, supervisor_headers, linked_pilot):
    _grid(client, admin_headers, ("pilot", "flight_plans.approve", "yes"))
    own = client.post(PLANS_URL, headers=pilot_headers, json=_plan_body(linked_pilot.id)).json()
    assert client.post(f"{PLANS_URL}/{own['id']}/approve", headers=pilot_headers, json={}).status_code == 403
    mine = client.post(PLANS_URL, headers=supervisor_headers, json=_plan_body(linked_pilot.id)).json()
    assert client.post(f"{PLANS_URL}/{mine['id']}/approve", headers=supervisor_headers, json={}).status_code == 403
    assert client.post(f"{PLANS_URL}/{mine['id']}/approve", headers=pilot_headers, json={}).status_code == 200


def test_plan_edit_and_cancel_follow_level(client, admin_headers, pilot_headers, supervisor_headers, linked_pilot):
    own = client.post(PLANS_URL, headers=pilot_headers, json=_plan_body(linked_pilot.id)).json()
    other = client.post(PLANS_URL, headers=supervisor_headers, json=_plan_body(linked_pilot.id)).json()
    assert client.patch(f"{PLANS_URL}/{own['id']}", headers=pilot_headers, json={"title": "X"}).status_code == 200
    assert client.patch(f"{PLANS_URL}/{other['id']}", headers=pilot_headers, json={"title": "X"}).status_code == 403
    assert client.post(f"{PLANS_URL}/{other['id']}/cancel", headers=pilot_headers).status_code == 403
    assert client.post(f"{PLANS_URL}/{own['id']}/cancel", headers=pilot_headers).status_code == 200
    _grid(client, admin_headers, ("pilot", "flight_plans.edit", "none"))
    assert client.patch(f"{PLANS_URL}/{other['id']}", headers=pilot_headers, json={"title": "Y"}).status_code == 403
    assert client.patch(f"{PLANS_URL}/{other['id']}", headers=supervisor_headers, json={"title": "Y"}).status_code == 200


@pytest.mark.parametrize("field,value", [
    ("status", RESOLVED),
    ("resolution", "Fixed"),
    ("resolution_date", "2026-03-05"),
    ("corrective_actions", "Retrain"),
])
def test_incident_reporter_cannot_set_resolve_fields(client, pilot_headers, field, value):
    created = client.post(INCIDENTS_URL, headers=pilot_headers, json=_incident_body()).json()
    resp = client.patch(f"{INCIDENTS_URL}/{created['id']}", headers=pilot_headers, json={field: value})
    assert resp.status_code == 403


def test_incident_reporter_can_edit_other_fields(client, db, pilot_headers, supervisor_headers):
    created = client.post(INCIDENTS_URL, headers=pilot_headers, json=_incident_body()).json()
    url = f"{INCIDENTS_URL}/{created['id']}"
    body = {"description": "More detail", "status": created["status"]}
    assert client.patch(url, headers=pilot_headers, json=body).status_code == 200
    theirs = client.post(INCIDENTS_URL, headers=supervisor_headers, json=_incident_body()).json()
    assert client.patch(f"{INCIDENTS_URL}/{theirs['id']}", headers=pilot_headers, json={"description": "X"}).status_code == 403


def test_incident_resolve_granted_to_pilot_works(client, admin_headers, pilot_headers):
    _grid(client, admin_headers, ("pilot", "incidents.resolve", "yes"))
    created = client.post(INCIDENTS_URL, headers=pilot_headers, json=_incident_body()).json()
    resp = client.patch(f"{INCIDENTS_URL}/{created['id']}", headers=pilot_headers,
                        json={"status": RESOLVED, "resolution": "Fixed"})
    assert resp.status_code == 200
    assert resp.json()["status"] == RESOLVED


def test_incident_delete_needs_permission(client, db, pilot_headers, supervisor_headers):
    created = client.post(INCIDENTS_URL, headers=pilot_headers, json=_incident_body()).json()
    url = f"{INCIDENTS_URL}/{created['id']}"
    assert client.delete(url, headers=pilot_headers).status_code == 403
    assert client.delete(url, headers=supervisor_headers).status_code == 200


@pytest.mark.parametrize("url", [MISSIONS_URL, TRAININGS_URL])
def test_log_edit_own_via_creator_and_via_roster(client, db, pilot_headers, supervisor_headers, linked_pilot, url):
    made = client.post(url, headers=pilot_headers, json=_log_body()).json()
    assert client.patch(f"{url}/{made['id']}", headers=pilot_headers, json={"title": "Mine"}).status_code == 200
    rostered = client.post(url, headers=supervisor_headers, json={
        **_log_body(), "pilots": [{"pilot_id": linked_pilot.id}]}).json()
    assert client.patch(f"{url}/{rostered['id']}", headers=pilot_headers, json={"title": "Roster"}).status_code == 200
    assert client.delete(f"{url}/{rostered['id']}", headers=pilot_headers).status_code == 200


@pytest.mark.parametrize("url", [MISSIONS_URL, TRAININGS_URL])
def test_log_edit_refused_for_others(client, db, pilot_headers, supervisor_headers, linked_pilot, url):
    other = _other_pilot(db)
    theirs = client.post(url, headers=supervisor_headers, json={
        **_log_body(), "pilots": [{"pilot_id": other.id}]}).json()
    log_url = f"{url}/{theirs['id']}"
    assert client.patch(log_url, headers=pilot_headers, json={"title": "X"}).status_code == 403
    assert client.delete(log_url, headers=pilot_headers).status_code == 403
    assert client.post(f"{log_url}/pilots", headers=pilot_headers, json={"pilot_id": linked_pilot.id}).status_code == 403
    assert client.delete(f"{log_url}/pilots/{other.id}", headers=pilot_headers).status_code == 403
    assert client.delete(f"{log_url}/pilots/{other.id}", headers=supervisor_headers).status_code == 200


def test_unlinked_pilot_matches_no_roster(client, db, pilot_user, pilot_headers, supervisor_headers):
    assert pilot_user.pilot_id is None
    other = _other_pilot(db)
    theirs = client.post(MISSIONS_URL, headers=supervisor_headers, json={
        **_log_body(), "pilots": [{"pilot_id": other.id}]}).json()
    assert client.patch(f"{MISSIONS_URL}/{theirs['id']}", headers=pilot_headers, json={"title": "X"}).status_code == 403


def test_maintenance_create_sets_created_by(client, db, pilot_user, pilot_headers, supervisor_headers):
    body = {"entity_type": "other", "description": "Fix"}
    created = client.post(MAINTENANCE_URL, headers=pilot_headers, json=body).json()
    record = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == created["id"]).one()
    assert record.created_by_id == pilot_user.id
    assert client.patch(f"{MAINTENANCE_URL}/{created['id']}", headers=pilot_headers, json={"notes": "n"}).status_code == 200
    theirs = client.post(MAINTENANCE_URL, headers=supervisor_headers, json=body).json()
    assert client.patch(f"{MAINTENANCE_URL}/{theirs['id']}", headers=pilot_headers, json={"notes": "n"}).status_code == 403
    assert client.delete(f"{MAINTENANCE_URL}/{theirs['id']}", headers=pilot_headers).status_code == 403


def test_maintenance_without_creator_needs_all(client, db, pilot_headers, supervisor_headers):
    record = MaintenanceRecord(entity_type="other", entity_id=0, maintenance_type="scheduled", description="Old")
    db.add(record)
    db.commit()
    url = f"{MAINTENANCE_URL}/{record.id}"
    assert client.patch(url, headers=pilot_headers, json={"notes": "n"}).status_code == 403
    assert client.patch(url, headers=supervisor_headers, json={"notes": "n"}).status_code == 200


def test_pilot_completes_schedule_by_default(client, db, pilot_headers):
    schedule = _schedule(db)
    assert client.post(f"{SCHEDULES_URL}/{schedule.id}/complete", headers=pilot_headers).status_code == 200


def test_complete_refused_when_toggled_off(client, db, admin_headers, pilot_headers):
    _grid(client, admin_headers, ("pilot", "schedules.complete", "no"))
    schedule = _schedule(db)
    assert client.post(f"{SCHEDULES_URL}/{schedule.id}/complete", headers=pilot_headers).status_code == 403


def test_pilot_cannot_manage_schedule(client, db, pilot_headers, supervisor_headers):
    schedule = _schedule(db)
    url = f"{SCHEDULES_URL}/{schedule.id}"
    body = {"name": "N", "entity_type": "other", "frequency": "monthly"}
    assert client.post(SCHEDULES_URL, headers=pilot_headers, json=body).status_code == 403
    assert client.patch(url, headers=pilot_headers, json={"name": "X"}).status_code == 403
    assert client.delete(url, headers=pilot_headers).status_code == 403
    assert client.post(SCHEDULES_URL, headers=supervisor_headers, json=body).status_code == 200


def test_calendar_viewer_creator_cannot_edit(client, db, viewer_user, viewer_headers):
    event = CalendarEvent(title="Old", category="event", start_date=date(2026, 3, 1), created_by_id=viewer_user.id)
    db.add(event)
    db.commit()
    url = f"{EVENTS_URL}/{event.id}"
    assert client.patch(url, headers=viewer_headers, json={"title": "X"}).status_code == 403
    assert client.delete(url, headers=viewer_headers).status_code == 403


def test_calendar_edit_levels_and_editable_flag(client, db, pilot_user, pilot_headers, supervisor_headers):
    body = {"title": "Mine", "start_date": "2026-03-01"}
    mine = client.post(EVENTS_URL, headers=pilot_headers, json=body).json()
    theirs = client.post(EVENTS_URL, headers=supervisor_headers, json=body).json()
    assert client.patch(f"{EVENTS_URL}/{mine['id']}", headers=pilot_headers, json={"title": "X"}).status_code == 200
    assert client.patch(f"{EVENTS_URL}/{theirs['id']}", headers=pilot_headers, json={"title": "X"}).status_code == 403
    params = {"start": "2026-03-01", "end": "2026-03-31"}
    events = client.get(CALENDAR_URL, headers=pilot_headers, params=params).json()["events"]
    flags = {e["event_id"]: e["editable"] for e in events}
    assert flags == {mine["id"]: True, theirs["id"]: False}
    events = client.get(CALENDAR_URL, headers=supervisor_headers, params=params).json()["events"]
    assert all(e["editable"] for e in events)


def test_calendar_flight_counts_need_flights_view(client, admin_headers, pilot_headers):
    params = {"start": "2026-03-01", "end": "2026-03-31"}
    assert "flight_counts" in client.get(CALENDAR_URL, headers=pilot_headers, params=params).json()
    _grid(client, admin_headers, ("pilot", "flights.create", "no"), ("pilot", "flights.edit", "none"),
          ("pilot", "flights.view", "no"))
    resp = client.get(CALENDAR_URL, headers=pilot_headers, params=params)
    assert resp.status_code == 200
    assert resp.json()["flight_counts"] == {}


def _alert(db):
    alert = Alert(type="x", severity="info", title="T", message="M")
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def test_alert_pilot_cannot_mark_read_or_dismiss_by_default(client, db, pilot_headers):
    alert = _alert(db)
    assert client.patch(f"{ALERTS_URL}/{alert.id}/read", headers=pilot_headers).status_code == 403
    assert client.patch(f"{ALERTS_URL}/{alert.id}/dismiss", headers=pilot_headers).status_code == 403
    assert client.post(f"{ALERTS_URL}/dismiss-all", headers=pilot_headers).status_code == 403
    assert client.get(ALERTS_URL, headers=pilot_headers).status_code == 200


def test_alert_granted_works(client, db, admin_headers, pilot_headers):
    _grid(client, admin_headers, ("pilot", "alerts.dismiss", "yes"))
    alert = _alert(db)
    assert client.patch(f"{ALERTS_URL}/{alert.id}/read", headers=pilot_headers).status_code == 200
    assert client.patch(f"{ALERTS_URL}/{alert.id}/dismiss", headers=pilot_headers).status_code == 200
    assert client.post(f"{ALERTS_URL}/dismiss-all", headers=pilot_headers).status_code == 200


def test_checklist_and_checkout_actions_follow_keys(client, admin_headers, pilot_headers, supervisor_headers):
    assert client.post(CHECKLISTS_URL, headers=pilot_headers, json={"name": "T", "items": []}).status_code == 403
    assert client.delete(f"{CHECKOUTS_URL}/1", headers=pilot_headers).status_code == 403
    assert client.delete(f"{CHECKOUTS_URL}/1", headers=supervisor_headers).status_code == 404
    _grid(client, admin_headers, ("pilot", "checkouts.use", "no"))
    body = {"entity_type": "vehicle", "entity_id": 1, "checked_out_by_id": 1}
    assert client.post(CHECKOUTS_URL, headers=pilot_headers, json=body).status_code == 403
    assert client.post(f"{CHECKOUTS_URL}/1/checkin", headers=pilot_headers, json={"checked_in_by_id": 1}).status_code == 403


@pytest.mark.parametrize("view_key,change_keys,url", [
    ("flight_plans.view", ["flight_plans.create", "flight_plans.edit"], PLANS_URL),
    ("incidents.view", ["incidents.create", "incidents.edit"], INCIDENTS_URL),
    ("logs.view", ["logs.create", "logs.edit"], MISSIONS_URL),
    ("logs.view", ["logs.create", "logs.edit"], TRAININGS_URL),
    ("maintenance.view", ["maintenance.create", "maintenance.edit", "schedules.complete"], MAINTENANCE_URL),
    ("maintenance.view", ["maintenance.create", "maintenance.edit", "schedules.complete"], SCHEDULES_URL),
    ("calendar.view", ["calendar.create", "calendar.edit"], CALENDAR_URL + "?start=2026-03-01&end=2026-03-31"),
    ("checklists.view", ["checklists.complete"], CHECKLISTS_URL),
    ("fleet.view", ["fleet.location", "checkouts.use"], CHECKOUTS_URL),
    ("alerts.view", [], ALERTS_URL),
])
def test_view_off_hides_each_feature(client, admin_headers, pilot_headers, view_key, change_keys, url):
    changes = []
    for key in change_keys:
        changes.append(("pilot", key, "none" if key.endswith(".edit") else "no"))
    changes.append(("pilot", view_key, "no"))
    _grid(client, admin_headers, *changes)
    assert client.get(url, headers=pilot_headers).status_code == 403
