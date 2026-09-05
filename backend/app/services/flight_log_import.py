"""Flight log import service for DJI, Litchi, and Airdata CSV formats.

Parses flight log files, extracts metadata and telemetry, creates Flight
records in the main database and TelemetryPoint records in the telemetry database.
Provider-specific telemetry fields are stored in the extra_data JSON column.
"""

import csv
import io
import json
import logging
import math
from datetime import datetime, date, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.flight import Flight
from app.models.telemetry import TelemetryPoint

from app.logsafe import for_log

logger = logging.getLogger(__name__)

# Standard telemetry fields mapped to our fixed columns
STANDARD_FIELDS = {"lat", "lon", "altitude_m", "speed_mps", "battery_pct", "heading_deg",
                   "pitch_deg", "roll_deg", "satellites", "battery_voltage"}


def _detect_airdata_json(content: str) -> bool:
    """Is this an Airdata JSON export?

    This used to parse only the first 5000 characters, to avoid decoding a
    whole export just to look at one key. Truncating JSON does not give you a
    smaller document, it gives you an invalid one: every real export is
    hundreds of kilobytes, so the parse raised, the exception was swallowed,
    and detection said no. The file then fell through to the CSV heuristics,
    matched on the word "latitude", and was parsed as a Litchi CSV, which
    found nothing in it.

    The marker is cheap to look for as text, and only a file that carries it
    is worth decoding. Anything that gets past this is parsed in full moments
    later anyway.
    """
    if not content.lstrip().startswith("{"):
        return False
    # Either marker is enough to be worth decoding: an export with telemetry
    # carries the channels, one without still carries the flight's id.
    if '"flight_telemetry"' not in content and '"flight_id"' not in content:
        return False
    try:
        data = json.loads(content)
    except ValueError:
        return False
    inner = data.get("data")
    if not isinstance(inner, dict):
        return False
    # An export can carry the flight without its telemetry. That is still this
    # format, and recognising it is what turns "could not detect file format"
    # into the accurate "no telemetry points found in file".
    return "flight_telemetry" in inner or isinstance(inner.get("flight"), dict)


def detect_format(content: str) -> str:
    """Auto-detect the flight log format from file content.

    Args:
        content: The raw text content of the uploaded file.

    Returns:
        Format identifier: "dji", "litchi", "airdata", "airdata_json",
        "parrot", or "unknown".
    """
    from app.services.parrot_import import is_gutma
    if is_gutma(content):
        return "parrot"

    if _detect_airdata_json(content):
        return "airdata_json"

    first_lines = content[:2000].lower()

    # OSD.* columns appear in no other format. The rule used to also require
    # DateTime(utc), which DJI Go 4 exports do not always carry, so those logs
    # fell through to the CSV path and imported nothing.
    if "osd.lati" in first_lines:
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
    """Parse various timestamp formats into a naive UTC datetime.

    ISO 8601 first. Airdata sends "2025-01-29T12:04:52.315549+00:00", with
    microseconds and an offset, which none of the fixed formats below match --
    so every flight in a real export arrived with no date, no duration, and no
    timestamp on any telemetry point.

    An offset-aware value is converted to UTC rather than having its offset
    dropped, or a log written at +00:00 and one written at -05:00 disagree by
    five hours while looking equally valid.
    """
    if not val:
        return None
    text = str(val).strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _cell(cols, index):
    """The value at `index`, or None when the row stops short of it.

    Rows in these logs are ragged: a log cut off mid-write, or a firmware that
    omits trailing columns, produces rows long enough for latitude and longitude
    but not for the columns after them. Indexing those directly raised
    IndexError and failed the whole import.
    """
    if index is None or index >= len(cols):
        return None
    return cols[index]


def _extract_dji_extra(cols, gimbal_pitch_col, gimbal_roll_col, gimbal_yaw_col, flight_mode_col) -> dict:
    """Extract DJI provider-specific extra data from a row."""
    extra = {}
    if gimbal_pitch_col is not None:
        extra["gimbal_pitch"] = _parse_float(_cell(cols, gimbal_pitch_col))
    if gimbal_roll_col is not None:
        extra["gimbal_roll"] = _parse_float(_cell(cols, gimbal_roll_col))
    if gimbal_yaw_col is not None:
        extra["gimbal_yaw"] = _parse_float(_cell(cols, gimbal_yaw_col))
    if flight_mode_col is not None:
        extra["flight_mode"] = _cell(cols, flight_mode_col)
    return {k: v for k, v in extra.items() if v is not None}


