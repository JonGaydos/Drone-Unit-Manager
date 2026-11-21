"""Flight distance and landing location worked out from GPS telemetry.

Distance is the length of the track, with bad fixes and impossible jumps left
out; the landing coordinates are the last good fix; the landing address is
looked up from them. Only empty fields are filled, so a value someone typed in
stays. ``fill_track_fields`` runs when telemetry is stored; ``fill_missing``
runs in the background (once after an upgrade, then daily) for flights still
missing values, and does the address lookups, which are kept off imports.
"""

import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app import database
from app.models.flight import Flight
from app.models.setting import Setting
from app.models.telemetry import TelemetryPoint
from app.services.audit_capture import machine_run

logger = logging.getLogger(__name__)

EARTH_RADIUS_M = 6_371_008.8
# A segment faster than this is a GPS jump, not flight.
MAX_SPEED_MPS = 60.0
BATCH_SIZE = 50
# Nominatim's usage policy: at most one request per second.
GEOCODE_INTERVAL_S = 1.0
# Set once a full backfill pass finishes, so startup does not run it again.
BACKFILL_DONE_KEY = "track_backfill_done"

_geocode_lock = threading.Lock()
_last_geocode = 0.0
_run_lock = threading.Lock()


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _field(point, name):
    return point.get(name) if isinstance(point, dict) else getattr(point, name, None)


def _fix(point):
    """(lat, lon, seconds) for a usable fix, else None. Missing, out-of-range
    and 0,0 coordinates are not fixes (Parrot's no-fix 500,500 is out of range)."""
    lat, lon = _field(point, "lat"), _field(point, "lon")
    if lat is None or lon is None:
        return None
    if abs(lat) > 90 or abs(lon) > 180 or (lat == 0 and lon == 0):
        return None
    ts = _field(point, "timestamp_ms") or 0
    return lat, lon, ts / 1000


def track_summary(points) -> dict:
    """Distance and landing fix over telemetry points in time order (dicts or
    rows with lat, lon and timestamp_ms). A point that would need more than
    MAX_SPEED_MPS from the last good fix is skipped. No good fix gives Nones."""
    last = None
    distance = 0.0
    for point in points:
        fix = _fix(point)
        if fix is None:
            continue
        if last is not None:
            meters = haversine_m(last[0], last[1], fix[0], fix[1])
            elapsed = fix[2] - last[2]
            if meters > MAX_SPEED_MPS * (elapsed if elapsed > 0 else 1.0):
                continue
            distance += meters
        last = fix
    if last is None:
        return {"distance_m": None, "landing_lat": None, "landing_lon": None}
    return {"distance_m": round(distance, 1), "landing_lat": last[0], "landing_lon": last[1]}


def _load_points(telemetry_db: Session, flight_id: int):
    return telemetry_db.query(
        TelemetryPoint.lat, TelemetryPoint.lon, TelemetryPoint.timestamp_ms,
    ).filter(TelemetryPoint.flight_id == flight_id).order_by(
        TelemetryPoint.timestamp_ms, TelemetryPoint.id,
    ).all()


def _fill_from_track(flight: Flight, telemetry_db: Session) -> bool:
    summary = track_summary(_load_points(telemetry_db, flight.id))
    changed = False
    if flight.distance_m is None and summary["distance_m"] is not None:
        flight.distance_m = summary["distance_m"]
        changed = True
    if flight.landing_lat is None and flight.landing_lon is None and summary["landing_lat"] is not None:
        flight.landing_lat = summary["landing_lat"]
        flight.landing_lon = summary["landing_lon"]
        changed = True
    return changed


