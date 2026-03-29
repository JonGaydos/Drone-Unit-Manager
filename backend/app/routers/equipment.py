from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.battery import Battery
from app.models.controller import Controller
from app.models.dock import Dock
from app.models.sensor import SensorPackage
from app.models.attachment import Attachment
from app.models.user import User
from app.routers.auth import get_current_user, require_admin

router = APIRouter(prefix="/api", tags=["equipment"])

class BatteryCreate(BaseModel):
    serial_number: str
    nickname: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    vehicle_model: Optional[str] = None
    cycle_count: int = Field(default=0, ge=0)
    health_pct: Optional[float] = Field(None, ge=0, le=100)
    status: str = "active"
    purchase_date: Optional[date] = None
    notes: Optional[str] = None

class BatteryUpdate(BaseModel):
    serial_number: Optional[str] = None
    nickname: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    vehicle_model: Optional[str] = None
    cycle_count: Optional[int] = Field(None, ge=0)
    health_pct: Optional[float] = Field(None, ge=0, le=100)
    status: Optional[str] = None
    purchase_date: Optional[date] = None
    notes: Optional[str] = None

class BatteryOut(BaseModel):
    id: int
    serial_number: str
    nickname: Optional[str] = None
    manufacturer: Optional[str]
    model: Optional[str]
    vehicle_model: Optional[str]
    cycle_count: int
    health_pct: Optional[float]
    status: str
    purchase_date: Optional[date]
    notes: Optional[str]
    model_config = {"from_attributes": True}

