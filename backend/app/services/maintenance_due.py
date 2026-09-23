"""Which maintenance records still carry a live due date.

Every completion of a recurring schedule logs a record with the next due date,
so the task done in March leaves behind the record from February whose due
date has passed. Shown as-is, the dashboard and the Upcoming list reported a
task done on time as overdue. A record's due date counts only while it is the
latest record for that task: same equipment, same description.
"""

from datetime import date

from app.models.maintenance import MaintenanceRecord


def _task_key(entity_type, entity_id, description) -> tuple:
    return entity_type, entity_id, (description or "").strip().lower()


def superseded_record_ids(db) -> set[int]:
    """Ids of records a later record for the same task has replaced."""
    rows = db.query(
        MaintenanceRecord.id, MaintenanceRecord.entity_type, MaintenanceRecord.entity_id,
        MaintenanceRecord.description, MaintenanceRecord.performed_date,
    ).all()
    latest: dict[tuple, tuple] = {}  # task -> (performed_date, id) of its newest record
    for row in rows:
        key = _task_key(row.entity_type, row.entity_id, row.description)
        rank = (row.performed_date or date.min, row.id)
        latest[key] = max(latest.get(key, rank), rank)
    current = {rank[1] for rank in latest.values()}
    return {row.id for row in rows} - current
