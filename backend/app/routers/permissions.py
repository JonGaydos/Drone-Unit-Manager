"""Admin API for the role permission grid.

Not listed in the API token scope map, so no token can reach these routes.
"""

from collections.abc import Callable
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import AdminUser, DBSession
from app.models.user import User
from app.responses import responses
from app.services import permissions
from app.services.audit import log_action

router = APIRouter(prefix="/api/permissions", tags=["permissions"])


class PermissionChange(BaseModel):
    role: str
    key: str
    value: str


class PermissionUpdate(BaseModel):
    changes: list[PermissionChange]


def _grid_response(db: Session) -> dict:
    roles = (permissions.ADMIN, *permissions.EDITABLE_ROLES)
    return {
        "registry": [asdict(definition) for definition in permissions.REGISTRY.values()],
        "values": {role: permissions.resolved_for(db, role) for role in roles},
    }


def _editable_values(db: Session) -> dict[tuple[str, str], str]:
    return {
        (role, key): value
        for role in permissions.EDITABLE_ROLES
        for key, value in permissions.resolved_for(db, role).items()
    }


def _apply_audited(db: Session, admin: User, action: str, apply: Callable[[], None]) -> None:
    """Apply a change and commit it with one audit entry of what actually changed."""
    before = _editable_values(db)
    apply()
    after = _editable_values(db)
    changes = {
        f"{role} {key}": {"old": old, "new": after[(role, key)]}
        for (role, key), old in before.items()
        if old != after[(role, key)]
    }
    if changes:
        log_action(db, admin.id, admin.display_name, action, "role_permissions",
                   entity_name="Role permissions", changes=changes)
    db.commit()


@router.get("")
def get_permissions(admin: AdminUser, db: DBSession):
    """The registry and every role's current values."""
    return _grid_response(db)


@router.put("", responses=responses(422))
def update_permissions(data: PermissionUpdate, admin: AdminUser, db: DBSession):
    """Validate every change, then apply them all, or none."""
    changes = [change.model_dump() for change in data.changes]
    errors = permissions.validate_grid(db, changes)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))
    _apply_audited(db, admin, "update", lambda: permissions.apply_changes(db, changes))
    return _grid_response(db)


@router.post("/reset")
def reset_permissions(admin: AdminUser, db: DBSession):
    """Return every role to the default grid."""
    _apply_audited(db, admin, "reset", lambda: permissions.reset(db))
    return _grid_response(db)
