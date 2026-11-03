"""Role permission registry, storage, admin API and resolved values."""

from typing import Annotated

import app.config
import pytest
from alembic import command
from app.main import app as fastapi_app
from app.models.api_token import ApiToken
from app.models.audit_log import AuditLog
from app.models.role_permission import RolePermission
from app.models.user import User
from app.routers.auth import require_permission
from app.services import api_tokens as api_tokens_service
from app.services import permissions
from fastapi import Depends, HTTPException
from sqlalchemy import create_engine, inspect

from tests.conftest import PILOT_PASSWORD
from tests.test_schema import _alembic_config

PERMISSIONS_URL = "/api/permissions"
RESET_URL = "/api/permissions/reset"
ME_URL = "/api/auth/me"
LOGIN_URL = "/api/auth/login"
PROBE_URL = "/api/flights/permission-probe"
PREVIOUS_REVISION = "0010_local_dates_for_spreadsheet_imports"

ADMIN = "admin"
SUPERVISOR = "supervisor"
PILOT = "pilot"
VIEWER = "viewer"
YES = "yes"
NO = "no"
NONE = "none"
OWN = "own"
ALL = "all"

FLIGHTS_VIEW = "flights.view"
FLIGHTS_CREATE = "flights.create"
FLIGHTS_EDIT = "flights.edit"
FLIGHTS_DELETE = "flights.delete"

# The spec's default grid: key, supervisor, pilot, viewer. A locked cell is
# written locked-<value>.
DEFAULT_GRID = """
flights.view yes yes yes
flights.create yes yes locked-no
flights.edit all own locked-none
flights.delete all none locked-none
flights.review yes no locked-no
flight_plans.view yes yes yes
flight_plans.create yes yes locked-no
flight_plans.edit all own locked-none
flight_plans.approve yes no locked-no
incidents.view yes yes yes
incidents.create yes yes locked-no
incidents.edit all own locked-none
incidents.resolve yes no locked-no
incidents.delete yes no locked-no
logs.view yes yes yes
logs.create yes yes locked-no
logs.edit all own locked-none
maintenance.view yes yes yes
maintenance.create yes yes locked-no
maintenance.edit all own locked-none
schedules.complete yes yes locked-no
schedules.manage yes no locked-no
fleet.view yes yes yes
fleet.manage yes no locked-no
fleet.location yes yes locked-no
checkouts.use yes yes locked-no
checkouts.delete yes no locked-no
pilots.view yes yes yes
pilots.contacts yes yes no
pilots.edit all own locked-none
pilots.manage yes no locked-no
certifications.view yes yes yes
certifications.manage yes no locked-no
checklists.view yes yes yes
checklists.complete yes yes locked-no
checklists.manage yes no locked-no
calendar.view yes yes yes
calendar.create yes yes locked-no
calendar.edit all own locked-none
files.view yes yes yes
files.upload all own locked-none
files.edit all own locked-none
files.custody yes no locked-no
folders.manage yes no locked-no
alerts.view yes yes yes
alerts.dismiss yes no locked-no
reports.generate yes yes no
reports.export yes yes yes
authority.view yes yes yes
authority.manage yes no locked-no
registrations.view yes yes yes
registrations.manage no no locked-no
audit.view no no no
digest.redirect yes no locked-no
"""
GRID_ROWS = [line.split() for line in DEFAULT_GRID.strip().splitlines()]
KEY_COUNT = 54


def _change(role, key, value):
    return {"role": role, "key": key, "value": value}


def _put(client, headers, *changes):
    return client.put(PERMISSIONS_URL, headers=headers, json={"changes": list(changes)})


def _store(db, role, key, value):
    db.add(RolePermission(role=role, permission_key=key, value=value))
    db.commit()


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _audit_entries(db):
    return db.query(AuditLog).filter(AuditLog.entity_type == "role_permissions").all()


@pytest.fixture
def probe_route():
    """A route guarded by flights.view, removed again when the test ends."""

    def probe(user: Annotated[User, Depends(require_permission(FLIGHTS_VIEW))]):
        return {"username": user.username}

    fastapi_app.add_api_route(PROBE_URL, probe, methods=["GET"])
    # First in the table, so it wins over /api/flights/{id} and the SPA fallback.
    route = fastapi_app.router.routes.pop()
    fastapi_app.router.routes.insert(0, route)
    yield
    fastapi_app.router.routes.remove(route)


# Registry --------------------------------------------------------------------

