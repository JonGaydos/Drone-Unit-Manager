"""Telemetry data endpoints for flight path and sensor visualization."""

from fastapi import APIRouter, HTTPException

from app.deps import DBSession, TelemetryDBSession, CurrentUser
from app.models.flight import Flight
from app.models.telemetry import TelemetryPoint
from app.responses import responses

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


def _avg(values):
    """Average a list of numbers, ignoring None values."""
    valid = [v for v in values if v is not None]
    return round(sum(valid) / len(valid), 2) if valid else None


def _downsample_with_averaging(points, max_points):
    """Downsample telemetry by averaging values within each bucket.

    Unlike simple every-Nth-point sampling, averaging smooths sensor noise
    and prevents altitude oscillation artifacts in charts.

    Args:
        points: List of TelemetryPoint ORM objects, ordered by timestamp.
        max_points: Target number of output points.

    Returns:
        List of dicts with averaged telemetry values.
    """
    if len(points) <= max_points:
        return None  # No downsampling needed

    base_ts = points[0].timestamp_ms
    bucket_size = len(points) / max_points
    result = []

    for i in range(max_points):
        start = int(i * bucket_size)
        end = int((i + 1) * bucket_size)
        bucket = points[start:end]
        if not bucket:
            continue

        # Use the middle point's timestamp and position for the bucket
        mid = bucket[len(bucket) // 2]

        result.append({
            "timestamp_ms": mid.timestamp_ms,
            "elapsed_s": round((mid.timestamp_ms - base_ts) / 1000, 1),
            "lat": mid.lat,
            "lon": mid.lon,
            "altitude_m": _avg([p.altitude_m for p in bucket]),
            "speed_mps": _avg([p.speed_mps for p in bucket]),
            "battery_pct": _avg([p.battery_pct for p in bucket]),
            "battery_voltage": _avg([p.battery_voltage for p in bucket]),
            "heading_deg": mid.heading_deg and round(mid.heading_deg, 1),
            "pitch_deg": mid.pitch_deg and round(mid.pitch_deg, 1),
            "roll_deg": mid.roll_deg and round(mid.roll_deg, 1),
            "satellites": mid.satellites,
        })

    return result


@router.get("/flight/{flight_id}", responses=responses(404))
def get_flight_telemetry(
    flight_id: int,
    db: DBSession,
    tdb: TelemetryDBSession,
    user: CurrentUser,
    max_points: int = 2000):
    """Get telemetry data points for a specific flight.

    Returns up to max_points telemetry records. When the flight has more
    points than the limit, uses bucket-averaging to smooth the data
    rather than simple every-Nth-point sampling (which amplifies noise).

    Args:
        flight_id: The flight record ID.
        max_points: Maximum number of points to return (default 2000).

    Returns:
        List of telemetry data points with elapsed_s timestamps.
    """
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")

    points = tdb.query(TelemetryPoint).filter(
        TelemetryPoint.flight_id == flight_id
    ).order_by(TelemetryPoint.timestamp_ms).all()

    if not points:
        return []

    # Use bucket averaging for downsampling (smooths sensor noise)
    averaged = _downsample_with_averaging(points, max_points)
    if averaged is not None:
        return averaged

    # No downsampling needed — return raw points
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
