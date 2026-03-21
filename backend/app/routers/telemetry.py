from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db, get_telemetry_db
from app.models.flight import Flight
from app.models.telemetry import TelemetryPoint
from app.models.user import User
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/flight/{flight_id}")
def get_flight_telemetry(
    flight_id: int,
    db: Session = Depends(get_db),
    tdb: Session = Depends(get_telemetry_db),
    user: User = Depends(get_current_user),
):
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")

    points = tdb.query(TelemetryPoint).filter(
        TelemetryPoint.flight_id == flight_id
    ).order_by(TelemetryPoint.timestamp_ms).all()

    if not points:
        return []

    print(f"[TELEM-API] Flight {flight_id}: {len(points)} points, first ts_ms={points[0].timestamp_ms}, alt={points[0].altitude_m}, speed={points[0].speed_mps}, battery={points[0].battery_pct}", flush=True)
    if len(points) > 100:
        mid = points[len(points)//2]
        print(f"[TELEM-API] Mid point: ts_ms={mid.timestamp_ms}, alt={mid.altitude_m}, speed={mid.speed_mps}", flush=True)

    base_ts = points[0].timestamp_ms
    return [
        {
            "timestamp_ms": p.timestamp_ms,
            "elapsed_s": round((p.timestamp_ms - base_ts) / 1000, 1),
            "lat": p.lat,
            "lon": p.lon,
            "altitude_m": round(p.altitude_m, 1) if p.altitude_m else None,
            "speed_mps": round(p.speed_mps, 1) if p.speed_mps else None,
            "battery_pct": round(p.battery_pct, 1) if p.battery_pct else None,
            "battery_voltage": round(p.battery_voltage, 2) if p.battery_voltage else None,
            "heading_deg": round(p.heading_deg, 1) if p.heading_deg else None,
            "pitch_deg": round(p.pitch_deg, 1) if p.pitch_deg else None,
            "roll_deg": round(p.roll_deg, 1) if p.roll_deg else None,
            "satellites": p.satellites,
        }
        for p in points
    ]
