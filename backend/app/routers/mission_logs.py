from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.constants import MISSION_LOG_NOT_FOUND
from app.deps import DBSession
from app.models.user import User
from app.routers.auth import require_permission
from app.services import permissions as permissions_service
from app.responses import responses
from app.models.mission_log import MissionLog
from app.models.mission_log_pilot import MissionLogPilot
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.schemas.mission_log import (
    MissionLogCreate, MissionLogUpdate, MissionLogOut,
    MissionLogPilotIn, MissionLogPilotOut,
)

router = APIRouter(prefix="/api/mission-logs", tags=["mission-logs"])

LOGS_EDIT = "logs.edit"

ViewUser = Annotated[User, Depends(require_permission("logs.view"))]
CreateUser = Annotated[User, Depends(require_permission("logs.create"))]
EditUser = Annotated[User, Depends(require_permission(LOGS_EDIT))]


def _require_edit(db: Session, user: User, log) -> None:
    """Raise 403 unless the user's logs.edit level covers this log."""
    permissions_service.require_record_access(db, user, LOGS_EDIT, permissions_service.owns_roster_log(user, log))


def _vehicle_display(vehicle: Vehicle) -> str:
    name = f"{vehicle.manufacturer} {vehicle.model}"
    if vehicle.nickname:
        name += f" ({vehicle.nickname})"
    return name


def _mission_to_out(mission: MissionLog, db: Session, vehicle_cache=None, pilot_cache=None) -> MissionLogOut:
    """Serialize a mission. For list endpoints, pass prebuilt vehicle_cache /
    pilot_cache (id -> object) to avoid a query per row; single-item callers
    omit them and fall back to direct lookups."""
    out = MissionLogOut.model_validate(mission)
    if mission.vehicle_id:
        if vehicle_cache is not None:
            vehicle = vehicle_cache.get(mission.vehicle_id)
        else:
            vehicle = db.query(Vehicle).filter(Vehicle.id == mission.vehicle_id).first()
        if vehicle:
            out.vehicle_name = _vehicle_display(vehicle)
    pilot_outs = []
    for mp in mission.pilots:
        po = MissionLogPilotOut.model_validate(mp)
        if pilot_cache is not None:
            pilot = pilot_cache.get(mp.pilot_id)
        else:
            pilot = db.query(Pilot).filter(Pilot.id == mp.pilot_id).first()
        if pilot:
            po.pilot_name = pilot.full_name
        pilot_outs.append(po)
    out.pilots = pilot_outs
    return out


def _sync_pilots(db: Session, mission: MissionLog, pilots_data: list[MissionLogPilotIn]):
    db.query(MissionLogPilot).filter(MissionLogPilot.mission_log_id == mission.id).delete()
    db.flush()
    for p in pilots_data:
        db.add(MissionLogPilot(
            mission_log_id=mission.id,
            pilot_id=p.pilot_id,
            role=p.role,
            hours=p.hours,
        ))


def _matches(text: str):
    """Missions whose title, reason, location, case number or a pilot's name
    contains ``text``. Run in the database so a search reaches every mission,
    not just the page the list returned."""
    by_pilot = (select(MissionLogPilot.mission_log_id)
                .join(Pilot, Pilot.id == MissionLogPilot.pilot_id)
                .where((Pilot.first_name + " " + Pilot.last_name).icontains(text, autoescape=True)))
    return or_(
        MissionLog.title.icontains(text, autoescape=True),
        MissionLog.reason.icontains(text, autoescape=True),
        MissionLog.location.icontains(text, autoescape=True),
        MissionLog.case_number.icontains(text, autoescape=True),
        MissionLog.id.in_(by_pilot),
    )


def _narrowed(q, pilot_id: int | None, search: str | None):
    """The mission query limited to one pilot's missions and to a text search."""
    if pilot_id:
        q = q.filter(MissionLog.id.in_(
            select(MissionLogPilot.mission_log_id).where(MissionLogPilot.pilot_id == pilot_id)))
    if search:
        q = q.filter(_matches(search.strip()))
    return q