def test_registry_defaults_match_spec():
    assert len(GRID_ROWS) == KEY_COUNT
    assert len(permissions.REGISTRY) == KEY_COUNT
    assert set(permissions.REGISTRY) == {row[0] for row in GRID_ROWS}
    for key, supervisor, pilot, viewer in GRID_ROWS:
        definition = permissions.REGISTRY[key]
        assert definition.key == key
        assert definition.defaults[SUPERVISOR] == supervisor
        assert definition.defaults[PILOT] == pilot
        assert definition.defaults[VIEWER] == viewer.removeprefix("locked-")
        assert definition.viewer_locked is viewer.startswith("locked-"), key
        assert definition.kind == ("level" if viewer.endswith(NONE) or ALL in (supervisor, pilot) else "bool"), key


@pytest.mark.parametrize("key,requires", [
    (FLIGHTS_VIEW, None),
    (FLIGHTS_CREATE, FLIGHTS_VIEW),
    (FLIGHTS_EDIT, FLIGHTS_VIEW),
    ("pilots.contacts", "pilots.view"),
    ("alerts.dismiss", "alerts.view"),
    ("audit.view", None),
    ("reports.generate", None),
    ("reports.export", None),
    ("digest.redirect", None),
])
def test_registry_requires(key, requires):
    assert permissions.REGISTRY[key].requires == requires


def test_registry_labels_come_from_spec():
    definition = permissions.REGISTRY["alerts.dismiss"]
    assert definition.feature == "Alerts"
    assert definition.action == "Mark read, dismiss (shared for everyone)"


# Resolving values ------------------------------------------------------------

def test_admin_always_highest(db):
    _store(db, ADMIN, FLIGHTS_VIEW, NO)
    _store(db, ADMIN, FLIGHTS_EDIT, NONE)
    assert permissions.get_value(db, ADMIN, FLIGHTS_VIEW) == YES
    assert permissions.get_value(db, ADMIN, FLIGHTS_EDIT) == ALL
    assert permissions.get_value(db, ADMIN, "audit.view") == YES
    assert permissions.resolved_for(db, ADMIN)[FLIGHTS_VIEW] == YES


def test_locked_viewer_ignores_stored_row(db):
    _store(db, VIEWER, FLIGHTS_EDIT, ALL)
    assert permissions.get_value(db, VIEWER, FLIGHTS_EDIT) == NONE
    assert permissions.resolved_for(db, VIEWER)[FLIGHTS_EDIT] == NONE


def test_stored_row_wins_over_default(db):
    _store(db, PILOT, FLIGHTS_EDIT, ALL)
    assert permissions.get_value(db, PILOT, FLIGHTS_EDIT) == ALL
    assert permissions.resolved_for(db, PILOT)[FLIGHTS_EDIT] == ALL


@pytest.mark.parametrize("stored", ["maybe", YES])
def test_invalid_stored_value_falls_back_to_default(db, stored):
    _store(db, PILOT, FLIGHTS_EDIT, stored)
    assert permissions.get_value(db, PILOT, FLIGHTS_EDIT) == OWN
    assert permissions.resolved_for(db, PILOT)[FLIGHTS_EDIT] == OWN


def test_stored_row_for_unknown_key_is_ignored(db):
    _store(db, PILOT, "no.such.key", YES)
    assert "no.such.key" not in permissions.resolved_for(db, PILOT)


def test_unknown_key_raises(db):
    with pytest.raises(KeyError):
        permissions.get_value(db, PILOT, "no.such.key")


def test_unknown_role_resolves_to_lowest(db):
    _store(db, "superuser", FLIGHTS_VIEW, YES)
    assert permissions.get_value(db, "superuser", FLIGHTS_VIEW) == NO
    assert permissions.get_value(db, "superuser", FLIGHTS_EDIT) == NONE
    assert set(permissions.resolved_for(db, "superuser").values()) == {NO, NONE}


def test_can_and_level_follow_value(db, pilot_user):
    assert permissions.can(db, pilot_user, FLIGHTS_VIEW) is True
    assert permissions.can(db, pilot_user, FLIGHTS_EDIT) is True
    assert permissions.level(db, pilot_user, FLIGHTS_EDIT) == OWN
    assert permissions.can(db, pilot_user, FLIGHTS_DELETE) is False
    assert permissions.level(db, pilot_user, FLIGHTS_DELETE) == NONE
    assert permissions.can(db, pilot_user, "flights.review") is False


def test_unknown_key_denies(db, admin_user, pilot_user):
    assert permissions.can(db, pilot_user, "no.such.key") is False
    assert permissions.can(db, admin_user, "no.such.key") is False
    assert permissions.level(db, admin_user, "no.such.key") == NONE


