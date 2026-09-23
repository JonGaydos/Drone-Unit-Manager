"""Generic CSV / XLSX import with field mapping for mission, training, and
maintenance logs. Two endpoints:

  POST /api/import/preview?entity=...  -> headers + sample + suggested mapping
  POST /api/import/commit?entity=...   -> apply mapping, create records
"""
import json
import re
from typing import Annotated

from fastapi import APIRouter, HTTPException, UploadFile, File
from starlette.concurrency import run_in_threadpool

from app.deps import DBSession, AdminUser
from app.responses import responses
from app.services.import_service import (
    parse_file, suggest_mapping, parse_date_value, parse_float_safe,
    split_members, parse_drone_list, resolve_pilot, find_unknown_pilot,
    resolve_vehicle,
)
from app.models.mission_log import MissionLog
from app.models.mission_log_pilot import MissionLogPilot
from app.models.training_log import TrainingLog
from app.models.training_log_pilot import TrainingLogPilot
from app.models.maintenance import MaintenanceRecord


router = APIRouter(prefix="/api/import", tags=["import"])


# Target field schemas. The frontend renders the mapping UI from these; the
# backend uses the same definitions to apply the mapping in commit.
MISSION_SCHEMA = [
    {"key": "date", "label": "Date", "required": True, "type": "date",
     "aliases": ["date of mission", "mission date", "date"]},
    {"key": "title", "label": "Title", "required": True, "type": "text",
     "aliases": ["title", "flight reason", "reason"]},
    {"key": "location", "label": "Location", "required": False, "type": "text",
     "aliases": ["location"]},
    {"key": "reason", "label": "Reason", "required": False, "type": "text",
     "aliases": ["flight reason", "reason"]},
    {"key": "case_number", "label": "Case Number", "required": False, "type": "text",
     "aliases": ["case", "case number"]},
    {"key": "man_hours", "label": "Total Hours", "required": False, "type": "number",
     "aliases": ["total hours", "man hours"]},
    {"key": "members", "label": "Members (semicolon-separated)", "required": False, "type": "text",
     "aliases": ["members present", "members", "pilots", "pilot"]},
    {"key": "per_pilot_hours", "label": "Hours per Person", "required": False, "type": "number",
     "aliases": ["mission hours per person", "hours per person", "hours per pilot"]},
    {"key": "notes", "label": "Notes", "required": False, "type": "text",
     "aliases": ["notes"]},
]

TRAINING_SCHEMA = [
    {"key": "date", "label": "Date", "required": True, "type": "date",
     "aliases": ["date of training", "date"]},
    {"key": "title", "label": "Title", "required": True, "type": "text",
     "aliases": ["title", "information"]},
    {"key": "training_type", "label": "Training Type", "required": False, "type": "text",
     "aliases": ["training type", "type"]},
    {"key": "description", "label": "Description", "required": False, "type": "text",
     "aliases": ["information", "description"]},
    {"key": "location", "label": "Location", "required": False, "type": "text",
     "aliases": ["location"]},
    {"key": "man_hours", "label": "Total Hours", "required": False, "type": "number",
     "aliases": ["total hours", "man hours"]},
    {"key": "members", "label": "Members (semicolon-separated)", "required": False, "type": "text",
     "aliases": ["members present", "members"]},
    {"key": "per_pilot_hours", "label": "Hours per Person", "required": False, "type": "number",
     "aliases": ["hours of training", "hours per person"]},
    {"key": "instructor", "label": "Instructor", "required": False, "type": "text",
     "aliases": ["instructor"]},
    {"key": "notes", "label": "Notes", "required": False, "type": "text",
     "aliases": ["notes"]},
]

MAINTENANCE_SCHEMA = [
    {"key": "performed_date", "label": "Date", "required": True, "type": "date",
     "aliases": ["date of maintenance", "date"]},
    {"key": "description", "label": "Description", "required": True, "type": "text",
     "aliases": ["reason for maintance", "reason for maintenance", "description"]},
    {"key": "location", "label": "Location", "required": False, "type": "text",
     "aliases": ["location"]},
    {"key": "performed_by", "label": "Performed By", "required": False, "type": "text",
     "aliases": ["member performing maintenance", "performed by", "members"]},
    {"key": "drones", "label": "Drone(s)", "required": True, "type": "text",
     "aliases": ["drone", "drone #", "drone %23", "vehicle", "vehicles", "drones"]},
    {"key": "maintenance_type", "label": "Type", "required": False, "type": "text",
     "aliases": ["maintenance type", "type"]},
    {"key": "notes", "label": "Notes", "required": False, "type": "text",
     "aliases": ["notes"]},
]

SCHEMAS = {
    "missions": MISSION_SCHEMA,
    "training": TRAINING_SCHEMA,
    "maintenance": MAINTENANCE_SCHEMA,
}


def _get(mapping: dict, key: str, row: dict):
    src = mapping.get(key)
    if not src:
        return None
    return row.get(src)


