"""Calendar event endpoint tests: authz on create.

``app.routers.calendar`` exposes a manual-event write endpoint,
``POST /api/calendar/events``. ``viewer`` is the system's read-only role (and
the default role for new users), so it must NOT be able to create events; every
other write endpoint is gated by ``require_pilot`` (admin/supervisor/pilot).

* A viewer posting to ``/api/calendar/events`` gets 403 and no row is written.
* A pilot CAN create an event (200) and it persists.

Read endpoints (GET ``/api/calendar``) stay open to any authenticated user,
including viewers, and are not exercised here.
"""

from app.models.calendar_event import CalendarEvent
from app.routers.auth import create_token
from tests.conftest import _seed_user

EVENTS_URL = "/api/calendar/events"


def _event_payload(**overrides):
    payload = {
        "title": "Range day",
        "category": "event",
        "start_date": "2025-06-01",
    }
    payload.update(overrides)
    return payload


def test_create_event_requires_pilot_viewer_403(client, db):
    viewer = _seed_user(db, username="viewer", role="viewer", password="ViewerPassw0rd!")
    headers = {"Authorization": f"Bearer {create_token(viewer.id)}"}

    resp = client.post(EVENTS_URL, headers=headers, json=_event_payload())
    assert resp.status_code == 403, resp.text

    db.expire_all()
    assert db.query(CalendarEvent).count() == 0


def test_create_event_allowed_for_pilot(client, db, pilot_headers):
    resp = client.post(EVENTS_URL, headers=pilot_headers, json=_event_payload())
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["title"] == "Range day"

    db.expire_all()
    row = db.query(CalendarEvent).filter(CalendarEvent.id == body["id"]).one()
    assert row.title == "Range day"
