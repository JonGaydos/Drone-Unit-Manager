from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func

from app.constants import BATTERY_NOT_FOUND, CONTROLLER_NOT_FOUND, SENSOR_NOT_FOUND, ATTACHMENT_NOT_FOUND, DOCK_NOT_FOUND
from app.deps import CurrentUser, DBSession
from app.models.user import User
from app.routers.auth import require_permission
from app.models.battery import Battery
from app.models.controller import Controller
from app.models.dock import Dock
from app.models.sensor import SensorPackage
from app.models.attachment import Attachment
from app.models.other_equipment import OtherEquipment
from app.models.vehicle import Vehicle
from app.responses import responses
from app.services.audit_capture import update_recorded
from app.services.equipment_lifecycle import end_schedules
from app.services.equipment_lifecycle import set_fields_with_lifecycle as _set_fields_with_lifecycle
from app.services.flight_scope import counted_flight_clause

router = APIRouter(prefix="/api", tags=["equipment"])

ViewUser = Annotated[User, Depends(require_permission("fleet.view"))]
ManageUser = Annotated[User, Depends(require_permission("fleet.manage"))]
# Flights and flyers of a piece of equipment follow the flights view permission.
FlightsViewUser = Annotated[User, Depends(require_permission("flights.view"))]

OTHER_EQUIPMENT_NOT_FOUND = "Equipment item not found"

SERIAL_OPTION_FIELD = ("serial_number",)
VEHICLE_OPTION_FIELDS = ("nickname", "manufacturer", "model", "serial_number")

def _option_rows(db, model, label, extra: tuple[str, ...] = ()) -> list[dict]:
    """Picker rows (id, name, status, plus any extra columns) for one equipment
    table, sorted by name."""
    rows = [
        {"id": r.id, "name": label(r), "status": r.status, **{field: getattr(r, field) for field in extra}}
        for r in db.query(model).all()
    ]
    return sorted(rows, key=lambda row: row["name"].lower())


def _nickname_or_serial(item) -> str:
    return item.nickname or item.serial_number


def _name_or_serial(item) -> str:
    return item.name or item.serial_number


@router.get("/fleet/options", responses=responses(401))
def fleet_options(db: DBSession, user: CurrentUser):
    """Every equipment type as picker rows of id, name and status.

    Open to any signed-in user so forms can offer a vehicle or item without the
    fleet lists. Retired items are included with their status. Flight forms store
    batteries, sensors and attachments by serial number, and vehicle pickers label
    and group by make and model, so those rows carry those fields as well.
    """
    return {
        "vehicles": _option_rows(db, Vehicle, _nickname_or_serial, VEHICLE_OPTION_FIELDS),
        "batteries": _option_rows(db, Battery, _nickname_or_serial, SERIAL_OPTION_FIELD),
        "controllers": _option_rows(db, Controller, _nickname_or_serial),
        "sensors": _option_rows(db, SensorPackage, _name_or_serial, SERIAL_OPTION_FIELD),
        "attachments": _option_rows(db, Attachment, _name_or_serial, SERIAL_OPTION_FIELD),
        "docks": _option_rows(db, Dock, _name_or_serial),
        "other_equipment": _option_rows(db, OtherEquipment, _name_or_serial),
    }


class BatteryCreate(BaseModel):
    serial_number: str
    nickname: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    vehicle_model: Optional[str] = None
    cycle_count: int = Field(default=0, ge=0)
    health_pct: Optional[float] = Field(None, ge=0, le=100)
    status: str = "active"
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
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
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None

class BatteryOut(BaseModel):
    id: int
    serial_number: str
    nickname: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    vehicle_model: Optional[str] = None
    cycle_count: int
    health_pct: Optional[float] = None
    status: str
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None
    model_config = {"from_attributes": True}

@router.get("/batteries", response_model=list[BatteryOut], responses=responses(401))
def list_batteries(db: DBSession, user: ViewUser):
    return [BatteryOut.model_validate(b) for b in db.query(Battery).order_by(Battery.serial_number).all()]

@router.post("/batteries", response_model=BatteryOut, responses=responses(401))
def create_battery(data: BatteryCreate, db: DBSession, admin: ManageUser):
    b = Battery()
    _set_fields_with_lifecycle(b, data.model_dump())
    db.add(b)
    db.commit()
    db.refresh(b)
    return BatteryOut.model_validate(b)

