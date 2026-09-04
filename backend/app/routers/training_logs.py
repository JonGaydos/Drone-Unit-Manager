from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.constants import TRAINING_LOG_NOT_FOUND
from app.deps import DBSession, CurrentUser, PilotUser
from app.responses import responses
from app.models.training_log import TrainingLog
from app.models.training_log_pilot import TrainingLogPilot
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.schemas.training_log import (
    TrainingLogCreate, TrainingLogUpdate, TrainingLogOut,
    TrainingLogPilotIn, TrainingLogPilotOut,
)

router = APIRouter(prefix="/api/training-logs", tags=["training-logs"])


def _vehicle_display(vehicle: Vehicle) -> str:
    name = f"{vehicle.manufacturer} {vehicle.model}"
    if vehicle.nickname:
        name += f" ({vehicle.nickname})"
    return name


def _training_to_out(training: TrainingLog, db: Session, vehicle_cache=None, pilot_cache=None) -> TrainingLogOut:
    """Serialize a training log. For list endpoints, pass prebuilt
    vehicle_cache / pilot_cache (id -> object) to avoid a query per row;
    single-item callers omit them and fall back to direct lookups."""
    out = TrainingLogOut.model_validate(training)
    if training.vehicle_id:
        if vehicle_cache is not None:
            vehicle = vehicle_cache.get(training.vehicle_id)
        else:
            vehicle = db.query(Vehicle).filter(Vehicle.id == training.vehicle_id).first()
        if vehicle:
            out.vehicle_name = _vehicle_display(vehicle)
    pilot_outs = []
    for tp in training.pilots:
        po = TrainingLogPilotOut.model_validate(tp)
        if pilot_cache is not None:
            pilot = pilot_cache.get(tp.pilot_id)
        else:
            pilot = db.query(Pilot).filter(Pilot.id == tp.pilot_id).first()
        if pilot:
            po.pilot_name = pilot.full_name
        pilot_outs.append(po)
    out.pilots = pilot_outs
    return out


def _sync_pilots(db: Session, training: TrainingLog, pilots_data: list[TrainingLogPilotIn]):
    db.query(TrainingLogPilot).filter(TrainingLogPilot.training_log_id == training.id).delete()
    db.flush()
    for p in pilots_data:
        db.add(TrainingLogPilot(
            training_log_id=training.id,
            pilot_id=p.pilot_id,
            role=p.role,
            hours=p.hours,
        ))


@router.get("", response_model=list[TrainingLogOut])
def list_training_logs(

    db: DBSession,

    user: CurrentUser,

    date_from: date | None = None,

    date_to: date | None = None,

    pilot_id: int | None = None,

    training_type: str | None = None,

    outcome: str | None = None,

    limit: Annotated[int, Query(le=1000)] = 200,

    offset: int = 0,
):
    q = db.query(TrainingLog)
    if date_from:
        q = q.filter(TrainingLog.date >= date_from)
    if date_to:
        q = q.filter(TrainingLog.date <= date_to)
    if training_type:
        q = q.filter(TrainingLog.training_type == training_type)
    if outcome:
        q = q.filter(TrainingLog.outcome == outcome)
    if pilot_id:
        training_ids = [
            tp.training_log_id
            for tp in db.query(TrainingLogPilot).filter(TrainingLogPilot.pilot_id == pilot_id).all()
        ]
        q = q.filter(TrainingLog.id.in_(training_ids))
    trainings = q.options(selectinload(TrainingLog.pilots)).order_by(
        TrainingLog.date.desc()
    ).offset(offset).limit(limit).all()

    # Batch-load referenced vehicles and pilots once, then enrich from caches.
    vehicle_ids = {t.vehicle_id for t in trainings if t.vehicle_id}
    pilot_ids = {tp.pilot_id for t in trainings for tp in t.pilots}
    vehicle_cache = {
        v.id: v for v in db.query(Vehicle).filter(Vehicle.id.in_(vehicle_ids)).all()
    } if vehicle_ids else {}
    pilot_cache = {
        p.id: p for p in db.query(Pilot).filter(Pilot.id.in_(pilot_ids)).all()
    } if pilot_ids else {}
    return [_training_to_out(t, db, vehicle_cache, pilot_cache) for t in trainings]


