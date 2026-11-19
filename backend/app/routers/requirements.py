"""Flight requirements: definitions, each pilot's progress, excusals, templates and settings.

Read routes that show results save the periods whose grace time has ended
first, so a page never shows a period as pending once it should be saved.
"""

import logging
from datetime import date, datetime, timedelta
from operator import attrgetter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import DBSession
from app.models.flight_requirement import (
    FlightRequirement, FlightRequirementModel, FlightRequirementPilot, FlightRequirementPurpose,
    FlightRequirementResult, FlightRequirementTemplate,
)
from app.models.pilot import Pilot
from app.models.setting import Setting
from app.models.user import User
from app.responses import responses
from app.routers.auth import require_permission
from app.schemas.requirement import (
    ExcuseIn, FlagOut, PilotRequirementsOut, RecalculateIn, RecalculateOut, RequirementDefinition,
    RequirementIn, RequirementOut, RequirementSettings, RequirementUpdate, StatusOut, TemplateIn,
    TemplateOut, TemplateUpdate,
)
from app.services.fleet_models import fleet_models
from app.services.local_time import local_today
from app.services.requirement_eval import (
    EXCUSED, MET, MISSED, PilotProgress, UnitEvalSettings, assigned_pilots, evaluate_period,
    unit_eval_settings,
)
from app.services.requirement_notify import notify_assigned
from app.services.requirement_periods import Period, period_containing
from app.services.requirement_results import (
    OFF_REASON, close_due_periods, open_misses, pending_periods, recalculate_period, requirements_score,
    saved_through,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/requirements", tags=["requirements"])

ViewUser = Annotated[User, Depends(require_permission("requirements.view"))]
ManageUser = Annotated[User, Depends(require_permission("requirements.manage"))]
ExcuseUser = Annotated[User, Depends(require_permission("requirements.excuse"))]

NIGHT_REFUSED = "Set the unit default location in Settings before using night"
NOT_FOUND = "Requirement not found"
TEMPLATE_NOT_FOUND = "Template not found"
LIST_FIELDS = ("models", "purposes", "pilot_ids")
SCALAR_FIELDS = tuple(name for name in RequirementIn.model_fields if name not in LIST_FIELDS)
DERIVED_FIELDS = (*LIST_FIELDS, "current_period")
GRACE_KEY = "requirements_grace_days"
FISCAL_KEY = "fiscal_year_start_month"


def _close_safely(db: Session, today: date) -> None:
    """Save due periods. When the scheduler saves the same period at the same
    moment, the unique index refuses the second writer; its rows are already
    saved, so roll back and carry on."""
    try:
        close_due_periods(db, today)
    except IntegrityError:
        db.rollback()


def _notify_safely(db: Session, req: FlightRequirement, pilot_ids: list[int]) -> None:
    """Email newly assigned pilots. A failure is logged, never raised: the edit is already saved."""
    try:
        notify_assigned(db, req, pilot_ids)
    except Exception:
        logger.exception("Assignment emails for requirement %s failed", req.id)
        db.rollback()


def _assigned_ids(db: Session, req: FlightRequirement) -> list[int]:
    """Ids of the pilots ``req`` applies to now; none while it is off."""
    return [pilot.id for pilot in assigned_pilots(db, req)] if req.is_active else []


def _get_requirement(db: Session, requirement_id: int) -> FlightRequirement:
    req = db.get(FlightRequirement, requirement_id)
    if req is None:
        raise HTTPException(404, NOT_FOUND)
    return req


def _current(req: FlightRequirement, fiscal_start_month: int, today: date) -> Period | None:
    return period_containing(req.to_period_spec(fiscal_start_month), today)


def _period_out(period: Period | None, today: date) -> dict | None:
    if period is None:
        return None
    return {"start": period[0], "end": period[1], "days_left": max((period[1] - today).days + 1, 0)}


def _ordered(rows, field: str) -> list:
    return [getattr(row, field) for row in sorted(rows, key=attrgetter("id"))]


def _out(req: FlightRequirement, fiscal_start_month: int, today: date) -> dict:
    data = {name: getattr(req, name) for name in RequirementOut.model_fields if name not in DERIVED_FIELDS}
    data.update(
        models=_ordered(req.models, "model"),
        purposes=_ordered(req.purposes, "purpose"),
        pilot_ids=_ordered(req.pilots, "pilot_id"),
        current_period=_period_out(_current(req, fiscal_start_month, today), today),
    )
    return data


def _check_night(db: Session, data: RequirementDefinition) -> None:
    settings = unit_eval_settings(db)
    if data.time_mode == "night" and (settings.lat is None or settings.lon is None):
        raise HTTPException(422, NIGHT_REFUSED)


def _check_pilots(db: Session, pilot_ids: list[int]) -> None:
    found = {pilot_id for (pilot_id,) in db.query(Pilot.id).filter(Pilot.id.in_(pilot_ids))}
    missing = [pilot_id for pilot_id in pilot_ids if pilot_id not in found]
    if missing:
        raise HTTPException(422, f"Unknown pilot: {', '.join(map(str, missing))}")


def _edited(req: FlightRequirement, data: RequirementUpdate) -> RequirementIn:
    """The requirement as it would be after the edit, validated whole."""
    current = {name: getattr(req, name) for name in SCALAR_FIELDS}
    current.update(models=_ordered(req.models, "model"), purposes=_ordered(req.purposes, "purpose"),
                   pilot_ids=_ordered(req.pilots, "pilot_id"))
    try:
        return RequirementIn.model_validate({**current, **data.model_dump(exclude_unset=True)})
    except ValidationError as e:
        raise RequestValidationError([
            {**error, "loc": ("body", *error["loc"])}
            for error in e.errors(include_url=False, include_context=False, include_input=False)
        ]) from e


def _replace_names(db: Session, req: FlightRequirement, attr: str, row_class, field: str,
                   names: list[str]) -> None:
    """Swap a name list's rows when the list changed. The deletes flush first:
    the unique index would refuse a new row repeating a name still pending removal."""
    if _ordered(getattr(req, attr), field) == names:
        return
    setattr(req, attr, [])
    db.flush()
    setattr(req, attr, [row_class(**{field: name}) for name in names])


def _new_pilot_row(pilot_id: int, covered: set[int], since: datetime) -> FlightRequirementPilot:
    if pilot_id in covered:
        return FlightRequirementPilot(pilot_id=pilot_id, added_at=since)
    return FlightRequirementPilot(pilot_id=pilot_id)


def _sync_pilots(db: Session, req: FlightRequirement, pilot_ids: list[int]) -> None:
    """Keep the rows of pilots who stay, so their assignment time still decides
    automatic excusals, and add rows for the new ones. Narrowing from all
    active pilots to a selection keeps the selected pilots covered from the
    requirement's creation, so they are not excused as newly added."""
    covered = {pilot.id for pilot in assigned_pilots(db, req)} if not req.pilots else set()
    kept = [row for row in req.pilots if row.pilot_id in pilot_ids]
    known = {row.pilot_id for row in kept}
    req.pilots = kept + [_new_pilot_row(pid, covered, req.created_at) for pid in pilot_ids if pid not in known]


def _apply(db: Session, req: FlightRequirement, data: RequirementIn) -> None:
    _sync_pilots(db, req, data.pilot_ids)
    # Set on the object, never by query, so is_active changes stamp active_changed_at.
    for name in SCALAR_FIELDS:
        setattr(req, name, getattr(data, name))
    _replace_names(db, req, "models", FlightRequirementModel, "model", data.models)
    _replace_names(db, req, "purposes", FlightRequirementPurpose, "purpose", data.purposes)


# Definitions


@router.get("", response_model=list[RequirementOut], responses=responses(401, 403))
def list_requirements(db: DBSession, user: ViewUser):
    today = local_today(db)
    fiscal = unit_eval_settings(db).fiscal_start_month
    reqs = db.query(FlightRequirement).order_by(FlightRequirement.name, FlightRequirement.id).all()
    return [_out(req, fiscal, today) for req in reqs]


@router.post("", status_code=201, response_model=RequirementOut, responses=responses(401, 403))
def create_requirement(data: RequirementIn, db: DBSession, user: ManageUser):
    _check_night(db, data)
    _check_pilots(db, data.pilot_ids)
    req = FlightRequirement(
        **data.model_dump(include=set(SCALAR_FIELDS)),
        models=[FlightRequirementModel(model=name) for name in data.models],
        purposes=[FlightRequirementPurpose(purpose=name) for name in data.purposes],
        pilots=[FlightRequirementPilot(pilot_id=pid) for pid in data.pilot_ids],
        created_by_id=user.id, modified_by_id=user.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    _notify_safely(db, req, _assigned_ids(db, req))
    return _out(req, unit_eval_settings(db).fiscal_start_month, local_today(db))


@router.patch("/{requirement_id}", response_model=RequirementOut, responses=responses(401, 403, 404))
def update_requirement(requirement_id: int, data: RequirementUpdate, db: DBSession, user: ManageUser):
    """Edit a requirement. Switching it on or off first saves the periods due
    under the old state, and switching it on saves again under the new one."""
    req = _get_requirement(db, requirement_id)
    edited = _edited(req, data)
    if "time_mode" in data.model_fields_set:
        _check_night(db, edited)
    _check_pilots(db, edited.pilot_ids)
    today = local_today(db)
    switching = edited.is_active != req.is_active
    if switching:
        _close_safely(db, today)
    before = set(_assigned_ids(db, req))
    _apply(db, req, edited)
    req.modified_by_id = user.id
    db.commit()
    if switching and edited.is_active:
        _close_safely(db, today)
    db.refresh(req)
    _notify_safely(db, req, [pilot_id for pilot_id in _assigned_ids(db, req) if pilot_id not in before])
    return _out(req, unit_eval_settings(db).fiscal_start_month, today)


@router.delete("/{requirement_id}", responses=responses(401, 403, 404, 409))
def delete_requirement(requirement_id: int, db: DBSession, user: ManageUser):
    """Delete a requirement with no saved results; one with history is switched off instead."""
    req = _get_requirement(db, requirement_id)
    if saved_through(db, req.id) is not None:
        raise HTTPException(409, "This requirement has saved results. Switch it off instead.")
    db.delete(req)
    db.commit()
    return {"ok": True}


# Progress and history


def _pilot_names(db: Session) -> dict[int, str]:
    return {pilot.id: pilot.full_name for pilot in db.query(Pilot)}


def _progress_out(progress: PilotProgress, name: str) -> dict:
    return {**vars(progress), "pilot_name": name}


def _active_requirements(db: Session) -> list[FlightRequirement]:
    return (db.query(FlightRequirement).filter(FlightRequirement.is_active.is_(True))
            .order_by(FlightRequirement.name, FlightRequirement.id).all())


def _period_block(period: Period, settings: UnitEvalSettings, today: date) -> dict:
    return {**_period_out(period, today), "review_until": period[1] + timedelta(days=settings.grace_days)}


def _period_progress(db: Session, req: FlightRequirement, period: Period, settings: UnitEvalSettings,
                     today: date, names: dict[int, str]) -> dict:
    progress = evaluate_period(db, req, period, today, settings.grace_days)
    return {**_period_block(period, settings, today),
            "pilots": [_progress_out(p, names.get(p.pilot_id, "")) for p in progress.values()]}


def _requirement_status(db: Session, req: FlightRequirement, settings: UnitEvalSettings, today: date,
                        names: dict[int, str]) -> dict:
    current = _current(req, settings.fiscal_start_month, today)
    return {
        "requirement_id": req.id, "name": req.name, "target_minutes": req.target_minutes,
        "target_flights": req.target_flights, "model_mode": req.model_mode,
        "current_period": _period_progress(db, req, current, settings, today, names) if current else None,
        "pending_periods": [_period_progress(db, req, period, settings, today, names)
                            for period in pending_periods(db, req, settings, today)],
    }


@router.get("/status", response_model=StatusOut, responses=responses(401, 403))
def requirements_status(db: DBSession, user: ViewUser):
    """The current period of each active requirement, and the periods still in
    their grace time, with every assigned pilot's progress; and the Requirements score."""
    today = local_today(db)
    _close_safely(db, today)
    settings = unit_eval_settings(db)
    names = _pilot_names(db)
    return {
        "score": requirements_score(db, today),
        "requirements": [_requirement_status(db, req, settings, today, names) for req in _active_requirements(db)],
    }


def _pilot_period(db: Session, req: FlightRequirement, pilot: Pilot, period: Period,
                  settings: UnitEvalSettings, today: date) -> dict | None:
    progress = evaluate_period(db, req, period, today, settings.grace_days).get(pilot.id)
    if progress is None:
        return None
    return {**_progress_out(progress, pilot.full_name), "requirement_id": req.id, "name": req.name,
            "period": _period_block(period, settings, today)}


def _pilot_progress(db: Session, pilot: Pilot, settings: UnitEvalSettings, today: date) -> tuple[list, list]:
    """The pilot's progress in each active requirement's current period, and in
    its periods still in grace time, oldest first."""
    current, pending = [], []
    for req in _active_requirements(db):
        period = _current(req, settings.fiscal_start_month, today)
        if period is not None:
            current.append(_pilot_period(db, req, pilot, period, settings, today))
        pending.extend(_pilot_period(db, req, pilot, p, settings, today)
                       for p in pending_periods(db, req, settings, today))
    pending = [row for row in pending if row is not None]
    pending.sort(key=lambda row: (row["period"]["start"], row["name"]))
    return [row for row in current if row is not None], pending


def _pilot_history(db: Session, pilot_id: int) -> list[dict]:
    rows = (
        db.query(FlightRequirementResult, FlightRequirement.name)
        .join(FlightRequirement, FlightRequirement.id == FlightRequirementResult.requirement_id)
        .filter(FlightRequirementResult.pilot_id == pilot_id, FlightRequirementResult.saved_at.isnot(None))
        .order_by(FlightRequirementResult.period_end.desc(), FlightRequirementResult.period_start.desc(),
                  FlightRequirement.name)
        .all()
    )
    return [{**{key: getattr(row, key) for key in (
        "requirement_id", "period_start", "period_end", "status", "totals", "target_snapshot",
        "excused", "excused_by_id", "excused_reason", "saved_at")}, "result_id": row.id, "name": name}
        for row, name in rows]


@router.get("/pilots/{pilot_id}", response_model=PilotRequirementsOut, responses=responses(401, 403, 404))
def pilot_requirements(pilot_id: int, db: DBSession, user: ViewUser):
    """One pilot's progress in each active requirement's current period and in
    periods still in grace time, and their saved results, newest first."""
    today = local_today(db)
    _close_safely(db, today)
    pilot = db.get(Pilot, pilot_id)
    if pilot is None:
        raise HTTPException(404, "Pilot not found")
    current, pending = _pilot_progress(db, pilot, unit_eval_settings(db), today)
    return {"pilot_id": pilot.id, "current": current, "pending": pending, "history": _pilot_history(db, pilot.id)}


@router.get("/flags", response_model=dict[int, list[FlagOut]], responses=responses(401, 403))
def requirement_flags(db: DBSession, user: ViewUser):
    """Per pilot, the saved misses still flagged."""
    _close_safely(db, local_today(db))
    return open_misses(db)


# Excusals and recalculation


def _reached(totals: dict | None, snapshot: dict | None) -> bool:
    """Whether saved totals meet the saved target on every model."""
    snapshot = snapshot or {}
    minutes, flights = snapshot.get("target_minutes"), snapshot.get("target_flights")
    return bool(totals) and all(
        (minutes is None or total["minutes"] >= minutes) and (flights is None or total["flights"] >= flights)
        for total in totals.values())


def _saved_status(row: FlightRequirementResult) -> str:
    if row.status == MET and row.excused:
        return MET
    if row.excused:
        return EXCUSED
    return MET if _reached(row.totals, row.target_snapshot) else MISSED


def _excuse_saved(row: FlightRequirementResult, data: ExcuseIn, user: User) -> None:
    """Excuse or un-excuse a saved result. A month the requirement was off stays excused."""
    if row.excused and row.excused_by_id is None and row.excused_reason == OFF_REASON:
        raise HTTPException(422, "This period was excused because the requirement was switched off")
    row.excused = data.excused
    row.excused_by_id = user.id
    row.excused_reason = data.reason if data.excused else None
    row.status = _saved_status(row)


def _excuse_open(db: Session, req: FlightRequirement, data: ExcuseIn, user: User) -> None:
    """Store an excusal for a period not saved yet; saving the period fills it in."""
    watermark = saved_through(db, req.id)
    if watermark is not None and data.period_start <= watermark:
        raise HTTPException(422, "That period is closed and has no saved result for this pilot")
    period = _current(req, unit_eval_settings(db).fiscal_start_month, data.period_start)
    if period is None or period[0] != data.period_start:
        raise HTTPException(422, "That date does not start a period of this requirement")
    if data.pilot_id not in {pilot.id for pilot in assigned_pilots(db, req)}:
        raise HTTPException(422, "That pilot is not assigned to this requirement")
    row = db.query(FlightRequirementResult).filter_by(
        requirement_id=req.id, pilot_id=data.pilot_id, period_start=data.period_start).first()
    if row is None:
        row = FlightRequirementResult(requirement_id=req.id, pilot_id=data.pilot_id,
                                      period_start=data.period_start)
        db.add(row)
    row.period_end = period[1]
    row.excused = data.excused
    row.excused_by_id = user.id
    row.excused_reason = data.reason if data.excused else None


@router.post("/{requirement_id}/excuse", responses=responses(401, 403, 404))
def excuse_pilot(requirement_id: int, data: ExcuseIn, db: DBSession, user: ExcuseUser):
    """Excuse or un-excuse a pilot for one period, open or saved."""
    req = _get_requirement(db, requirement_id)
    if db.get(Pilot, data.pilot_id) is None:
        raise HTTPException(404, "Pilot not found")
    saved = db.query(FlightRequirementResult).filter(
        FlightRequirementResult.requirement_id == req.id, FlightRequirementResult.pilot_id == data.pilot_id,
        FlightRequirementResult.period_start == data.period_start, FlightRequirementResult.saved_at.isnot(None),
    ).first()
    if saved is not None:
        _excuse_saved(saved, data, user)
    else:
        _excuse_open(db, req, data, user)
    db.commit()
    return {"ok": True}


@router.post("/{requirement_id}/recalculate", response_model=RecalculateOut, responses=responses(401, 403, 404))
def recalculate(requirement_id: int, data: RecalculateIn, db: DBSession, user: ManageUser):
    """Re-evaluate one saved period against today's flights. Admins only."""
    if user.role != "admin":
        raise HTTPException(403, "Only an admin can recalculate a saved period")
    req = _get_requirement(db, requirement_id)
    has_rows = db.query(FlightRequirementResult.id).filter(
        FlightRequirementResult.requirement_id == req.id,
        FlightRequirementResult.period_start == data.period_start,
        FlightRequirementResult.saved_at.isnot(None),
    ).first()
    if has_rows is None:
        raise HTTPException(404, "No saved results for that period")
    return {"recalculated": recalculate_period(db, req, data.period_start, user)}


# Fleet models and settings


@router.get("/models", responses=responses(401, 403))
def requirement_models(db: DBSession, user: ManageUser):
    return fleet_models(db)


@router.get("/settings", response_model=RequirementSettings, responses=responses(401, 403))
def get_requirement_settings(db: DBSession, user: ViewUser):
    settings = unit_eval_settings(db)
    return {"grace_days": settings.grace_days, "fiscal_year_start_month": settings.fiscal_start_month}


@router.put("/settings", response_model=RequirementSettings, responses=responses(401, 403))
def put_requirement_settings(data: RequirementSettings, db: DBSession, user: ManageUser):
    """Save the settings, after saving the periods due under the old ones."""
    _close_safely(db, local_today(db))
    for key, value in ((GRACE_KEY, data.grace_days), (FISCAL_KEY, data.fiscal_year_start_month)):
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=str(value)))
        else:
            row.value = str(value)
    db.commit()
    return data


