"""Flight log import service for DJI, Litchi, and Airdata CSV formats.

Parses flight log files, extracts metadata and telemetry, creates Flight
records in the main database and TelemetryPoint records in the telemetry database.
Provider-specific telemetry fields are stored in the extra_data JSON column.
"""

import csv
import io
import json
import logging
from datetime import datetime, date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.flight import Flight
from app.models.telemetry import TelemetryPoint

logger = logging.getLogger(__name__)

# Standard telemetry fields mapped to our fixed columns
STANDARD_FIELDS = {"lat", "lon", "altitude_m", "speed_mps", "battery_pct", "heading_deg",
                   "pitch_deg", "roll_deg", "satellites", "battery_voltage"}


def detect_format(content: str) -> str:
    """Auto-detect the flight log format from file content.

    Args:
        content: The raw text content of the uploaded file.

    Returns:
        Format identifier: "dji", "litchi", "airdata", "airdata_json", or "unknown".
    """
    # Check for Airdata JSON format (starts with { and has flight_telemetry)
    if content.strip().startswith('{'):
        try:
            import json as _json
            peek = _json.loads(content[:5000] if len(content) > 5000 else content)
            if isinstance(peek, dict) and "data" in peek:
                inner = peek["data"]
                if isinstance(inner, dict) and "flight_telemetry" in inner:
                    return "airdata_json"
        except (ValueError, KeyError):
            pass

    first_lines = content[:2000].lower()

    if "datetime(utc)" in first_lines and "osd.latitude" in first_lines:
        return "dji"
    if "latitude" in first_lines and "litchi" in first_lines:
        return "litchi"
    if "height_above_takeoff(feet)" in first_lines:
        return "airdata"
    if "aircraft_name" in first_lines or "airdata" in first_lines:
        return "airdata"

    # Check for common CSV header patterns
    if "latitude" in first_lines and "longitude" in first_lines:
        if "altitude(feet)" in first_lines or "altitude(m)" in first_lines:
            return "airdata"
        return "litchi"

    return "unknown"


def _parse_float(val) -> Optional[float]:
    """Safely parse a float value, returning None on failure."""
    if val is None or val == "" or val == "N/A":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_int(val) -> Optional[int]:
    """Safely parse an integer value, returning None on failure."""
    if val is None or val == "" or val == "N/A":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _parse_timestamp(val) -> Optional[datetime]:
    """Parse various timestamp formats into a datetime object."""
    if not val:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
    ):
        try:
            return datetime.strptime(str(val).strip(), fmt)
        except ValueError:
            continue
    return None


