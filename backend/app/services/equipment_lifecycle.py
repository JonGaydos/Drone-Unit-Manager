"""Shared lifecycle handling for fleet equipment records."""

from datetime import date

from sqlalchemy.orm import object_session

# Statuses that take an item out of service.
DECOMMISSIONED_STATUSES = {"retired", "damaged"}

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
    return db.query(MaintenanceSchedule).filter(
        MaintenanceSchedule.entity_type == entity_type,
        MaintenanceSchedule.entity_id == entity.id,
        MaintenanceSchedule.is_active.is_(True),
    ).update({MaintenanceSchedule.is_active: False}, synchronize_session=False)


def set_fields_with_lifecycle(entity, updates: dict) -> None:
    """Apply field updates; auto-fill decommissioned_date when the status
    moves an item out of service and no date is set. The date stays editable
    and is never cleared automatically."""
    for k, v in updates.items():
        setattr(entity, k, v)
    if updates.get("status") not in DECOMMISSIONED_STATUSES:
        return
    if updates.get("decommissioned_date") is None and entity.decommissioned_date is None:
        entity.decommissioned_date = date.today()
    db = object_session(entity)
    if db is not None:
        end_schedules(db, entity)
