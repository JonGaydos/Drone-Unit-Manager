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
# A fix after a pause longer than this, and longer than PAUSE_FACTOR times
# the interval before it, is held until a following fix agrees with it. A log
# that records a fix a minute has no pauses, since its first step sets the rhythm.
MIN_PAUSE_S = 30.0
PAUSE_FACTOR = 2
# Distance counts once the craft has moved this far from the last counted fix,
# so hovering and GPS jitter add nothing.
MIN_MOVE_M = 5.0
# Fixes are averaged over this many seconds either side before measuring.
SMOOTH_WINDOW_S = 2.0
BATCH_SIZE = 50
# Nominatim's usage policy: at most one request per second.
GEOCODE_INTERVAL_S = 1.0
# Lookups failing this many times in a row means the service is unreachable;
# the rest of the run skips addresses and the pass does not count as finished.
GEOCODE_FAILURE_LIMIT = 5
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


def _possible(a, b) -> bool:
    """Whether a craft could get from fix a to fix b without passing MAX_SPEED_MPS."""
    elapsed = b[2] - a[2]
    return haversine_m(a[0], a[1], b[0], b[1]) <= MAX_SPEED_MPS * (elapsed if elapsed > 0 else 1.0)


def _drop_spikes(fixes: list) -> list:
    """Drop single fixes that jump out of the track and back. A long gap can
    make the jump out look possible, so a fix goes when either side of it is
    impossible while its neighbours are possible without it."""
    kept = fixes[:1]
    for i in range(1, len(fixes) - 1):
        prev, fix, nxt = kept[-1], fixes[i], fixes[i + 1]
        out_and_back = not (_possible(prev, fix) and _possible(fix, nxt))
        if not (out_and_back and _possible(prev, nxt)):
            kept.append(fix)
    if len(fixes) > 1:
        kept.append(fixes[-1])
    return kept


class _Walk:
    """Walks the fixes, keeping the accepted ones in stretches and the landing fix.

    ``anchor`` is the last accepted fix (the speed rule measures from it).
    ``held`` is a fix after a pause, accepted only once a following fix agrees
    with it, so a bad fix at the end of a gap is never measured or landed on.
    ``rejected`` is a fix the speed rule turned down; if the next fix agrees
    with it, the anchor was the bad one and the track carries on from them.
    Each stretch is (joined, fixes): joined stretches are measured from the
    end of the one before; a new stretch starts after more than
    SMOOTH_WINDOW_S without fixes, or unjoined after a bad anchor."""

    def __init__(self, first):
        self.anchor = self.landing = first
        self.interval = None
        self.held = self.rejected = None
        self.stretches = [(False, [first])]

    def step(self, fix) -> None:
        held, self.held = self.held, None
        if held is not None and _possible(held, fix):
            self._join(held)
            self._join(fix)
        elif _possible(self.anchor, fix):
            self._take(fix)
        elif self.rejected is not None and _possible(self.rejected, fix):
            self.stretches.append((False, [self.rejected]))
            self.anchor, self.interval = self.rejected, None
            self._join(fix)
        else:
            self.rejected = fix

    def _take(self, fix) -> None:
        interval = fix[2] - self.anchor[2]
        # The first step after a start sets the rhythm, so it is never a pause.
        paused = (interval > MIN_PAUSE_S and self.interval is not None
                  and interval > PAUSE_FACTOR * self.interval)
        if paused:
            self.held, self.rejected = fix, None
        else:
            self._join(fix)

    def _join(self, fix) -> None:
        interval = fix[2] - self.anchor[2]
        if interval > SMOOTH_WINDOW_S:
            self.stretches.append((True, [fix]))
        else:
            self.stretches[-1][1].append(fix)
        self.anchor = self.landing = fix
        self.interval = interval
        self.rejected = None


def _smoothed(segment: list) -> list:
    """Each fix replaced by the mean of the fixes within SMOOTH_WINDOW_S of it,
    which averages GPS jitter away without moving a steady track. The window
    narrows towards the ends so it stays even, and the end fixes stay put."""
    out = []
    lo = hi = 0
    sum_lat = sum_lon = 0.0
    first, last = segment[0][2], segment[-1][2]
    for fix in segment:
        half = min(SMOOTH_WINDOW_S, fix[2] - first, last - fix[2])
        while hi < len(segment) and segment[hi][2] <= fix[2] + half:
            sum_lat += segment[hi][0]
            sum_lon += segment[hi][1]
            hi += 1
        while segment[lo][2] < fix[2] - half:
            sum_lat -= segment[lo][0]
            sum_lon -= segment[lo][1]
            lo += 1
        count = hi - lo
        out.append((sum_lat / count, sum_lon / count))
    return out