def parse_dji_txt(content: str) -> dict:
    """Parse a DJI Go 4 .txt flight log.

    DJI logs are tab-separated with columns like:
    CUSTOM.date, OSD.latitude, OSD.longitude, OSD.altitude [m], etc.

    Args:
        content: Raw text content of the .txt file.

    Returns:
        Dict with 'metadata' and 'telemetry' keys.
    """
    lines = content.strip().split("\n")
    if len(lines) < 2:
        return {"metadata": {}, "telemetry": [], "error": "File too short"}

    # Parse header
    headers = lines[0].strip().split("\t")
    header_map = {h.strip().lower(): i for i, h in enumerate(headers)}

    # Column name mappings (DJI uses various naming conventions)
    col_mappings = {
        "timestamp": ["custom.date", "datetime(utc)", "time(millisecond)"],
        "lat": ["osd.latitude", "latitude", "osd.lati"],
        "lon": ["osd.longitude", "longitude", "osd.longi"],
        "alt": ["osd.altitude [m]", "osd.altitude(m)", "altitude [m]", "osd.height [m]"],
        "speed": ["osd.xspeed [m/s]", "osd.hspeed [m/s]", "speed(m/s)"],
        "battery": ["battery:level[%]", "battery:rsoc[%]", "osd.flyc_state.gps_level"],
        "heading": ["osd.yaw", "compass_heading(degrees)"],
        "satellites": ["osd.flyc_state.gps_num", "satellites"],
        "gimbal_pitch": ["gimbal.pitch", "gimbal_heading(degrees)"],
        "gimbal_roll": ["gimbal.roll"],
        "gimbal_yaw": ["gimbal.yaw"],
        "flight_mode": ["osd.flyc_state", "flycstate"],
    }

    def find_col(field_name):
        for candidate in col_mappings.get(field_name, []):
            if candidate in header_map:
                return header_map[candidate]
        return None

    ts_col = find_col("timestamp")
    lat_col = find_col("lat")
    lon_col = find_col("lon")
    alt_col = find_col("alt")
    speed_col = find_col("speed")
    bat_col = find_col("battery")
    heading_col = find_col("heading")
    sat_col = find_col("satellites")
    gimbal_pitch_col = find_col("gimbal_pitch")
    gimbal_roll_col = find_col("gimbal_roll")
    gimbal_yaw_col = find_col("gimbal_yaw")
    flight_mode_col = find_col("flight_mode")

    if lat_col is None or lon_col is None:
        return {"metadata": {}, "telemetry": [], "error": "Could not find latitude/longitude columns"}

    telemetry = []
    first_ts = None
    max_alt = 0
    max_speed = 0
    first_lat = None
    first_lon = None

    for line in lines[1:]:
        cols = line.strip().split("\t")
        if len(cols) < max(lat_col, lon_col) + 1:
            continue

        lat = _parse_float(cols[lat_col])
        lon = _parse_float(cols[lon_col])
        if lat is None or lon is None or (lat == 0 and lon == 0):
            continue

        alt = _parse_float(cols[alt_col]) if alt_col is not None else None
        speed = _parse_float(cols[speed_col]) if speed_col is not None else None
        battery = _parse_float(cols[bat_col]) if bat_col is not None else None
        heading = _parse_float(cols[heading_col]) if heading_col is not None else None
        sats = _parse_int(cols[sat_col]) if sat_col is not None else None

        ts = None
        if ts_col is not None:
            ts = _parse_timestamp(cols[ts_col])

        if first_ts is None and ts:
            first_ts = ts
        if first_lat is None:
            first_lat = lat
            first_lon = lon
        if alt and alt > max_alt:
            max_alt = alt
        if speed and speed > max_speed:
            max_speed = speed

        # Provider-specific extra data
        extra = {}
        if gimbal_pitch_col is not None:
            extra["gimbal_pitch"] = _parse_float(cols[gimbal_pitch_col])
        if gimbal_roll_col is not None:
            extra["gimbal_roll"] = _parse_float(cols[gimbal_roll_col])
        if gimbal_yaw_col is not None:
            extra["gimbal_yaw"] = _parse_float(cols[gimbal_yaw_col])
        if flight_mode_col is not None:
            extra["flight_mode"] = cols[flight_mode_col] if flight_mode_col < len(cols) else None
        # Remove None values
        extra = {k: v for k, v in extra.items() if v is not None}

        point = {
            "lat": lat,
            "lon": lon,
            "altitude_m": alt,
            "speed_mps": speed,
            "battery_pct": battery,
            "heading_deg": heading,
            "satellites": sats,
            "timestamp": ts,
            "extra_data": extra if extra else None,
        }
        telemetry.append(point)

    # Compute duration
    duration = None
    if telemetry and telemetry[0].get("timestamp") and telemetry[-1].get("timestamp"):
        duration = int((telemetry[-1]["timestamp"] - telemetry[0]["timestamp"]).total_seconds())

    metadata = {
        "takeoff_time": first_ts,
        "date": first_ts.date() if first_ts else None,
        "duration_seconds": duration,
        "max_altitude_m": max_alt if max_alt > 0 else None,
        "max_speed_mps": max_speed if max_speed > 0 else None,
        "takeoff_lat": first_lat,
        "takeoff_lon": first_lon,
    }

    return {"metadata": metadata, "telemetry": telemetry, "error": None}