@router.get("/batteries", response_model=list[BatteryOut])
def list_batteries(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [BatteryOut.model_validate(b) for b in db.query(Battery).order_by(Battery.serial_number).all()]

@router.post("/batteries", response_model=BatteryOut)
def create_battery(data: BatteryCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    b = Battery(**data.model_dump())
    db.add(b)
    db.commit()
    db.refresh(b)
    return BatteryOut.model_validate(b)

@router.patch("/batteries/{bid}", response_model=BatteryOut)
def update_battery(bid: int, data: BatteryUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    b = db.query(Battery).filter(Battery.id == bid).first()
    if not b:
        raise HTTPException(404, "Battery not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(b, k, v)
    db.commit()
    db.refresh(b)
    return BatteryOut.model_validate(b)

@router.delete("/batteries/{bid}")
def delete_battery(bid: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    b = db.query(Battery).filter(Battery.id == bid).first()
    if not b:
        raise HTTPException(404, "Battery not found")
    db.delete(b)
    db.commit()
    return {"ok": True}

@router.get("/batteries/{bid}", response_model=BatteryOut)
def get_battery(bid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    b = db.query(Battery).filter(Battery.id == bid).first()
    if not b:
        raise HTTPException(404, "Battery not found")
    return BatteryOut.model_validate(b)

@router.get("/batteries/{bid}/stats")
def get_battery_stats(bid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.flight import Flight
    battery = db.query(Battery).filter(Battery.id == bid).first()
    if not battery:
        raise HTTPException(404, "Battery not found")
    flight_count = db.query(func.count(Flight.id)).filter(Flight.battery_serial == battery.serial_number).scalar()
    total_seconds = db.query(func.coalesce(func.sum(Flight.duration_seconds), 0)).filter(Flight.battery_serial == battery.serial_number).scalar()
    return {"total_flights": flight_count, "total_hours": round(total_seconds / 3600, 2)}


@router.get("/batteries/{bid}/flights")
def get_battery_flights(bid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get all flights that used a specific battery."""
    from app.models.flight import Flight
    from app.models.pilot import Pilot
    battery = db.query(Battery).filter(Battery.id == bid).first()
    if not battery:
        raise HTTPException(404, "Battery not found")
    flights = db.query(Flight).filter(Flight.battery_serial == battery.serial_number).order_by(Flight.date.desc()).all()
    return [
        {
            "id": f.id,
            "date": str(f.date) if f.date else None,
            "pilot_name": f"{f.pilot.first_name} {f.pilot.last_name}" if f.pilot else None,
            "pilot_id": f.pilot_id,
            "vehicle_name": f.vehicle.nickname or f"{f.vehicle.manufacturer} {f.vehicle.model}" if f.vehicle else None,
            "duration_seconds": f.duration_seconds,
            "purpose": f.purpose,
            "max_altitude_m": f.max_altitude_m,
        }
        for f in flights
    ]


@router.get("/batteries/{bid}/pilots")
def get_battery_pilots(bid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get unique pilots who have used a specific battery."""
    from app.models.flight import Flight
    from app.models.pilot import Pilot
    battery = db.query(Battery).filter(Battery.id == bid).first()
    if not battery:
        raise HTTPException(404, "Battery not found")
    pilot_ids = db.query(Flight.pilot_id).filter(
        Flight.battery_serial == battery.serial_number,
        Flight.pilot_id.isnot(None),
    ).distinct().all()
    pilots = db.query(Pilot).filter(Pilot.id.in_([p[0] for p in pilot_ids])).all()
    return [{"id": p.id, "name": f"{p.first_name} {p.last_name}", "badge_number": p.badge_number} for p in pilots]


@router.post("/batteries/{bid}/merge")
def merge_batteries(bid: int, merge_from_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Merge a duplicate battery into this one. Updates all flight references and deletes the duplicate."""
    from app.models.flight import Flight
    target = db.query(Battery).filter(Battery.id == bid).first()
    source = db.query(Battery).filter(Battery.id == merge_from_id).first()
    if not target or not source:
        raise HTTPException(404, "Battery not found")
    if target.id == source.id:
        raise HTTPException(400, "Cannot merge a battery with itself")
    # Update all flights referencing the source serial to use the target serial
    updated = db.query(Flight).filter(Flight.battery_serial == source.serial_number).update(
        {Flight.battery_serial: target.serial_number}, synchronize_session=False
    )
    db.delete(source)
    db.commit()
    return {"ok": True, "flights_updated": updated, "message": f"Merged '{source.serial_number}' into '{target.serial_number}'"}


@router.post("/attachments/{aid}/merge")
def merge_attachments(aid: int, merge_from_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Merge a duplicate attachment into this one."""
    target = db.query(Attachment).filter(Attachment.id == aid).first()
    source = db.query(Attachment).filter(Attachment.id == merge_from_id).first()
    if not target or not source:
        raise HTTPException(404, "Attachment not found")
    if target.id == source.id:
        raise HTTPException(400, "Cannot merge an attachment with itself")
    from app.models.flight import Flight
    # Update all attachment fields across all flights
    for field in ["attachment_top", "attachment_bottom", "attachment_left", "attachment_right"]:
        db.query(Flight).filter(getattr(Flight, field) == source.serial_number).update(
            {getattr(Flight, field): target.serial_number}, synchronize_session=False
        )
    db.delete(source)
    db.commit()
    return {"ok": True, "message": f"Merged '{source.serial_number}' into '{target.serial_number}'"}


@router.post("/sensors/{sid}/merge")
def merge_sensors(sid: int, merge_from_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Merge a duplicate sensor package into this one."""
    from app.models.sensor import SensorPackage as SP
    from app.models.flight import Flight
    target = db.query(SP).filter(SP.id == sid).first()
    source = db.query(SP).filter(SP.id == merge_from_id).first()
    if not target or not source:
        raise HTTPException(404, "Sensor not found")
    updated = db.query(Flight).filter(Flight.sensor_package == source.serial_number).update(
        {Flight.sensor_package: target.serial_number}, synchronize_session=False
    )
    db.delete(source)
    db.commit()
    return {"ok": True, "flights_updated": updated, "message": f"Merged '{source.serial_number}' into '{target.serial_number}'"}


class BatteryReadingCreate(BaseModel):
    """Schema for manually recording a battery health reading."""
    health_pct: Optional[float] = Field(None, ge=0, le=100)
    cycle_count: Optional[int] = Field(None, ge=0)
    voltage: Optional[float] = None
    capacity_mah: Optional[float] = None
    temperature_c: Optional[float] = None
    notes: Optional[str] = None


@router.get("/batteries/{bid}/health-history")
def get_battery_health_history(bid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get historical health readings for a battery, ordered by date."""
    from app.models.battery_reading import BatteryReading
    b = db.query(Battery).filter(Battery.id == bid).first()
    if not b:
        raise HTTPException(404, "Battery not found")
    readings = db.query(BatteryReading).filter(
        BatteryReading.battery_id == bid
    ).order_by(BatteryReading.recorded_at).all()
    return [
        {
            "id": r.id,
            "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
            "health_pct": r.health_pct,
            "cycle_count": r.cycle_count,
            "voltage": r.voltage,
            "capacity_mah": r.capacity_mah,
            "temperature_c": r.temperature_c,
            "source": r.source,
            "notes": r.notes,
        }
        for r in readings
    ]


@router.post("/batteries/{bid}/readings")
def add_battery_reading(bid: int, data: BatteryReadingCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Manually record a battery health reading."""
    from app.models.battery_reading import BatteryReading
    b = db.query(Battery).filter(Battery.id == bid).first()
    if not b:
        raise HTTPException(404, "Battery not found")
    reading = BatteryReading(
        battery_id=bid,
        health_pct=data.health_pct,
        cycle_count=data.cycle_count,
        voltage=data.voltage,
        capacity_mah=data.capacity_mah,
        temperature_c=data.temperature_c,
        source="manual",
        notes=data.notes,
    )
    db.add(reading)
    # Also update the battery's current values
    if data.health_pct is not None:
        b.health_pct = data.health_pct
    if data.cycle_count is not None:
        b.cycle_count = data.cycle_count
    db.commit()
    return {"ok": True, "id": reading.id}


class ControllerCreate(BaseModel):
    serial_number: str
    nickname: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: str = "active"
    assigned_pilot_id: Optional[int] = None
    notes: Optional[str] = None

class ControllerUpdate(BaseModel):
    serial_number: Optional[str] = None
    nickname: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None
    assigned_pilot_id: Optional[int] = None
    notes: Optional[str] = None

class ControllerOut(BaseModel):
    id: int
    serial_number: str
    nickname: Optional[str] = None
    manufacturer: Optional[str]
    model: Optional[str]
    status: str
    assigned_pilot_id: Optional[int]
    notes: Optional[str]
    model_config = {"from_attributes": True}

@router.get("/controllers", response_model=list[ControllerOut])
def list_controllers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [ControllerOut.model_validate(c) for c in db.query(Controller).order_by(Controller.serial_number).all()]

@router.post("/controllers", response_model=ControllerOut)
def create_controller(data: ControllerCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    c = Controller(**data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return ControllerOut.model_validate(c)

@router.patch("/controllers/{cid}", response_model=ControllerOut)
def update_controller(cid: int, data: ControllerUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    c = db.query(Controller).filter(Controller.id == cid).first()
    if not c:
        raise HTTPException(404, "Controller not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return ControllerOut.model_validate(c)

@router.delete("/controllers/{cid}")
def delete_controller(cid: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    c = db.query(Controller).filter(Controller.id == cid).first()
    if not c:
        raise HTTPException(404, "Controller not found")
    db.delete(c)
    db.commit()
    return {"ok": True}

@router.get("/controllers/{cid}", response_model=ControllerOut)
def get_controller(cid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.query(Controller).filter(Controller.id == cid).first()
    if not c:
        raise HTTPException(404, "Controller not found")
    return ControllerOut.model_validate(c)


class DockCreate(BaseModel):
    serial_number: str
    name: Optional[str] = None
    location_name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    status: str = "active"
    notes: Optional[str] = None

class DockUpdate(BaseModel):
    serial_number: Optional[str] = None
    name: Optional[str] = None
    location_name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None

class DockOut(BaseModel):
    id: int
    serial_number: str
    name: Optional[str]
    location_name: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    status: str
    notes: Optional[str]
    model_config = {"from_attributes": True}

@router.get("/docks", response_model=list[DockOut])
def list_docks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [DockOut.model_validate(d) for d in db.query(Dock).order_by(Dock.name).all()]

@router.post("/docks", response_model=DockOut)
def create_dock(data: DockCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    d = Dock(**data.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    return DockOut.model_validate(d)

@router.patch("/docks/{did}", response_model=DockOut)
def update_dock(did: int, data: DockUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    d = db.query(Dock).filter(Dock.id == did).first()
    if not d:
        raise HTTPException(404, "Dock not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(d, k, v)
    db.commit()
    db.refresh(d)
    return DockOut.model_validate(d)

@router.delete("/docks/{did}")
def delete_dock(did: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    d = db.query(Dock).filter(Dock.id == did).first()
    if not d:
        raise HTTPException(404, "Dock not found")
    db.delete(d)
    db.commit()
    return {"ok": True}


class SensorCreate(BaseModel):
    serial_number: str
    name: Optional[str] = None
    type: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: str = "active"
    notes: Optional[str] = None

class SensorUpdate(BaseModel):
    serial_number: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None

class SensorOut(BaseModel):
    id: int
    serial_number: str
    name: Optional[str]
    type: Optional[str]
    manufacturer: Optional[str]
    model: Optional[str]
    status: str
    notes: Optional[str]
    model_config = {"from_attributes": True}

@router.get("/sensors", response_model=list[SensorOut])
def list_sensors(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [SensorOut.model_validate(s) for s in db.query(SensorPackage).order_by(SensorPackage.name).all()]

@router.post("/sensors", response_model=SensorOut)
def create_sensor(data: SensorCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    s = SensorPackage(**data.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return SensorOut.model_validate(s)

@router.patch("/sensors/{sid}", response_model=SensorOut)
def update_sensor(sid: int, data: SensorUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    s = db.query(SensorPackage).filter(SensorPackage.id == sid).first()
    if not s:
        raise HTTPException(404, "Sensor not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return SensorOut.model_validate(s)

@router.delete("/sensors/{sid}")
def delete_sensor(sid: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    s = db.query(SensorPackage).filter(SensorPackage.id == sid).first()
    if not s:
        raise HTTPException(404, "Sensor not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


class AttachmentCreate(BaseModel):
    serial_number: str
    name: Optional[str] = None
    type: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: str = "active"
    notes: Optional[str] = None

class AttachmentUpdate(BaseModel):
    serial_number: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None

class AttachmentOut(BaseModel):
    id: int
    serial_number: str
    name: Optional[str]
    type: Optional[str]
    manufacturer: Optional[str]
    model: Optional[str]
    status: str
    notes: Optional[str]
    model_config = {"from_attributes": True}

@router.get("/attachments", response_model=list[AttachmentOut])
def list_attachments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [AttachmentOut.model_validate(a) for a in db.query(Attachment).order_by(Attachment.name).all()]

@router.post("/attachments", response_model=AttachmentOut)
def create_attachment(data: AttachmentCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    a = Attachment(**data.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return AttachmentOut.model_validate(a)

@router.patch("/attachments/{aid}", response_model=AttachmentOut)
def update_attachment(aid: int, data: AttachmentUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    a = db.query(Attachment).filter(Attachment.id == aid).first()
    if not a:
        raise HTTPException(404, "Attachment not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    db.commit()
    db.refresh(a)
    return AttachmentOut.model_validate(a)

@router.delete("/attachments/{aid}")
def delete_attachment(aid: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    a = db.query(Attachment).filter(Attachment.id == aid).first()
    if not a:
        raise HTTPException(404, "Attachment not found")
    db.delete(a)
    db.commit()
    return {"ok": True}