def _segment_length(segment: list) -> float:
    """Length of a smoothed segment, counted only in moves of MIN_MOVE_M or more."""
    points = _smoothed(segment)
    counted = points[0]
    meters = 0.0
    for point in points[1:]:
        step = haversine_m(counted[0], counted[1], point[0], point[1])
        if step >= MIN_MOVE_M:
            meters += step
            counted = point
    return meters


def _distance(stretches: list) -> float:
    """Total of each stretch's length and of the joins between them, a join
    counting only when it is at least MIN_MOVE_M."""
    meters = 0.0
    previous_end = None
    for joined, fixes in stretches:
        if joined and previous_end is not None:
            step = haversine_m(previous_end[0], previous_end[1], fixes[0][0], fixes[0][1])
            if step >= MIN_MOVE_M:
                meters += step
        meters += _segment_length(fixes)
        previous_end = fixes[-1]
    return meters


def track_summary(points) -> dict:
    """Distance and landing fix over telemetry points in time order (dicts or
    rows with lat, lon and timestamp_ms). A jump that would need more than
    MAX_SPEED_MPS is never measured, nor a fix after a pause that nothing after
    it confirms, and smoothing plus MIN_MOVE_M keep hovering and GPS jitter
    from adding distance. No good fix gives Nones."""
    fixes = _drop_spikes([fix for fix in map(_fix, points) if fix is not None])
    if not fixes:
        return {"distance_m": None, "landing_lat": None, "landing_lon": None}
    walk = _Walk(fixes[0])
    for fix in fixes[1:]:
        walk.step(fix)
    distance = _distance(walk.stretches)
    return {"distance_m": round(distance, 1),
            "landing_lat": walk.landing[0], "landing_lon": walk.landing[1]}


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


def _geocode_landings(flights: list[Flight], stats: dict) -> None:
    """Look up landing addresses, counting found ones and failures in a row in
    ``stats``. Call with nothing pending, so the requests hold no write lock."""
    for flight in flights:
        if stats["failures_in_row"] >= GEOCODE_FAILURE_LIMIT:
            return
        if flight.landing_address or flight.landing_lat is None or flight.landing_lon is None:
            continue
        address = _geocode(flight.landing_lat, flight.landing_lon)
        if address is None:
            stats["failures_in_row"] += 1
            continue
        stats["failures_in_row"] = 0
        if address:
            flight.landing_address = address
            stats["geocoded"] += 1


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
    stats = {"checked": 0, "filled": 0, "geocoded": 0, "failures_in_row": 0}
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
        _geocode_landings(batch, stats)
        db.commit()
        stats["checked"] += len(batch)
        logger.info("Track fill: %d of %d flights checked, %d filled, %d addresses found",
                    stats["checked"], total, stats["filled"], stats["geocoded"])


def fill_missing(batch_size: int = BATCH_SIZE) -> dict | None:
    """Fill flights still missing distance, landing location, address or
    landing time, newest first, committing each batch, so a rerun picks up
    where an interrupted one stopped. Returns the counts, or None when a run
    is already going. A pass whose address lookups all went through sets
    BACKFILL_DONE_KEY."""
    if not _run_lock.acquire(blocking=False):
        logger.info("Track fill skipped: already running")
        return None
    try:
        with database.SessionLocal() as db:
            with machine_run(db, "track_fill", "flight"):
                stats = _fill_all(db, batch_size)
                finished = stats["failures_in_row"] < GEOCODE_FAILURE_LIMIT
                if finished and not backfill_done(db):
                    db.add(Setting(key=BACKFILL_DONE_KEY, value=datetime.now(timezone.utc).isoformat()))
            db.commit()
        return stats
    finally:
        _run_lock.release()


def backfill_done(db: Session) -> bool:
    """Whether a full fill pass has finished before."""
    return db.query(Setting).filter(Setting.key == BACKFILL_DONE_KEY).first() is not None
