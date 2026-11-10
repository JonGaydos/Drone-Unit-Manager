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
    # _authenticate_image_request: a signed URL, or a login or API token holding files.view.
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

# Each route's permission keys, written from the Route Mapping in the plan. Only
# keys a route declares as guards appear here. test_permission_matrix.py and the
# test_permissions_*.py files cover checks made inside handlers, which a dependency
# walk cannot see:
#   Level checks with require_record_access:
#     PATCH and DELETE on flights, maintenance records and calendar events
#     PATCH and cancel on flight plans
#     PATCH on incidents and pilots
#     PATCH, DELETE and roster add and remove on mission and training logs
#     PATCH and DELETE on documents and photos
#     DELETE /api/media/{media_id}, which holds no key here (see SIGNED_IN_ROUTES)
#   POST /api/documents/upload: files.upload at All to attach to anyone's record
#   PATCH /api/flights/{flight_id}: flights.review for the sign-off fields
#   POST /api/flights/bulk-update: flights.edit at All to change pilot or purpose
#   POST /api/flights/bulk-delete: flights.delete at All
#   PATCH /api/incidents/{incident_id}: incidents.resolve for its fields
#   PATCH /api/pilots/{pilot_id}: pilots.manage for the supervisor-only fields
#   The /api/reports routes: the view keys for the report's content
FLIGHTS_VIEW = "flights.view"
FLIGHTS_REVIEW = "flights.review"
PLANS_VIEW = "flight_plans.view"
PLANS_EDIT = "flight_plans.edit"
PLANS_APPROVE = "flight_plans.approve"
INCIDENTS_VIEW = "incidents.view"
LOGS_VIEW = "logs.view"
LOGS_CREATE = "logs.create"
LOGS_EDIT = "logs.edit"
MAINTENANCE_VIEW = "maintenance.view"
MAINTENANCE_EDIT = "maintenance.edit"
SCHEDULES_MANAGE = "schedules.manage"
FLEET_VIEW = "fleet.view"
FLEET_MANAGE = "fleet.manage"
CHECKOUTS_USE = "checkouts.use"
PILOTS_VIEW = "pilots.view"
PILOTS_MANAGE = "pilots.manage"
CERTIFICATIONS_VIEW = "certifications.view"
CERTIFICATIONS_MANAGE = "certifications.manage"
CHECKLISTS_VIEW = "checklists.view"
CHECKLISTS_MANAGE = "checklists.manage"
CALENDAR_EDIT = "calendar.edit"
FILES_VIEW = "files.view"
FILES_UPLOAD = "files.upload"
FILES_EDIT = "files.edit"
FILES_CUSTODY = "files.custody"
FOLDERS_MANAGE = "folders.manage"
ALERTS_VIEW = "alerts.view"
ALERTS_DISMISS = "alerts.dismiss"
AUTHORITY_VIEW = "authority.view"
AUTHORITY_MANAGE = "authority.manage"
REGISTRATIONS_VIEW = "registrations.view"
REGISTRATIONS_MANAGE = "registrations.manage"
AUDIT_VIEW = "audit.view"
REPORTS_GENERATE = "reports.generate"
REPORTS_EXPORT = "reports.export"

