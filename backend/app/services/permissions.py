"""Role permissions: the code registry, stored overrides and resolved values.

The registry holds every permission key with its labels, option type, default
per role and viewer lock. The role_permissions table stores admin changes only,
so a missing row means the default. Resolution fails closed: an unknown role or
key never grants anything.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.models.role_permission import RolePermission
from app.models.user import User

ADMIN = "admin"
SUPERVISOR = "supervisor"
PILOT = "pilot"
VIEWER = "viewer"
# The roles the grid configures. Admin always resolves to the highest value.
EDITABLE_ROLES = (SUPERVISOR, PILOT, VIEWER)

YES = "yes"
NO = "no"
NONE = "none"
OWN = "own"
ALL = "all"

Kind = Literal["bool", "level"]
BOOL: Kind = "bool"
LEVEL: Kind = "level"
# Each kind's options, lowest first.
OPTIONS: dict[str, tuple[str, ...]] = {BOOL: (NO, YES), LEVEL: (NONE, OWN, ALL)}

# Marks a viewer cell that resolves to the lowest value whatever is stored.
LOCKED = "locked"

VIEW = "View"
CREATE = "Create"
EDIT = "Edit"
EDIT_DELETE = "Edit, delete"
DELETE = "Delete"
MANAGE = "Manage"
COMPLETE = "Complete"


@dataclass(frozen=True)
class PermissionDef:
    key: str
    feature: str
    action: str
    kind: Kind
    defaults: dict[str, str]
    viewer_locked: bool
    requires: str | None


# Feature label, then rows of key, action label, supervisor, pilot and viewer.
# Within a feature, the row labelled View is the key every other row requires.
# A feature with no View row of its own depends on _FEATURE_VIEW_OVERRIDES.
_DEFAULT_GRID = (
    ("Flights", (
        ("flights.view", VIEW, YES, YES, YES),
        ("flights.create", CREATE, YES, YES, LOCKED),
        ("flights.edit", EDIT, ALL, OWN, LOCKED),
        ("flights.delete", DELETE, ALL, NONE, LOCKED),
        ("flights.review", "Review, bulk actions", YES, NO, LOCKED),
    )),
    ("Flight plans", (
        ("flight_plans.view", VIEW, YES, YES, YES),
        ("flight_plans.create", CREATE, YES, YES, LOCKED),
        ("flight_plans.edit", EDIT, ALL, OWN, LOCKED),
        ("flight_plans.approve", "Approve, deny, delete", YES, NO, LOCKED),
    )),
    ("Incidents", (
        ("incidents.view", VIEW, YES, YES, YES),
        ("incidents.create", CREATE, YES, YES, LOCKED),
        ("incidents.edit", EDIT, ALL, OWN, LOCKED),
        ("incidents.resolve", "Resolve or close", YES, NO, LOCKED),
        ("incidents.delete", DELETE, YES, NO, LOCKED),
    )),
    ("Mission and training logs", (
        ("logs.view", VIEW, YES, YES, YES),
        ("logs.create", CREATE, YES, YES, LOCKED),
        ("logs.edit", EDIT_DELETE, ALL, OWN, LOCKED),
    )),
    ("Maintenance records", (
        ("maintenance.view", VIEW, YES, YES, YES),
        ("maintenance.create", CREATE, YES, YES, LOCKED),
        ("maintenance.edit", EDIT_DELETE, ALL, OWN, LOCKED),
    )),
    ("Maintenance schedules", (
        ("schedules.complete", COMPLETE, YES, YES, LOCKED),
        ("schedules.manage", "Create, edit, delete", YES, NO, LOCKED),
    )),
    ("Fleet equipment", (
        ("fleet.view", VIEW, YES, YES, YES),
        ("fleet.manage", "Manage, including components", YES, NO, LOCKED),
        ("fleet.location", "Update vehicle location", YES, YES, LOCKED),
    )),
    ("Equipment checkouts", (
        ("checkouts.use", "Check out, check in", YES, YES, LOCKED),
        ("checkouts.delete", DELETE, YES, NO, LOCKED),
    )),
    ("Pilots", (
        ("pilots.view", VIEW, YES, YES, YES),
        ("pilots.contacts", "View email and phone", YES, YES, NO),
        ("pilots.edit", "Edit profile", ALL, OWN, LOCKED),
        ("pilots.manage", "Create, delete, merge", YES, NO, LOCKED),
    )),
    ("Certifications and currency", (
        ("certifications.view", VIEW, YES, YES, YES),
        ("certifications.manage", "Manage, send reminders", YES, NO, LOCKED),
    )),
    ("Checklists", (
        ("checklists.view", VIEW, YES, YES, YES),
        ("checklists.complete", COMPLETE, YES, YES, LOCKED),
        ("checklists.manage", "Manage templates", YES, NO, LOCKED),
    )),
    ("Calendar", (
        ("calendar.view", VIEW, YES, YES, YES),
        ("calendar.create", CREATE, YES, YES, LOCKED),
        ("calendar.edit", EDIT_DELETE, ALL, OWN, LOCKED),
    )),
    ("Documents and photos", (
        ("files.view", VIEW, YES, YES, YES),
        ("files.upload", "Upload", ALL, OWN, LOCKED),
        ("files.edit", "Edit, soft delete", ALL, OWN, LOCKED),
        ("files.custody", "Restore, legal hold", YES, NO, LOCKED),
    )),
    ("Folders", (
        ("folders.manage", MANAGE, YES, NO, LOCKED),
    )),
    ("Alerts", (
        ("alerts.view", VIEW, YES, YES, YES),
        ("alerts.dismiss", "Mark read, dismiss (shared for everyone)", YES, NO, LOCKED),
    )),
    ("Reports and exports", (
        ("reports.generate", "Generate reports", YES, YES, NO),
        ("reports.export", "Export CSV", YES, YES, YES),
    )),
    ("Operating authority, geofences", (
        ("authority.view", VIEW, YES, YES, YES),
        ("authority.manage", MANAGE, YES, NO, LOCKED),
    )),
    ("Vehicle registrations", (
        ("registrations.view", VIEW, YES, YES, YES),
        ("registrations.manage", MANAGE, NO, NO, LOCKED),
    )),
    ("Audit log", (
        ("audit.view", VIEW, NO, NO, NO),
    )),
    ("Email digest", (
        ("digest.redirect", "Send to another address", YES, NO, LOCKED),
    )),
)


# Features whose records are seen through another feature's view.
_FEATURE_VIEW_OVERRIDES = {
    "Maintenance schedules": "maintenance.view",
    "Equipment checkouts": "fleet.view",
    "Folders": "files.view",
}


def _build_registry() -> dict[str, PermissionDef]:
    registry = {}
    for feature, rows in _DEFAULT_GRID:
        own_view = next((row[0] for row in rows if row[1] == VIEW), None)
        view_key = _FEATURE_VIEW_OVERRIDES.get(feature, own_view)
        for key, action, supervisor, pilot, viewer in rows:
            kind = LEVEL if {supervisor, pilot} & {NONE, OWN, ALL} else BOOL
            registry[key] = PermissionDef(
                key=key,
                feature=feature,
                action=action,
                kind=kind,
                defaults={
                    SUPERVISOR: supervisor,
                    PILOT: pilot,
                    VIEWER: OPTIONS[kind][0] if viewer == LOCKED else viewer,
                },
                viewer_locked=viewer == LOCKED,
                requires=None if key == view_key else view_key,
            )
    return registry


REGISTRY: dict[str, PermissionDef] = _build_registry()


def _lowest(definition: PermissionDef) -> str:
    return OPTIONS[definition.kind][0]


def _resolve(definition: PermissionDef, role: str, stored: str | None) -> str:
    if role == ADMIN:
        return OPTIONS[definition.kind][-1]
    if role not in definition.defaults or (role == VIEWER and definition.viewer_locked):
        return _lowest(definition)
    if stored in OPTIONS[definition.kind]:
        return stored
    return definition.defaults[role]


def _stored_row(db: Session, role: str, key: str) -> RolePermission | None:
    return (
        db.query(RolePermission)
        .filter(RolePermission.role == role, RolePermission.permission_key == key)
        .first()
    )


def get_value(db: Session, role: str, key: str) -> str:
    """The value a role holds for a key. Raises KeyError for an unknown key."""
    definition = REGISTRY[key]
    row = _stored_row(db, role, key)
    return _resolve(definition, role, row.value if row else None)


def resolved_for(db: Session, role: str) -> dict[str, str]:
    """Every key's value for a role, from a single query."""
    rows = db.query(RolePermission).filter(RolePermission.role == role).all()
    stored = {row.permission_key: row.value for row in rows}
    return {key: _resolve(definition, role, stored.get(key)) for key, definition in REGISTRY.items()}


