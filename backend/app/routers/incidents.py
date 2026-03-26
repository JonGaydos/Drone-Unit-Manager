from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.incident import Incident
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.user import User
from app.routers.auth import get_current_user, require_pilot, require_supervisor
from app.services.audit import log_action

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


# --- Schemas ---

class IncidentCreate(BaseModel):
    date: str
    title: str
    severity: str
    category: str
    description: str
    location: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    flight_id: Optional[int] = None
    pilot_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    equipment_grounded: bool = False
    damage_description: Optional[str] = None
    estimated_cost: Optional[float] = None
    notes: Optional[str] = None
    report_type: str = "incident"
    impact_level: Optional[str] = None
    outcome_description: Optional[str] = None


class IncidentUpdate(BaseModel):
    date: Optional[str] = None
    title: Optional[str] = None
    severity: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    flight_id: Optional[int] = None
    pilot_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    status: Optional[str] = None
    resolution: Optional[str] = None
    resolution_date: Optional[str] = None
    equipment_grounded: Optional[bool] = None
    damage_description: Optional[str] = None
    corrective_actions: Optional[str] = None
    estimated_cost: Optional[float] = None
    notes: Optional[str] = None
    report_type: Optional[str] = None
    impact_level: Optional[str] = None
    outcome_description: Optional[str] = None


class IncidentOut(BaseModel):
    id: int
    date: date
    title: str
    severity: str
    category: str
    description: str
    location: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    flight_id: Optional[int]
    pilot_id: Optional[int]
    vehicle_id: Optional[int]
    reported_by_id: Optional[int]
    status: str
    resolution: Optional[str]
    resolution_date: Optional[date]
    equipment_grounded: bool
    damage_description: Optional[str]
    corrective_actions: Optional[str]
    estimated_cost: Optional[float]
    notes: Optional[str]
    report_type: Optional[str] = "incident"
    impact_level: Optional[str] = None
    outcome_description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    pilot_name: Optional[str] = None
    vehicle_name: Optional[str] = None
    reported_by_name: Optional[str] = None

    model_config = {"from_attributes": True}


def _enrich(incident: Incident, db: Session) -> IncidentOut:
    out = IncidentOut.model_validate(incident)
    if incident.pilot_id:
        pilot = db.query(Pilot).filter(Pilot.id == incident.pilot_id).first()
        if pilot:
            out.pilot_name = pilot.full_name
    if incident.vehicle_id:
        v = db.query(Vehicle).filter(Vehicle.id == incident.vehicle_id).first()
        if v:
            out.vehicle_name = f"{v.manufacturer} {v.model}" + (f" ({v.nickname})" if v.nickname else "")
    if incident.reported_by_id:
        u = db.query(User).filter(User.id == incident.reported_by_id).first()
        if u:
            out.reported_by_name = u.display_name
    return out


# --- Routes ---

@router.get("/stats")
def incident_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    status_counts = dict(
        db.query(Incident.status, func.count(Incident.id))
        .group_by(Incident.status).all()
    )
    severity_counts = dict(
        db.query(Incident.severity, func.count(Incident.id))
        .group_by(Incident.severity).all()
    )
    category_counts = dict(
        db.query(Incident.category, func.count(Incident.id))
        .group_by(Incident.category).all()
    )
    return {
        "by_status": status_counts,
        "by_severity": severity_counts,
        "by_category": category_counts,
        "total": db.query(func.count(Incident.id)).scalar() or 0,
    }


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    status: str | None = None,
    severity: str | None = None,
    category: str | None = None,
    pilot_id: int | None = None,
    vehicle_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    report_type: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Incident)
    if status:
        q = q.filter(Incident.status == status)
    if severity:
        q = q.filter(Incident.severity == severity)
    if category:
        q = q.filter(Incident.category == category)
    if report_type:
        q = q.filter(Incident.report_type == report_type)
    if pilot_id:
        q = q.filter(Incident.pilot_id == pilot_id)
    if vehicle_id:
        q = q.filter(Incident.vehicle_id == vehicle_id)
    if date_from:
        q = q.filter(Incident.date >= date_from)
    if date_to:
        q = q.filter(Incident.date <= date_to)
    incidents = q.order_by(Incident.date.desc(), Incident.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return [_enrich(i, db) for i in incidents]


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _enrich(incident, db)


@router.post("", response_model=IncidentOut)
def create_incident(data: IncidentCreate, db: Session = Depends(get_db), user: User = Depends(require_pilot)):
    try:
        parsed_date = date.fromisoformat(data.date)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid date format: {data.date}")
    incident = Incident(
        date=parsed_date,
        title=data.title,
        severity=data.severity,
        category=data.category,
        description=data.description,
        location=data.location,
        lat=data.lat,
        lon=data.lon,
        flight_id=data.flight_id,
        pilot_id=data.pilot_id,
        vehicle_id=data.vehicle_id,
        reported_by_id=user.id,
        equipment_grounded=data.equipment_grounded,
        damage_description=data.damage_description,
        estimated_cost=data.estimated_cost,
        notes=data.notes,
        report_type=data.report_type,
        impact_level=data.impact_level,
        outcome_description=data.outcome_description,
    )
    db.add(incident)
    db.flush()
    log_action(db, user.id, user.display_name, "create", "incident", incident.id, incident.title,
               details=f"Reported incident: {incident.title} (severity={incident.severity})")
    db.commit()
    db.refresh(incident)
    return _enrich(incident, db)


@router.patch("/{incident_id}", response_model=IncidentOut)
def update_incident(incident_id: int, data: IncidentUpdate, db: Session = Depends(get_db), user: User = Depends(require_pilot)):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    # Pilots can only update their own reports; supervisors can update any
    if user.role not in ("admin", "supervisor") and incident.reported_by_id != user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own incident reports")
    update_data = data.model_dump(exclude_unset=True)
    if "date" in update_data and update_data["date"] is not None:
        try:
            update_data["date"] = date.fromisoformat(update_data["date"])
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid date format: {update_data['date']}")
    if "resolution_date" in update_data and update_data["resolution_date"] is not None:
        try:
            update_data["resolution_date"] = date.fromisoformat(update_data["resolution_date"])
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid resolution_date format: {update_data['resolution_date']}")
    for key, value in update_data.items():
        setattr(incident, key, value)
    log_action(db, user.id, user.display_name, "update", "incident", incident.id, incident.title,
               details=f"Updated incident fields: {', '.join(update_data.keys())}")
    db.commit()
    db.refresh(incident)
    return _enrich(incident, db)


@router.delete("/{incident_id}")
def delete_incident(incident_id: int, db: Session = Depends(get_db), user: User = Depends(require_supervisor)):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    title = incident.title
    log_action(db, user.id, user.display_name, "delete", "incident", incident_id, title,
               details=f"Deleted incident: {title}")
    db.delete(incident)
    db.commit()
    return {"ok": True}