@router.post("/preview", responses=responses(400, 401))
async def preview_import(
    db: DBSession,
    admin: AdminUser,
    file: Annotated[UploadFile, File()],
    entity: str = "missions",
):
    """Inspect a CSV/XLSX without writing. Returns the file's headers, a sample
    of rows, and a suggested target->source mapping."""
    if entity not in SCHEMAS:
        raise HTTPException(400, f"Unknown entity '{entity}'. Must be one of: {', '.join(SCHEMAS)}")
    content = await file.read()
    try:
        # Off the event loop: a large workbook takes seconds to parse, and on
        # the loop every other request would wait for it.
        headers, rows, truncated = await run_in_threadpool(parse_file, content, file.filename or "")
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}") from e
    if not headers:
        raise HTTPException(400, "File has no header row")
    schema = SCHEMAS[entity]
    return {
        "entity": entity,
        "headers": [h for h in headers if h],
        "row_count": len(rows),
        "truncated": truncated,
        "sample_rows": rows[:10],
        "suggested_mapping": suggest_mapping(schema, headers),
        "target_schema": schema,
    }


@router.post("/commit", responses=responses(400, 401))
async def commit_import(
    db: DBSession,
    admin: AdminUser,
    file: Annotated[UploadFile, File()],
    entity: str = "missions",
    mapping: str = "{}",
):
    """Apply the supplied target->source mapping and create records. Returns a
    summary of created/skipped rows and any unmatched member/drone names."""
    if entity not in SCHEMAS:
        raise HTTPException(400, f"Unknown entity '{entity}'")
    try:
        mapping_dict = json.loads(mapping or "{}")
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid mapping JSON")
    content = await file.read()
    try:
        _, rows, truncated = await run_in_threadpool(parse_file, content, file.filename or "")
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}") from e
    commit = {"missions": _commit_missions, "training": _commit_training}.get(entity, _commit_maintenance)
    result = await run_in_threadpool(commit, db, rows, mapping_dict, admin.id)
    result["truncated"] = truncated
    return result


def _clean(mapping: dict, key: str, row: dict):
    """Mapped cell value trimmed, or None when blank."""
    return (_get(mapping, key, row) or "").strip() or None


def _cap(v, n: int):
    """Truncate an optional string to n chars, preserving None."""
    return v[:n] if v else None


def _build_mission_from_row(row: dict, mapping: dict, user_id) -> tuple:
    """Build a MissionLog (not yet added to the session) and the row's
    members string. Returns (None, '') if the row should be skipped."""
    d = parse_date_value(_get(mapping, "date", row))
    if not d:
        return None, ""
    reason = _clean(mapping, "reason", row)
    location = _clean(mapping, "location", row)
    title = _clean(mapping, "title", row) or reason or location or f"Mission {d}"
    notes = _clean(mapping, "notes", row)
    man_hours = parse_float_safe(_get(mapping, "man_hours", row)) or 0.0
    members_str = _get(mapping, "members", row) or ""
    return MissionLog(
        date=d,
        title=title[:300],
        reason=_cap(reason, 200),
        location=_cap(location, 500),
        case_number=_cap(_clean(mapping, "case_number", row), 100),
        man_hours=man_hours,
        status="completed",
        notes=notes,
        created_by_id=user_id,
    ), members_str


def _build_training_from_row(row: dict, mapping: dict, user_id) -> tuple:
    """Build a TrainingLog (not yet added) and the row's members string."""
    d = parse_date_value(_get(mapping, "date", row))
    if not d:
        return None, ""
    info = (_get(mapping, "description", row) or "").strip()
    title = _clean(mapping, "title", row) or (info[:80] if info else f"Training {d}")
    training_type = _clean(mapping, "training_type", row) or "Practice"
    notes = _clean(mapping, "notes", row)
    man_hours = parse_float_safe(_get(mapping, "man_hours", row)) or 0.0
    members_str = _get(mapping, "members", row) or ""
    return TrainingLog(
        date=d,
        title=title[:300],
        training_type=training_type[:100],
        description=info or None,
        location=_cap(_clean(mapping, "location", row), 500),
        instructor=_cap(_clean(mapping, "instructor", row), 200),
        man_hours=man_hours,
        outcome="completed",
        notes=notes,
        created_by_id=user_id,
    ), members_str


def _attach_pilots(db, link_model, parent_id_col: str, parent_id: int,
                   members_str: str, per_pilot: float, unknown_id,
                   unmatched_acc: dict) -> None:
    """Resolve members_str into pilot IDs and add roster link rows.
    Tracks unmatched names in unmatched_acc. Dedupes by pilot_id within one parent."""
    seen: set[int] = set()
    for member in split_members(members_str):
        pid, matched = resolve_pilot(db, member, unknown_id)
        if pid is None:
            continue
        if not matched:
            unmatched_acc[member] = unmatched_acc.get(member, 0) + 1
        if pid in seen:
            continue
        seen.add(pid)
        db.add(link_model(**{parent_id_col: parent_id, "pilot_id": pid, "hours": per_pilot}))