EXPECTED_ROUTE_KEYS = {
    # flights
    "GET /api/flights": {FLIGHTS_VIEW},
    "GET /api/flights/count": {FLIGHTS_VIEW},
    "GET /api/flights/review": {FLIGHTS_VIEW},
    "GET /api/flights/{flight_id}": {FLIGHTS_VIEW},
    "GET /api/flights/preflight-check": {FLIGHTS_VIEW},
    "GET /api/flights/purposes/usage": {FLIGHTS_REVIEW},
    "POST /api/flights": {"flights.create"},
    "PATCH /api/flights/{flight_id}": {"flights.edit"},
    "DELETE /api/flights/{flight_id}": {"flights.delete"},
    "POST /api/flights/bulk-update": {FLIGHTS_REVIEW},
    "POST /api/flights/bulk-delete": {FLIGHTS_REVIEW, "flights.delete"},
    "PATCH /api/flights/{flight_id}/telemetry-status": {FLIGHTS_REVIEW},
    "PATCH /api/flights/{flight_id}/review-status": {FLIGHTS_REVIEW},
    # telemetry
    "GET /api/telemetry/flight/{flight_id}": {FLIGHTS_VIEW},
    # flight_plans
    "GET /api/flight-plans": {PLANS_VIEW},
    "GET /api/flight-plans/pending/count": {PLANS_VIEW},
    "GET /api/flight-plans/{plan_id}": {PLANS_VIEW},
    "POST /api/flight-plans": {"flight_plans.create"},
    "PATCH /api/flight-plans/{plan_id}": {PLANS_EDIT},
    "POST /api/flight-plans/{plan_id}/cancel": {PLANS_EDIT},
    "POST /api/flight-plans/{plan_id}/approve": {PLANS_APPROVE},
    "POST /api/flight-plans/{plan_id}/deny": {PLANS_APPROVE},
    "DELETE /api/flight-plans/{plan_id}": {PLANS_APPROVE},
    # incidents
    "GET /api/incidents": {INCIDENTS_VIEW},
    "GET /api/incidents/stats": {INCIDENTS_VIEW},
    "GET /api/incidents/{incident_id}": {INCIDENTS_VIEW},
    "POST /api/incidents": {"incidents.create"},
    "PATCH /api/incidents/{incident_id}": {"incidents.edit"},
    "DELETE /api/incidents/{incident_id}": {"incidents.delete"},
    # mission_logs
    "GET /api/mission-logs": {LOGS_VIEW},
    "GET /api/mission-logs/{mission_id}": {LOGS_VIEW},
    "POST /api/mission-logs": {LOGS_CREATE},
    "PATCH /api/mission-logs/{mission_id}": {LOGS_EDIT},
    "DELETE /api/mission-logs/{mission_id}": {LOGS_EDIT},
    "POST /api/mission-logs/{mission_id}/pilots": {LOGS_EDIT},
    "DELETE /api/mission-logs/{mission_id}/pilots/{pilot_id}": {LOGS_EDIT},
    # training_logs
    "GET /api/training-logs": {LOGS_VIEW},
    "GET /api/training-logs/{training_id}": {LOGS_VIEW},
    "POST /api/training-logs": {LOGS_CREATE},
    "PATCH /api/training-logs/{training_id}": {LOGS_EDIT},
    "DELETE /api/training-logs/{training_id}": {LOGS_EDIT},
    "POST /api/training-logs/{training_id}/pilots": {LOGS_EDIT},
    "DELETE /api/training-logs/{training_id}/pilots/{pilot_id}": {LOGS_EDIT},
    # maintenance
    "GET /api/maintenance": {MAINTENANCE_VIEW},
    "GET /api/maintenance/{record_id}": {MAINTENANCE_VIEW},
    "POST /api/maintenance": {"maintenance.create"},
    "PATCH /api/maintenance/{record_id}": {MAINTENANCE_EDIT},
    "DELETE /api/maintenance/{record_id}": {MAINTENANCE_EDIT},
    # maintenance_schedules
    "GET /api/maintenance/schedules": {MAINTENANCE_VIEW},
    "GET /api/maintenance/schedules/{schedule_id}": {MAINTENANCE_VIEW},
    "POST /api/maintenance/schedules/{schedule_id}/complete": {"schedules.complete"},
    "POST /api/maintenance/schedules": {SCHEDULES_MANAGE},
    "PATCH /api/maintenance/schedules/{schedule_id}": {SCHEDULES_MANAGE},
    "DELETE /api/maintenance/schedules/{schedule_id}": {SCHEDULES_MANAGE},
    # vehicles. The stats also follow flights.view, under the design's rule that
    # flight figures follow that feature's view, which the mapping row does not state.
    "GET /api/vehicles": {FLEET_VIEW},
    "GET /api/vehicles/locations": {FLEET_VIEW},
    "GET /api/vehicles/{vehicle_id}": {FLEET_VIEW},
    "GET /api/vehicles/{vehicle_id}/photo/view": {FLEET_VIEW},
    "GET /api/vehicles/{vehicle_id}/stats": {FLEET_VIEW, FLIGHTS_VIEW},
    "POST /api/vehicles": {FLEET_MANAGE},
    "PATCH /api/vehicles/{vehicle_id}": {FLEET_MANAGE},
    "DELETE /api/vehicles/{vehicle_id}": {FLEET_MANAGE},
    "POST /api/vehicles/{target_id}/merge": {FLEET_MANAGE},
    "PATCH /api/vehicles/{vehicle_id}/location": {"fleet.location"},
    # equipment. Stats, flights and pilots also follow flights.view where they
    # draw on flights, by the same design rule. Controller and dock stats do not.
    "GET /api/batteries": {FLEET_VIEW},
    "GET /api/batteries/{bid}": {FLEET_VIEW},
    "GET /api/batteries/{bid}/health-history": {FLEET_VIEW},
    "GET /api/batteries/{bid}/stats": {FLEET_VIEW, FLIGHTS_VIEW},
    "GET /api/batteries/{bid}/flights": {FLEET_VIEW, FLIGHTS_VIEW},
    "GET /api/batteries/{bid}/pilots": {FLEET_VIEW, FLIGHTS_VIEW},
    "POST /api/batteries": {FLEET_MANAGE},
    "PATCH /api/batteries/{bid}": {FLEET_MANAGE},
    "DELETE /api/batteries/{bid}": {FLEET_MANAGE},
    "POST /api/batteries/{bid}/merge": {FLEET_MANAGE},
    "POST /api/batteries/{bid}/readings": {FLEET_MANAGE},
    "GET /api/controllers": {FLEET_VIEW},
    "GET /api/controllers/{cid}": {FLEET_VIEW},
    "GET /api/controllers/{cid}/stats": {FLEET_VIEW},
    "POST /api/controllers": {FLEET_MANAGE},
    "PATCH /api/controllers/{cid}": {FLEET_MANAGE},
    "DELETE /api/controllers/{cid}": {FLEET_MANAGE},
    "GET /api/docks": {FLEET_VIEW},
    "GET /api/docks/{did}": {FLEET_VIEW},
    "GET /api/docks/{did}/stats": {FLEET_VIEW},
    "POST /api/docks": {FLEET_MANAGE},
    "PATCH /api/docks/{did}": {FLEET_MANAGE},
    "DELETE /api/docks/{did}": {FLEET_MANAGE},
    "GET /api/sensors": {FLEET_VIEW},
    "GET /api/sensors/{sid}": {FLEET_VIEW},
    "GET /api/sensors/{sid}/stats": {FLEET_VIEW, FLIGHTS_VIEW},
    "GET /api/sensors/{sid}/flights": {FLEET_VIEW, FLIGHTS_VIEW},
    "GET /api/sensors/{sid}/pilots": {FLEET_VIEW, FLIGHTS_VIEW},
    "POST /api/sensors": {FLEET_MANAGE},
    "PATCH /api/sensors/{sid}": {FLEET_MANAGE},
    "DELETE /api/sensors/{sid}": {FLEET_MANAGE},
    "POST /api/sensors/{sid}/merge": {FLEET_MANAGE},
    "GET /api/attachments": {FLEET_VIEW},
    "GET /api/attachments/{aid}": {FLEET_VIEW},
    "GET /api/attachments/{aid}/stats": {FLEET_VIEW, FLIGHTS_VIEW},
    "GET /api/attachments/{aid}/flights": {FLEET_VIEW, FLIGHTS_VIEW},
    "GET /api/attachments/{aid}/pilots": {FLEET_VIEW, FLIGHTS_VIEW},
    "POST /api/attachments": {FLEET_MANAGE},
    "PATCH /api/attachments/{aid}": {FLEET_MANAGE},
    "DELETE /api/attachments/{aid}": {FLEET_MANAGE},
    "POST /api/attachments/{aid}/merge": {FLEET_MANAGE},
    "GET /api/other-equipment": {FLEET_VIEW},
    "GET /api/other-equipment/{oid}": {FLEET_VIEW},
    "POST /api/other-equipment": {FLEET_MANAGE},
    "PATCH /api/other-equipment/{oid}": {FLEET_MANAGE},
    "DELETE /api/other-equipment/{oid}": {FLEET_MANAGE},
    # components
    "GET /api/components": {FLEET_VIEW},
    "GET /api/components/{component_id}": {FLEET_VIEW},
    "POST /api/components": {FLEET_MANAGE},
    "PATCH /api/components/{component_id}": {FLEET_MANAGE},
    "DELETE /api/components/{component_id}": {FLEET_MANAGE},
    # equipment_checkouts
    "GET /api/equipment-checkouts": {FLEET_VIEW},
    "GET /api/equipment-checkouts/active": {FLEET_VIEW},
    "POST /api/equipment-checkouts": {CHECKOUTS_USE},
    "POST /api/equipment-checkouts/{checkout_id}/checkin": {CHECKOUTS_USE},
    "DELETE /api/equipment-checkouts/{checkout_id}": {"checkouts.delete"},
    # pilots. Stats and needs-attention also follow the view of what they show,
    # under the design's read-path rule, which the mapping row does not state.
    "GET /api/pilots": {PILOTS_VIEW},
    "GET /api/pilots/{pilot_id}": {PILOTS_VIEW},
    "GET /api/pilots/{pilot_id}/photo/view": {PILOTS_VIEW},
    "GET /api/pilots/{pilot_id}/stats": {PILOTS_VIEW, FLIGHTS_VIEW},
    "GET /api/pilots/{pilot_id}/needs-attention": {PILOTS_VIEW, CERTIFICATIONS_VIEW},
    "PATCH /api/pilots/{pilot_id}": {"pilots.edit"},
    "POST /api/pilots": {PILOTS_MANAGE},
    "DELETE /api/pilots/{pilot_id}": {PILOTS_MANAGE},
    "POST /api/pilots/{target_id}/merge": {PILOTS_MANAGE},
    # certifications
    "GET /api/certification-types": {CERTIFICATIONS_VIEW},
    "POST /api/certification-types": {CERTIFICATIONS_MANAGE},
    "PATCH /api/certification-types/reorder": {CERTIFICATIONS_MANAGE},
    "PATCH /api/certification-types/{ct_id}": {CERTIFICATIONS_MANAGE},
    "DELETE /api/certification-types/{ct_id}": {CERTIFICATIONS_MANAGE},
    "GET /api/pilot-certifications": {CERTIFICATIONS_VIEW},
    "GET /api/pilot-certifications/{pc_id}/history": {CERTIFICATIONS_VIEW},
    "POST /api/pilot-certifications": {CERTIFICATIONS_MANAGE},
    "PATCH /api/pilot-certifications/{pc_id}": {CERTIFICATIONS_MANAGE},
    "POST /api/pilot-certifications/{pc_id}/renew": {CERTIFICATIONS_MANAGE},
    "POST /api/pilot-certifications/bulk-renew": {CERTIFICATIONS_MANAGE},
    "DELETE /api/pilot-certifications/{pc_id}": {CERTIFICATIONS_MANAGE},
    "GET /api/pilot-equipment-quals": {CERTIFICATIONS_VIEW},
    "POST /api/pilot-equipment-quals": {CERTIFICATIONS_MANAGE},
    "PATCH /api/pilot-equipment-quals/{peq_id}": {CERTIFICATIONS_MANAGE},
    "DELETE /api/pilot-equipment-quals/{peq_id}": {CERTIFICATIONS_MANAGE},
    "GET /api/certifications/matrix": {CERTIFICATIONS_VIEW},
    # currency
    "GET /api/currency/rules": {CERTIFICATIONS_VIEW},
    "GET /api/currency/status": {CERTIFICATIONS_VIEW},
    "GET /api/currency/status/{pilot_id}": {CERTIFICATIONS_VIEW},
    "POST /api/currency/rules": {CERTIFICATIONS_MANAGE},
    "PATCH /api/currency/rules/{rule_id}": {CERTIFICATIONS_MANAGE},
    "DELETE /api/currency/rules/{rule_id}": {CERTIFICATIONS_MANAGE},
    "POST /api/currency/send-reminders": {CERTIFICATIONS_MANAGE},
    # checklists
    "GET /api/checklists/templates": {CHECKLISTS_VIEW},
    "GET /api/checklists/templates/{template_id}": {CHECKLISTS_VIEW},
    "GET /api/checklists/completions": {CHECKLISTS_VIEW},
    "GET /api/checklists/completions/{completion_id}": {CHECKLISTS_VIEW},
    "POST /api/checklists/complete": {"checklists.complete"},
    "POST /api/checklists/templates": {CHECKLISTS_MANAGE},
    "PATCH /api/checklists/templates/{template_id}": {CHECKLISTS_MANAGE},
    "DELETE /api/checklists/templates/{template_id}": {CHECKLISTS_MANAGE},
    "DELETE /api/checklists/completions/{completion_id}": {CHECKLISTS_MANAGE},
    # calendar
    "GET /api/calendar": {"calendar.view"},
    "POST /api/calendar/events": {"calendar.create"},
    "PATCH /api/calendar/events/{event_id}": {CALENDAR_EDIT},
    "DELETE /api/calendar/events/{event_id}": {CALENDAR_EDIT},
    # documents
    "GET /api/documents": {FILES_VIEW},
    "GET /api/documents/{doc_id}/view": {FILES_VIEW},
    "POST /api/documents/upload": {FILES_UPLOAD},
    "PATCH /api/documents/{doc_id}": {FILES_EDIT},
    "DELETE /api/documents/{doc_id}": {FILES_EDIT},
    "GET /api/documents/deleted": {FILES_CUSTODY},
    "POST /api/documents/{doc_id}/restore": {FILES_CUSTODY},
    "PUT /api/documents/{doc_id}/hold": {FILES_CUSTODY},
    # photos
    "GET /api/photos": {FILES_VIEW},
    "GET /api/photos/{photo_id}/signed-urls": {FILES_VIEW},
    "POST /api/photos/upload": {FILES_UPLOAD},
    "PATCH /api/photos/{photo_id}": {FILES_EDIT},
    "DELETE /api/photos/{photo_id}": {FILES_EDIT},
    "GET /api/photos/deleted": {FILES_CUSTODY},
    "POST /api/photos/{photo_id}/restore": {FILES_CUSTODY},
    "PUT /api/photos/{photo_id}/hold": {FILES_CUSTODY},
    "POST /api/photos/{photo_id}/flight/{flight_id}": {FILES_CUSTODY},
    "DELETE /api/photos/{photo_id}/flight/{flight_id}": {FILES_CUSTODY},
    "POST /api/photos/{photo_id}/incident/{incident_id}": {FILES_CUSTODY},
    "DELETE /api/photos/{photo_id}/incident/{incident_id}": {FILES_CUSTODY},
    # media
    "GET /api/media": {FILES_VIEW},
    "GET /api/media/count": {FILES_VIEW},
    # folders
    "GET /api/folders": {FILES_VIEW},
    "GET /api/folders/{folder_id}/documents": {FILES_VIEW},
    "POST /api/folders": {FOLDERS_MANAGE},
    "PATCH /api/folders/{folder_id}": {FOLDERS_MANAGE},
    "DELETE /api/folders/{folder_id}": {FOLDERS_MANAGE},
    # alerts
    "GET /api/alerts": {ALERTS_VIEW},
    "GET /api/alerts/count": {ALERTS_VIEW},
    "PATCH /api/alerts/{alert_id}/read": {ALERTS_DISMISS},
    "PATCH /api/alerts/{alert_id}/dismiss": {ALERTS_DISMISS},
    "POST /api/alerts/dismiss-all": {ALERTS_DISMISS},
    # operating_authorities
    "GET /api/operating-authorities": {AUTHORITY_VIEW},
    "GET /api/operating-authorities/{authority_id}": {AUTHORITY_VIEW},
    "POST /api/operating-authorities": {AUTHORITY_MANAGE},
    "PATCH /api/operating-authorities/{authority_id}": {AUTHORITY_MANAGE},
    "DELETE /api/operating-authorities/{authority_id}": {AUTHORITY_MANAGE},
    # vehicle_registrations
    "GET /api/vehicles/{vehicle_id}/registrations": {REGISTRATIONS_VIEW},
    "GET /api/vehicle-registrations/current": {REGISTRATIONS_VIEW},
    "POST /api/vehicles/{vehicle_id}/registrations": {REGISTRATIONS_MANAGE},
    "DELETE /api/vehicle-registrations/{reg_id}": {REGISTRATIONS_MANAGE},
    # audit
    "GET /api/audit": {AUDIT_VIEW},
    # reports
    "POST /api/reports/generate": {REPORTS_GENERATE},
    "POST /api/reports/generate/pdf": {REPORTS_GENERATE},
    "POST /api/reports/per-pilot/zip": {REPORTS_GENERATE},
    # export. The roster stays supervisor-level through pilots.manage, a call the
    # mapping records. Checkouts follow fleet.view.
    "GET /api/export/flights/csv": {REPORTS_EXPORT, FLIGHTS_VIEW},
    "GET /api/export/flights/{flight_id}/gpx": {REPORTS_EXPORT, FLIGHTS_VIEW},
    "GET /api/export/flights/{flight_id}/kml": {REPORTS_EXPORT, FLIGHTS_VIEW},
    "GET /api/export/pilots/csv": {REPORTS_EXPORT, PILOTS_MANAGE},
    "GET /api/export/vehicles/csv": {REPORTS_EXPORT, FLEET_VIEW},
    "GET /api/export/fleet/{equipment_type}/csv": {REPORTS_EXPORT, FLEET_VIEW},
    "GET /api/export/equipment-checkouts/csv": {REPORTS_EXPORT, FLEET_VIEW},
    "GET /api/export/maintenance/csv": {REPORTS_EXPORT, MAINTENANCE_VIEW},
    "GET /api/export/checklists/csv": {REPORTS_EXPORT, CHECKLISTS_VIEW},
    "GET /api/export/certifications/csv": {REPORTS_EXPORT, CERTIFICATIONS_VIEW},
    "GET /api/export/training-logs/csv": {REPORTS_EXPORT, LOGS_VIEW},
    "GET /api/export/mission-logs/csv": {REPORTS_EXPORT, LOGS_VIEW},
    "GET /api/export/incidents/csv": {REPORTS_EXPORT, INCIDENTS_VIEW},
    "GET /api/export/flight-plans/csv": {REPORTS_EXPORT, PLANS_VIEW},
    "GET /api/export/audit/csv": {REPORTS_EXPORT, AUDIT_VIEW},
    # dashboard
    "GET /api/dashboard/activity-by-month": {FLIGHTS_VIEW},
    "GET /api/dashboard/top-pilots-30d": {FLIGHTS_VIEW},
    "GET /api/dashboard/analytics/flights-by-purpose": {FLIGHTS_VIEW},
    "GET /api/dashboard/analytics/flights-by-year": {FLIGHTS_VIEW},
    "GET /api/dashboard/analytics/flights-by-year-purpose": {FLIGHTS_VIEW},
    "GET /api/dashboard/analytics/flights-by-pilot": {FLIGHTS_VIEW},
    "GET /api/dashboard/analytics/avg-duration-by-year": {FLIGHTS_VIEW},
    "GET /api/dashboard/analytics/monthly-flights": {FLIGHTS_VIEW},
    "GET /api/dashboard/analytics/pilot-hours": {FLIGHTS_VIEW},
    "GET /api/dashboard/analytics/pilot-performance/{pilot_id}": {FLIGHTS_VIEW},
    "GET /api/dashboard/top-vehicles-30d": {FLEET_VIEW},
    "GET /api/dashboard/analytics/vehicle-hours": {FLEET_VIEW},
    "GET /api/dashboard/analytics/fleet-health": {FLEET_VIEW},
    "GET /api/dashboard/maintenance-due": {MAINTENANCE_VIEW},
    "GET /api/dashboard/upcoming-expirations": {CERTIFICATIONS_VIEW},
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


def _route_key_problems(table: dict[str, Guards], expected: dict[str, set[str]]) -> list[str]:
    """Every difference between the keys routes declare and the expected table."""
    actual = {name: guards.keys for name, guards in table.items() if guards.keys}
    problems = [f"{name}: declares {sorted(keys)} but is missing from the expected table"
                for name, keys in actual.items() if name not in expected]
    problems += [f"{name}: in the expected table with {sorted(keys)} but declares no key or no longer exists"
                 for name, keys in expected.items() if name not in actual]
    problems += [f"{name}: declares {sorted(actual[name])} but {sorted(keys)} is expected"
                 for name, keys in expected.items() if name in actual and actual[name] != keys]
    return problems


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


def test_every_route_has_its_expected_keys():
    problems = _route_key_problems(_route_table(app), EXPECTED_ROUTE_KEYS)
    assert not problems, _report(problems)


def test_walk_reaches_included_routers_and_stacked_guards():
    table = _route_table(app)
    assert table["GET /api/flights"].keys == {FLIGHTS_VIEW}
    assert table["GET /api/export/flights/csv"].keys == {REPORTS_EXPORT, FLIGHTS_VIEW}
    assert table["POST /api/auth/users"].admin
    assert table["GET /api/auth/me"].login


# The gate itself -------------------------------------------------------------

GUARDED_KEY = FLIGHTS_VIEW
BARE_ROUTE = "GET /router/bare"
NESTED_DEPENDENCY_ROUTE = "GET /router/nested"
ROUTER_GUARD_ROUTE = "GET /router/guarded/handler"
ADMIN_ROUTE = "GET /router/admin"
SIGNED_IN_ROUTE = "GET /router/signed-in"
GUARD = Annotated[object, Depends(require_permission(GUARDED_KEY))]


def _nested_guard(user: GUARD):
    return user


def _handler():
    return {}


def _scratch_app() -> FastAPI:
    router = APIRouter(prefix="/router")
    router.add_api_route("/bare", _handler)
    guarded = APIRouter(prefix="/guarded", dependencies=[Depends(require_permission(GUARDED_KEY))])
    guarded.add_api_route("/handler", _handler)
    router.include_router(guarded)

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
    assert f"{BARE_ROUTE}: has no permission key, no require_admin and no allowlist entry" in problems


def test_gate_names_a_non_api_route():
    assert any(problem.startswith("GET /docs:") for problem in _problems(_route_table(_scratch_app()), {}))


def test_gate_finds_nested_and_router_level_guards():
    table = _route_table(_scratch_app())
    assert table[NESTED_DEPENDENCY_ROUTE].keys == {GUARDED_KEY}
    assert table[ROUTER_GUARD_ROUTE].keys == {GUARDED_KEY}
    assert table[ADMIN_ROUTE].admin


def test_gate_refuses_a_guarded_route_on_an_allowlist():
    table = _route_table(_scratch_app())
    for name in (NESTED_DEPENDENCY_ROUTE, ADMIN_ROUTE):
        problems = _problems({name: table[name]}, {"SOME_LIST": frozenset({name})})
        assert len(problems) == 1
        assert problems[0].startswith(f"{name}: on SOME_LIST but also guarded")


def test_gate_refuses_a_route_on_two_allowlists():
    table = _route_table(_scratch_app())
    allowlists = {"FIRST": frozenset({BARE_ROUTE}), "SECOND": frozenset({BARE_ROUTE})}
    assert _problems({BARE_ROUTE: table[BARE_ROUTE]}, allowlists) == [
        f"{BARE_ROUTE}: on more than one allowlist: FIRST, SECOND"]


def test_gate_refuses_a_signed_in_entry_with_no_login():
    table = _route_table(_scratch_app())
    assert len(_problems({BARE_ROUTE: table[BARE_ROUTE]}, {"SIGNED_IN_ROUTES": frozenset({BARE_ROUTE})})) == 1
    allowlists = {"SIGNED_IN_ROUTES": frozenset({SIGNED_IN_ROUTE})}
    assert not _problems({SIGNED_IN_ROUTE: table[SIGNED_IN_ROUTE]}, allowlists)


def test_gate_names_every_key_difference():
    table = _route_table(_scratch_app())
    nested = NESTED_DEPENDENCY_ROUTE
    guard = ROUTER_GUARD_ROUTE
    assert _route_key_problems(table, {nested: {GUARDED_KEY}, guard: {GUARDED_KEY}}) == []
    assert _route_key_problems(table, {nested: {GUARDED_KEY}}) == [
        f"{guard}: declares ['{GUARDED_KEY}'] but is missing from the expected table"]
    stale = "GET /router/gone"
    assert _route_key_problems(table, {nested: {GUARDED_KEY}, guard: {GUARDED_KEY}, stale: {GUARDED_KEY}}) == [
        f"{stale}: in the expected table with ['{GUARDED_KEY}'] but declares no key or no longer exists"]
    assert _route_key_problems(table, {nested: {"other.key"}, guard: {GUARDED_KEY}}) == [
        f"{nested}: declares ['{GUARDED_KEY}'] but ['other.key'] is expected"]


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


def test_photo_serving_needs_a_login_or_signature(client, db):
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
