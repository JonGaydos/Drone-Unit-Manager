"""Parser for Parrot Drones GUTMA DX JSON flight logs (e.g. ANAFI exports).

Returns the same {metadata, telemetry, error} shape used by the other
flight-log parsers, so flight_log_import.import_flight_log can create the
Flight + TelemetryPoint records with shared dedup/vehicle-match logic.
"""
import json
import math
from datetime import datetime, timedelta
from typing import Optional


def _to_float(val) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_int(val) -> Optional[int]:
    f = _to_float(val)
    return int(f) if f is not None else None


def is_gutma(text: str) -> bool:
    """Cheap content check for a Parrot/GUTMA DX JSON log."""
    return "GUTMA_DX_JSON" in text or "flight_logging_keys" in text


def _gutma_msg(text: str):
    """Decode the GUTMA envelope. Returns (fdata, flog) on success, or a
    string error message on failure."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return "Invalid JSON"
    try:
        msg = data["exchange"]["message"]
        return msg["flight_data"], msg["flight_logging"]
    except (KeyError, TypeError):
        return "Not a GUTMA flight log"


def _gutma_start_local(flog):
    """Parse logging_start_dtg into a naive (local wall-clock) datetime."""
    raw = flog.get("logging_start_dtg")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).replace(tzinfo=None)
    except ValueError:
        return None


def _gutma_event_ts(events, info: str, last: bool = False):
    """First (or last) timestamp from events whose event_info matches `info`."""
    matches = [
        _to_float(e.get("event_timestamp"))
        for e in events
        if e.get("event_info") == info and e.get("event_timestamp") is not None
    ]
    matches = [m for m in matches if m is not None]
    if not matches:
        return None
    return matches[-1] if last else matches[0]


def _gutma_times(flog, items, col):
    """Derive (takeoff_ts, landing_ts, duration_seconds) from events with a
    telemetry fallback. duration is None when boundaries can't be ordered."""
    events = flog.get("events") or []
    first_ts = _to_float(col(items[0], "timestamp")) or 0.0
    last_ts = _to_float(col(items[-1], "timestamp")) or first_ts
    tof_ts = _gutma_event_ts(events, "TOF")
    lnd_ts = _gutma_event_ts(events, "LND", last=True)
    takeoff_ts = tof_ts if tof_ts is not None else first_ts
    landing_ts = lnd_ts if (lnd_ts is not None and lnd_ts > takeoff_ts) else last_ts
    duration = int(round(landing_ts - takeoff_ts)) if landing_ts > takeoff_ts else None
    return takeoff_ts, landing_ts, duration


def _gutma_gps_coord(row, col):
    """Return (lat, lon) only for a real GPS fix, else (None, None).

    Parrot encodes "no fix" as lat/lon = 500 and leaves product_gps_available
    at 0, so unfixed rows must be dropped or they plot off the map.
    """
    if col(row, "product_gps_available") != 1:
        return None, None
    lat = _to_float(col(row, "gps_lat"))
    lon = _to_float(col(row, "gps_lon"))
    if not lat or not lon or abs(lat) > 90 or abs(lon) > 180:
        return None, None
    return lat, lon


def _first_valid_fix(rows_iter, col):
    """First (lat, lon) where the row has a valid GPS fix; (None, None) otherwise."""
    return next(
        ((la, lo) for la, lo in (_gutma_gps_coord(r, col) for r in rows_iter) if la is not None),
        (None, None),
    )


def _gutma_telemetry_point(row, col, start_local):
    """Build one telemetry-point dict from a GUTMA row."""
    ts = _to_float(col(row, "timestamp")) or 0.0
    ato = _to_float(col(row, "altitude_ato"))
    vx = _to_float(col(row, "speed_vx")) or 0.0
    vy = _to_float(col(row, "speed_vy")) or 0.0
    psi = _to_float(col(row, "angle_psi"))
    heading = (math.degrees(psi) % 360 + 360) % 360 if psi is not None else None
    battery = _to_float(col(row, "battery_percent"))
    if battery is not None and battery < 0:
        battery = None
    lat, lon = _gutma_gps_coord(row, col)
    return {
        "timestamp": start_local + timedelta(seconds=ts) if start_local else None,
        "lat": lat,
        "lon": lon,
        "altitude_m": ato,
        "speed_mps": math.hypot(vx, vy),
        "battery_pct": battery,
        "heading_deg": heading,
        "satellites": _to_int(col(row, "product_gps_sat_used_count")),
        "extra_data": {
            "battery_voltage": _to_float(col(row, "battery_voltage")),
            "gps_amsl_altitude": _to_float(col(row, "gps_amsl_altitude")),
        },
    }


def _gutma_telemetry_and_maxes(items, col, start_local):
    """Walk every row producing the telemetry list while tracking running
    max altitude (above-takeoff) and max horizontal speed."""
    telemetry = []
    max_alt = 0.0
    max_speed = 0.0
    for row in items:
        pt = _gutma_telemetry_point(row, col, start_local)
        ato = pt["altitude_m"]
        if ato is not None and ato > max_alt:
            max_alt = ato
        if pt["speed_mps"] > max_speed:
            max_speed = pt["speed_mps"]
        telemetry.append(pt)
    return telemetry, max_alt, max_speed


def parse_gutma(text: str) -> dict:
    """Parse a Parrot/GUTMA DX JSON flight log.

    Returns {"metadata": dict, "telemetry": list, "error": str | None}.
    """
    parsed = _gutma_msg(text)
    if isinstance(parsed, str):
        return {"metadata": {}, "telemetry": [], "error": parsed}
    fdata, flog = parsed

    keys = flog.get("flight_logging_keys") or []
    items = flog.get("flight_logging_items") or []
    if not keys or not items:
        return {"metadata": {}, "telemetry": [], "error": "No telemetry in GUTMA log"}

    idx = {k: i for i, k in enumerate(keys)}

    def col(row, name):
        i = idx.get(name)
        if i is None or i >= len(row):
            return None
        return row[i]

    start_local = _gutma_start_local(flog)
    takeoff_ts, landing_ts, duration = _gutma_times(flog, items, col)

    takeoff_time = start_local + timedelta(seconds=takeoff_ts) if start_local else None
    landing_time = start_local + timedelta(seconds=landing_ts) if start_local else None
    flight_date = takeoff_time.date() if takeoff_time else None

    takeoff_lat, takeoff_lon = _first_valid_fix(items, col)
    landing_lat, landing_lon = _first_valid_fix(reversed(items), col)

    telemetry, max_alt, max_speed = _gutma_telemetry_and_maxes(items, col, start_local)

    aircraft = fdata.get("aircraft") or {}
    payloads = fdata.get("payload") or []
    sensor_serial = payloads[0].get("serial_number") if payloads else None
    metadata = {
        "external_id": fdata.get("flight_id"),
        "vehicle_serial": aircraft.get("serial_number"),
        "sensor_package": sensor_serial,
        "date": flight_date,
        "takeoff_time": takeoff_time,
        "landing_time": landing_time,
        "duration_seconds": duration,
        "takeoff_lat": takeoff_lat,
        "takeoff_lon": takeoff_lon,
        "landing_lat": landing_lat,
        "landing_lon": landing_lon,
        "max_altitude_m": max_alt if max_alt > 0 else None,
        "max_speed_mps": max_speed if max_speed > 0 else None,
    }
    return {"metadata": metadata, "telemetry": telemetry, "error": None}
