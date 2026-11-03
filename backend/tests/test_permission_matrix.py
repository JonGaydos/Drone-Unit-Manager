"""Every permission key against every role, at its default and when flipped.

Each case is one real route with a real record behind it, so a 200 or 201 shows
the request got through and a 403 shows the gate refused it. A 404 or 422 fails
the test rather than passing as "not refused". Expected defaults come from the
registry, which test_permissions.test_registry_defaults_match_spec pins to the
design.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models.alert import Alert
from app.models.calendar_event import CalendarEvent
from app.models.checklist import ChecklistTemplate
from app.models.document import Document
from app.models.equipment_checkout import EquipmentCheckout
from app.models.flight import Flight
from app.models.flight_approval import FlightPlan
from app.models.incident import Incident
from app.models.maintenance import MaintenanceRecord
from app.models.maintenance_schedule import MaintenanceSchedule
from app.models.mission_log import MissionLog
from app.models.operating_authority import OperatingAuthority
from app.models.photo import Photo
from app.models.pilot import Pilot
from app.models.role_permission import RolePermission
from app.models.training_log import TrainingLog
from app.models.user import User
from app.models.vehicle import Vehicle
from app.routers.auth import create_token
from app.services.permissions import (
    ADMIN,
    ALL,
    EDITABLE_ROLES,
    LEVEL,
    NO,
    NONE,
    OPTIONS,
    OWN,
    PILOT,
    REGISTRY,
    SUPERVISOR,
    VIEWER,
    YES,
)

ROLES = (ADMIN, *EDITABLE_ROLES)
FORBIDDEN = 403
CREATED = 201

PERMISSIONS_URL = "/api/permissions"
FLIGHTS_URL = "/api/flights"
PLANS_URL = "/api/flight-plans"
INCIDENTS_URL = "/api/incidents"
MISSIONS_URL = "/api/mission-logs"
TRAININGS_URL = "/api/training-logs"
MAINTENANCE_URL = "/api/maintenance"
SCHEDULES_URL = "/api/maintenance/schedules"
VEHICLES_URL = "/api/vehicles"
CHECKOUTS_URL = "/api/equipment-checkouts"
PILOTS_URL = "/api/pilots"
CHECKLISTS_URL = "/api/checklists"
CALENDAR_URL = "/api/calendar"
DOCUMENTS_URL = "/api/documents"
PHOTOS_URL = "/api/photos"
ALERTS_URL = "/api/alerts"
AUTHORITIES_URL = "/api/operating-authorities"

DAY = "2026-03-01"
TITLE = "Changed"
CONTACT_EMAIL = "pilot@example.test"
CONTACTS_KEY = "pilots.contacts"


@dataclass(frozen=True)
class Req:
    method: str
    url: str
    json: dict | None = None
    ok: int = 200
    data: dict | None = None
    files: dict | None = None


def _get(url):
    return Req("GET", url)


def _post(url, json=None, ok=200):
    return Req("POST", url, json=json, ok=ok)


def _patch(url, json):
    return Req("PATCH", url, json=json)


def _put(url, json):
    return Req("PUT", url, json=json)


def _delete(url):
    return Req("DELETE", url)


@dataclass
class Env:
    client: TestClient
    db: Session
    user_ids: dict[str, int]
    headers: dict[str, dict]
    other_user_id: int
    counter: int = 0

    def unique(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}-{self.counter}"

    def add(self, record):
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def send(self, role: str, req: Req) -> int:
        response = self.client.request(req.method, req.url, headers=self.headers[role], json=req.json,
                                       data=req.data, files=req.files)
        return response.status_code

    def set_grid(self, role: str, changes: dict[str, str]) -> None:
        body = {"changes": [{"role": role, "key": key, "value": value} for key, value in changes.items()]}
        response = self.client.put(PERMISSIONS_URL, headers=self.headers[ADMIN], json=body)
        assert response.status_code == 200, response.text


def _seed_user(db, role, username):
    user = User(username=username, password_hash="", display_name=username.title(), role=role, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def env(client, db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    users = {role: _seed_user(db, role, role) for role in ROLES}
    other = _seed_user(db, PILOT, "other")
    return Env(
        client=client,
        db=db,
        user_ids={role: user.id for role, user in users.items()},
        headers={role: {"Authorization": f"Bearer {create_token(user.id)}"} for role, user in users.items()},
        other_user_id=other.id,
    )


# Record seeds ----------------------------------------------------------------

def _pilot(env, **fields):
    return env.add(Pilot(first_name="Some", last_name=env.unique("Pilot"), **fields))


def _vehicle(env):
    return env.add(Vehicle(serial_number=env.unique("V"), manufacturer="Skydio", model="X10"))


def _flight(env, **fields):
    return env.add(Flight(date=date(2026, 3, 1), review_status="needs_review", **fields))


def _plan(env, submitted_by):
    return env.add(FlightPlan(title="Plan", date_planned=datetime(2026, 3, 1, 10), pilot_id=_pilot(env).id,
                              submitted_by_id=submitted_by))


def _incident(env, reported_by):
    return env.add(Incident(date=date(2026, 3, 1), title="Hard landing", severity="minor", category="other",
                            description="Bumped", reported_by_id=reported_by))


def _mission(env, created_by=None):
    return env.add(MissionLog(date=date(2026, 3, 1), title="Mission", created_by_id=created_by))


def _training(env, created_by):
    return env.add(TrainingLog(date=date(2026, 3, 1), title="Training", training_type="drill",
                               created_by_id=created_by))


def _maintenance(env, created_by=None):
    return env.add(MaintenanceRecord(entity_type="vehicle", entity_id=_vehicle(env).id, description="Oil",
                                     maintenance_type="scheduled", created_by_id=created_by))


def _schedule(env):
    return env.add(MaintenanceSchedule(name="Check", entity_type="vehicle", entity_id=_vehicle(env).id,
                                       frequency="monthly", is_active=True))


def _checkout(env):
    return env.add(EquipmentCheckout(entity_type="vehicle", entity_id=_vehicle(env).id,
                                     checked_out_by_id=_pilot(env).id))


def _template(env):
    return env.add(ChecklistTemplate(name="Preflight", items=[]))


def _event(env, created_by):
    return env.add(CalendarEvent(title="Event", category="event", start_date=date(2026, 3, 1),
                                 created_by_id=created_by))


def _document(env, uploaded_by=None, **fields):
    return env.add(Document(entity_type="general", document_type="other", title="Doc", filename="d.pdf",
                            file_path="/nonexistent/d.pdf", mime_type="application/pdf", file_size_bytes=1,
                            uploaded_by_id=uploaded_by, **fields))


def _photo(env, uploaded_by):
    return env.add(Photo(filename="p.png", original_filename="p.png", mime_type="image/png",
                         uploaded_by_id=uploaded_by))


def _alert(env):
    return env.add(Alert(type="x", severity="info", title="T", message="M"))


def _authority(env):
    return env.add(OperatingAuthority(authority_type="coa", title="County COA", record_status="active",
                                      grounds_unit=False))


# Yes / No keys ---------------------------------------------------------------
# Each entry builds the request for a role, seeding what the route needs. Records
# a role must own to get past another check are seeded as that role's.

Builder = Callable[[Env, str], Req]

BOOL_CASES: dict[str, Builder] = {
    "flights.view": lambda env, role: _get(f"{FLIGHTS_URL}/{_flight(env).id}"),
    "flights.create": lambda env, role: _post(FLIGHTS_URL, {"date": DAY}),
    "flights.review": lambda env, role: _patch(f"{FLIGHTS_URL}/{_flight(env).id}/review-status",
                                               {"review_status": "reviewed"}),
    "flight_plans.view": lambda env, role: _get(f"{PLANS_URL}/{_plan(env, env.other_user_id).id}"),
    "flight_plans.create": lambda env, role: _post(PLANS_URL, {"title": "Plan", "date_planned": f"{DAY}T10:00:00",
                                                               "pilot_id": _pilot(env).id}),
    "flight_plans.approve": lambda env, role: _post(f"{PLANS_URL}/{_plan(env, env.other_user_id).id}/approve", {}),
    "incidents.view": lambda env, role: _get(f"{INCIDENTS_URL}/{_incident(env, None).id}"),
    "incidents.create": lambda env, role: _post(INCIDENTS_URL, {"date": DAY, "title": "Hard landing",
                                                                "severity": "minor", "category": "other",
                                                                "description": "Bumped"}),
    "incidents.resolve": lambda env, role: _patch(f"{INCIDENTS_URL}/{_incident(env, env.user_ids[role]).id}",
                                                  {"status": "resolved"}),
    "incidents.delete": lambda env, role: _delete(f"{INCIDENTS_URL}/{_incident(env, None).id}"),
    "logs.view": lambda env, role: _get(f"{MISSIONS_URL}/{_mission(env).id}"),
    "logs.create": lambda env, role: _post(MISSIONS_URL, {"date": DAY, "title": "Mission"}),
    "maintenance.view": lambda env, role: _get(f"{MAINTENANCE_URL}/{_maintenance(env).id}"),
    "maintenance.create": lambda env, role: _post(MAINTENANCE_URL, {"entity_type": "vehicle",
                                                                    "entity_id": _vehicle(env).id,
                                                                    "description": "Oil"}),
    "schedules.complete": lambda env, role: _post(f"{SCHEDULES_URL}/{_schedule(env).id}/complete"),
    "schedules.manage": lambda env, role: _post(SCHEDULES_URL, {"name": "Check", "entity_type": "vehicle",
                                                                "entity_id": _vehicle(env).id,
                                                                "frequency": "monthly"}),
    "fleet.view": lambda env, role: _get(f"{VEHICLES_URL}/{_vehicle(env).id}"),
    "fleet.manage": lambda env, role: _post(VEHICLES_URL, {"serial_number": env.unique("NEW"),
                                                           "manufacturer": "Skydio", "model": "X10"}),
    "fleet.location": lambda env, role: _patch(f"{VEHICLES_URL}/{_vehicle(env).id}/location", {"place": "Hangar"}),
    "checkouts.use": lambda env, role: _post(CHECKOUTS_URL, {"entity_type": "vehicle",
                                                             "entity_id": _vehicle(env).id,
                                                             "checked_out_by_id": _pilot(env).id}),
    "checkouts.delete": lambda env, role: _delete(f"{CHECKOUTS_URL}/{_checkout(env).id}"),
    "pilots.view": lambda env, role: _get(f"{PILOTS_URL}/{_pilot(env).id}"),
    "pilots.manage": lambda env, role: _post(PILOTS_URL, {"first_name": "New", "last_name": "Pilot"}),
    "certifications.view": lambda env, role: _get("/api/certification-types"),
    "certifications.manage": lambda env, role: _post("/api/certification-types", {"name": "Part 107"}),
    "checklists.view": lambda env, role: _get(f"{CHECKLISTS_URL}/templates/{_template(env).id}"),
    "checklists.complete": lambda env, role: _post(f"{CHECKLISTS_URL}/complete", {"template_id": _template(env).id,
                                                                                  "pilot_id": _pilot(env).id,
                                                                                  "responses": []}),
    "checklists.manage": lambda env, role: _post(f"{CHECKLISTS_URL}/templates",
                                                     {"name": "T", "items": [{"label": "Props"}]}),
    "calendar.view": lambda env, role: _get(f"{CALENDAR_URL}?start=2026-03-01&end=2026-03-31"),
    "calendar.create": lambda env, role: _post(f"{CALENDAR_URL}/events", {"title": "Event", "start_date": DAY}),
    "files.view": lambda env, role: _get(f"{PHOTOS_URL}/{_photo(env, None).id}/signed-urls"),
    "files.custody": lambda env, role: _post(f"{DOCUMENTS_URL}/{_document(env, deleted_at=datetime(2026, 3, 2)).id}"
                                             "/restore"),
    "folders.manage": lambda env, role: _post("/api/folders", {"name": env.unique("Folder")}),
    "alerts.view": lambda env, role: _get(ALERTS_URL),
    "alerts.dismiss": lambda env, role: _patch(f"{ALERTS_URL}/{_alert(env).id}/read", {}),
    "reports.generate": lambda env, role: _post("/api/reports/generate", {"report_type": "flight_summary"}),
    "reports.export": lambda env, role: _get("/api/export/flights/csv"),
    "authority.view": lambda env, role: _get(f"{AUTHORITIES_URL}/{_authority(env).id}"),
    "authority.manage": lambda env, role: _post(AUTHORITIES_URL, {"authority_type": "coa", "title": "County COA"},
                                                    ok=CREATED),
    "registrations.view": lambda env, role: _get(f"{VEHICLES_URL}/{_vehicle(env).id}/registrations"),
    "registrations.manage": lambda env, role: _post(f"{VEHICLES_URL}/{_vehicle(env).id}/registrations",
                                                    {"registration_number": "R-1"}),
    "audit.view": lambda env, role: _get("/api/audit"),
    "digest.redirect": lambda env, role: _put("/api/notifications/preferences",
                                              {"email_override": "other@example.test"}),
}


def _holds_by_default(key: str, role: str) -> bool:
    definition = REGISTRY[key]
    return role == ADMIN or definition.defaults[role] != OPTIONS[definition.kind][0]


def _dependents(key: str) -> list[str]:
    return [other for other, definition in REGISTRY.items() if definition.requires == key]


def _off_changes(key: str, role: str) -> dict[str, str]:
    """Turn a key off for a role, with whatever depends on it, as the grid requires."""
    held = [dependent for dependent in _dependents(key) if _holds_by_default(dependent, role)]
    return {other: OPTIONS[REGISTRY[other].kind][0] for other in [key, *held]}


def _assert_gate(env, role, build, allowed, stage):
    req = build(env, role)
    actual = env.send(role, req)
    expected = req.ok if allowed else FORBIDDEN
    assert actual == expected, f"{stage}: {req.method} {req.url} as {role} returned {actual}, expected {expected}"


def _bool_cells():
    return [(key, role) for key in BOOL_CASES for role in ROLES]


def _locked_keys():
    return [key for key, definition in REGISTRY.items() if definition.viewer_locked]


@pytest.mark.parametrize("key,role", _bool_cells())
def test_yes_no_key_at_default_and_flipped(env, key, role):
    build = BOOL_CASES[key]
    held = _holds_by_default(key, role)
    _assert_gate(env, role, build, held, "default")
    if role == ADMIN or (role == VIEWER and REGISTRY[key].viewer_locked):
        return
    env.set_grid(role, _off_changes(key, role) if held else {key: YES})
    _assert_gate(env, role, build, not held, "flipped")


# Contact details are masked rather than refused ------------------------------

def _seen_email(env, role, pilot_id):
    response = env.client.get(f"{PILOTS_URL}/{pilot_id}", headers=env.headers[role])
    assert response.status_code == 200, response.text
    return response.json()["email"]


@pytest.mark.parametrize("role", ROLES)
def test_contacts_key_at_default_and_flipped(env, role):
    pilot_id = _pilot(env, email=CONTACT_EMAIL).id
    held = _holds_by_default(CONTACTS_KEY, role)
    assert _seen_email(env, role, pilot_id) == (CONTACT_EMAIL if held else None)
    if role != ADMIN:
        env.set_grid(role, {CONTACTS_KEY: NO if held else YES})
        assert _seen_email(env, role, pilot_id) == (None if held else CONTACT_EMAIL)


# None / Own / All keys -------------------------------------------------------

def _upload(**form):
    return Req("POST", f"{DOCUMENTS_URL}/upload", data={"document_type": "other", "title": "Doc", **form},
               files={"file": ("doc.pdf", b"%PDF-1.4 test", "application/pdf")})


@dataclass(frozen=True)
class LevelCase:
    """One record type under a level key. Builders take the record owner's user id."""
    key: str
    record: str
    own: Callable[[Env, int], Req]
    other: Callable[[Env, int], Req]

    def __str__(self) -> str:
        return f"{self.key}:{self.record}"