def test_values_are_cached_on_the_loaded_user(db, pilot_user):
    assert permissions.level(db, pilot_user, FLIGHTS_EDIT) == OWN
    _store(db, PILOT, FLIGHTS_EDIT, ALL)
    assert permissions.level(db, pilot_user, FLIGHTS_EDIT) == OWN
    pilot_user.role = SUPERVISOR
    assert permissions.level(db, pilot_user, FLIGHTS_EDIT) == ALL


# Validation ------------------------------------------------------------------

@pytest.mark.parametrize("role,key,value,fragment", [
    (VIEWER, FLIGHTS_EDIT, ALL, FLIGHTS_EDIT),
    (VIEWER, FLIGHTS_EDIT, NONE, FLIGHTS_EDIT),
    (PILOT, "no.such.key", YES, "no.such.key"),
    (PILOT, FLIGHTS_EDIT, YES, FLIGHTS_EDIT),
    (PILOT, FLIGHTS_VIEW, ALL, FLIGHTS_VIEW),
    (ADMIN, FLIGHTS_VIEW, NO, ADMIN),
    ("superuser", FLIGHTS_VIEW, NO, "superuser"),
])
def test_validate_change_refuses(role, key, value, fragment):
    assert fragment in permissions.validate_change(role, key, value)


@pytest.mark.parametrize("role,key,value", [
    (PILOT, FLIGHTS_EDIT, ALL),
    (SUPERVISOR, FLIGHTS_VIEW, NO),
    (VIEWER, FLIGHTS_VIEW, NO),
    (VIEWER, "pilots.contacts", YES),
])
def test_validate_change_accepts(role, key, value):
    assert permissions.validate_change(role, key, value) is None


def test_validate_grid_applies_view_rule_to_resulting_grid(db):
    errors = permissions.validate_grid(db, [_change(PILOT, "fleet.view", NO)])
    assert len(errors) == 1
    assert "fleet.location" in errors[0]
    assert permissions.validate_grid(db, [
        _change(PILOT, "fleet.view", NO),
        _change(PILOT, "fleet.location", NO),
    ]) == []


def test_validate_grid_reads_stored_rows(db):
    _store(db, PILOT, "fleet.location", NO)
    assert permissions.validate_grid(db, [_change(PILOT, "fleet.view", NO)]) == []
    errors = permissions.validate_grid(db, [_change(PILOT, "fleet.location", YES), _change(PILOT, "fleet.view", NO)])
    assert any("fleet.location" in error for error in errors)


def test_validate_grid_covers_contacts_on_viewer(db):
    errors = permissions.validate_grid(db, [
        _change(VIEWER, "pilots.contacts", YES),
        _change(VIEWER, "pilots.view", NO),
    ])
    assert any("pilots.contacts" in error for error in errors)


# Admin API -------------------------------------------------------------------

def test_get_returns_registry_and_values(client, db, admin_headers):
    _store(db, PILOT, FLIGHTS_EDIT, ALL)
    body = client.get(PERMISSIONS_URL, headers=admin_headers).json()
    assert len(body["registry"]) == KEY_COUNT
    entry = next(item for item in body["registry"] if item["key"] == FLIGHTS_EDIT)
    assert entry["feature"] == "Flights"
    assert entry["kind"] == "level"
    assert entry["viewer_locked"] is True
    assert entry["requires"] == FLIGHTS_VIEW
    assert entry["defaults"][PILOT] == OWN
    assert body["values"][PILOT][FLIGHTS_EDIT] == ALL
    assert body["values"][VIEWER][FLIGHTS_EDIT] == NONE
    assert body["values"][ADMIN][FLIGHTS_EDIT] == ALL


def test_put_stores_change_and_returns_grid(client, db, admin_headers):
    resp = _put(client, admin_headers, _change(PILOT, FLIGHTS_EDIT, ALL))
    assert resp.status_code == 200, resp.text
    assert resp.json()["values"][PILOT][FLIGHTS_EDIT] == ALL
    assert permissions.get_value(db, PILOT, FLIGHTS_EDIT) == ALL


def test_put_back_to_default_removes_row(client, db, admin_headers):
    _put(client, admin_headers, _change(PILOT, FLIGHTS_EDIT, ALL))
    resp = _put(client, admin_headers, _change(PILOT, FLIGHTS_EDIT, OWN))
    assert resp.status_code == 200, resp.text
    assert db.query(RolePermission).count() == 0


def test_put_refuses_locked_viewer_cell(client, db, admin_headers):
    resp = _put(client, admin_headers, _change(VIEWER, FLIGHTS_EDIT, ALL))
    assert resp.status_code == 422
    assert FLIGHTS_EDIT in resp.text
    assert db.query(RolePermission).count() == 0


