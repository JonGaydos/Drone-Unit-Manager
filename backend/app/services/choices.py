"""Fixed-choice checks for values written through the API."""

from fastapi import HTTPException


def require_choices(updates: dict, current, fields: dict) -> None:
    """Raise 422 when a field in `updates` holds a value outside its choices.

    `fields` maps a field name to its allowed values. `current` is the stored
    record, or None for a new one. A value equal to the stored one passes, so
    a record holding an older value can still be edited and saved.
    """
    for name, choices in fields.items():
        if name not in updates or updates[name] is None:
            continue
        value = updates[name]
        if current is not None and value == getattr(current, name):
            continue
        if value not in choices:
            raise HTTPException(422, f"{name} must be one of: {', '.join(choices)}")
