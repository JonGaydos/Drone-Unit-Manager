"""Pilot email and phone numbers are shown only to roles holding pilots.contacts.

An admin always sees them. For any other role the permission decides, and a
viewer holds it off by default. Wherever a pilot record or a pilot's contact
details come back, a user without the permission gets them blank.
"""

import re

from app.schemas.pilot import PilotOut
from app.services import permissions as permissions_service

CONTACT_FIELDS = ("email", "phone", "phone_type", "phone_work")
CONTACT_HIDDEN = "(hidden)"
# What separates an address from the text around it in an audit entry's details.
_ADDRESS_BOUNDARY = re.compile(r"([\s<>;,=]+)")


def hides_contacts(db, user) -> bool:
    """Whether this user must not see pilot email and phone numbers."""
    return not permissions_service.can(db, user, "pilots.contacts")


def pilot_out(db, pilot, user) -> PilotOut:
    """A pilot as this user may see it."""
    out = PilotOut.model_validate(pilot)
    if hides_contacts(db, user):
        for field in CONTACT_FIELDS:
            setattr(out, field, None)
    return out


def redact_audit_changes(changes):
    """An audit entry's field changes with any contact field's values hidden.
    Returns a copy; the stored row keeps them."""
    if not isinstance(changes, dict):
        return changes
    return {
        field: {"old": CONTACT_HIDDEN, "new": CONTACT_HIDDEN} if field in CONTACT_FIELDS else change
        for field, change in changes.items()
    }


def redact_audit_details(details: str | None) -> str | None:
    """An audit entry's details with any email address hidden, such as the
    recipients of a currency reminder."""
    if not details:
        return details
    return "".join(CONTACT_HIDDEN if "@" in part else part for part in _ADDRESS_BOUNDARY.split(details))