def test_put_refuses_unknown_key(client, db, admin_headers):
    resp = _put(client, admin_headers, _change(PILOT, "no.such.key", YES))
    assert resp.status_code == 422
    assert "no.such.key" in resp.text
    assert db.query(RolePermission).count() == 0


def test_put_refuses_invalid_value(client, db, admin_headers):
    resp = _put(client, admin_headers, _change(PILOT, FLIGHTS_EDIT, YES))
    assert resp.status_code == 422
    assert FLIGHTS_EDIT in resp.text
    assert db.query(RolePermission).count() == 0


def test_put_is_atomic(client, db, admin_headers):
    resp = _put(
        client, admin_headers,
        _change(PILOT, FLIGHTS_DELETE, ALL),
        _change(PILOT, FLIGHTS_EDIT, "maybe"),
    )
    assert resp.status_code == 422
    assert FLIGHTS_EDIT in resp.text
    assert FLIGHTS_DELETE not in resp.text
    assert db.query(RolePermission).count() == 0
    assert _audit_entries(db) == []


def test_put_refuses_change_without_view(client, db, admin_headers):
    resp = _put(
        client, admin_headers,
        _change(PILOT, FLIGHTS_VIEW, NO),
        _change(PILOT, FLIGHTS_EDIT, OWN),
    )
    assert resp.status_code == 422
    assert FLIGHTS_EDIT in resp.text
    assert db.query(RolePermission).count() == 0

    # flights.create is also on for pilots by default, so it goes off as well.
    resp = _put(
        client, admin_headers,
        _change(PILOT, FLIGHTS_VIEW, NO),
        _change(PILOT, FLIGHTS_CREATE, NO),
        _change(PILOT, FLIGHTS_EDIT, NONE),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["values"][PILOT][FLIGHTS_VIEW] == NO


def test_put_writes_one_audit_entry_with_old_and_new(client, db, admin_user, admin_headers):
    resp = _put(
        client, admin_headers,
        _change(PILOT, FLIGHTS_EDIT, ALL),
        _change(SUPERVISOR, FLIGHTS_DELETE, NONE),
    )
    assert resp.status_code == 200, resp.text
    entries = _audit_entries(db)
    assert len(entries) == 1
    assert entries[0].user_id == admin_user.id
    assert entries[0].changes == {
        f"{PILOT} {FLIGHTS_EDIT}": {"old": OWN, "new": ALL},
        f"{SUPERVISOR} {FLIGHTS_DELETE}": {"old": ALL, "new": NONE},
    }


def test_put_without_effect_writes_no_audit_entry(client, db, admin_headers):
    resp = _put(client, admin_headers, _change(PILOT, FLIGHTS_EDIT, OWN))
    assert resp.status_code == 200, resp.text
    assert _audit_entries(db) == []
    assert db.query(RolePermission).count() == 0


def test_reset_clears_rows_and_audits(client, db, admin_headers):
    _put(client, admin_headers, _change(PILOT, FLIGHTS_EDIT, ALL))
    resp = client.post(RESET_URL, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["values"][PILOT][FLIGHTS_EDIT] == OWN
    assert db.query(RolePermission).count() == 0
    entries = _audit_entries(db)
    assert len(entries) == 2
    reset_entry = next(entry for entry in entries if entry.action == "reset")
    assert reset_entry.changes == {f"{PILOT} {FLIGHTS_EDIT}": {"old": ALL, "new": OWN}}


@pytest.mark.parametrize("headers_fixture", ["supervisor_headers", "pilot_headers", "viewer_headers"])
def test_non_admin_refused(client, db, request, headers_fixture):
    headers = request.getfixturevalue(headers_fixture)
    assert client.get(PERMISSIONS_URL, headers=headers).status_code == 403
    assert _put(client, headers, _change(PILOT, FLIGHTS_EDIT, ALL)).status_code == 403
    assert client.post(RESET_URL, headers=headers).status_code == 403
    assert db.query(RolePermission).count() == 0


def test_unauthenticated_refused(client):
    assert client.get(PERMISSIONS_URL).status_code == 401


# Guard -----------------------------------------------------------------------

def test_require_permission_carries_its_key():
    assert require_permission(FLIGHTS_EDIT).permission_key == FLIGHTS_EDIT


def test_require_permission_with_unknown_key_denies_admin(db, admin_user):
    guard = require_permission("no.such.key")
    with pytest.raises(HTTPException) as refused:
        guard(user=admin_user, db=db)
    assert refused.value.status_code == 403


@pytest.mark.usefixtures("probe_route")
def test_change_applies_on_next_request(client, pilot_headers, admin_headers):
    assert client.get(PROBE_URL, headers=pilot_headers).status_code == 200
    resp = _put(
        client, admin_headers,
        _change(PILOT, FLIGHTS_VIEW, NO),
        _change(PILOT, FLIGHTS_CREATE, NO),
        _change(PILOT, FLIGHTS_EDIT, NONE),
    )
    assert resp.status_code == 200, resp.text
    assert client.get(PROBE_URL, headers=pilot_headers).status_code == 403


# API tokens ------------------------------------------------------------------

def test_api_token_refused_on_permissions_routes(client, admin_headers):
    created = client.post(
        "/api/api-tokens", headers=admin_headers,
        json={"name": "Automation", "read_only": False},
    ).json()
    headers = _bearer(created["token"])
    assert client.get(PERMISSIONS_URL, headers=headers).status_code == 403
    assert _put(client, headers, _change(PILOT, FLIGHTS_EDIT, ALL)).status_code == 403
    assert client.post(RESET_URL, headers=headers).status_code == 403


@pytest.mark.usefixtures("probe_route")
def test_api_token_follows_owner_permissions(client, db, pilot_user, admin_headers):
    raw = api_tokens_service.generate_token()
    db.add(ApiToken(
        name="Pilot token",
        token_hash=api_tokens_service.hash_token(raw),
        token_prefix=raw[:12],
        user_id=pilot_user.id,
    ))
    db.commit()
    assert client.get(PROBE_URL, headers=_bearer(raw)).status_code == 200
    _put(
        client, admin_headers,
        _change(PILOT, FLIGHTS_VIEW, NO),
        _change(PILOT, FLIGHTS_CREATE, NO),
        _change(PILOT, FLIGHTS_EDIT, NONE),
    )
    assert client.get(PROBE_URL, headers=_bearer(raw)).status_code == 403


# Resolved values on the signed-in user ---------------------------------------

def test_me_returns_resolved_permissions(client, db, pilot_headers, viewer_headers, admin_headers):
    _store(db, PILOT, FLIGHTS_DELETE, OWN)
    pilot = client.get(ME_URL, headers=pilot_headers).json()["permissions"]
    assert len(pilot) == KEY_COUNT
    assert pilot[FLIGHTS_EDIT] == OWN
    assert pilot[FLIGHTS_DELETE] == OWN
    assert client.get(ME_URL, headers=viewer_headers).json()["permissions"][FLIGHTS_EDIT] == NONE
    assert client.get(ME_URL, headers=admin_headers).json()["permissions"]["audit.view"] == YES


def test_login_returns_resolved_permissions(client, pilot_user):
    resp = client.post(LOGIN_URL, json={"username": pilot_user.username, "password": PILOT_PASSWORD})
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["permissions"][FLIGHTS_EDIT] == OWN


def test_profile_update_keeps_resolved_permissions(client, pilot_headers):
    resp = client.patch(ME_URL, headers=pilot_headers, json={"theme": "dark"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["permissions"][FLIGHTS_EDIT] == OWN


@pytest.mark.usefixtures("pilot_user")
def test_other_users_responses_carry_no_permissions(client, admin_headers):
    users = client.get("/api/auth/users", headers=admin_headers).json()
    assert [listed["permissions"] for listed in users] == [{}, {}]


# Always enforced -------------------------------------------------------------

def test_last_admin_still_protected(client, db, admin_user, admin_headers):
    user_url = f"/api/auth/users/{admin_user.id}"
    assert client.patch(user_url, headers=admin_headers, json={"role": PILOT}).status_code == 400
    assert client.patch(user_url, headers=admin_headers, json={"is_active": False}).status_code == 400
    assert client.delete(user_url, headers=admin_headers).status_code == 400
    assert _put(client, admin_headers, _change(ADMIN, FLIGHTS_VIEW, NO)).status_code == 422
    db.expire_all()
    remaining = db.get(User, admin_user.id)
    assert remaining.role == ADMIN
    assert remaining.is_active is True


# Migration -------------------------------------------------------------------

def test_migration_downgrade_removes_table_and_column(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setattr(app.config.settings, "DATABASE_URL", url)
    config = _alembic_config(url)
    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        assert "role_permissions" in inspector.get_table_names()
        assert "uploaded_by_id" in {col["name"] for col in inspector.get_columns("documents")}
        command.downgrade(config, PREVIOUS_REVISION)
        inspector = inspect(engine)
        assert "role_permissions" not in inspector.get_table_names()
        assert "uploaded_by_id" not in {col["name"] for col in inspector.get_columns("documents")}
    finally:
        engine.dispose()