def parse_csv_log(content: str, format_type: str) -> dict:
    """Parse a CSV flight log (Litchi or Airdata format).

    Args:
        content: Raw CSV text content.
        format_type: "litchi" or "airdata".

    Returns:
        Dict with 'metadata' and 'telemetry' keys.
    """
    reader = csv.DictReader(io.StringIO(content))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]

    if not headers:
        return {"metadata": {}, "telemetry": [], "error": "No CSV headers found"}

    # Flexible column mapping for both formats
    def find(candidates):
        for c in candidates:
            for h in reader.fieldnames or []:
                if c in h.lower():
                    return h
        return None

    lat_col = find(["latitude", "lat"])
    lon_col = find(["longitude", "lon", "lng"])
    alt_col = find(["altitude(m)", "altitude [m]", "altitude_m", "height_above_takeoff", "height"])
    speed_col = find(["speed(m/s)", "speed_mph", "groundspeed"])
    bat_col = find(["battery(%)", "batterylevel", "battery_percent", "battery_level"])
    heading_col = find(["heading", "compass_heading", "yaw"])
    ts_col = find(["datetime", "timestamp", "time", "date_time"])

    if lat_col is None or lon_col is None:
        return {"metadata": {}, "telemetry": [], "error": "Could not find latitude/longitude columns"}

    telemetry = []
    first_ts = None
    max_alt = 0
    max_speed = 0
    first_lat = None
    first_lon = None

    for row in reader:
        lat = _parse_float(row.get(lat_col))
        lon = _parse_float(row.get(lon_col))
        if lat is None or lon is None or (lat == 0 and lon == 0):
            continue

        alt = _parse_float(row.get(alt_col)) if alt_col else None
        # Convert feet to meters if Airdata CSV (column names include units)
        if alt is not None and alt_col and 'feet' in alt_col.lower():
            alt = alt / 3.28084

        speed = _parse_float(row.get(speed_col)) if speed_col else None

        # Convert mph to m/s if speed column indicates mph
        if speed is not None and speed_col and 'mph' in speed_col.lower():
            speed = speed * 0.44704

        battery = _parse_float(row.get(bat_col)) if bat_col else None
        heading = _parse_float(row.get(heading_col)) if heading_col else None

        ts = _parse_timestamp(row.get(ts_col)) if ts_col else None
        if first_ts is None and ts:
            first_ts = ts
        if first_lat is None:
            first_lat = lat
            first_lon = lon
        if alt and alt > max_alt:
            max_alt = alt
        if speed and speed > max_speed:
            max_speed = speed

        # Collect all non-standard columns as extra_data
        extra = {}
        for key, value in row.items():
            k_lower = key.lower().strip()
            if k_lower in {"latitude", "longitude", "lat", "lon", "lng"}:
                continue
            if key in {lat_col, lon_col, alt_col, speed_col, bat_col, heading_col, ts_col}:
                continue
            parsed = _parse_float(value)
            if parsed is not None:
                extra[key] = parsed
            elif value and value.strip():
                extra[key] = value.strip()

        # Airdata-specific extra fields
        airdata_extra_fields = {
            'gimbal_heading(degrees)': 'gimbal_heading',
            'gimbal_pitch(degrees)': 'gimbal_pitch',
            'gimbal_roll(degrees)': 'gimbal_roll',
            'rc_elevator(percent)': 'rc_elevator_pct',
            'rc_aileron(percent)': 'rc_aileron_pct',
            'rc_throttle(percent)': 'rc_throttle_pct',
            'rc_rudder(percent)': 'rc_rudder_pct',
            'battery_temperature(f)': 'battery_temperature_f',
            'current(a)': 'current_a',
            'flycstate': 'flight_mode',
            'isphotograph': 'is_photo',
            'isvideo': 'is_video',
        }
        for csv_key, extra_key in airdata_extra_fields.items():
            for header in (reader.fieldnames or []):
                if header.lower().strip() == csv_key:
                    val = row.get(header)
                    if val and val.strip():
                        parsed_val = _parse_float(val)
                        extra[extra_key] = parsed_val if parsed_val is not None else val.strip()
                    break

        # Limit extra_data size
        if len(extra) > 30:
            extra = dict(list(extra.items())[:30])

        point = {
            "lat": lat,
            "lon": lon,
            "altitude_m": alt,
            "speed_mps": speed,
            "battery_pct": battery,
            "heading_deg": heading,
            "timestamp": ts,
            "extra_data": extra if extra else None,
        }
        telemetry.append(point)

    duration = None
    if telemetry and telemetry[0].get("timestamp") and telemetry[-1].get("timestamp"):
        duration = int((telemetry[-1]["timestamp"] - telemetry[0]["timestamp"]).total_seconds())

    metadata = {
        "takeoff_time": first_ts,
        "date": first_ts.date() if first_ts else None,
        "duration_seconds": duration,
        "max_altitude_m": max_alt if max_alt > 0 else None,
        "max_speed_mps": max_speed if max_speed > 0 else None,
        "takeoff_lat": first_lat,
        "takeoff_lon": first_lon,
    }

    return {"metadata": metadata, "telemetry": telemetry, "error": None}


