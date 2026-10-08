"""3.2.2: server-stamped times carry their zone, the Flights list searches and
sorts every flight rather than one page, and a submitted checklist can be
removed by a supervisor."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.audit_log import AuditLog
from app.models.checklist import ChecklistCompletion, ChecklistTemplate
from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.routers.auth import create_token
from tests.conftest import _seed_user


@pytest.fixture
def supervisor_headers(db):
    user = _seed_user(db, username="sup", role="supervisor", password="SuperPassw0rd!!")
    return {"Authorization": f"Bearer {create_token(user.id)}"}


def _parse(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


# ── Server timestamps ────────────────────────────────────────────────────────

def test_a_stamped_time_reads_back_as_utc(db):
    """Stored naive as before; read back aware, so a browser converts it."""
    entry = AuditLog(user_id=None, user_name="x", action="create", entity_type="t",
                     created_at=datetime(2026, 10, 8, 1, 27, 43))
    db.add(entry)
    db.commit()
    db.expire_all()
    stamp = db.get(AuditLog, entry.id).created_at
    assert stamp.tzinfo is not None
    assert stamp == datetime(2026, 10, 8, 1, 27, 43, tzinfo=timezone.utc)


def test_an_aware_time_is_stored_as_utc(db):
    """An 8:27 PM Central stamp is kept as 01:27 UTC, not as 20:27."""
    central = timezone(timedelta(hours=-5))
    entry = AuditLog(user_id=None, user_name="x", action="create", entity_type="t",
                     created_at=datetime(2026, 10, 7, 20, 27, 43, tzinfo=central))
    db.add(entry)
    db.commit()
    db.expire_all()
    assert db.get(AuditLog, entry.id).created_at == datetime(2026, 10, 8, 1, 27, 43, tzinfo=timezone.utc)


def test_the_audit_log_sends_its_zone(client, db, admin_headers):
    db.add(AuditLog(user_id=None, user_name="x", action="create", entity_type="t",
                    created_at=datetime(2026, 10, 8, 1, 27, 43)))
    db.commit()
    resp = client.get("/api/audit", headers=admin_headers)
    assert resp.status_code == 200
    stamp = resp.json()["logs"][0]["created_at"]
    assert stamp.endswith(("Z", "+00:00"))
    assert _parse(stamp) == datetime(2026, 10, 8, 1, 27, 43, tzinfo=timezone.utc)


def test_an_entered_time_stays_wall_clock(db):
    """Times a person types in are local wall-clock times and get no zone."""
    flight = Flight(date=date(2026, 10, 7), takeoff_time=datetime(2026, 10, 7, 20, 0))
    db.add(flight)
    db.commit()
    db.expire_all()
    assert db.get(Flight, flight.id).takeoff_time.tzinfo is None


def test_api_token_expiry_still_works(client, db, admin_headers):
    """Expiry compares an aware "now" with the stored time; both must be UTC."""
    from app.models.api_token import ApiToken

    created = client.post("/api/api-tokens", json={"name": "t", "read_only": True, "expires_in_days": 1},
                          headers=admin_headers)
    assert created.status_code == 200, created.text
    assert _parse(created.json()["expires_at"]).tzinfo is not None
    bearer = {"Authorization": f"Bearer {created.json()['token']}"}
    assert client.get("/api/vehicles", headers=bearer).status_code == 200

    row = db.query(ApiToken).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert client.get("/api/vehicles", headers=bearer).status_code == 401


# ── Flights search and sort ──────────────────────────────────────────────────

@pytest.fixture
def flights(db):
    smith = Pilot(first_name="Ann", last_name="Smith", status="active")
    jones = Pilot(first_name="Bob", last_name="Jones", status="active")
    drone = Vehicle(serial_number="SN-1", manufacturer="Skydio", model="X10", nickname="Eagle")
    db.add_all([smith, jones, drone])
    db.flush()
    rows = [
        Flight(date=date(2026, 1, 1), pilot_id=smith.id, vehicle_id=drone.id, purpose="Training",
               duration_seconds=300, case_number="26-0001"),
        Flight(date=date(2026, 1, 2), pilot_id=jones.id, purpose="Search", duration_seconds=100),
        Flight(date=date(2026, 1, 3), pilot_id=jones.id, purpose="Patrol", duration_seconds=200),
    ]
    db.add_all(rows)
    db.commit()
    return rows


def _ids(resp):
    assert resp.status_code == 200, resp.text
    return [f["id"] for f in resp.json()["flights"]]


@pytest.mark.parametrize("text", ["smith", "ann smith", "eagle", "skydio x10", "SN-1", "26-0001", "train"])
def test_search_finds_a_flight_on_any_page(client, admin_headers, flights, text):
    resp = client.get("/api/flights", params={"search": text, "per_page": 1}, headers=admin_headers)
    assert _ids(resp) == [flights[0].id]
    assert resp.json()["total"] == 1


def test_search_treats_wildcards_as_text(client, admin_headers, flights):
    resp = client.get("/api/flights", params={"search": "%"}, headers=admin_headers)
    assert _ids(resp) == []


def test_sort_covers_every_flight_not_one_page(client, admin_headers, flights):
    resp = client.get("/api/flights", params={"sort": "duration_seconds", "order": "asc", "per_page": 1},
                      headers=admin_headers)
    assert _ids(resp) == [flights[1].id]
    resp = client.get("/api/flights", params={"sort": "duration_seconds", "order": "desc", "per_page": 1},
                      headers=admin_headers)
    assert _ids(resp) == [flights[0].id]


def test_sort_by_pilot_name(client, admin_headers, flights):
    resp = client.get("/api/flights", params={"sort": "pilot_name", "order": "asc"}, headers=admin_headers)
    assert _ids(resp)[0] == flights[0].id


def test_default_order_is_newest_first(client, admin_headers, flights):
    assert _ids(client.get("/api/flights", headers=admin_headers)) == [f.id for f in reversed(flights)]


def test_an_unknown_sort_falls_back_to_date(client, admin_headers, flights):
    resp = client.get("/api/flights", params={"sort": "nope"}, headers=admin_headers)
    assert _ids(resp) == [f.id for f in reversed(flights)]


# ── Checklists ───────────────────────────────────────────────────────────────

@pytest.fixture
def completion(db):
    pilot = Pilot(first_name="Ann", last_name="Smith", status="active")
    template = ChecklistTemplate(name="Preflight", items=[{"label": "Props", "required": True}])
    db.add_all([pilot, template])
    db.flush()
    done = ChecklistCompletion(template_id=template.id, pilot_id=pilot.id,
                               responses=[{"label": "Props", "checked": True}], all_passed=True)
    db.add(done)
    db.commit()
    return done


def test_a_supervisor_can_delete_a_submitted_checklist(client, db, supervisor_headers, completion):
    completion_id = completion.id
    resp = client.delete(f"/api/checklists/completions/{completion_id}", headers=supervisor_headers)
    assert resp.status_code == 200
    db.expire_all()
    assert db.get(ChecklistCompletion, completion_id) is None
    entry = db.query(AuditLog).filter(AuditLog.entity_type == "checklist_completion").one()
    assert entry.action == "delete"
    assert "Preflight" in entry.entity_name


def test_a_pilot_cannot_delete_a_submitted_checklist(client, db, pilot_headers, completion):
    resp = client.delete(f"/api/checklists/completions/{completion.id}", headers=pilot_headers)
    assert resp.status_code == 403
    db.expire_all()
    assert db.get(ChecklistCompletion, completion.id) is not None


def test_deleting_a_missing_checklist_is_404(client, supervisor_headers):
    assert client.delete("/api/checklists/completions/999", headers=supervisor_headers).status_code == 404


def test_a_template_in_use_says_why_it_cannot_be_deleted(client, supervisor_headers, completion):
    resp = client.delete(f"/api/checklists/templates/{completion.template_id}", headers=supervisor_headers)
    assert resp.status_code == 409
    assert "Used by 1 submitted checklist" in resp.json()["detail"]
    assert "Active" in resp.json()["detail"]


def test_a_template_is_deletable_once_its_submissions_are_gone(client, supervisor_headers, completion):
    template_id = completion.template_id
    client.delete(f"/api/checklists/completions/{completion.id}", headers=supervisor_headers)
    resp = client.delete(f"/api/checklists/templates/{template_id}", headers=supervisor_headers)
    assert resp.status_code == 200
