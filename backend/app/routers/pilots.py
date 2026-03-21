from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.pilot import Pilot
from app.models.flight import Flight
from app.models.user import User
from app.routers.auth import get_current_user, require_admin
from app.schemas.pilot import PilotCreate, PilotUpdate, PilotOut, PilotStats

router = APIRouter(prefix="/api/pilots", tags=["pilots"])


@router.get("", response_model=list[PilotOut])
def list_pilots(
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Pilot)
    if status:
        q = q.filter(Pilot.status == status)
    return [PilotOut.model_validate(p) for p in q.order_by(Pilot.last_name, Pilot.first_name).all()]


@router.get("/{pilot_id}", response_model=PilotOut)
def get_pilot(pilot_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail="Pilot not found")
    return PilotOut.model_validate(pilot)


@router.get("/{pilot_id}/stats", response_model=PilotStats)
def get_pilot_stats(pilot_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail="Pilot not found")
    stats = db.query(
        func.count(Flight.id).label("total_flights"),
        func.coalesce(func.sum(Flight.duration_seconds), 0).label("total_seconds"),
        func.coalesce(func.avg(Flight.duration_seconds), 0).label("avg_seconds"),
    ).filter(Flight.pilot_id == pilot_id).first()
    return PilotStats(
        total_flights=stats.total_flights,
        total_flight_hours=stats.total_seconds / 3600,
        avg_flight_duration_seconds=float(stats.avg_seconds),
    )


@router.post("", response_model=PilotOut)
def create_pilot(data: PilotCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    pilot = Pilot(**data.model_dump())
    db.add(pilot)
    db.commit()
    db.refresh(pilot)
    return PilotOut.model_validate(pilot)


@router.patch("/{pilot_id}", response_model=PilotOut)
def update_pilot(pilot_id: int, data: PilotUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail="Pilot not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(pilot, key, value)
    db.commit()
    db.refresh(pilot)
    return PilotOut.model_validate(pilot)


@router.delete("/{pilot_id}")
def delete_pilot(pilot_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        raise HTTPException(status_code=404, detail="Pilot not found")
    db.delete(pilot)
    db.commit()
    return {"ok": True}