def _infer_maintenance_type(desc: str, mtype_raw: str) -> str:
    """Best-effort maintenance type when none is mapped."""
    if mtype_raw:
        return mtype_raw
    if re.search(r"inspection", desc, re.IGNORECASE):
        return "inspection"
    if re.search(r"monthly|scheduled|maintenance", desc, re.IGNORECASE):
        return "scheduled"
    return "unscheduled"


def _maintenance_records_for_row(db, row: dict, mapping: dict, user_id,
                                 unmatched_drones: dict):
    """Build a list of MaintenanceRecord objects (one per matched drone) for
    one row. Returns None if the row should be skipped (no drones listed)."""
    d = parse_date_value(_get(mapping, "performed_date", row))
    desc = (_get(mapping, "description", row) or "").strip() or "Maintenance"
    drones_raw = _get(mapping, "drones", row) or ""
    performer = (_get(mapping, "performed_by", row) or "").strip() or None
    if performer:
        performer = "; ".join(split_members(performer))
    notes = (_get(mapping, "notes", row) or "").strip() or None
    mtype = _infer_maintenance_type(
        desc, (_get(mapping, "maintenance_type", row) or "").strip().lower()
    )

    drones = parse_drone_list(drones_raw)
    if not drones:
        return None

    records = []
    for drone in drones:
        vid = resolve_vehicle(db, drone)
        if not vid:
            unmatched_drones[drone] = unmatched_drones.get(drone, 0) + 1
            continue
        records.append(MaintenanceRecord(
            entity_type="vehicle",
            entity_id=vid,
            maintenance_type=mtype,
            description=desc[:65535],
            performed_by=performer,
            performed_date=d,
            notes=notes,
            created_by_id=user_id,
        ))
    return records


def _log_exists(db, model, log) -> bool:
    """Whether a mission or training log with this date and title is already
    stored, so importing the same file twice does not double the hours."""
    return db.query(model.id).filter(model.date == log.date, model.title == log.title).first() is not None


def _commit_logs(db, rows, mapping, user_id, build, model, link_model, link_col):
    """Create mission or training logs from rows, each in its own savepoint:
    a row that fails is rolled back alone instead of taking the import with it."""
    unknown_id = find_unknown_pilot(db)
    counts = {"created": 0, "skipped": 0, "duplicates": 0}
    unmatched_names: dict[str, int] = {}
    errors: list[str] = []
    for i, row in enumerate(rows, start=2):
        try:
            with db.begin_nested():
                log, members_str = build(row, mapping, user_id)
                if log is None:
                    counts["skipped"] += 1
                    continue
                if _log_exists(db, model, log):
                    counts["duplicates"] += 1
                    continue
                db.add(log)
                db.flush()
                per_pilot = parse_float_safe(_get(mapping, "per_pilot_hours", row)) or 0.0
                _attach_pilots(db, link_model, link_col, log.id,
                               members_str, per_pilot, unknown_id, unmatched_names)
            counts["created"] += 1
        except Exception as e:
            errors.append(f"Row {i}: {e}")
    db.commit()
    return {**counts, "unmatched_names": unmatched_names, "errors": errors[:20]}


def _commit_missions(db, rows, mapping, user_id):
    return _commit_logs(db, rows, mapping, user_id, _build_mission_from_row,
                        MissionLog, MissionLogPilot, "mission_log_id")


def _commit_training(db, rows, mapping, user_id):
    return _commit_logs(db, rows, mapping, user_id, _build_training_from_row,
                        TrainingLog, TrainingLogPilot, "training_log_id")


def _maintenance_exists(db, rec) -> bool:
    """Whether the same work on the same aircraft on the same day is stored."""
    return db.query(MaintenanceRecord.id).filter(
        MaintenanceRecord.entity_type == rec.entity_type,
        MaintenanceRecord.entity_id == rec.entity_id,
        MaintenanceRecord.performed_date == rec.performed_date,
        MaintenanceRecord.description == rec.description,
    ).first() is not None


def _commit_maintenance(db, rows, mapping, user_id):
    counts = {"created": 0, "skipped": 0, "duplicates": 0}
    unmatched_drones: dict[str, int] = {}
    errors: list[str] = []
    for i, row in enumerate(rows, start=2):
        try:
            with db.begin_nested():
                records = _maintenance_records_for_row(db, row, mapping, user_id, unmatched_drones)
                if records is None:
                    counts["skipped"] += 1
                    continue
                fresh = [rec for rec in records if not _maintenance_exists(db, rec)]
                counts["duplicates"] += len(records) - len(fresh)
                db.add_all(fresh)
                db.flush()
            counts["created"] += len(fresh)
        except Exception as e:
            errors.append(f"Row {i}: {e}")
    db.commit()
    return {**counts, "unmatched_drones": unmatched_drones, "errors": errors[:20]}