def parse_airdata_json(content: str) -> dict:
    """Parse an Airdata.com JSON export file.

    Airdata JSON uses channel-based telemetry with separate arrays for each sensor.
    Converts to point-based format for storage.

    Args:
        content: Raw JSON text content.

    Returns:
        Dict with 'metadata', 'telemetry', and 'error' keys.
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return {"metadata": {}, "telemetry": [], "error": f"Invalid JSON: {e}"}

    flight = data.get("data", {}).get("flight", {})
    ft = data.get("data", {}).get("flight_telemetry", {})

    if not flight:
        return {"metadata": {}, "telemetry": [], "error": "No flight data found"}

    # Extract flight metadata
    takeoff_time = _parse_timestamp(flight.get("takeoff"))
    landing_time = _parse_timestamp(flight.get("landing"))
    duration = None
    if takeoff_time and landing_time:
        duration = int((landing_time - takeoff_time).total_seconds())

    metadata = {
        "external_id": flight.get("flight_id"),
        "takeoff_time": takeoff_time,
        "date": takeoff_time.date() if takeoff_time else None,
        "duration_seconds": duration,
        "takeoff_lat": flight.get("takeoff_latitude"),
        "takeoff_lon": flight.get("takeoff_longitude"),
        "vehicle_serial": flight.get("vehicle_serial"),
        "battery_serial": flight.get("battery_serial"),
        "user_email": flight.get("user_email"),
    }

    if not ft:
        return {"metadata": metadata, "telemetry": [], "error": None}

    # Extract channel data
    gps_data = ft.get("gps", {}).get("data", [])
    gps_ts = ft.get("gps", {}).get("timestamps", [])
    hat_data = ft.get("height_above_takeoff", {}).get("data", [])
    bat_data = ft.get("battery_percentage", {}).get("data", [])
    vel_data = ft.get("velocity", {}).get("data", [])
    sat_data = ft.get("gps_num_satellites", {}).get("data", [])

    # Use GPS timestamps as the primary time axis
    if not gps_data or not gps_ts:
        return {"metadata": metadata, "telemetry": [], "error": "No GPS data in telemetry"}

    import math

    # Build timestamp lookup maps for non-GPS channels (index by position since counts may differ)
    num_points = len(gps_data)
    telemetry = []
    max_alt = 0
    max_speed = 0

    for i in range(num_points):
        lat, lon = gps_data[i] if i < len(gps_data) else (None, None)
        if lat is None or lon is None:
            continue

        ts = _parse_timestamp(gps_ts[i]) if i < len(gps_ts) else None

        # Altitude: height_above_takeoff is in METERS in JSON format
        alt = hat_data[i] if i < len(hat_data) else None

        # Battery: Airdata stores as 0-1 fraction
        battery = bat_data[i] if i < len(bat_data) else None
        if battery is not None and battery <= 1.0:
            battery = round(battery * 100, 1)

        # Speed: magnitude of velocity vector [vx, vy, vz]
        speed = None
        if i < len(vel_data) and isinstance(vel_data[i], list) and len(vel_data[i]) >= 2:
            speed = round(math.sqrt(sum(v**2 for v in vel_data[i][:3])), 2)

        sats = sat_data[i] if i < len(sat_data) else None

        if alt is not None and alt > max_alt:
            max_alt = alt
        if speed is not None and speed > max_speed:
            max_speed = speed

        telemetry.append({
            "lat": lat,
            "lon": lon,
            "altitude_m": round(alt, 2) if alt is not None else None,
            "speed_mps": speed,
            "battery_pct": battery,
            "heading_deg": None,
            "satellites": sats,
            "timestamp": ts,
            "extra_data": None,
        })

    metadata["max_altitude_m"] = max_alt if max_alt > 0 else None
    metadata["max_speed_mps"] = max_speed if max_speed > 0 else None

    return {"metadata": metadata, "telemetry": telemetry, "error": None}


def import_flight_log(
    content: bytes,
    db: Session,
    telemetry_db: Session,
    format_hint: str = "auto",
    user_id: int = None,
) -> dict:
    """Parse a flight log file and create Flight + TelemetryPoint records.

    Args:
        content: Raw bytes of the uploaded file.
        db: Main database session.
        telemetry_db: Telemetry database session.
        format_hint: Format hint ("dji", "litchi", "airdata", "auto").
        user_id: ID of the user performing the import.

    Returns:
        Dict with flight_id, points_imported, data_source, and any errors.
    """
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        return {"error": "Could not decode file as text", "flight_id": None, "points_imported": 0}

    # Detect format
    fmt = format_hint if format_hint != "auto" else detect_format(text)

    if fmt == "dji":
        result = parse_dji_txt(text)
        data_source = "dji_log"
    elif fmt == "airdata_json":
        result = parse_airdata_json(text)
        data_source = "airdata_json"
    elif fmt in ("litchi", "airdata"):
        result = parse_csv_log(text, fmt)
        data_source = f"{fmt}_csv"
    elif fmt == "unknown":
        # Try CSV as fallback
        result = parse_csv_log(text, "airdata")
        data_source = "csv_import"
        if result.get("error"):
            return {"error": f"Could not detect file format. {result['error']}", "flight_id": None, "points_imported": 0}
    else:
        return {"error": f"Unsupported format: {fmt}", "flight_id": None, "points_imported": 0}

    if result.get("error"):
        return {"error": result["error"], "flight_id": None, "points_imported": 0}

    meta = result["metadata"]
    telemetry = result["telemetry"]

    if not telemetry:
        return {"error": "No telemetry points found in file", "flight_id": None, "points_imported": 0}

    # Deduplication: check if flight already exists by external_id
    if meta.get("external_id"):
        from sqlalchemy import func
        ext_id = str(meta["external_id"]).upper().replace("-", "")
        existing = db.query(Flight).filter(
            func.replace(func.upper(Flight.external_id), "-", "") == ext_id
        ).first()
        if existing:
            return {
                "flight_id": existing.id,
                "points_imported": 0,
                "data_source": data_source,
                "format_detected": fmt,
                "date": str(meta.get("date")) if meta.get("date") else None,
                "duration_seconds": meta.get("duration_seconds"),
                "error": None,
                "skipped": True,
                "message": "Flight already exists (duplicate external_id)",
            }

    # Create flight record
    flight = Flight(
        date=meta.get("date"),
        takeoff_time=meta.get("takeoff_time"),
        duration_seconds=meta.get("duration_seconds"),
        max_altitude_m=meta.get("max_altitude_m"),
        max_speed_mps=meta.get("max_speed_mps"),
        takeoff_lat=meta.get("takeoff_lat"),
        takeoff_lon=meta.get("takeoff_lon"),
        data_source=data_source,
        has_telemetry=True,
        telemetry_synced=True,
        review_status="needs_review",
        pilot_confirmed=False,
        created_by_id=user_id,
    )
    if meta.get("external_id"):
        flight.external_id = meta["external_id"]
    if meta.get("battery_serial"):
        flight.battery_serial = meta["battery_serial"]
    if meta.get("vehicle_serial"):
        # Try to match to existing vehicle
        from app.models.vehicle import Vehicle
        v = db.query(Vehicle).filter(
            (Vehicle.provider_serial == meta["vehicle_serial"]) |
            (Vehicle.serial_number == meta["vehicle_serial"])
        ).first()
        if v:
            flight.vehicle_id = v.id

    db.add(flight)
    db.flush()

    # Auto-tag the flight
    from app.services.flight_tagger import compute_flight_tags
    tags = compute_flight_tags(flight)
    if tags:
        flight.tags = json.dumps(tags)

    db.commit()
    db.refresh(flight)

    # Create telemetry points
    base_ts = meta.get("takeoff_time")
    points_created = 0
    for i, pt in enumerate(telemetry):
        ts_ms = int(pt["timestamp"].timestamp() * 1000) if pt.get("timestamp") else (
            int(base_ts.timestamp() * 1000) + (i * 1000) if base_ts else i * 1000
        )

        extra_json = json.dumps(pt["extra_data"]) if pt.get("extra_data") else None

        tp = TelemetryPoint(
            flight_id=flight.id,
            timestamp_ms=ts_ms,
            lat=pt.get("lat"),
            lon=pt.get("lon"),
            altitude_m=pt.get("altitude_m"),
            speed_mps=pt.get("speed_mps"),
            battery_pct=pt.get("battery_pct"),
            heading_deg=pt.get("heading_deg"),
            satellites=pt.get("satellites"),
            source=fmt,
        )
        # Set extra_data if the model supports it
        if hasattr(tp, "extra_data"):
            tp.extra_data = extra_json

        telemetry_db.add(tp)
        points_created += 1

    telemetry_db.commit()

    logger.info("Imported flight %d with %d telemetry points from %s", flight.id, points_created, data_source)

    return {
        "flight_id": flight.id,
        "points_imported": points_created,
        "data_source": data_source,
        "format_detected": fmt,
        "date": str(meta.get("date")) if meta.get("date") else None,
        "duration_seconds": meta.get("duration_seconds"),
        "error": None,
    }
