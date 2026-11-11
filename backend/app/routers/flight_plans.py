from datetime import date, datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.flight_approval import FlightPlan
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.user import User
from app.constants import FLIGHT_PLAN_NOT_FOUND
from app.deps import DBSession
from app.routers.auth import require_permission
from app.services import permissions as permissions_service
from app.services.audit import log_action
from app.responses import responses

router = APIRouter(prefix="/api/flight-plans", tags=["flight-plans"])

PLANS_EDIT = "flight_plans.edit"

ViewUser = Annotated[User, Depends(require_permission("flight_plans.view"))]
CreateUser = Annotated[User, Depends(require_permission("flight_plans.create"))]
EditUser = Annotated[User, Depends(require_permission(PLANS_EDIT))]
ApproveUser = Annotated[User, Depends(require_permission("flight_plans.approve"))]

PLAN_STATUSES = ("pending", "approved", "denied", "cancelled", "completed")

# Text limits follow the flight_plans columns.
PlanTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Location = Annotated[str, StringConstraints(max_length=500)]
Purpose = Annotated[str, StringConstraints(max_length=200)]
CaseNumber = Annotated[str, StringConstraints(max_length=100)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
DurationMin = Annotated[int, Field(ge=0)]


class FlightPlanCreate(BaseModel):
    title: PlanTitle
    date_planned: str  # ISO datetime string
    pilot_id: int
    vehicle_id: Optional[int] = None
    location: Optional[Location] = None
    lat: Optional[Latitude] = None
    lon: Optional[Longitude] = None
    purpose: Optional[Purpose] = None
    case_number: Optional[CaseNumber] = None
    description: Optional[str] = None
    max_altitude_planned: Optional[float] = None
    estimated_duration_min: Optional[DurationMin] = None
    checklist_completed: bool = False
    notes: Optional[str] = None


class FlightPlanUpdate(BaseModel):
    title: Optional[PlanTitle] = None
    date_planned: Optional[str] = None
    pilot_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    location: Optional[Location] = None
    lat: Optional[Latitude] = None
    lon: Optional[Longitude] = None
    purpose: Optional[Purpose] = None
    case_number: Optional[CaseNumber] = None
    description: Optional[str] = None
    max_altitude_planned: Optional[float] = None
    estimated_duration_min: Optional[DurationMin] = None
    checklist_completed: Optional[bool] = None
    linked_flight_id: Optional[int] = None
    notes: Optional[str] = None
    status: Optional[str] = None

    @field_validator("title", "date_planned", "pilot_id", "checklist_completed")
    @classmethod
    def _not_null(cls, v):
        # Optional only so a patch can leave them out; a sent null is refused.
        if v is None:
            raise ValueError("cannot be empty")
        return v


class ApproveRequest(BaseModel):
    review_notes: Optional[str] = None


class DenyRequest(BaseModel):
    denial_reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    review_notes: Optional[str] = None


class FlightPlanOut(BaseModel):
    id: int
    title: str
    date_planned: datetime
    pilot_id: int
    vehicle_id: Optional[int] = None
    location: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    purpose: Optional[str] = None
    case_number: Optional[str] = None
    description: Optional[str] = None
    max_altitude_planned: Optional[float] = None
    estimated_duration_min: Optional[int] = None
    checklist_completed: bool
    weather_briefing_id: Optional[int] = None
    status: str
    submitted_by_id: int
    reviewed_by_id: Optional[int] = None
    review_date: Optional[datetime] = None
    review_notes: Optional[str] = None
    denial_reason: Optional[str] = None
    linked_flight_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    pilot_name: Optional[str] = None
    vehicle_name: Optional[str] = None
    submitted_by_name: Optional[str] = None
    reviewed_by_name: Optional[str] = None

    model_config = {"from_attributes": True}


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid datetime format: {value}")


def _resolve(obj_id, cache, db: Session, model):
    """Resolve a row by id from a prebuilt cache (list endpoint) or a direct
    query (single-item callers). None when there is no id or no match."""
    if not obj_id:
        return None
    if cache is not None:
        return cache.get(obj_id)
    return db.query(model).filter(model.id == obj_id).first()


def _enrich(plan: FlightPlan, db: Session, pilot_cache=None, vehicle_cache=None, user_cache=None) -> FlightPlanOut:
    """Serialize a flight plan. For the list endpoint, pass prebuilt caches
    (id -> object) to avoid a pilot/vehicle/user query per row; single-item
    callers omit them and fall back to direct lookups."""
    out = FlightPlanOut.model_validate(plan)
    pilot = _resolve(plan.pilot_id, pilot_cache, db, Pilot)
    if pilot:
        out.pilot_name = pilot.full_name
    v = _resolve(plan.vehicle_id, vehicle_cache, db, Vehicle)
    if v:
        out.vehicle_name = f"{v.manufacturer} {v.model}" + (f" ({v.nickname})" if v.nickname else "")
    submitter = _resolve(plan.submitted_by_id, user_cache, db, User)
    if submitter:
        out.submitted_by_name = submitter.display_name
    reviewer = _resolve(plan.reviewed_by_id, user_cache, db, User)
    if reviewer:
        out.reviewed_by_name = reviewer.display_name
    return out



@router.get("/pending/count", responses=responses(401))
def pending_count(db: DBSession, user: ViewUser):
    count = db.query(func.count(FlightPlan.id)).filter(FlightPlan.status == "pending").scalar() or 0
    return {"count": count}


@router.get("", response_model=list[FlightPlanOut])
def list_flight_plans(

    db: DBSession,

    user: ViewUser,

    status: str | None = None,

    pilot_id: int | None = None,

    date_from: date | None = None,

    date_to: date | None = None,

    submitted_by_id: int | None = None,

    page: Annotated[int, Query(ge=1)] = 1,

    per_page: Annotated[int, Query(le=200)] = 50,
):
    q = db.query(FlightPlan)
    if status:
        q = q.filter(FlightPlan.status == status)
    if pilot_id:
        q = q.filter(FlightPlan.pilot_id == pilot_id)
    if submitted_by_id:
        q = q.filter(FlightPlan.submitted_by_id == submitted_by_id)
    if date_from:
        q = q.filter(func.date(FlightPlan.date_planned) >= date_from)
    if date_to:
        q = q.filter(func.date(FlightPlan.date_planned) <= date_to)
    plans = q.order_by(FlightPlan.date_planned.desc()).offset((page - 1) * per_page).limit(per_page).all()
    # Batch-load referenced pilots, vehicles and users once, then enrich from caches.
    pilot_ids = {p.pilot_id for p in plans if p.pilot_id}
    vehicle_ids = {p.vehicle_id for p in plans if p.vehicle_id}
    user_ids = {p.submitted_by_id for p in plans if p.submitted_by_id} | {
        p.reviewed_by_id for p in plans if p.reviewed_by_id
    }
    pilot_cache = {
        pil.id: pil for pil in db.query(Pilot).filter(Pilot.id.in_(pilot_ids)).all()
    } if pilot_ids else {}
    vehicle_cache = {
        v.id: v for v in db.query(Vehicle).filter(Vehicle.id.in_(vehicle_ids)).all()
    } if vehicle_ids else {}
    user_cache = {
        u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}
    return [_enrich(p, db, pilot_cache, vehicle_cache, user_cache) for p in plans]


@router.get("/{plan_id}", response_model=FlightPlanOut, responses=responses(401, 404))
def get_flight_plan(plan_id: int, db: DBSession, user: ViewUser):
    plan = db.query(FlightPlan).filter(FlightPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=FLIGHT_PLAN_NOT_FOUND)
    return _enrich(plan, db)


def _require_edit(db: Session, user: User, plan: FlightPlan) -> None:
    """Raise 403 unless the user's flight_plans.edit level covers this plan."""
    permissions_service.require_record_access(db, user, PLANS_EDIT, plan.submitted_by_id == user.id)


def _validate_altitude(value: Optional[float]) -> None:
    """Enforce the FAA Part 107 400 ft AGL ceiling on a planned altitude."""
    if value is None:
        return
    if value < 0:
        raise HTTPException(status_code=422, detail="Altitude cannot be negative")
    if value > 400:
        raise HTTPException(status_code=422, detail="Altitude exceeds 400 ft AGL limit (FAA Part 107)")


# What a reviewer's approval or denial covered. Changing any of these after the
# decision sends the plan back for review; bookkeeping (notes, the linked
# executed flight) does not.
REVIEWED_PLAN_FIELDS = frozenset({
    "title", "date_planned", "pilot_id", "vehicle_id", "location", "lat", "lon",
    "purpose", "case_number", "description", "max_altitude_planned",
    "estimated_duration_min", "checklist_completed",
})


def _changes_reviewed_content(plan: FlightPlan, update_data: dict) -> bool:
    """True when the update alters a field the reviewer's decision covered."""
    for key, new in update_data.items():
        if key not in REVIEWED_PLAN_FIELDS:
            continue
        if isinstance(new, datetime):
            new = new.replace(tzinfo=None)  # stored as the naive wall time sent
        if getattr(plan, key) != new:
            return True
    return False


def _clear_review(plan: FlightPlan) -> None:
    """Back to pending: the earlier decision, and its reason, no longer apply."""
    plan.status = "pending"
    plan.reviewed_by_id = None
    plan.review_date = None
    plan.review_notes = None
    plan.denial_reason = None


def _apply_status_change(plan: FlightPlan, update_data: dict, user) -> None:
    """Handle ``status`` on a plan edit. Approval only ever happens through the
    /approve endpoint, which needs flight_plans.approve, so the one status an edit may set is
    ``pending``, and only an admin may set it (to reopen a reviewed plan)."""
    requested = update_data.pop("status", None)
    if requested is None:
        return
    if requested not in PLAN_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of: {', '.join(PLAN_STATUSES)}")
    if user.role != "admin" or requested != "pending":
        raise HTTPException(status_code=403, detail="Only an admin can reopen a plan, and only as pending")
    _clear_review(plan)


@router.post("", response_model=FlightPlanOut, responses=responses(401, 422))
def create_flight_plan(data: FlightPlanCreate, db: DBSession, user: CreateUser):
    _validate_altitude(data.max_altitude_planned)

    plan = FlightPlan(
        title=data.title,
        date_planned=_parse_datetime(data.date_planned),
        pilot_id=data.pilot_id,
        vehicle_id=data.vehicle_id,
        location=data.location,
        lat=data.lat,
        lon=data.lon,
        purpose=data.purpose,
        case_number=data.case_number,
        description=data.description,
        max_altitude_planned=data.max_altitude_planned,
        estimated_duration_min=data.estimated_duration_min,
        checklist_completed=data.checklist_completed,
        notes=data.notes,
        submitted_by_id=user.id,
    )
    db.add(plan)
    db.flush()
    log_action(db, user.id, user.display_name, "create", "flight_plan", plan.id, plan.title,
               details=f"Submitted flight plan: {plan.title}")
    db.commit()
    db.refresh(plan)
    return _enrich(plan, db)


@router.patch("/{plan_id}", response_model=FlightPlanOut, responses=responses(400, 401, 403, 404, 422))
def update_flight_plan(plan_id: int, data: FlightPlanUpdate, db: DBSession, user: EditUser):
    plan = db.query(FlightPlan).filter(FlightPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=FLIGHT_PLAN_NOT_FOUND)
    _require_edit(db, user, plan)
    if plan.status not in ("pending", "denied") and user.role != "admin":
        raise HTTPException(status_code=400, detail="Can only edit pending or denied plans")
    update_data = data.model_dump(exclude_unset=True)
    _apply_status_change(plan, update_data, user)
    _validate_altitude(update_data.get("max_altitude_planned"))
    if "date_planned" in update_data and update_data["date_planned"] is not None:
        update_data["date_planned"] = _parse_datetime(update_data["date_planned"])
    # A decision covered the plan as it was reviewed, so changing what was
    # reviewed sends it back; an approved plan cannot be edited into a
    # different one after the fact.
    reopen = plan.status in ("approved", "denied") and _changes_reviewed_content(plan, update_data)
    for key, value in update_data.items():
        setattr(plan, key, value)
    if reopen:
        _clear_review(plan)
    suffix = "; returned to pending review" if reopen else ""
    log_action(db, user.id, user.display_name, "update", "flight_plan", plan.id, plan.title,
               details=f"Updated flight plan fields: {', '.join(update_data.keys()) or 'status'}{suffix}")
    db.commit()
    db.refresh(plan)
    return _enrich(plan, db)


@router.post("/{plan_id}/approve", response_model=FlightPlanOut, responses=responses(400, 401, 404))
def approve_flight_plan(plan_id: int, data: ApproveRequest, db: DBSession, user: ApproveUser):
    plan = db.query(FlightPlan).filter(FlightPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=FLIGHT_PLAN_NOT_FOUND)
    if plan.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending plans can be approved")
    if plan.submitted_by_id == user.id:
        raise HTTPException(status_code=403, detail="You cannot approve a flight plan you submitted")
    plan.status = "approved"
    plan.reviewed_by_id = user.id
    plan.review_date = datetime.now(timezone.utc)
    plan.review_notes = data.review_notes
    log_action(db, user.id, user.display_name, "approve", "flight_plan", plan.id, plan.title,
               details=f"Approved flight plan: {plan.title}")
    db.commit()
    db.refresh(plan)
    return _enrich(plan, db)


@router.post("/{plan_id}/deny", response_model=FlightPlanOut, responses=responses(400, 401, 403, 404, 422))
def deny_flight_plan(plan_id: int, data: DenyRequest, db: DBSession, user: ApproveUser):
    plan = db.query(FlightPlan).filter(FlightPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=FLIGHT_PLAN_NOT_FOUND)
    if plan.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending plans can be denied")
    if plan.submitted_by_id == user.id:
        raise HTTPException(status_code=403, detail="You cannot deny a flight plan you submitted")
    plan.status = "denied"
    plan.reviewed_by_id = user.id
    plan.review_date = datetime.now(timezone.utc)
    plan.denial_reason = data.denial_reason
    plan.review_notes = data.review_notes
    log_action(db, user.id, user.display_name, "deny", "flight_plan", plan.id, plan.title,
               details=f"Denied flight plan: {plan.title} — reason: {data.denial_reason}")
    db.commit()
    db.refresh(plan)
    return _enrich(plan, db)


@router.post("/{plan_id}/cancel", response_model=FlightPlanOut, responses=responses(400, 401, 403, 404))
def cancel_flight_plan(plan_id: int, db: DBSession, user: EditUser):
    plan = db.query(FlightPlan).filter(FlightPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=FLIGHT_PLAN_NOT_FOUND)
    _require_edit(db, user, plan)
    if plan.status not in ("pending", "approved"):
        raise HTTPException(status_code=400, detail="Can only cancel pending or approved plans")
    plan.status = "cancelled"
    log_action(db, user.id, user.display_name, "cancel", "flight_plan", plan.id, plan.title,
               details=f"Cancelled flight plan: {plan.title}")
    db.commit()
    db.refresh(plan)
    return _enrich(plan, db)


@router.delete("/{plan_id}", responses=responses(401, 404))
def delete_flight_plan(plan_id: int, db: DBSession, user: ApproveUser):
    plan = db.query(FlightPlan).filter(FlightPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=FLIGHT_PLAN_NOT_FOUND)
    title = plan.title
    log_action(db, user.id, user.display_name, "delete", "flight_plan", plan_id, title,
               details=f"Deleted flight plan: {title}")
    db.delete(plan)
    db.commit()
    return {"ok": True}
