"""Shared lifecycle handling for fleet equipment records."""

from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import object_session

# Statuses that take an item out of service.
DECOMMISSIONED_STATUSES = {"retired", "damaged"}

# The statuses each equipment table takes. Mirrored by EQUIPMENT_STATUSES in
# frontend/src/lib/constants.js, which the Fleet and detail editors offer.
_IN_SERVICE = ("active", "maintenance")
_OUT_OF_SERVICE = ("retired", "damaged")
EQUIPMENT_STATUSES = {
    "vehicles": _IN_SERVICE + _OUT_OF_SERVICE,
    "batteries": ("active", "charging", "maintenance") + _OUT_OF_SERVICE,
    "controllers": _IN_SERVICE + _OUT_OF_SERVICE,
    "docks": ("active", "online", "offline", "maintenance") + _OUT_OF_SERVICE,
    "sensor_packages": _IN_SERVICE + _OUT_OF_SERVICE,
    "attachments": _IN_SERVICE + _OUT_OF_SERVICE,
    "other_equipment": _IN_SERVICE + _OUT_OF_SERVICE,
}

# The maintenance-schedule entity_type for each equipment table.
SCHEDULE_ENTITY_TYPES = {
    "vehicles": "vehicle",
    "batteries": "battery",
    "controllers": "controller",
    "docks": "dock",
    "sensor_packages": "sensor",
    "attachments": "attachment",
    "other_equipment": "other",
}


def end_schedules(db, entity) -> int:
    """Deactivate the maintenance schedules of equipment leaving service, so a
    retired or deleted item stops showing as overdue and stops counting
    against compliance. Returns how many were active."""
    from app.models.maintenance_schedule import MaintenanceSchedule
    entity_type = SCHEDULE_ENTITY_TYPES.get(entity.__tablename__)
    if entity_type is None or entity.id is None:
        return 0
    schedules = db.query(MaintenanceSchedule).filter(
        MaintenanceSchedule.entity_type == entity_type,
        MaintenanceSchedule.entity_id == entity.id,
        MaintenanceSchedule.is_active.is_(True),
    ).all()
    for schedule in schedules:
        schedule.is_active = False
    return len(schedules)


def set_fields_with_lifecycle(entity, updates: dict) -> None:
    """Apply field updates; auto-fill decommissioned_date when the status
    moves an item out of service and no date is set. The date stays editable
    and is never cleared automatically.

    A status outside the type's list is refused (422) unless it is the value
    already stored, so a record holding an old status can still be edited. A
    decommissioned date before the acquired date, and text longer than its
    column (SQLite would store it whole), are refused (422) as well."""
    columns = entity.__table__.columns
    for k, v in updates.items():
        length = getattr(columns[k].type, "length", None) if k in columns else None
        if isinstance(v, str) and length and len(v) > length:
            raise HTTPException(422, f"{k} must be at most {length} characters")
    allowed = EQUIPMENT_STATUSES.get(entity.__tablename__)
    status = updates.get("status")
    if allowed and "status" in updates and status != entity.status and status not in allowed:
        raise HTTPException(422, f"Status must be one of: {', '.join(allowed)}")
    acquired = updates.get("acquired_date", getattr(entity, "acquired_date", None))
    decommissioned = updates.get("decommissioned_date", getattr(entity, "decommissioned_date", None))
    if acquired and decommissioned and decommissioned < acquired:
        raise HTTPException(422, "Decommissioned date cannot be before the acquired date")
    for k, v in updates.items():
        setattr(entity, k, v)
    if updates.get("status") not in DECOMMISSIONED_STATUSES:
        return
    if updates.get("decommissioned_date") is None and entity.decommissioned_date is None:
        entity.decommissioned_date = date.today()
    db = object_session(entity)
    if db is not None:
        end_schedules(db, entity)