def _user_values(db: Session, user: User) -> dict[str, str]:
    """A user's values, loaded once per loaded user object, so once per request."""
    cached = getattr(user, "_resolved_permissions", None)
    if cached is None or cached[0] != user.role:
        cached = (user.role, resolved_for(db, user.role))
        user._resolved_permissions = cached
    return cached[1]


def level(db: Session, user: User, key: str) -> str:
    """The user's value for a key. An unknown key resolves to none."""
    return _user_values(db, user).get(key, NONE)


def can(db: Session, user: User, key: str) -> bool:
    """True when the user holds the key at any level above the lowest."""
    return level(db, user, key) in (YES, OWN, ALL)


def validate_change(role: str, key: str, value: str) -> str | None:
    """The reason a single change is not allowed, or None when it is."""
    if role not in EDITABLE_ROLES:
        return f"{key}: role '{role}' cannot be configured"
    definition = REGISTRY.get(key)
    if definition is None:
        return f"{key}: unknown permission"
    if role == VIEWER and definition.viewer_locked:
        return f"{key}: locked for viewers"
    if value not in OPTIONS[definition.kind]:
        return f"{key}: invalid value '{value}'"
    return None


def _missing_views(grid: Mapping[str, Mapping[str, str]]) -> list[str]:
    """Errors for every change permission held while its view key is off."""
    return [
        f"{key}: {role} needs {definition.requires} to hold this permission"
        for role, values in grid.items()
        for key, definition in REGISTRY.items()
        if definition.requires
        and values[definition.requires] == NO
        and values[key] != _lowest(definition)
    ]


def validate_grid(db: Session, changes: Iterable[Mapping[str, str]]) -> list[str]:
    """Every problem with a set of changes, each a mapping of role, key and value.

    Covers each change on its own, then the change-without-view rule on the grid
    the valid changes would produce.
    """
    errors = []
    grid = {role: resolved_for(db, role) for role in EDITABLE_ROLES}
    for change in changes:
        role, key, value = change["role"], change["key"], change["value"]
        error = validate_change(role, key, value)
        if error:
            errors.append(error)
        else:
            grid[role][key] = value
    return errors + _missing_views(grid)


def apply_changes(db: Session, changes: Iterable[Mapping[str, str]]) -> None:
    """Store validated changes without committing. A default value keeps no row."""
    for change in changes:
        role, key, value = change["role"], change["key"], change["value"]
        row = _stored_row(db, role, key)
        if value == REGISTRY[key].defaults[role]:
            if row:
                db.delete(row)
        elif row:
            row.value = value
        else:
            db.add(RolePermission(role=role, permission_key=key, value=value))
        # Flushed each time so a repeated role and key finds the row just written.
        db.flush()


def reset(db: Session) -> None:
    """Remove every stored change without committing."""
    db.query(RolePermission).delete()
