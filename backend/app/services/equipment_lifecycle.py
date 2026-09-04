"""Shared lifecycle handling for fleet equipment records."""

from datetime import date

# Statuses that take an item out of service.
DECOMMISSIONED_STATUSES = {"retired", "damaged"}


def set_fields_with_lifecycle(entity, updates: dict) -> None:
    """Apply field updates; auto-fill decommissioned_date when the status
    moves an item out of service and no date is set. The date stays editable
    and is never cleared automatically."""
    for k, v in updates.items():
        setattr(entity, k, v)
    if (
        updates.get("status") in DECOMMISSIONED_STATUSES
        and updates.get("decommissioned_date") is None
        and entity.decommissioned_date is None
    ):
        entity.decommissioned_date = date.today()
