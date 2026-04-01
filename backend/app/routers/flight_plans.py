from datetime import date, datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.flight_approval import FlightPlan
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.user import User
from app.constants import FLIGHT_PLAN_NOT_FOUND
from app.deps import DBSession, CurrentUser, PilotUser, SupervisorUser
from app.services.audit import log_action
from app.responses import responses

router = APIRouter(prefix="/api/flight-plans", tags=["flight-plans"])



class FlightPlanCreate(BaseModel):
    title: str
    date_planned: str  # ISO datetime string
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
    checklist_completed: bool = False
    notes: Optional[str] = None


class FlightPlanUpdate(BaseModel):
    title: Optional[str] = None
    date_planned: Optional[str] = None
    pilot_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    location: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    purpose: Optional[str] = None
    case_number: Optional[str] = None
    description: Optional[str] = None
    max_altitude_planned: Optional[float] = None
    estimated_duration_min: Optional[int] = None
    checklist_completed: Optional[bool] = None
    linked_flight_id: Optional[int] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class ApproveRequest(BaseModel):
    review_notes: Optional[str] = None


class DenyRequest(BaseModel):
    denial_reason: str
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


def _enrich(plan: FlightPlan, db: Session) -> FlightPlanOut:
    out = FlightPlanOut.model_validate(plan)
    if plan.pilot_id:
        pilot = db.query(Pilot).filter(Pilot.id == plan.pilot_id).first()
        if pilot:
            out.pilot_name = pilot.full_name
    if plan.vehicle_id:
        v = db.query(Vehicle).filter(Vehicle.id == plan.vehicle_id).first()
        if v:
            out.vehicle_name = f"{v.manufacturer} {v.model}" + (f" ({v.nickname})" if v.nickname else "")
    if plan.submitted_by_id:
        u = db.query(User).filter(User.id == plan.submitted_by_id).first()
        if u:
            out.submitted_by_name = u.display_name
    if plan.reviewed_by_id:
        u = db.query(User).filter(User.id == plan.reviewed_by_id).first()
        if u:
            out.reviewed_by_name = u.display_name
    return out



@router.get("/pending/count", responses=responses(401))
def pending_count(db: DBSession, user: CurrentUser):
    count = db.query(func.count(FlightPlan.id)).filter(FlightPlan.status == "pending").scalar() or 0
    return {"count": count}


@router.get("", response_model=list[FlightPlanOut])
def list_flight_plans(

    db: DBSession,

    user: CurrentUser,

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
    return [_enrich(p, db) for p in plans]


@router.get("/{plan_id}", response_model=FlightPlanOut, responses=responses(401, 404))
def get_flight_plan(plan_id: int, db: DBSession, user: CurrentUser):
    plan = db.query(FlightPlan).filter(FlightPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=FLIGHT_PLAN_NOT_FOUND)
    return _enrich(plan, db)


@router.post("", response_model=FlightPlanOut, responses=responses(401, 422))
def create_flight_plan(data: FlightPlanCreate, db: DBSession, user: PilotUser):
    # Validate altitude (FAA Part 107: max 400ft AGL)
    if data.max_altitude_planned is not None:
        if data.max_altitude_planned < 0:
            raise HTTPException(status_code=422, detail="Altitude cannot be negative")
        if data.max_altitude_planned > 400:
            raise HTTPException(status_code=422, detail="Altitude exceeds 400 ft AGL limit (FAA Part 107)")

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


@router.patch("/{plan_id}", response_model=FlightPlanOut, responses=responses(400, 401, 403, 404))
def update_flight_plan(plan_id: int, data: FlightPlanUpdate, db: DBSession, user: PilotUser):
    plan = db.query(FlightPlan).filter(FlightPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=FLIGHT_PLAN_NOT_FOUND)
    if user.role not in ("admin", "supervisor") and plan.submitted_by_id != user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own flight plans")
    if plan.status not in ("pending", "denied") and user.role != "admin":
        raise HTTPException(status_code=400, detail="Can only edit pending or denied plans")
    update_data = data.model_dump(exclude_unset=True)
    if "date_planned" in update_data and update_data["date_planned"] is not None:
        update_data["date_planned"] = _parse_datetime(update_data["date_planned"])
    for key, value in update_data.items():
        setattr(plan, key, value)
    log_action(db, user.id, user.display_name, "update", "flight_plan", plan.id, plan.title,
               details=f"Updated flight plan fields: {', '.join(update_data.keys())}")
    db.commit()
    db.refresh(plan)
    return _enrich(plan, db)


@router.post("/{plan_id}/approve", response_model=FlightPlanOut, responses=responses(400, 401, 404))
def approve_flight_plan(plan_id: int, data: ApproveRequest, db: DBSession, user: SupervisorUser):
    plan = db.query(FlightPlan).filter(FlightPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=FLIGHT_PLAN_NOT_FOUND)
    if plan.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending plans can be approved")
    plan.status = "approved"
    plan.reviewed_by_id = user.id
    plan.review_date = datetime.now(timezone.utc)
    plan.review_notes = data.review_notes
    log_action(db, user.id, user.display_name, "approve", "flight_plan", plan.id, plan.title,
               details=f"Approved flight plan: {plan.title}")
    db.commit()
    db.refresh(plan)
    return _enrich(plan, db)


@router.post("/{plan_id}/deny", response_model=FlightPlanOut, responses=responses(400, 401, 404))
def deny_flight_plan(plan_id: int, data: DenyRequest, db: DBSession, user: SupervisorUser):
    plan = db.query(FlightPlan).filter(FlightPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=FLIGHT_PLAN_NOT_FOUND)
    if plan.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending plans can be denied")
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
def cancel_flight_plan(plan_id: int, db: DBSession, user: PilotUser):
    plan = db.query(FlightPlan).filter(FlightPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=FLIGHT_PLAN_NOT_FOUND)
    if plan.submitted_by_id != user.id and user.role not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Only the submitter can cancel a flight plan")
    if plan.status not in ("pending", "approved"):
        raise HTTPException(status_code=400, detail="Can only cancel pending or approved plans")
    plan.status = "cancelled"
    log_action(db, user.id, user.display_name, "cancel", "flight_plan", plan.id, plan.title,
               details=f"Cancelled flight plan: {plan.title}")
    db.commit()
    db.refresh(plan)
    return _enrich(plan, db)


@router.delete("/{plan_id}", responses=responses(401, 404))
def delete_flight_plan(plan_id: int, db: DBSession, user: SupervisorUser):
    plan = db.query(FlightPlan).filter(FlightPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=FLIGHT_PLAN_NOT_FOUND)
    title = plan.title
    log_action(db, user.id, user.display_name, "delete", "flight_plan", plan_id, title,
               details=f"Deleted flight plan: {title}")
    db.delete(plan)
    db.commit()
    return {"ok": True}