# Templates


def _get_template(db: Session, template_id: int) -> FlightRequirementTemplate:
    template = db.get(FlightRequirementTemplate, template_id)
    if template is None:
        raise HTTPException(404, TEMPLATE_NOT_FOUND)
    return template


def _check_template_name(db: Session, name: str, template_id: int | None = None) -> None:
    clash = db.query(FlightRequirementTemplate.id).filter(
        FlightRequirementTemplate.name == name, FlightRequirementTemplate.id != template_id).first()
    if clash is not None:
        raise HTTPException(409, "A template with that name already exists")


@router.get("/templates", response_model=list[TemplateOut], responses=responses(401, 403))
def list_templates(db: DBSession, user: ManageUser):
    return db.query(FlightRequirementTemplate).order_by(FlightRequirementTemplate.name).all()


@router.post("/templates", status_code=201, response_model=TemplateOut, responses=responses(401, 403, 409))
def create_template(data: TemplateIn, db: DBSession, user: ManageUser):
    _check_template_name(db, data.name)
    _check_night(db, data.settings)
    template = FlightRequirementTemplate(name=data.name, settings=data.settings.model_dump(mode="json"),
                                         created_by_id=user.id, modified_by_id=user.id)
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.patch("/templates/{template_id}", response_model=TemplateOut, responses=responses(401, 403, 404, 409))
def update_template(template_id: int, data: TemplateUpdate, db: DBSession, user: ManageUser):
    template = _get_template(db, template_id)
    if data.name is not None:
        _check_template_name(db, data.name, template.id)
        template.name = data.name
    if data.settings is not None:
        _check_night(db, data.settings)
        template.settings = data.settings.model_dump(mode="json")
    template.modified_by_id = user.id
    db.commit()
    db.refresh(template)
    return template


@router.delete("/templates/{template_id}", responses=responses(401, 403, 404))
def delete_template(template_id: int, db: DBSession, user: ManageUser):
    db.delete(_get_template(db, template_id))
    db.commit()
    return {"ok": True}
