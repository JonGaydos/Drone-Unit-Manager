"""Soft delete, legal hold and purge rules shared by photos and documents.

A delete hides the record and keeps its file; a supervisor can restore it, and
only an admin can purge it for good. A legal hold blocks both delete and purge,
so held material cannot leave the system by any route.
"""

import logging
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

ON_HOLD = "This item is on legal hold. Release the hold before deleting it."


class HoldUpdate(BaseModel):
    """Body of the set-hold routes."""
    legal_hold: bool


def soft_delete(item, user) -> None:
    """Mark ``item`` deleted by ``user``.

    Raises:
        HTTPException: 409 while the item is on legal hold.
    """
    if item.legal_hold:
        raise HTTPException(409, ON_HOLD)
    item.deleted_at = datetime.utcnow()
    item.deleted_by_id = user.id


def restore(item) -> None:
    """Bring a deleted item back.

    Raises:
        HTTPException: 409 when the item is not deleted.
    """
    if item.deleted_at is None:
        raise HTTPException(409, "This item is not deleted.")
    item.deleted_at = None
    item.deleted_by_id = None


def check_purgeable(item) -> None:
    """Refuse a purge unless the item is already deleted and not on hold.

    Raises:
        HTTPException: 409 otherwise.
    """
    if item.deleted_at is None:
        raise HTTPException(409, "Delete this item before purging it.")
    if item.legal_hold:
        raise HTTPException(409, ON_HOLD)


def remove_file(path: str | Path | None, root: str | Path) -> None:
    """Delete ``path`` if it exists and resolves inside ``root``.

    A stored path is data, so it is never trusted to point where it should: one
    that resolves outside the upload root is left alone and logged.
    """
    if not path:
        return
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(Path(root).resolve())
    except ValueError:
        logger.warning("Not removing %s: outside the upload directory", resolved)
        return
    if resolved.is_file():
        resolved.unlink()


def deleted_row(item, name: str, users_by_id: dict) -> dict:
    """One row of a Recently deleted listing."""
    who = users_by_id.get(item.deleted_by_id)
    return {
        "id": item.id,
        "name": name,
        "deleted_at": item.deleted_at.isoformat() if item.deleted_at else None,
        "deleted_by": who.display_name if who else None,
        "legal_hold": item.legal_hold,
    }