@router.get("", response_model=list[MissionLogOut])
def list_mission_logs(

    db: DBSession,

    user: ViewUser,

    date_from: date | None = None,

    date_to: date | None = None,

    pilot_id: int | None = None,

    status: str | None = None,

    search: str | None = None,

    limit: Annotated[int, Query(le=1000)] = 200,

    offset: int = 0,
):
    q = db.query(MissionLog)
    if date_from:
        q = q.filter(MissionLog.date >= date_from)
    if date_to:
        q = q.filter(MissionLog.date <= date_to)
    if status:
        q = q.filter(MissionLog.status == status)
    q = _narrowed(q, pilot_id, search)
    missions = q.options(selectinload(MissionLog.pilots)).order_by(
        MissionLog.date.desc()
    ).offset(offset).limit(limit).all()

    # Batch-load referenced vehicles and pilots once, then enrich from caches.
    vehicle_ids = {m.vehicle_id for m in missions if m.vehicle_id}
    pilot_ids = {mp.pilot_id for m in missions for mp in m.pilots}
    vehicle_cache = {
        v.id: v for v in db.query(Vehicle).filter(Vehicle.id.in_(vehicle_ids)).all()
    } if vehicle_ids else {}
    pilot_cache = {
        p.id: p for p in db.query(Pilot).filter(Pilot.id.in_(pilot_ids)).all()
    } if pilot_ids else {}
    return [_mission_to_out(m, db, vehicle_cache, pilot_cache) for m in missions]


@router.get("/{mission_id}", response_model=MissionLogOut, responses=responses(401, 404))
def get_mission_log(mission_id: int, db: DBSession, user: ViewUser):
    mission = db.query(MissionLog).filter(MissionLog.id == mission_id).first()
    if not mission:
        raise HTTPException(status_code=404, detail=MISSION_LOG_NOT_FOUND)
    return _mission_to_out(mission, db)


@router.post("", response_model=MissionLogOut, responses=responses(401))
def create_mission_log(data: MissionLogCreate, db: DBSession, admin: CreateUser):
    from app.services.audit import log_action
    pilots_data = data.pilots
    mission_dict = data.model_dump(exclude={"pilots"})
    mission = MissionLog(**mission_dict, created_by_id=admin.id)
    db.add(mission)
    db.flush()
    for p in pilots_data:
        db.add(MissionLogPilot(
            mission_log_id=mission.id,
            pilot_id=p.pilot_id,
            role=p.role,
            hours=p.hours,
        ))
    log_action(db, admin.id, admin.display_name, "create", "mission_log", mission.id, mission.title or f"Mission {mission.id}")
    db.commit()
    db.refresh(mission)
    return _mission_to_out(mission, db)


@router.patch("/{mission_id}", response_model=MissionLogOut, responses=responses(401, 404))
def update_mission_log(mission_id: int, data: MissionLogUpdate, db: DBSession, admin: EditUser):
    mission = db.query(MissionLog).filter(MissionLog.id == mission_id).first()
    if not mission:
        raise HTTPException(status_code=404, detail=MISSION_LOG_NOT_FOUND)
    _require_edit(db, admin, mission)
    update_data = data.model_dump(exclude_unset=True)
    pilots_data = update_data.pop("pilots", None)
    for key, value in update_data.items():
        setattr(mission, key, value)
    if pilots_data is not None:
        _sync_pilots(db, mission, [MissionLogPilotIn(**p) for p in pilots_data])
    from app.services.audit import log_action
    log_action(db, admin.id, admin.display_name, "update", "mission_log", mission.id, mission.title or f"Mission {mission.id}")
    db.commit()
    db.refresh(mission)
    return _mission_to_out(mission, db)


@router.delete("/{mission_id}", responses=responses(401, 404))
def delete_mission_log(mission_id: int, db: DBSession, admin: EditUser):
    from app.services.audit import log_action
    mission = db.query(MissionLog).filter(MissionLog.id == mission_id).first()
    if not mission:
        raise HTTPException(status_code=404, detail=MISSION_LOG_NOT_FOUND)
    _require_edit(db, admin, mission)
    log_action(db, admin.id, admin.display_name, "delete", "mission_log", mission.id, mission.title or f"Mission {mission.id}")
    db.delete(mission)
    db.commit()
    return {"ok": True}


@router.post("/{mission_id}/pilots", response_model=MissionLogPilotOut, responses=responses(401, 404))
def add_pilot_to_mission(mission_id: int, data: MissionLogPilotIn, db: DBSession, admin: EditUser):
    mission = db.query(MissionLog).filter(MissionLog.id == mission_id).first()
    if not mission:
        raise HTTPException(status_code=404, detail=MISSION_LOG_NOT_FOUND)
    _require_edit(db, admin, mission)
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


@router.delete("/{mission_id}/pilots/{pilot_id}", responses=responses(401, 404))
def remove_pilot_from_mission(mission_id: int, pilot_id: int, db: DBSession, admin: EditUser):
    mission = db.query(MissionLog).filter(MissionLog.id == mission_id).first()
    if not mission:
        raise HTTPException(status_code=404, detail=MISSION_LOG_NOT_FOUND)
    _require_edit(db, admin, mission)
    mp = db.query(MissionLogPilot).filter(
        MissionLogPilot.mission_log_id == mission_id,
        MissionLogPilot.pilot_id == pilot_id,
    ).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Pilot not found in mission")
    db.delete(mp)
    db.commit()
    return {"ok": True}