def _level_case(key, record, build):
    """A case whose own and other requests differ only in who owns the record."""
    return LevelCase(key, record, build, lambda env, _user_id: build(env, env.other_user_id))


def _own_profile(env, user_id):
    pilot = _pilot(env)
    env.db.get(User, user_id).pilot_id = pilot.id
    env.db.commit()
    return _patch(f"{PILOTS_URL}/{pilot.id}", {"notes": TITLE})


LEVEL_CASES = [
    _level_case("flights.edit", "flight",
                lambda env, owner: _patch(f"{FLIGHTS_URL}/{_flight(env, created_by_id=owner).id}", {"notes": TITLE})),
    _level_case("flights.delete", "flight",
                lambda env, owner: _delete(f"{FLIGHTS_URL}/{_flight(env, created_by_id=owner).id}")),
    _level_case("flight_plans.edit", "plan",
                lambda env, owner: _patch(f"{PLANS_URL}/{_plan(env, owner).id}", {"title": TITLE})),
    _level_case("incidents.edit", "incident",
                lambda env, owner: _patch(f"{INCIDENTS_URL}/{_incident(env, owner).id}", {"title": TITLE})),
    _level_case("logs.edit", "mission",
                lambda env, owner: _patch(f"{MISSIONS_URL}/{_mission(env, owner).id}", {"title": TITLE})),
    _level_case("logs.edit", "training",
                lambda env, owner: _patch(f"{TRAININGS_URL}/{_training(env, owner).id}", {"title": TITLE})),
    _level_case("maintenance.edit", "record",
                lambda env, owner: _patch(f"{MAINTENANCE_URL}/{_maintenance(env, owner).id}", {"notes": TITLE})),
    _level_case("calendar.edit", "event",
                lambda env, owner: _patch(f"{CALENDAR_URL}/events/{_event(env, owner).id}", {"title": TITLE})),
    _level_case("files.edit", "document",
                lambda env, owner: _patch(f"{DOCUMENTS_URL}/{_document(env, owner).id}", {"title": TITLE})),
    _level_case("files.edit", "photo",
                lambda env, owner: Req("PATCH", f"{PHOTOS_URL}/{_photo(env, owner).id}", data={"title": TITLE})),
    LevelCase("pilots.edit", "profile", _own_profile,
              lambda env, _user_id: _patch(f"{PILOTS_URL}/{_pilot(env).id}", {"notes": TITLE})),
    LevelCase("files.upload", "attachment",
              lambda env, _user_id: _upload(entity_type="general"),
              lambda env, _user_id: _upload(entity_type="pilot", entity_id=str(_pilot(env).id))),
]


