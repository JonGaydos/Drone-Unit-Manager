"""Pilot email and phone numbers are shown only to roles holding pilots.contacts.

An admin always sees them. For any other role the permission decides, and a
viewer holds it off by default. Wherever a pilot record or a pilot's contact
details come back, a user without the permission gets them blank.
"""

from app.schemas.pilot import PilotOut
from app.services import permissions as permissions_service

CONTACT_FIELDS = ("email", "phone", "phone_type", "phone_work")


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