# DJI writes the same field under several names, depending on which app and
# firmware produced the log.
DJI_COLUMNS = {
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


def _dji_columns(header_line: str) -> dict:
    """Each field we read mapped to its column index, or None when absent."""
    header_map = {h.strip().lower(): i
                  for i, h in enumerate(header_line.strip().split("\t"))}
    resolved = {}
    for field, candidates in DJI_COLUMNS.items():
        resolved[field] = next(
            (header_map[c] for c in candidates if c in header_map), None)
    return resolved


def _dji_point(cols, col: dict) -> Optional[dict]:
    """One telemetry point, or None for a row with no usable fix.

    0,0 is how these logs encode "no fix"; kept, it draws the track to the Gulf
    of Guinea on every map.
    """
    lat = _parse_float(_cell(cols, col["lat"]))
    lon = _parse_float(_cell(cols, col["lon"]))
    if lat is None or lon is None or (lat == 0 and lon == 0):
        return None

    extra = _extract_dji_extra(cols, col["gimbal_pitch"], col["gimbal_roll"],
                               col["gimbal_yaw"], col["flight_mode"])
    return {
        "lat": lat,
        "lon": lon,
        "altitude_m": _parse_float(_cell(cols, col["alt"])),
        "speed_mps": _parse_float(_cell(cols, col["speed"])),
        "battery_pct": _parse_float(_cell(cols, col["battery"])),
        "heading_deg": _parse_float(_cell(cols, col["heading"])),
        "satellites": _parse_int(_cell(cols, col["satellites"])),
        "timestamp": _parse_timestamp(_cell(cols, col["timestamp"])),
        "extra_data": extra or None,
    }


def parse_dji_txt(content: str) -> dict:
    """Parse a DJI Go 4 .txt flight log.

    DJI logs are tab-separated with columns like CUSTOM.date, OSD.latitude,
    OSD.longitude, OSD.altitude [m].

    Args:
        content: Raw text content of the .txt file.

    Returns:
        Dict with 'metadata', 'telemetry' and 'error' keys.
    """
    lines = content.strip().split("\n")
    if len(lines) < 2:
        return {"metadata": {}, "telemetry": [], "error": "File too short"}

    col = _dji_columns(lines[0])
    if col["lat"] is None or col["lon"] is None:
        return {"metadata": {}, "telemetry": [],
                "error": "Could not find latitude/longitude columns"}

    telemetry = []
    first_ts = None
    for line in lines[1:]:
        point = _dji_point(line.strip().split("\t"), col)
        if point is None:
            continue
        if first_ts is None and point["timestamp"]:
            first_ts = point["timestamp"]
        telemetry.append(point)

    return {"metadata": _build_telemetry_metadata(telemetry, first_ts),
            "telemetry": telemetry, "error": None}


def _convert_alt_units(alt: Optional[float], alt_col: Optional[str]) -> Optional[float]:
    """Convert altitude from feet to meters if the column name indicates feet."""
    if alt is not None and alt_col and 'feet' in alt_col.lower():
        return alt / 3.28084
    return alt


def _convert_speed_units(speed: Optional[float], speed_col: Optional[str]) -> Optional[float]:
    """Convert speed from mph to m/s if the column name indicates mph."""
    if speed is not None and speed_col and 'mph' in speed_col.lower():
        return speed * 0.44704
    return speed


# Columns already mapped to a fixed field, so they must not also appear in
# extra_data. The coordinate names are listed by every spelling these exports
# use, because the fixed mapping only ever picked one of them.
COORDINATE_HEADERS = {"latitude", "longitude", "lat", "lon", "lng"}

# Airdata columns worth keeping under a stable name rather than their raw header.
AIRDATA_EXTRA_FIELDS = {
    "gimbal_heading(degrees)": "gimbal_heading",
    "gimbal_pitch(degrees)": "gimbal_pitch",
    "gimbal_roll(degrees)": "gimbal_roll",
    "rc_elevator(percent)": "rc_elevator_pct",
    "rc_aileron(percent)": "rc_aileron_pct",
    "rc_throttle(percent)": "rc_throttle_pct",
    "rc_rudder(percent)": "rc_rudder_pct",
    "battery_temperature(f)": "battery_temperature_f",
    "current(a)": "current_a",
    "flycstate": "flight_mode",
    "isphotograph": "is_photo",
    "isvideo": "is_video",
}

# A wide export must not put an unbounded blob on every telemetry row.
MAX_EXTRA_COLUMNS = 30


def _extra_value(value):
    """A number where the cell holds one, the trimmed text where it does not,
    and None for a cell with nothing in it."""
    parsed = _parse_float(value)
    if parsed is not None:
        return parsed
    if value and value.strip():
        return value.strip()
    return None


def _unmapped_columns(row: dict, standard_cols: set) -> dict:
    """Everything in the row that is not already a fixed field."""
    extra = {}
    for key, value in row.items():
        if key.lower().strip() in COORDINATE_HEADERS or key in standard_cols:
            continue
        parsed = _extra_value(value)
        if parsed is not None:
            extra[key] = parsed
    return extra


def _airdata_named_columns(row: dict, fieldnames) -> dict:
    """The Airdata columns worth carrying under a stable name."""
    header_lookup = {h.lower().strip(): h for h in (fieldnames or [])}
    named = {}
    for csv_key, extra_key in AIRDATA_EXTRA_FIELDS.items():
        header = header_lookup.get(csv_key)
        if header is None:
            continue
        parsed = _extra_value(row.get(header))
        if parsed is not None:
            named[extra_key] = parsed
    return named


def _collect_extra_columns(row: dict, standard_cols: set, fieldnames) -> dict:
    """Collect non-standard columns as extra_data from a CSV row."""
    extra = _unmapped_columns(row, standard_cols)
    extra.update(_airdata_named_columns(row, fieldnames))
    if len(extra) > MAX_EXTRA_COLUMNS:
        extra = dict(list(extra.items())[:MAX_EXTRA_COLUMNS])
    return extra


def _build_telemetry_metadata(telemetry: list, first_ts) -> dict:
    """Compute metadata from a list of telemetry points."""
    duration = None
    if telemetry and telemetry[0].get("timestamp") and telemetry[-1].get("timestamp"):
        duration = int((telemetry[-1]["timestamp"] - telemetry[0]["timestamp"]).total_seconds())

    first_lat = None
    first_lon = None
    max_alt = 0
    max_speed = 0
    for pt in telemetry:
        if first_lat is None:
            first_lat = pt.get("lat")
            first_lon = pt.get("lon")
        alt = pt.get("altitude_m")
        speed = pt.get("speed_mps")
        if alt and alt > max_alt:
            max_alt = alt
        if speed and speed > max_speed:
            max_speed = speed

    return {
        "takeoff_time": first_ts,
        "date": first_ts.date() if first_ts else None,
        "duration_seconds": duration,
        "max_altitude_m": max_alt if max_alt > 0 else None,
        "max_speed_mps": max_speed if max_speed > 0 else None,
        "takeoff_lat": first_lat,
        "takeoff_lon": first_lon,
    }


# Litchi and Airdata both ship "name(unit)" headers but disagree on the names,
# so each field is matched by the first candidate that appears anywhere in a
# header. Order matters: the more specific name has to come first.
CSV_COLUMNS = {
    "lat": ["latitude", "lat"],
    "lon": ["longitude", "lon", "lng"],
    "alt": ["altitude(m)", "altitude [m]", "altitude_m", "height_above_takeoff", "height"],
    # Airdata names the column "speed(mph)"; "speed_mph" never matched it, so
    # every Airdata CSV imported with no speed and no max_speed_mps.
    "speed": ["speed(m/s)", "speed(mph)", "speed_mph", "groundspeed"],
    "battery": ["battery(%)", "batterylevel", "battery_percent", "battery_level"],
    "heading": ["heading", "compass_heading", "yaw"],
    "timestamp": ["datetime", "timestamp", "time", "date_time"],
}


def _csv_columns(fieldnames) -> dict:
    """Each field we read mapped to its header, or None when absent."""
    headers = list(fieldnames or [])
    resolved = {}
    for field, candidates in CSV_COLUMNS.items():
        resolved[field] = next(
            (h for c in candidates for h in headers if c in h.lower()), None)
    return resolved


def _csv_value(row, header):
    """The parsed float under `header`, or None when the column is absent."""
    return _parse_float(row.get(header)) if header else None


def _csv_point(row, col: dict, fieldnames, standard_cols: set) -> Optional[dict]:
    """One telemetry point, or None for a row with no usable fix."""
    lat = _parse_float(row.get(col["lat"]))
    lon = _parse_float(row.get(col["lon"]))
    if lat is None or lon is None or (lat == 0 and lon == 0):
        return None

    extra = _collect_extra_columns(row, standard_cols, fieldnames)
    return {
        "lat": lat,
        "lon": lon,
        "altitude_m": _convert_alt_units(_csv_value(row, col["alt"]), col["alt"]),
        "speed_mps": _convert_speed_units(_csv_value(row, col["speed"]), col["speed"]),
        "battery_pct": _csv_value(row, col["battery"]),
        "heading_deg": _csv_value(row, col["heading"]),
        "timestamp": _parse_timestamp(row.get(col["timestamp"])) if col["timestamp"] else None,
        "extra_data": extra or None,
    }


def parse_csv_log(content: str, _format_type: str) -> dict:
    """Parse a CSV flight log (Litchi or Airdata format).

    Args:
        content: Raw CSV text content.
        _format_type: "litchi" or "airdata" (reserved for future format-specific logic).

    Returns:
        Dict with 'metadata', 'telemetry' and 'error' keys.
    """
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return {"metadata": {}, "telemetry": [], "error": "No CSV headers found"}

    col = _csv_columns(reader.fieldnames)
    if col["lat"] is None or col["lon"] is None:
        return {"metadata": {}, "telemetry": [],
                "error": "Could not find latitude/longitude columns"}

    standard_cols = set(col.values())
    telemetry = []
    first_ts = None
    for row in reader:
        point = _csv_point(row, col, reader.fieldnames, standard_cols)
        if point is None:
            continue
        if first_ts is None and point["timestamp"]:
            first_ts = point["timestamp"]
        telemetry.append(point)

    return {"metadata": _build_telemetry_metadata(telemetry, first_ts),
            "telemetry": telemetry, "error": None}


def _at(channel, index):
    """The value a channel holds at `index`, or None when it is shorter.

    Airdata sends each sensor as its own array, and they are not guaranteed to
    be the same length: a channel that stopped reporting mid-flight is simply
    shorter than the GPS track.
    """
    return channel[index] if index < len(channel) else None


def _airdata_battery(raw):
    """Airdata sends 0.98 for 98% on some exports and 98 on others. Stored raw,
    the first reads as a dead battery."""
    if raw is None:
        return None
    return round(raw * 100, 1) if raw <= 1.0 else raw


def _airdata_speed(velocity):
    """The magnitude of a velocity vector, or None when the channel has none."""
    if not isinstance(velocity, list) or len(velocity) < 2:
        return None
    return round(math.sqrt(sum(v ** 2 for v in velocity[:3])), 2)


def _parse_airdata_telemetry_channels(gps_data, gps_ts, hat_data, bat_data, vel_data, sat_data) -> list:
    """Convert Airdata channel-based telemetry into point-based format."""
    telemetry = []
    for i, fix in enumerate(gps_data):
        lat, lon = fix
        if lat is None or lon is None:
            continue

        alt = _at(hat_data, i)
        telemetry.append({
            "lat": lat, "lon": lon,
            "altitude_m": round(alt, 2) if alt is not None else None,
            "speed_mps": _airdata_speed(_at(vel_data, i)),
            "battery_pct": _airdata_battery(_at(bat_data, i)),
            "heading_deg": None,
            "satellites": _at(sat_data, i),
            "timestamp": _parse_timestamp(_at(gps_ts, i)),
            "extra_data": None,
        })
    return telemetry


def _airdata_metadata(flight: dict) -> dict:
    """The flight-level fields, independent of the telemetry channels."""
    takeoff_time = _parse_timestamp(flight.get("takeoff"))
    landing_time = _parse_timestamp(flight.get("landing"))
    duration = None
    if takeoff_time and landing_time:
        duration = int((landing_time - takeoff_time).total_seconds())
    return {
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


def _maxima(telemetry: list) -> dict:
    """Highest altitude and speed seen, or None where nothing was recorded."""
    alts = [p["altitude_m"] for p in telemetry if p["altitude_m"] is not None]
    speeds = [p["speed_mps"] for p in telemetry if p["speed_mps"] is not None]
    max_alt = max(alts, default=0)
    max_speed = max(speeds, default=0)
    return {
        "max_altitude_m": max_alt if max_alt > 0 else None,
        "max_speed_mps": max_speed if max_speed > 0 else None,
    }


def parse_airdata_json(content: str) -> dict:
    """Parse an Airdata.com JSON export file.

    Airdata JSON uses channel-based telemetry with separate arrays for each
    sensor. Converts to point-based format for storage.

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
    if not flight:
        return {"metadata": {}, "telemetry": [], "error": "No flight data found"}

    metadata = _airdata_metadata(flight)
    channels = data.get("data", {}).get("flight_telemetry", {})
    if not channels:
        return {"metadata": metadata, "telemetry": [], "error": None}

    def channel(name, key="data"):
        return channels.get(name, {}).get(key, [])

    gps_data = channel("gps")
    gps_ts = channel("gps", "timestamps")
    # GPS is the time axis; without it the other channels have nothing to hang on.
    if not gps_data or not gps_ts:
        return {"metadata": metadata, "telemetry": [], "error": "No GPS data in telemetry"}

    telemetry = _parse_airdata_telemetry_channels(
        gps_data, gps_ts, channel("height_above_takeoff"),
        channel("battery_percentage"), channel("velocity"),
        channel("gps_num_satellites"))
    metadata.update(_maxima(telemetry))
    return {"metadata": metadata, "telemetry": telemetry, "error": None}


def _check_duplicate_by_external_id(meta: dict, db: Session):
    """Check if a flight with the same external_id already exists. Returns existing Flight or None."""
    if not meta.get("external_id"):
        return None
    from sqlalchemy import func
    ext_id = str(meta["external_id"]).upper().replace("-", "")
    return db.query(Flight).filter(
        func.replace(func.upper(Flight.external_id), "-", "") == ext_id
    ).first()


def _point_timestamp_ms(point_time, base_ts, index) -> int:
    """Milliseconds for one telemetry point.

    Its own timestamp when it has one. A log that carries none still has to
    plot in order, so the points are spaced a second apart from the takeoff
    time, or from zero when even that is missing.
    """
    if point_time:
        return int(point_time.timestamp() * 1000)
    if base_ts:
        return int(base_ts.timestamp() * 1000) + index * 1000
    return index * 1000


def _create_telemetry_points(telemetry: list, flight_id: int, meta: dict, fmt: str, telemetry_db: Session) -> int:
    """Create TelemetryPoint records from parsed telemetry data. Returns count created."""
    base_ts = meta.get("takeoff_time")
    points_created = 0
    for i, pt in enumerate(telemetry):
        ts_ms = _point_timestamp_ms(pt.get("timestamp"), base_ts, i)
        extra_json = json.dumps(pt["extra_data"]) if pt.get("extra_data") else None
        tp = TelemetryPoint(
            flight_id=flight_id,
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
        if hasattr(tp, "extra_data"):
            tp.extra_data = extra_json
        telemetry_db.add(tp)
        points_created += 1
    telemetry_db.commit()
    return points_created


def _parse_for_format(text: str, fmt: str):
    """Run the parser for `fmt`. Returns (result, data_source), or (None, None)
    for a format nothing here handles."""
    if fmt == "dji":
        return parse_dji_txt(text), "dji_log"
    if fmt == "airdata_json":
        return parse_airdata_json(text), "airdata_json"
    if fmt in ("litchi", "airdata"):
        return parse_csv_log(text, fmt), f"{fmt}_csv"
    if fmt == "parrot":
        from app.services.parrot_import import parse_gutma
        return parse_gutma(text), "parrot_gutma"
    if fmt == "unknown":
        # Nothing matched, so try CSV: it is the shape most exports land in.
        return parse_csv_log(text, "airdata"), "csv_import"
    return None, None


def _match_vehicle(db: Session, serial: str):
    """The airframe this serial belongs to, by either serial column."""
    from app.models.vehicle import Vehicle
    return db.query(Vehicle).filter(
        (Vehicle.provider_serial == serial) | (Vehicle.serial_number == serial)
    ).first()


def _flight_from_metadata(meta: dict, data_source: str, user_id, db: Session) -> Flight:
    """The Flight row a parsed log describes, not yet added to the session."""
    flight = Flight(
        date=meta.get("date"),
        takeoff_time=meta.get("takeoff_time"),
        landing_time=meta.get("landing_time"),
        duration_seconds=meta.get("duration_seconds"),
        max_altitude_m=meta.get("max_altitude_m"),
        max_speed_mps=meta.get("max_speed_mps"),
        takeoff_lat=meta.get("takeoff_lat"),
        takeoff_lon=meta.get("takeoff_lon"),
        landing_lat=meta.get("landing_lat"),
        landing_lon=meta.get("landing_lon"),
        data_source=data_source,
        has_telemetry=True,
        telemetry_synced=True,
        review_status="needs_review",
        pilot_confirmed=False,
        created_by_id=user_id,
    )
    for field in ("external_id", "battery_serial", "sensor_package"):
        if meta.get(field):
            setattr(flight, field, meta[field])
    if meta.get("vehicle_serial"):
        vehicle = _match_vehicle(db, meta["vehicle_serial"])
        if vehicle:
            flight.vehicle_id = vehicle.id
    return flight


def _import_summary(meta: dict, data_source: str, fmt: str, **extra) -> dict:
    """The response shape every outcome of an import shares."""
    summary = {
        "data_source": data_source,
        "format_detected": fmt,
        "date": str(meta.get("date")) if meta.get("date") else None,
        "duration_seconds": meta.get("duration_seconds"),
        "error": None,
    }
    summary.update(extra)
    return summary


def _import_failure(message: str) -> dict:
    return {"error": message, "flight_id": None, "points_imported": 0}


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
    text = content.decode("utf-8", errors="replace")
    fmt = format_hint if format_hint != "auto" else detect_format(text)

    result, data_source = _parse_for_format(text, fmt)
    if result is None:
        return _import_failure(f"Unsupported format: {fmt}")
    if result.get("error"):
        # Detection already failed once, so say so rather than reporting the
        # fallback parser's complaint as if CSV had been the intent.
        if fmt == "unknown":
            return _import_failure(f"Could not detect file format. {result['error']}")
        return _import_failure(result["error"])

    meta = result["metadata"]
    telemetry = result["telemetry"]
    if not telemetry:
        return _import_failure("No telemetry points found in file")

    existing = _check_duplicate_by_external_id(meta, db)
    if existing:
        return _import_summary(
            meta, data_source, fmt, flight_id=existing.id, points_imported=0,
            skipped=True, message="Flight already exists (duplicate external_id)")

    flight = _flight_from_metadata(meta, data_source, user_id, db)
    db.add(flight)
    db.flush()

    from app.services.flight_tagger import compute_flight_tags
    tags = compute_flight_tags(flight)
    if tags:
        flight.tags = json.dumps(tags)

    # Insert telemetry FIRST. If it fails, roll the flight back so we do not
    # leave a phantom row with has_telemetry=True but zero points.
    try:
        points_created = _create_telemetry_points(telemetry, flight.id, meta, fmt, telemetry_db)
    except Exception:
        db.rollback()
        raise

    db.commit()
    db.refresh(flight)
    logger.info("Imported flight %d with %d telemetry points from %s",
                flight.id, points_created, for_log(data_source))

    return _import_summary(meta, data_source, fmt,
                           flight_id=flight.id, points_imported=points_created)
