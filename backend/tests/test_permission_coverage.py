"""Every route must say who may call it, so a new route cannot ship unguarded.

A route is classified by walking its whole dependency tree. It passes when it
holds at least one permission key, depends on require_admin, or is named on
exactly one allowlist below. When one of these tests fails, fix the route's
guard in its router. Add to an allowlist only what the design says is outside
the grid, and name the check when the handler does the authorizing itself.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import iter_route_contexts

from app.main import app
from app.models.photo import Photo
from app.routers.auth import get_current_user, require_admin, require_permission
from app.services.permissions import REGISTRY

# Admin only, with the check made inside the handler rather than by require_admin.
ADMIN_ONLY_ROUTES = frozenset({
    # _verify_admin_or_install_token: an admin login, or the install token before
    # any user exists. Pinned by test_backup_import_is_admin_only.
    "POST /api/backup/import",
})

# Any login, with no permission key.
SIGNED_IN_ROUTES = frozenset({
    # Own account.
    "POST /api/auth/logout",
    "GET /api/auth/me",
    "PATCH /api/auth/me",
    "POST /api/auth/change-password",
    "GET /api/notifications/preferences",
    "PUT /api/notifications/preferences",
    "GET /api/notifications/preview",
    "POST /api/notifications/send-test",
    "GET /api/notifications/log",
    # Pickers that forms offer with the feature's view off.
    "GET /api/flights/purposes/list",
    "GET /api/pilots/options",
    "GET /api/fleet/options",
    # Reference lookups, and settings reads, which show non-admins only public keys.
    "GET /api/weather/briefing",
    "GET /api/weather/thresholds",
    "GET /api/adsb/nearby",
    "GET /api/geocode",
    "GET /api/geocode/reverse",
    "GET /api/settings",
    "GET /api/settings/{key}",
    # Filters each result group by its view key.
    "GET /api/search",
    # Unit-wide totals with no names.
    "GET /api/dashboard/stats",
    "GET /api/dashboard/trends",
    "GET /api/dashboard/activity-by-month",
    "GET /api/dashboard/compliance",
    # Media rows have no owner, so the handler's require_record_access needs
    # files.edit at All. Pinned by test_permissions_files.test_media_delete_needs_all.
    "DELETE /api/media/{media_id}",
})

# No login dependency.
PUBLIC_ROUTES = frozenset({
    # The login and first-run screens.
    "GET /api/auth/setup-required",
    "POST /api/auth/login",
    # The handler requires the install token, and only while no user exists.
    # Pinned by the setup tests in test_auth.
    "POST /api/auth/setup",
    # Loaded by image tags, which cannot send a login token. Pinned by
    # test_logo_is_served_without_a_login.
    "GET /api/settings/logo/view",
    "GET /api/health",
    "GET /{full_path:path}",
    # _authorize_photo_request: a signed URL, or a login holding files.view.
    # Pinned by test_photo_serving_needs_a_login_or_signature, the signed URL tests
    # in test_photos, and test_permissions_files.test_view_off_blocks_serving_by_login_token.
    "GET /api/photos/{photo_id}/view",
    "GET /api/photos/{photo_id}/thumbnail",
})

ALLOWLISTS = {
    "ADMIN_ONLY_ROUTES": ADMIN_ONLY_ROUTES,
    "SIGNED_IN_ROUTES": SIGNED_IN_ROUTES,
    "PUBLIC_ROUTES": PUBLIC_ROUTES,
}

# Keys no route depends on, because a handler or service checks them inline.
NON_ROUTE_CHECKS = {
    "digest.redirect": "the digest address override",
    "incidents.resolve": "the incident resolution fields",
    "pilots.contacts": "masking pilot email and phone",
}

APP_SOURCE = Path(__file__).resolve().parent.parent / "app"
# The registry itself names every key, so it says nothing about what is checked.
REGISTRY_SOURCE = APP_SOURCE / "services" / "permissions.py"


@dataclass
class Guards:
    keys: set[str]
    admin: bool
    login: bool


def _calls(dependant):
    """Every callable in a dependency tree, however deeply nested."""
    yield dependant.call
    for child in dependant.dependencies:
        yield from _calls(child)


def _guards(context) -> Guards:
    # A plain Starlette route or mount has no dependant, so it holds no guards.
    dependant = getattr(context, "dependant", None)
    calls = list(_calls(dependant)) if dependant else []
    return Guards(
        keys={call.permission_key for call in calls if hasattr(call, "permission_key")},
        admin=require_admin in calls,
        login=get_current_user in calls,
    )


def _route_table(target) -> dict[str, Guards]:
    """Each "METHOD /path" to its guards, including routes from included routers.

    target.routes holds included routers as single entries, so a walk that only
    looks at the APIRoute objects in it finds almost nothing. Where a method and
    path are registered twice the first wins, as it does when serving a request.
    """
    table = {}
    for context in iter_route_contexts(target.routes):
        for method in sorted(context.methods or {"ANY"}):
            table.setdefault(f"{method} {context.path}", _guards(context))
    return table


def _route_problem(name: str, guards: Guards, allowlists: dict[str, frozenset[str]]) -> str | None:
    lists = [list_name for list_name, entries in allowlists.items() if name in entries]
    guarded = bool(guards.keys) or guards.admin
    if len(lists) > 1:
        return f"{name}: on more than one allowlist: {', '.join(lists)}"
    if guarded and lists:
        return f"{name}: on {lists[0]} but also guarded by {sorted(guards.keys) or 'require_admin'}"
    if not guarded and not lists:
        return f"{name}: has no permission key, no require_admin and no allowlist entry"
    if lists == ["SIGNED_IN_ROUTES"] and not guards.login:
        return f"{name}: on SIGNED_IN_ROUTES but does not depend on get_current_user"
    return None


def _problems(table: dict[str, Guards], allowlists: dict[str, frozenset[str]] = ALLOWLISTS) -> list[str]:
    found = (_route_problem(name, guards, allowlists) for name, guards in table.items())
    return [problem for problem in found if problem]


def _report(problems) -> str:
    return "\n" + "\n".join(sorted(problems))


# Route classes ---------------------------------------------------------------

def test_every_route_is_classified():
    problems = _problems(_route_table(app))
    assert not problems, _report(problems)


def test_no_stale_allowlist_entries():
    table = _route_table(app)
    stale = [f"{name}: on {list_name} but no such route exists"
             for list_name, entries in ALLOWLISTS.items() for name in entries if name not in table]
    assert not stale, _report(stale)


def test_route_permission_keys_are_in_the_registry():
    # An unknown key denies everyone, so a typo would quietly lock a route.
    unknown = [f"{name}: unknown key {key}"
               for name, guards in _route_table(app).items() for key in guards.keys if key not in REGISTRY]
    assert not unknown, _report(unknown)


def test_walk_reaches_included_routers_and_stacked_guards():
    table = _route_table(app)
    assert table["GET /api/flights"].keys == {"flights.view"}
    assert table["GET /api/export/flights/csv"].keys == {"reports.export", "flights.view"}
    assert table["POST /api/auth/users"].admin
    assert table["GET /api/auth/me"].login


# The gate itself -------------------------------------------------------------

GUARDED_KEY = "flights.view"
GUARD = Annotated[object, Depends(require_permission(GUARDED_KEY))]


def _nested_guard(user: GUARD):
    return user


def _handler():
    return {}


def _scratch_app() -> FastAPI:
    router = APIRouter(prefix="/router")
    router.add_api_route("/bare", _handler)
    router.add_api_route("/router-guard", _handler, dependencies=[Depends(require_permission(GUARDED_KEY))])

    def nested(user: Annotated[object, Depends(_nested_guard)]):
        return user

    def admin_only(user: Annotated[object, Depends(require_admin)]):
        return user

    def signed_in(user: Annotated[object, Depends(get_current_user)]):
        return user

    router.add_api_route("/nested", nested)
    router.add_api_route("/admin", admin_only)
    router.add_api_route("/signed-in", signed_in)
    scratch = FastAPI(docs_url="/docs", redoc_url=None)
    scratch.include_router(router)
    return scratch


def test_gate_names_an_unguarded_route():
    problems = _problems(_route_table(_scratch_app()), {})
    assert "GET /router/bare: has no permission key, no require_admin and no allowlist entry" in problems


def test_gate_names_a_non_api_route():
    assert any(problem.startswith("GET /docs:") for problem in _problems(_route_table(_scratch_app()), {}))


def test_gate_finds_nested_and_router_level_guards():
    table = _route_table(_scratch_app())
    assert table["GET /router/nested"].keys == {GUARDED_KEY}
    assert table["GET /router/router-guard"].keys == {GUARDED_KEY}
    assert table["GET /router/admin"].admin


def test_gate_refuses_a_guarded_route_on_an_allowlist():
    table = _route_table(_scratch_app())
    for name in ("GET /router/nested", "GET /router/admin"):
        problems = _problems({name: table[name]}, {"SOME_LIST": frozenset({name})})
        assert len(problems) == 1
        assert problems[0].startswith(f"{name}: on SOME_LIST but also guarded")


def test_gate_refuses_a_route_on_two_allowlists():
    name = "GET /router/bare"
    table = _route_table(_scratch_app())
    allowlists = {"FIRST": frozenset({name}), "SECOND": frozenset({name})}
    assert _problems({name: table[name]}, allowlists) == [f"{name}: on more than one allowlist: FIRST, SECOND"]


def test_gate_refuses_a_signed_in_entry_with_no_login():
    name = "GET /router/bare"
    table = _route_table(_scratch_app())
    assert len(_problems({name: table[name]}, {"SIGNED_IN_ROUTES": frozenset({name})})) == 1
    signed_in = "GET /router/signed-in"
    assert not _problems({signed_in: table[signed_in]}, {"SIGNED_IN_ROUTES": frozenset({signed_in})})


# Registry keys ---------------------------------------------------------------

def _keys_checked_inline() -> set[str]:
    """Keys passed straight to a permission check anywhere in the app's source."""
    pattern = re.compile(r'\b(?:can|level|require_record_access)\(\s*db,\s*\w+,\s*"([\w.]+)"')
    checked = set()
    for path in APP_SOURCE.rglob("*.py"):
        if path != REGISTRY_SOURCE:
            checked.update(pattern.findall(path.read_text(encoding="utf-8")))
    return checked


