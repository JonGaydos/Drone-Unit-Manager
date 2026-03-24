from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.training_log import TrainingLog
from app.models.training_log_pilot import TrainingLogPilot
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.user import User
from app.routers.auth import get_current_user, require_pilot
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


def _training_to_out(training: TrainingLog, db: Session) -> TrainingLogOut:
    out = TrainingLogOut.model_validate(training)
    if training.vehicle_id:
        vehicle = db.query(Vehicle).filter(Vehicle.id == training.vehicle_id).first()
        if vehicle:
            out.vehicle_name = _vehicle_display(vehicle)
    pilot_outs = []
    for tp in training.pilots:
        po = TrainingLogPilotOut.model_validate(tp)
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
    date_from: date | None = None,
    date_to: date | None = None,
    pilot_id: int | None = None,
    training_type: str | None = None,
    outcome: str | None = None,
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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
    trainings = q.order_by(TrainingLog.date.desc()).offset(offset).limit(limit).all()
    return [_training_to_out(t, db) for t in trainings]


@router.get("/{training_id}", response_model=TrainingLogOut)
def get_training_log(training_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    training = db.query(TrainingLog).filter(TrainingLog.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Training log not found")
    return _training_to_out(training, db)


@router.post("", response_model=TrainingLogOut)
def create_training_log(data: TrainingLogCreate, db: Session = Depends(get_db), admin: User = Depends(require_pilot)):
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


@router.patch("/{training_id}", response_model=TrainingLogOut)
def update_training_log(training_id: int, data: TrainingLogUpdate, db: Session = Depends(get_db), admin: User = Depends(require_pilot)):
    training = db.query(TrainingLog).filter(TrainingLog.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Training log not found")
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


@router.delete("/{training_id}")
def delete_training_log(training_id: int, db: Session = Depends(get_db), admin: User = Depends(require_pilot)):
    from app.services.audit import log_action
    training = db.query(TrainingLog).filter(TrainingLog.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Training log not found")
    log_action(db, admin.id, admin.display_name, "delete", "training_log", training.id, training.title or f"Training {training.id}")
    db.delete(training)
    db.commit()
    return {"ok": True}


@router.post("/{training_id}/pilots", response_model=TrainingLogPilotOut)
def add_pilot_to_training(training_id: int, data: TrainingLogPilotIn, db: Session = Depends(get_db), admin: User = Depends(require_pilot)):
    training = db.query(TrainingLog).filter(TrainingLog.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Training log not found")
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


@router.delete("/{training_id}/pilots/{pilot_id}")
def remove_pilot_from_training(training_id: int, pilot_id: int, db: Session = Depends(get_db), admin: User = Depends(require_pilot)):
    tp = db.query(TrainingLogPilot).filter(
        TrainingLogPilot.training_log_id == training_id,
        TrainingLogPilot.pilot_id == pilot_id,
    ).first()
    if not tp:
        raise HTTPException(status_code=404, detail="Pilot not found in training")
    db.delete(tp)
    db.commit()
    return {"ok": True}