def _assert_level(env, case, role, value):
    """Own covers the role's own record, All covers another's too, None neither."""
    user_id = env.user_ids[role]
    _assert_gate(env, role, lambda e, _r: case.own(e, user_id), value in (OWN, ALL), f"{value}, own record")
    _assert_gate(env, role, lambda e, _r: case.other(e, user_id), value == ALL, f"{value}, other record")


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("case", LEVEL_CASES, ids=str)
def test_level_key_at_default(env, case, role):
    value = ALL if role == ADMIN else REGISTRY[case.key].defaults[role]
    _assert_level(env, case, role, value)


@pytest.mark.parametrize("role", [SUPERVISOR, PILOT])
@pytest.mark.parametrize("value", [NONE, OWN, ALL])
@pytest.mark.parametrize("case", LEVEL_CASES, ids=str)
def test_level_key_at_each_value(env, case, value, role):
    env.set_grid(role, {case.key: value})
    _assert_level(env, case, role, value)


# Locked viewer cells ---------------------------------------------------------

def _viewer_request(env, key):
    if key in BOOL_CASES:
        return BOOL_CASES[key](env, VIEWER)
    case = next(case for case in LEVEL_CASES if case.key == key)
    return case.own(env, env.user_ids[VIEWER])


@pytest.mark.parametrize("key", _locked_keys())
def test_locked_viewer_cell_ignores_a_stored_row(env, key):
    highest = OPTIONS[REGISTRY[key].kind][-1]
    env.add(RolePermission(role=VIEWER, permission_key=key, value=highest))
    _assert_gate(env, VIEWER, lambda e, _role: _viewer_request(e, key), False, "stored row")


# The matrix itself -----------------------------------------------------------

def test_every_key_has_a_matrix_case():
    covered = {*BOOL_CASES, CONTACTS_KEY, *(case.key for case in LEVEL_CASES)}
    assert covered == set(REGISTRY), f"Keys and cases differ: {sorted(covered ^ set(REGISTRY))}"


def test_key_kinds_match_their_case_type():
    assert {case.key for case in LEVEL_CASES} == {k for k, d in REGISTRY.items() if d.kind == LEVEL}