def _keys_on_routes() -> set[str]:
    return {key for guards in _route_table(app).values() for key in guards.keys}


def test_every_registry_key_is_used():
    unused = set(REGISTRY) - _keys_on_routes() - set(NON_ROUTE_CHECKS)
    assert not unused, f"Keys with no route and no named non-route check: {sorted(unused)}"


def test_non_route_checks_are_real():
    named = set(NON_ROUTE_CHECKS)
    assert named <= set(REGISTRY), f"Not in the registry: {sorted(named - set(REGISTRY))}"
    missing = named - _keys_checked_inline()
    assert not missing, f"Named as non-route checks but not checked in the app source: {sorted(missing)}"
    on_routes = named & _keys_on_routes()
    assert not on_routes, f"Named as non-route checks but used by a route: {sorted(on_routes)}"


# Checks made inside handlers -------------------------------------------------

def test_backup_import_is_admin_only(client, pilot_headers, admin_headers):
    url = "/api/backup/import"
    body = {"not_file": "x"}
    assert client.post(url, data=body).status_code == 401
    assert client.post(url, headers=pilot_headers, data=body).status_code == 403
    # Past the check, the missing file is what gets refused.
    assert client.post(url, headers=admin_headers, data=body).status_code == 400


def test_photo_serving_needs_a_login_or_signature(client, db, admin_user):
    photo = Photo(filename="p.png", original_filename="p.png", mime_type="image/png")
    db.add(photo)
    db.commit()
    for action in ("view", "thumbnail"):
        assert client.get(f"/api/photos/{photo.id}/{action}").status_code == 401, action


def test_logo_is_served_without_a_login(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.routers.settings.app_settings.UPLOAD_DIR", str(tmp_path))
    (tmp_path / "org").mkdir()
    url = "/api/settings/logo/view"
    assert client.get(url).status_code == 404
    (tmp_path / "org" / "logo.png").write_bytes(b"png")
    assert client.get(url).status_code == 200