def fill_track_fields(db: Session, flight: Flight, telemetry_db: Session | None = None) -> bool:
    """Fill the flight's empty distance, landing coordinates and landing time.
    Returns whether anything changed; the caller commits. ``db`` is the
    flight's session; telemetry is read from ``telemetry_db`` or a new one."""
    changed = False
    if flight.landing_time is None and flight.takeoff_time and flight.duration_seconds:
        flight.landing_time = flight.takeoff_time + timedelta(seconds=flight.duration_seconds)
        changed = True
    if not flight.has_telemetry or (flight.distance_m is not None and flight.landing_lat is not None):
        return changed
    if telemetry_db is not None:
        return _fill_from_track(flight, telemetry_db) or changed
    with database.TelemetrySessionLocal() as tdb:
        return _fill_from_track(flight, tdb) or changed


def _geocode(lat: float, lon: float) -> str | None:
    """Reverse geocode, spaced at least GEOCODE_INTERVAL_S apart."""
    global _last_geocode
    from app.services import sync_manager
    with _geocode_lock:
        wait = GEOCODE_INTERVAL_S - (time.monotonic() - _last_geocode)
        if wait > 0:
            time.sleep(wait)
        try:
            return sync_manager._reverse_geocode(lat, lon)
        finally:
            _last_geocode = time.monotonic()


def _geocode_landings(db: Session, flights: list[Flight]) -> int:
    """Look up landing addresses. Call with nothing pending, so the requests
    hold no write lock."""
    found = 0
    for flight in flights:
        if flight.landing_address or flight.landing_lat is None or flight.landing_lon is None:
            continue
        address = _geocode(flight.landing_lat, flight.landing_lon)
        if address:
            flight.landing_address = address
            found += 1
    return found


def _candidates(db: Session):
    """Flights that may still have something to fill."""
    return db.query(Flight).filter(or_(
        and_(Flight.has_telemetry.is_(True),
             or_(Flight.distance_m.is_(None), Flight.landing_lat.is_(None))),
        and_(Flight.landing_lat.isnot(None), Flight.landing_lon.isnot(None),
             Flight.landing_address.is_(None)),
        and_(Flight.landing_time.is_(None), Flight.takeoff_time.isnot(None),
             Flight.duration_seconds.isnot(None)),
    ))


def _fill_all(db: Session, batch_size: int) -> dict:
    total = _candidates(db).count()
    stats = {"checked": 0, "filled": 0, "geocoded": 0}
    cursor = None
    while True:
        query = _candidates(db).order_by(Flight.id.desc())
        if cursor is not None:
            query = query.filter(Flight.id < cursor)
        batch = query.limit(batch_size).all()
        if not batch:
            return stats
        cursor = batch[-1].id
        with database.TelemetrySessionLocal() as tdb:
            stats["filled"] += sum(fill_track_fields(db, f, tdb) for f in batch)
        db.commit()
        stats["geocoded"] += _geocode_landings(db, batch)
        db.commit()
        stats["checked"] += len(batch)
        logger.info("Track fill: %d of %d flights checked, %d filled, %d addresses found",
                    stats["checked"], total, stats["filled"], stats["geocoded"])


def fill_missing(batch_size: int = BATCH_SIZE) -> dict | None:
    """Fill flights still missing distance, landing location, address or
    landing time, newest first, committing each batch, so a rerun picks up
    where an interrupted one stopped. Returns the counts, or None when a run
    is already going. A finished pass sets BACKFILL_DONE_KEY."""
    if not _run_lock.acquire(blocking=False):
        logger.info("Track fill skipped: already running")
        return None
    try:
        with database.SessionLocal() as db:
            with machine_run(db, "track_fill", "flight"):
                stats = _fill_all(db, batch_size)
                if not backfill_done(db):
                    db.add(Setting(key=BACKFILL_DONE_KEY, value=datetime.now(timezone.utc).isoformat()))
            db.commit()
        return stats
    finally:
        _run_lock.release()


def backfill_done(db: Session) -> bool:
    """Whether a full fill pass has finished before."""
    return db.query(Setting).filter(Setting.key == BACKFILL_DONE_KEY).first() is not None