@router.patch("/batteries/{bid}", response_model=BatteryOut, responses=responses(401, 404))
def update_battery(bid: int, data: BatteryUpdate, db: DBSession, admin: ManageUser):
    b = db.query(Battery).filter(Battery.id == bid).first()
    if not b:
        raise HTTPException(404, BATTERY_NOT_FOUND)
    _set_fields_with_lifecycle(b, data.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(b)
    return BatteryOut.model_validate(b)

@router.delete("/batteries/{bid}", responses=responses(401, 404))
def delete_battery(bid: int, db: DBSession, admin: ManageUser):
    b = db.query(Battery).filter(Battery.id == bid).first()
    if not b:
        raise HTTPException(404, BATTERY_NOT_FOUND)
    end_schedules(db, b)
    # Health readings belong to the battery and go with it.
    from app.models.battery_reading import BatteryReading
    for reading in db.query(BatteryReading).filter(BatteryReading.battery_id == bid).all():
        db.delete(reading)
    db.flush()
    db.delete(b)
    db.commit()
    return {"ok": True}

@router.get("/batteries/{bid}", response_model=BatteryOut, responses=responses(401, 404))
def get_battery(bid: int, db: DBSession, user: ViewUser):
    b = db.query(Battery).filter(Battery.id == bid).first()
    if not b:
        raise HTTPException(404, BATTERY_NOT_FOUND)
    return BatteryOut.model_validate(b)

@router.get("/batteries/{bid}/stats", responses=responses(401, 404))
def get_battery_stats(bid: int, db: DBSession, user: ViewUser, _flights: FlightsViewUser):
    from app.models.flight import Flight
    battery = db.query(Battery).filter(Battery.id == bid).first()
    if not battery:
        raise HTTPException(404, BATTERY_NOT_FOUND)
    flight_count = db.query(func.count(Flight.id)).filter(counted_flight_clause(), Flight.battery_serial == battery.serial_number).scalar()
    total_seconds = db.query(func.coalesce(func.sum(Flight.duration_seconds), 0)).filter(counted_flight_clause(), Flight.battery_serial == battery.serial_number).scalar()
    return {"total_flights": flight_count, "total_hours": round(total_seconds / 3600, 2)}


@router.get("/batteries/{bid}/flights", responses=responses(401, 404))
def get_battery_flights(bid: int, db: DBSession, user: ViewUser, _flights: FlightsViewUser):
    """Get all flights that used a specific battery."""
    from app.models.flight import Flight
    from app.models.pilot import Pilot
    battery = db.query(Battery).filter(Battery.id == bid).first()
    if not battery:
        raise HTTPException(404, BATTERY_NOT_FOUND)
    flights = db.query(Flight).filter(Flight.battery_serial == battery.serial_number).order_by(Flight.date.desc()).all()
    return [
        {
            "id": f.id,
            "date": str(f.date) if f.date else None,
            "pilot_name": f"{f.pilot.first_name} {f.pilot.last_name}" if f.pilot else None,
            "pilot_id": f.pilot_id,
            "vehicle_id": f.vehicle_id,
            "vehicle_name": f.vehicle.nickname or f"{f.vehicle.manufacturer} {f.vehicle.model}" if f.vehicle else None,
            "duration_seconds": f.duration_seconds,
            "takeoff_address": f.takeoff_address,
            "purpose": f.purpose,
            "max_altitude_m": f.max_altitude_m,
        }
        for f in flights
    ]


@router.get("/batteries/{bid}/pilots", responses=responses(401, 404))
def get_battery_pilots(bid: int, db: DBSession, user: ViewUser, _flights: FlightsViewUser):
    """Get unique pilots who have used a specific battery."""
    from app.models.flight import Flight
    from app.models.pilot import Pilot
    battery = db.query(Battery).filter(Battery.id == bid).first()
    if not battery:
        raise HTTPException(404, BATTERY_NOT_FOUND)
    pilot_ids = db.query(Flight.pilot_id).filter(
        Flight.battery_serial == battery.serial_number,
        Flight.pilot_id.isnot(None),
    ).distinct().all()
    pilots = db.query(Pilot).filter(Pilot.id.in_([p[0] for p in pilot_ids])).all()
    return [{"id": p.id, "name": f"{p.first_name} {p.last_name}", "badge_number": p.badge_number} for p in pilots]


@router.post("/batteries/{bid}/merge", responses=responses(400, 401, 404))
def merge_batteries(bid: int, merge_from_id: int, db: DBSession, admin: ManageUser):
    """Merge a duplicate battery into this one. Updates all flight references and deletes the duplicate."""
    from app.services.audit import log_action
    from app.models.flight import Flight
    from app.models.battery_reading import BatteryReading
    from app.models.equipment_checkout import EquipmentCheckout
    target = db.query(Battery).filter(Battery.id == bid).first()
    source = db.query(Battery).filter(Battery.id == merge_from_id).first()
    if not target or not source:
        raise HTTPException(404, BATTERY_NOT_FOUND)
    if target.id == source.id:
        raise HTTPException(400, "Cannot merge a battery with itself")
    # Update all flights referencing the source serial to use the target serial
    updated = update_recorded(db, db.query(Flight).filter(Flight.battery_serial == source.serial_number),
                              {Flight.battery_serial: (source.serial_number, target.serial_number)})
    # Repoint health readings from the source battery to the target.
    update_recorded(db, db.query(BatteryReading).filter(BatteryReading.battery_id == source.id),
                    {BatteryReading.battery_id: (source.id, target.id)})
    # Repoint polymorphic equipment-checkout rows (entity_type="battery").
    update_recorded(db, db.query(EquipmentCheckout).filter(
        EquipmentCheckout.entity_type == "battery",
        EquipmentCheckout.entity_id == source.id,
    ), {EquipmentCheckout.entity_id: (source.id, target.id)})
    db.delete(source)
    log_action(db, admin.id, admin.display_name, "merge", "battery", target.id, target.serial_number, details=f"{source.serial_number} -> {target.serial_number}")
    db.commit()
    return {"ok": True, "flights_updated": updated, "message": f"Merged '{source.serial_number}' into '{target.serial_number}'"}


@router.post("/attachments/{aid}/merge", responses=responses(400, 401, 404))
def merge_attachments(aid: int, merge_from_id: int, db: DBSession, admin: ManageUser):
    """Merge a duplicate attachment into this one."""
    from app.services.audit import log_action
    target = db.query(Attachment).filter(Attachment.id == aid).first()
    source = db.query(Attachment).filter(Attachment.id == merge_from_id).first()
    if not target or not source:
        raise HTTPException(404, ATTACHMENT_NOT_FOUND)
    if target.id == source.id:
        raise HTTPException(400, "Cannot merge an attachment with itself")
    from app.models.flight import Flight
    # Update all attachment fields across all flights
    for field in ["attachment_top", "attachment_bottom", "attachment_left", "attachment_right"]:
        column = getattr(Flight, field)
        update_recorded(db, db.query(Flight).filter(column == source.serial_number),
                        {column: (source.serial_number, target.serial_number)})
    db.delete(source)
    log_action(db, admin.id, admin.display_name, "merge", "attachment", target.id, target.serial_number, details=f"{source.serial_number} -> {target.serial_number}")
    db.commit()
    return {"ok": True, "message": f"Merged '{source.serial_number}' into '{target.serial_number}'"}


@router.post("/sensors/{sid}/merge", responses=responses(400, 401, 404))
def merge_sensors(sid: int, merge_from_id: int, db: DBSession, admin: ManageUser):
    """Merge a duplicate sensor package into this one."""
    from app.services.audit import log_action
    from app.models.sensor import SensorPackage as SP
    from app.models.flight import Flight
    target = db.query(SP).filter(SP.id == sid).first()
    source = db.query(SP).filter(SP.id == merge_from_id).first()
    if not target or not source:
        raise HTTPException(404, SENSOR_NOT_FOUND)
    if target.id == source.id:
        raise HTTPException(400, "Cannot merge a sensor package with itself")
    updated = update_recorded(db, db.query(Flight).filter(Flight.sensor_package == source.serial_number),
                              {Flight.sensor_package: (source.serial_number, target.serial_number)})
    db.delete(source)
    log_action(db, admin.id, admin.display_name, "merge", "sensor", target.id, target.serial_number, details=f"{source.serial_number} -> {target.serial_number}")
    db.commit()
    return {"ok": True, "flights_updated": updated, "message": f"Merged '{source.serial_number}' into '{target.serial_number}'"}


class BatteryReadingCreate(BaseModel):
    """Schema for manually recording a battery health reading."""
    health_pct: Optional[float] = Field(None, ge=0, le=100)
    cycle_count: Optional[int] = Field(None, ge=0)
    voltage: Optional[float] = Field(None, ge=0)
    capacity_mah: Optional[float] = Field(None, ge=0)
    temperature_c: Optional[float] = Field(None, ge=-50, le=100)
    notes: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def _has_a_value(self):
        if all(getattr(self, f) is None for f in READING_VALUES):
            raise ValueError(f"Give at least one of: {', '.join(READING_VALUES)}")
        return self


READING_VALUES = ("health_pct", "cycle_count", "voltage", "capacity_mah", "temperature_c")


@router.get("/batteries/{bid}/health-history", responses=responses(401, 404))
def get_battery_health_history(bid: int, db: DBSession, user: ViewUser):
    """Get historical health readings for a battery, ordered by date."""
    from app.models.battery_reading import BatteryReading
    b = db.query(Battery).filter(Battery.id == bid).first()
    if not b:
        raise HTTPException(404, BATTERY_NOT_FOUND)
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


@router.post("/batteries/{bid}/readings", responses=responses(401, 404, 422))
def add_battery_reading(bid: int, data: BatteryReadingCreate, db: DBSession, admin: ManageUser):
    """Manually record a battery health reading."""
    from app.models.battery_reading import BatteryReading
    b = db.query(Battery).filter(Battery.id == bid).first()
    if not b:
        raise HTTPException(404, BATTERY_NOT_FOUND)
    if data.cycle_count is not None and b.cycle_count and data.cycle_count < b.cycle_count:
        # Cycle counts only grow; a lower one is a typo or the wrong battery.
        raise HTTPException(422, f"Cycle count cannot be lower than the battery's current count ({b.cycle_count})")
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
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    assigned_pilot_id: Optional[int] = None
    notes: Optional[str] = None

class ControllerUpdate(BaseModel):
    serial_number: Optional[str] = None
    nickname: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    assigned_pilot_id: Optional[int] = None
    notes: Optional[str] = None

class ControllerOut(BaseModel):
    id: int
    serial_number: str
    nickname: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: str
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    assigned_pilot_id: Optional[int] = None
    notes: Optional[str] = None
    model_config = {"from_attributes": True}

@router.get("/controllers", response_model=list[ControllerOut], responses=responses(401))
def list_controllers(db: DBSession, user: ViewUser):
    return [ControllerOut.model_validate(c) for c in db.query(Controller).order_by(Controller.serial_number).all()]

@router.post("/controllers", response_model=ControllerOut, responses=responses(401))
def create_controller(data: ControllerCreate, db: DBSession, admin: ManageUser):
    c = Controller()
    _set_fields_with_lifecycle(c, data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return ControllerOut.model_validate(c)

@router.patch("/controllers/{cid}", response_model=ControllerOut, responses=responses(401, 404))
def update_controller(cid: int, data: ControllerUpdate, db: DBSession, admin: ManageUser):
    c = db.query(Controller).filter(Controller.id == cid).first()
    if not c:
        raise HTTPException(404, CONTROLLER_NOT_FOUND)
    _set_fields_with_lifecycle(c, data.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(c)
    return ControllerOut.model_validate(c)

@router.delete("/controllers/{cid}", responses=responses(401, 404))
def delete_controller(cid: int, db: DBSession, admin: ManageUser):
    c = db.query(Controller).filter(Controller.id == cid).first()
    if not c:
        raise HTTPException(404, CONTROLLER_NOT_FOUND)
    end_schedules(db, c)
    db.delete(c)
    db.commit()
    return {"ok": True}

@router.get("/controllers/{cid}", response_model=ControllerOut, responses=responses(401, 404))
def get_controller(cid: int, db: DBSession, user: ViewUser):
    c = db.query(Controller).filter(Controller.id == cid).first()
    if not c:
        raise HTTPException(404, CONTROLLER_NOT_FOUND)
    return ControllerOut.model_validate(c)


@router.get("/controllers/{cid}/stats", responses=responses(401, 404))
def get_controller_stats(cid: int, db: DBSession, user: ViewUser):
    """Get basic stats for a controller. Flights do not record the controller
    flown with, so there are no flight figures to give."""
    ctrl = db.query(Controller).filter(Controller.id == cid).first()
    if not ctrl:
        raise HTTPException(404, CONTROLLER_NOT_FOUND)
    return {"assigned_pilot": ctrl.assigned_pilot_id}


class DockCreate(BaseModel):
    serial_number: str
    name: Optional[str] = None
    location_name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    status: str = "active"
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None

class DockUpdate(BaseModel):
    serial_number: Optional[str] = None
    name: Optional[str] = None
    location_name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    status: Optional[str] = None
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None

class DockOut(BaseModel):
    id: int
    serial_number: str
    name: Optional[str] = None
    location_name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    status: str
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None
    model_config = {"from_attributes": True}

@router.get("/docks", response_model=list[DockOut], responses=responses(401))
def list_docks(db: DBSession, user: ViewUser):
    return [DockOut.model_validate(d) for d in db.query(Dock).order_by(Dock.name).all()]

@router.post("/docks", response_model=DockOut, responses=responses(401))
def create_dock(data: DockCreate, db: DBSession, admin: ManageUser):
    d = Dock()
    _set_fields_with_lifecycle(d, data.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    return DockOut.model_validate(d)

@router.patch("/docks/{did}", response_model=DockOut, responses=responses(401, 404))
def update_dock(did: int, data: DockUpdate, db: DBSession, admin: ManageUser):
    d = db.query(Dock).filter(Dock.id == did).first()
    if not d:
        raise HTTPException(404, DOCK_NOT_FOUND)
    _set_fields_with_lifecycle(d, data.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(d)
    return DockOut.model_validate(d)

@router.delete("/docks/{did}", responses=responses(401, 404))
def delete_dock(did: int, db: DBSession, admin: ManageUser):
    d = db.query(Dock).filter(Dock.id == did).first()
    if not d:
        raise HTTPException(404, DOCK_NOT_FOUND)
    end_schedules(db, d)
    db.delete(d)
    db.commit()
    return {"ok": True}


@router.get("/docks/{did}", response_model=DockOut, responses=responses(401, 404))
def get_dock(did: int, db: DBSession, user: ViewUser):
    d = db.query(Dock).filter(Dock.id == did).first()
    if not d:
        raise HTTPException(404, DOCK_NOT_FOUND)
    return DockOut.model_validate(d)


@router.get("/docks/{did}/stats", responses=responses(401, 404))
def get_dock_stats(did: int, db: DBSession, user: ViewUser):
    """Get basic stats for a dock. Docks don't link to flights directly."""
    d = db.query(Dock).filter(Dock.id == did).first()
    if not d:
        raise HTTPException(404, DOCK_NOT_FOUND)
    return {"name": d.name, "location_name": d.location_name, "status": d.status}


class SensorCreate(BaseModel):
    serial_number: str
    name: Optional[str] = None
    type: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: str = "active"
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None

class SensorUpdate(BaseModel):
    serial_number: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None

class SensorOut(BaseModel):
    id: int
    serial_number: str
    name: Optional[str] = None
    type: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: str
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None
    model_config = {"from_attributes": True}

@router.get("/sensors", response_model=list[SensorOut], responses=responses(401))
def list_sensors(db: DBSession, user: ViewUser):
    return [SensorOut.model_validate(s) for s in db.query(SensorPackage).order_by(SensorPackage.name).all()]

@router.post("/sensors", response_model=SensorOut, responses=responses(401))
def create_sensor(data: SensorCreate, db: DBSession, admin: ManageUser):
    s = SensorPackage()
    _set_fields_with_lifecycle(s, data.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return SensorOut.model_validate(s)

@router.patch("/sensors/{sid}", response_model=SensorOut, responses=responses(401, 404))
def update_sensor(sid: int, data: SensorUpdate, db: DBSession, admin: ManageUser):
    s = db.query(SensorPackage).filter(SensorPackage.id == sid).first()
    if not s:
        raise HTTPException(404, SENSOR_NOT_FOUND)
    _set_fields_with_lifecycle(s, data.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(s)
    return SensorOut.model_validate(s)

@router.delete("/sensors/{sid}", responses=responses(401, 404))
def delete_sensor(sid: int, db: DBSession, admin: ManageUser):
    s = db.query(SensorPackage).filter(SensorPackage.id == sid).first()
    if not s:
        raise HTTPException(404, SENSOR_NOT_FOUND)
    end_schedules(db, s)
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.get("/sensors/{sid}", response_model=SensorOut, responses=responses(401, 404))
def get_sensor(sid: int, db: DBSession, user: ViewUser):
    s = db.query(SensorPackage).filter(SensorPackage.id == sid).first()
    if not s:
        raise HTTPException(404, SENSOR_NOT_FOUND)
    return SensorOut.model_validate(s)


@router.get("/sensors/{sid}/stats", responses=responses(401, 404))
def get_sensor_stats(sid: int, db: DBSession, user: ViewUser, _flights: FlightsViewUser):
    """Get flight stats for a sensor package."""
    from app.models.flight import Flight
    sensor = db.query(SensorPackage).filter(SensorPackage.id == sid).first()
    if not sensor:
        raise HTTPException(404, SENSOR_NOT_FOUND)
    flight_count = db.query(func.count(Flight.id)).filter(counted_flight_clause(), Flight.sensor_package == sensor.serial_number).scalar()
    total_seconds = db.query(func.coalesce(func.sum(Flight.duration_seconds), 0)).filter(counted_flight_clause(), Flight.sensor_package == sensor.serial_number).scalar()
    unique_pilots = db.query(func.count(func.distinct(Flight.pilot_id))).filter(counted_flight_clause(), Flight.sensor_package == sensor.serial_number).scalar()
    return {"total_flights": flight_count, "total_hours": round(total_seconds / 3600, 2), "unique_pilots": unique_pilots}


@router.get("/sensors/{sid}/flights", responses=responses(401, 404))
def get_sensor_flights(sid: int, db: DBSession, user: ViewUser, _flights: FlightsViewUser):
    """Get all flights that used a specific sensor package."""
    from app.models.flight import Flight
    from app.models.pilot import Pilot
    sensor = db.query(SensorPackage).filter(SensorPackage.id == sid).first()
    if not sensor:
        raise HTTPException(404, SENSOR_NOT_FOUND)
    flights = db.query(Flight).filter(Flight.sensor_package == sensor.serial_number).order_by(Flight.date.desc()).all()
    return [
        {
            "id": f.id,
            "date": str(f.date) if f.date else None,
            "pilot_name": f"{f.pilot.first_name} {f.pilot.last_name}" if f.pilot else None,
            "pilot_id": f.pilot_id,
            "vehicle_id": f.vehicle_id,
            "vehicle_name": f.vehicle.nickname or f"{f.vehicle.manufacturer} {f.vehicle.model}" if f.vehicle else None,
            "duration_seconds": f.duration_seconds,
            "takeoff_address": f.takeoff_address,
            "purpose": f.purpose,
            "max_altitude_m": f.max_altitude_m,
        }
        for f in flights
    ]


@router.get("/sensors/{sid}/pilots", responses=responses(401, 404))
def get_sensor_pilots(sid: int, db: DBSession, user: ViewUser, _flights: FlightsViewUser):
    """Get unique pilots who have used a specific sensor package."""
    from app.models.flight import Flight
    from app.models.pilot import Pilot
    sensor = db.query(SensorPackage).filter(SensorPackage.id == sid).first()
    if not sensor:
        raise HTTPException(404, SENSOR_NOT_FOUND)
    pilot_ids = db.query(Flight.pilot_id).filter(
        Flight.sensor_package == sensor.serial_number,
        Flight.pilot_id.isnot(None),
    ).distinct().all()
    pilots = db.query(Pilot).filter(Pilot.id.in_([p[0] for p in pilot_ids])).all()
    return [{"id": p.id, "name": f"{p.first_name} {p.last_name}", "badge_number": p.badge_number} for p in pilots]


class AttachmentCreate(BaseModel):
    serial_number: str
    name: Optional[str] = None
    type: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: str = "active"
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None

class AttachmentUpdate(BaseModel):
    serial_number: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None

class AttachmentOut(BaseModel):
    id: int
    serial_number: str
    name: Optional[str] = None
    type: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    status: str
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None
    model_config = {"from_attributes": True}

@router.get("/attachments", response_model=list[AttachmentOut], responses=responses(401))
def list_attachments(db: DBSession, user: ViewUser):
    return [AttachmentOut.model_validate(a) for a in db.query(Attachment).order_by(Attachment.name).all()]

@router.post("/attachments", response_model=AttachmentOut, responses=responses(401))
def create_attachment(data: AttachmentCreate, db: DBSession, admin: ManageUser):
    a = Attachment()
    _set_fields_with_lifecycle(a, data.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return AttachmentOut.model_validate(a)

@router.patch("/attachments/{aid}", response_model=AttachmentOut, responses=responses(401, 404))
def update_attachment(aid: int, data: AttachmentUpdate, db: DBSession, admin: ManageUser):
    a = db.query(Attachment).filter(Attachment.id == aid).first()
    if not a:
        raise HTTPException(404, ATTACHMENT_NOT_FOUND)
    _set_fields_with_lifecycle(a, data.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(a)
    return AttachmentOut.model_validate(a)

@router.delete("/attachments/{aid}", responses=responses(401, 404))
def delete_attachment(aid: int, db: DBSession, admin: ManageUser):
    a = db.query(Attachment).filter(Attachment.id == aid).first()
    if not a:
        raise HTTPException(404, ATTACHMENT_NOT_FOUND)
    end_schedules(db, a)
    db.delete(a)
    db.commit()
    return {"ok": True}


@router.get("/attachments/{aid}", response_model=AttachmentOut, responses=responses(401, 404))
def get_attachment(aid: int, db: DBSession, user: ViewUser):
    a = db.query(Attachment).filter(Attachment.id == aid).first()
    if not a:
        raise HTTPException(404, ATTACHMENT_NOT_FOUND)
    return AttachmentOut.model_validate(a)


@router.get("/attachments/{aid}/stats", responses=responses(401, 404))
def get_attachment_stats(aid: int, db: DBSession, user: ViewUser, _flights: FlightsViewUser):
    """Get flight stats for an attachment across all positions."""
    from app.models.flight import Flight
    from sqlalchemy import or_
    attachment = db.query(Attachment).filter(Attachment.id == aid).first()
    if not attachment:
        raise HTTPException(404, ATTACHMENT_NOT_FOUND)
    sn = attachment.serial_number
    attachment_filter = or_(
        Flight.attachment_top == sn,
        Flight.attachment_bottom == sn,
        Flight.attachment_left == sn,
        Flight.attachment_right == sn,
    )
    flight_count = db.query(func.count(Flight.id)).filter(counted_flight_clause(), attachment_filter).scalar()
    total_seconds = db.query(func.coalesce(func.sum(Flight.duration_seconds), 0)).filter(counted_flight_clause(), attachment_filter).scalar()
    unique_pilots = db.query(func.count(func.distinct(Flight.pilot_id))).filter(counted_flight_clause(), attachment_filter).scalar()
    return {"total_flights": flight_count, "total_hours": round(total_seconds / 3600, 2), "unique_pilots": unique_pilots}


def _attachment_flight_item(f, sn) -> dict:
    """Serialize one flight that used an attachment, listing the mount positions
    the attachment occupied on that flight."""
    positions = []
    if f.attachment_top == sn:
        positions.append("top")
    if f.attachment_bottom == sn:
        positions.append("bottom")
    if f.attachment_left == sn:
        positions.append("left")
    if f.attachment_right == sn:
        positions.append("right")
    return {
        "id": f.id,
        "date": str(f.date) if f.date else None,
        "pilot_name": f"{f.pilot.first_name} {f.pilot.last_name}" if f.pilot else None,
        "pilot_id": f.pilot_id,
        "vehicle_id": f.vehicle_id,
        "vehicle_name": f.vehicle.nickname or f"{f.vehicle.manufacturer} {f.vehicle.model}" if f.vehicle else None,
        "duration_seconds": f.duration_seconds,
        "takeoff_address": f.takeoff_address,
        "purpose": f.purpose,
        "max_altitude_m": f.max_altitude_m,
        "positions": positions,
    }


@router.get("/attachments/{aid}/flights", responses=responses(401, 404))
def get_attachment_flights(aid: int, db: DBSession, user: ViewUser, _flights: FlightsViewUser):
    """Get all flights that used a specific attachment, including which position."""
    from app.models.flight import Flight
    from app.models.pilot import Pilot
    from sqlalchemy import or_
    attachment = db.query(Attachment).filter(Attachment.id == aid).first()
    if not attachment:
        raise HTTPException(404, ATTACHMENT_NOT_FOUND)
    sn = attachment.serial_number
    attachment_filter = or_(
        Flight.attachment_top == sn,
        Flight.attachment_bottom == sn,
        Flight.attachment_left == sn,
        Flight.attachment_right == sn,
    )
    flights = db.query(Flight).filter(attachment_filter).order_by(Flight.date.desc()).all()
    return [_attachment_flight_item(f, sn) for f in flights]


@router.get("/attachments/{aid}/pilots", responses=responses(401, 404))
def get_attachment_pilots(aid: int, db: DBSession, user: ViewUser, _flights: FlightsViewUser):
    """Get unique pilots who have used a specific attachment."""
    from app.models.flight import Flight
    from app.models.pilot import Pilot
    from sqlalchemy import or_
    attachment = db.query(Attachment).filter(Attachment.id == aid).first()
    if not attachment:
        raise HTTPException(404, ATTACHMENT_NOT_FOUND)
    sn = attachment.serial_number
    attachment_filter = or_(
        Flight.attachment_top == sn,
        Flight.attachment_bottom == sn,
        Flight.attachment_left == sn,
        Flight.attachment_right == sn,
    )
    pilot_ids = db.query(Flight.pilot_id).filter(
        attachment_filter,
        Flight.pilot_id.isnot(None),
    ).distinct().all()
    pilots = db.query(Pilot).filter(Pilot.id.in_([p[0] for p in pilot_ids])).all()
    return [{"id": p.id, "name": f"{p.first_name} {p.last_name}", "badge_number": p.badge_number} for p in pilots]


class OtherEquipmentCreate(BaseModel):
    name: str
    category: Optional[str] = None
    serial_number: Optional[str] = None
    status: str = "active"
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None

class OtherEquipmentUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    serial_number: Optional[str] = None
    status: Optional[str] = None
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None

class OtherEquipmentOut(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    serial_number: Optional[str] = None
    status: str
    acquired_date: Optional[date] = None
    decommissioned_date: Optional[date] = None
    notes: Optional[str] = None
    model_config = {"from_attributes": True}

@router.get("/other-equipment", response_model=list[OtherEquipmentOut], responses=responses(401))
def list_other_equipment(db: DBSession, user: ViewUser):
    return [OtherEquipmentOut.model_validate(o) for o in db.query(OtherEquipment).order_by(OtherEquipment.name).all()]

@router.post("/other-equipment", response_model=OtherEquipmentOut, responses=responses(401))
def create_other_equipment(data: OtherEquipmentCreate, db: DBSession, admin: ManageUser):
    o = OtherEquipment()
    _set_fields_with_lifecycle(o, data.model_dump())
    db.add(o)
    db.commit()
    db.refresh(o)
    return OtherEquipmentOut.model_validate(o)

@router.patch("/other-equipment/{oid}", response_model=OtherEquipmentOut, responses=responses(401, 404))
def update_other_equipment(oid: int, data: OtherEquipmentUpdate, db: DBSession, admin: ManageUser):
    o = db.query(OtherEquipment).filter(OtherEquipment.id == oid).first()
    if not o:
        raise HTTPException(404, OTHER_EQUIPMENT_NOT_FOUND)
    _set_fields_with_lifecycle(o, data.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(o)
    return OtherEquipmentOut.model_validate(o)

@router.delete("/other-equipment/{oid}", responses=responses(401, 404))
def delete_other_equipment(oid: int, db: DBSession, admin: ManageUser):
    o = db.query(OtherEquipment).filter(OtherEquipment.id == oid).first()
    if not o:
        raise HTTPException(404, OTHER_EQUIPMENT_NOT_FOUND)
    end_schedules(db, o)
    db.delete(o)
    db.commit()
    return {"ok": True}

@router.get("/other-equipment/{oid}", response_model=OtherEquipmentOut, responses=responses(401, 404))
def get_other_equipment(oid: int, db: DBSession, user: ViewUser):
    o = db.query(OtherEquipment).filter(OtherEquipment.id == oid).first()
    if not o:
        raise HTTPException(404, OTHER_EQUIPMENT_NOT_FOUND)
    return OtherEquipmentOut.model_validate(o)
