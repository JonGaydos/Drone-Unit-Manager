"""Pilot email and phone numbers are kept from viewer accounts.

A viewer is read-only, often someone outside the unit, and has no reason to
contact pilots through the app. Wherever a pilot record or a pilot's contact
details come back, a viewer gets them blank.
"""

from app.schemas.pilot import PilotOut

CONTACT_FIELDS = ("email", "phone", "phone_type", "phone_work")


def hides_contacts(user) -> bool:
    """Whether this user must not see pilot email and phone numbers."""
    return user.role == "viewer"


def pilot_out(pilot, user) -> PilotOut:
    """A pilot as this user may see it."""
    out = PilotOut.model_validate(pilot)
    if hides_contacts(user):
        for field in CONTACT_FIELDS:
            setattr(out, field, None)
    return out
