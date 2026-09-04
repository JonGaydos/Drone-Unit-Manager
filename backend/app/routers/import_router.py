"""Generic CSV / XLSX import with field mapping for mission, training, and
maintenance logs. Two endpoints:

  POST /api/import/preview?entity=...  -> headers + sample + suggested mapping
  POST /api/import/commit?entity=...   -> apply mapping, create records
"""
import json
import re
from typing import Annotated

from fastapi import APIRouter, HTTPException, UploadFile, File

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
        headers, rows = parse_file(content, file.filename or "")
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}") from e
    if not headers:
        raise HTTPException(400, "File has no header row")
    schema = SCHEMAS[entity]
    return {
        "entity": entity,
        "headers": [h for h in headers if h],
        "row_count": len(rows),
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
        _, rows = parse_file(content, file.filename or "")
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}") from e
    if entity == "missions":
        return _commit_missions(db, rows, mapping_dict, admin.id)
    if entity == "training":
        return _commit_training(db, rows, mapping_dict, admin.id)
    return _commit_maintenance(db, rows, mapping_dict, admin.id)


def _build_mission_from_row(row: dict, mapping: dict, user_id) -> tuple:
    """Build a MissionLog (not yet added to the session) and the row's
    members string. Returns (None, '') if the row should be skipped."""
    d = parse_date_value(_get(mapping, "date", row))
    if not d:
        return None, ""
    reason = (_get(mapping, "reason", row) or "").strip() or None
    location = (_get(mapping, "location", row) or "").strip() or None
    title = (_get(mapping, "title", row) or "").strip() or reason or location or f"Mission {d}"
    case_number = (_get(mapping, "case_number", row) or "").strip() or None
    notes = (_get(mapping, "notes", row) or "").strip() or None
    man_hours = parse_float_safe(_get(mapping, "man_hours", row)) or 0.0
    members_str = _get(mapping, "members", row) or ""
    return MissionLog(
        date=d,
        title=title[:300],
        reason=reason[:200] if reason else None,
        location=location[:500] if location else None,
        case_number=case_number[:100] if case_number else None,
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
    title = (_get(mapping, "title", row) or "").strip() or (info[:80] if info else f"Training {d}")
    training_type = (_get(mapping, "training_type", row) or "").strip() or "Practice"
    location = (_get(mapping, "location", row) or "").strip() or None
    instructor = (_get(mapping, "instructor", row) or "").strip() or None
    notes = (_get(mapping, "notes", row) or "").strip() or None
    man_hours = parse_float_safe(_get(mapping, "man_hours", row)) or 0.0
    members_str = _get(mapping, "members", row) or ""
    return TrainingLog(
        date=d,
        title=title[:300],
        training_type=training_type[:100],
        description=info or None,
        location=location[:500] if location else None,
        instructor=instructor[:200] if instructor else None,
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


def _commit_missions(db, rows, mapping, user_id):
    unknown_id = find_unknown_pilot(db)
    created = 0
    skipped = 0
    unmatched_names: dict[str, int] = {}
    errors: list[str] = []
    for i, row in enumerate(rows, start=2):
        try:
            mission, members_str = _build_mission_from_row(row, mapping, user_id)
            if mission is None:
                skipped += 1
                continue
            db.add(mission)
            db.flush()
            per_pilot = parse_float_safe(_get(mapping, "per_pilot_hours", row)) or 0.0
            _attach_pilots(db, MissionLogPilot, "mission_log_id", mission.id,
                           members_str, per_pilot, unknown_id, unmatched_names)
            created += 1
        except Exception as e:
            errors.append(f"Row {i}: {e}")
    db.commit()
    return {
        "created": created, "skipped": skipped,
        "unmatched_names": unmatched_names, "errors": errors[:20],
    }


def _commit_training(db, rows, mapping, user_id):
    unknown_id = find_unknown_pilot(db)
    created = 0
    skipped = 0
    unmatched_names: dict[str, int] = {}
    errors: list[str] = []
    for i, row in enumerate(rows, start=2):
        try:
            tr, members_str = _build_training_from_row(row, mapping, user_id)
            if tr is None:
                skipped += 1
                continue
            db.add(tr)
            db.flush()
            per_pilot = parse_float_safe(_get(mapping, "per_pilot_hours", row)) or 0.0
            _attach_pilots(db, TrainingLogPilot, "training_log_id", tr.id,
                           members_str, per_pilot, unknown_id, unmatched_names)
            created += 1
        except Exception as e:
            errors.append(f"Row {i}: {e}")
    db.commit()
    return {
        "created": created, "skipped": skipped,
        "unmatched_names": unmatched_names, "errors": errors[:20],
    }


def _commit_maintenance(db, rows, mapping, user_id):
    created = 0
    skipped = 0
    unmatched_drones: dict[str, int] = {}
    errors: list[str] = []
    for i, row in enumerate(rows, start=2):
        try:
            records = _maintenance_records_for_row(db, row, mapping, user_id, unmatched_drones)
            if records is None:
                skipped += 1
                continue
            for rec in records:
                db.add(rec)
                created += 1
        except Exception as e:
            errors.append(f"Row {i}: {e}")
    db.commit()
    return {
        "created": created, "skipped": skipped,
        "unmatched_drones": unmatched_drones, "errors": errors[:20],
    }
