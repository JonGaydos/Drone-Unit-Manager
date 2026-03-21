from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.mission_log import MissionLog
from app.models.mission_log_pilot import MissionLogPilot
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.user import User
from app.routers.auth import get_current_user, require_admin
from app.schemas.mission_log import (
    MissionLogCreate, MissionLogUpdate, MissionLogOut,
    MissionLogPilotIn, MissionLogPilotOut,
)

router = APIRouter(prefix="/api/mission-logs", tags=["mission-logs"])


def _vehicle_display(vehicle: Vehicle) -> str:
    name = f"{vehicle.manufacturer} {vehicle.model}"
    if vehicle.nickname:
        name += f" ({vehicle.nickname})"
    return name


def _mission_to_out(mission: MissionLog, db: Session) -> MissionLogOut:
    out = MissionLogOut.model_validate(mission)
    if mission.vehicle_id:
        vehicle = db.query(Vehicle).filter(Vehicle.id == mission.vehicle_id).first()
        if vehicle:
            out.vehicle_name = _vehicle_display(vehicle)
    pilot_outs = []
    for mp in mission.pilots:
        po = MissionLogPilotOut.model_validate(mp)
        pilot = db.query(Pilot).filter(Pilot.id == mp.pilot_id).first()
        if pilot:
            po.pilot_name = pilot.full_name
        pilot_outs.append(po)
    out.pilots = pilot_outs
    return out


def _sync_pilots(db: Session, mission: MissionLog, pilots_data: list[MissionLogPilotIn]):
    # Remove existing
    db.query(MissionLogPilot).filter(MissionLogPilot.mission_log_id == mission.id).delete()
    db.flush()
    # Add new
    for p in pilots_data:
        db.add(MissionLogPilot(
            mission_log_id=mission.id,
            pilot_id=p.pilot_id,
            role=p.role,
            hours=p.hours,
        ))


@router.get("", response_model=list[MissionLogOut])
def list_mission_logs(
    date_from: date | None = None,
    date_to: date | None = None,
    pilot_id: int | None = None,
    status: str | None = None,
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(MissionLog)
    if date_from:
        q = q.filter(MissionLog.date >= date_from)
    if date_to:
        q = q.filter(MissionLog.date <= date_to)
    if status:
        q = q.filter(MissionLog.status == status)
    if pilot_id:
        mission_ids = [
            mp.mission_log_id
            for mp in db.query(MissionLogPilot).filter(MissionLogPilot.pilot_id == pilot_id).all()
        ]
        q = q.filter(MissionLog.id.in_(mission_ids))
    missions = q.order_by(MissionLog.date.desc()).offset(offset).limit(limit).all()
    return [_mission_to_out(m, db) for m in missions]


@router.get("/{mission_id}", response_model=MissionLogOut)
def get_mission_log(mission_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    mission = db.query(MissionLog).filter(MissionLog.id == mission_id).first()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission log not found")
    return _mission_to_out(mission, db)


@router.post("", response_model=MissionLogOut)
def create_mission_log(data: MissionLogCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    pilots_data = data.pilots
    mission_dict = data.model_dump(exclude={"pilots"})
    mission = MissionLog(**mission_dict)
    db.add(mission)
    db.flush()
    for p in pilots_data:
        db.add(MissionLogPilot(
            mission_log_id=mission.id,
            pilot_id=p.pilot_id,
            role=p.role,
            hours=p.hours,
        ))
    db.commit()
    db.refresh(mission)
    return _mission_to_out(mission, db)


@router.patch("/{mission_id}", response_model=MissionLogOut)
def update_mission_log(mission_id: int, data: MissionLogUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    mission = db.query(MissionLog).filter(MissionLog.id == mission_id).first()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission log not found")
    update_data = data.model_dump(exclude_unset=True)
    pilots_data = update_data.pop("pilots", None)
    for key, value in update_data.items():
        setattr(mission, key, value)
    if pilots_data is not None:
        _sync_pilots(db, mission, [MissionLogPilotIn(**p) for p in pilots_data])
    db.commit()
    db.refresh(mission)
    return _mission_to_out(mission, db)


@router.delete("/{mission_id}")
def delete_mission_log(mission_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    mission = db.query(MissionLog).filter(MissionLog.id == mission_id).first()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission log not found")
    db.delete(mission)
    db.commit()
    return {"ok": True}


@router.post("/{mission_id}/pilots", response_model=MissionLogPilotOut)
def add_pilot_to_mission(mission_id: int, data: MissionLogPilotIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    mission = db.query(MissionLog).filter(MissionLog.id == mission_id).first()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission log not found")
    mp = MissionLogPilot(
        mission_log_id=mission_id,
        pilot_id=data.pilot_id,
        role=data.role,
        hours=data.hours,
    )
    db.add(mp)
    db.commit()
    db.refresh(mp)
    out = MissionLogPilotOut.model_validate(mp)
    pilot = db.query(Pilot).filter(Pilot.id == mp.pilot_id).first()
    if pilot:
        out.pilot_name = pilot.full_name
    return out


@router.delete("/{mission_id}/pilots/{pilot_id}")
def remove_pilot_from_mission(mission_id: int, pilot_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    mp = db.query(MissionLogPilot).filter(
        MissionLogPilot.mission_log_id == mission_id,
        MissionLogPilot.pilot_id == pilot_id,
    ).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Pilot not found in mission")
    db.delete(mp)
    db.commit()
    return {"ok": True}