@router.get("/{training_id}", response_model=TrainingLogOut, responses=responses(401, 404))
def get_training_log(training_id: int, db: DBSession, user: CurrentUser):
    training = db.query(TrainingLog).filter(TrainingLog.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail=TRAINING_LOG_NOT_FOUND)
    return _training_to_out(training, db)


@router.post("", response_model=TrainingLogOut, responses=responses(401))
def create_training_log(data: TrainingLogCreate, db: DBSession, admin: PilotUser):
    from app.services.audit import log_action
    pilots_data = data.pilots
    training_dict = data.model_dump(exclude={"pilots"})
    training = TrainingLog(**training_dict)
    db.add(training)
    db.flush()
    for p in pilots_data:
        db.add(TrainingLogPilot(
            training_log_id=training.id,
            pilot_id=p.pilot_id,
            role=p.role,
            hours=p.hours,
        ))
    log_action(db, admin.id, admin.display_name, "create", "training_log", training.id, training.title or f"Training {training.id}")
    db.commit()
    db.refresh(training)
    return _training_to_out(training, db)


@router.patch("/{training_id}", response_model=TrainingLogOut, responses=responses(401, 404))
def update_training_log(training_id: int, data: TrainingLogUpdate, db: DBSession, admin: PilotUser):
    training = db.query(TrainingLog).filter(TrainingLog.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail=TRAINING_LOG_NOT_FOUND)
    update_data = data.model_dump(exclude_unset=True)
    pilots_data = update_data.pop("pilots", None)
    for key, value in update_data.items():
        setattr(training, key, value)
    if pilots_data is not None:
        _sync_pilots(db, training, [TrainingLogPilotIn(**p) for p in pilots_data])
    from app.services.audit import log_action
    log_action(db, admin.id, admin.display_name, "update", "training_log", training.id, training.title or f"Training {training.id}")
    db.commit()
    db.refresh(training)
    return _training_to_out(training, db)


@router.delete("/{training_id}", responses=responses(401, 404))
def delete_training_log(training_id: int, db: DBSession, admin: PilotUser):
    from app.services.audit import log_action
    training = db.query(TrainingLog).filter(TrainingLog.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail=TRAINING_LOG_NOT_FOUND)
    log_action(db, admin.id, admin.display_name, "delete", "training_log", training.id, training.title or f"Training {training.id}")
    db.delete(training)
    db.commit()
    return {"ok": True}


@router.post("/{training_id}/pilots", response_model=TrainingLogPilotOut, responses=responses(401, 404))
def add_pilot_to_training(training_id: int, data: TrainingLogPilotIn, db: DBSession, admin: PilotUser):
    training = db.query(TrainingLog).filter(TrainingLog.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail=TRAINING_LOG_NOT_FOUND)
    tp = TrainingLogPilot(
        training_log_id=training_id,
        pilot_id=data.pilot_id,
        role=data.role,
        hours=data.hours,
    )
    db.add(tp)
    db.commit()
    db.refresh(tp)
    out = TrainingLogPilotOut.model_validate(tp)
    pilot = db.query(Pilot).filter(Pilot.id == tp.pilot_id).first()
    if pilot:
        out.pilot_name = pilot.full_name
    return out


@router.delete("/{training_id}/pilots/{pilot_id}", responses=responses(401, 404))
def remove_pilot_from_training(training_id: int, pilot_id: int, db: DBSession, admin: PilotUser):
    tp = db.query(TrainingLogPilot).filter(
        TrainingLogPilot.training_log_id == training_id,
        TrainingLogPilot.pilot_id == pilot_id,
    ).first()
    if not tp:
        raise HTTPException(status_code=404, detail="Pilot not found in training")
    db.delete(tp)
    db.commit()
    return {"ok": True}
