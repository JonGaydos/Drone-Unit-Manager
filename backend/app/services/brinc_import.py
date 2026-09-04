"""BRINC flight-list CSV import.

BRINC has no API yet, so flights arrive as a multi-flight manifest export: one
row per flight, no telemetry. That is the same shape as the Skydio CSV rather
than the single-flight-plus-telemetry logs (DJI, Litchi, Airdata), so this
mirrors ``excel_import.import_skydio_csv`` and plugs into the same upload
endpoint, auto-detected by its columns.

Two deliberate differences from the Skydio importer:

* It never creates vehicles. A drone the fleet does not know about is reported,
  not invented, so a serial typo cannot quietly produce a junk airframe.
* It never creates flight purposes. Auto-creating purposes from unrecognised
  values is how a mistyped "CPTEd" became a permanent option alongside "CPTED".
"""

import csv
import io
import logging
import re
import time
import os
from datetime import date, datetime, timezone
from typing import NamedTuple, Optional
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.flight import Flight
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle

logger = logging.getLogger(__name__)

# Columns that identify a BRINC export. Deliberately excludes the timestamp
# headers: those carry the export's timezone in their label and change wording
# when the export is switched between local time and UTC.
BRINC_REQUIRED_COLUMNS = {"Flight Id", "Drone Name", "Flight Time (Seconds)", "Org Name"}

# Rows at or below this are session artifacts, not flights: BRINC emits a row
# whenever a session opens, and 69 of 218 in the first real export had an end
# time identical to the start. Importing them would inflate the flight count
# with entries carrying no airtime.
MINIMUM_DURATION_SECONDS = 1

# Nominatim asks for no more than one request per second.
GEOCODE_INTERVAL_SECONDS = 1.0
GEOCODE_TIMEOUT_SECONDS = 8.0
# Whole-run cap on the network phase, so the upload cannot outlive the proxy's
# 60-second read timeout. Whatever is left resolves on the next import.
GEOCODE_BUDGET_SECONDS = 30.0


def is_brinc_csv(headers) -> bool:
    """True when a CSV's header row looks like a BRINC flight export."""
    return BRINC_REQUIRED_COLUMNS <= {h.strip() for h in headers if h}


def _find_time_column(fieldnames, prefix: str) -> Optional[str]:
    """Locate a timestamp column by prefix, whatever its timezone label says."""
    for name in fieldnames or []:
        if name and name.strip().lower().startswith(prefix.lower()):
            return name
    return None


def _header_declares_utc(column: Optional[str]) -> bool:
    """True when the timestamp column heading says the values are already UTC."""
    if not column:
        return False
    return re.search(r"\bUTC\b(?!\s*[+-])", column, re.IGNORECASE) is not None


def _header_offset_hours(column: Optional[str]) -> Optional[int]:
    """The offset a local export's heading claims, as in "(CDT / UTC-5)"."""
    match = re.search(r"UTC\s*([+-]\d{1,2})", column or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


def _local_zone(db: Session) -> ZoneInfo:
    """The organization's configured display timezone, for local-time exports."""
    from app.models.setting import Setting

    row = db.query(Setting).filter(Setting.key == "display_timezone").first()
    name = (row.value if row and row.value else None) or os.environ.get("TZ", "America/Chicago")
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("America/Chicago")


def _to_utc(value: Optional[datetime], already_utc: bool, zone: ZoneInfo) -> Optional[datetime]:
    """Normalize a parsed timestamp to the naive UTC the Flight model stores.

    A local export is converted through a real timezone rather than the offset
    printed in its heading. BRINC emits true local wall-clock time and labels the
    column with whatever offset applied at export time, so a file spanning a
    daylight-saving change is mislabelled for half its rows: an export headed
    "CDT / UTC-5" was measured to be UTC-6 for its December through February
    flights. Applying the label flatly puts those an hour early.
    """
    if value is None:
        return None
    if already_utc:
        return value
    return value.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)


def _parse_dt(value: str) -> tuple[Optional[datetime], bool]:
    """Parse a BRINC timestamp. Returns (naive datetime, is_explicitly_utc).

    The UTC export emits ISO 8601 with a Z suffix ("2026-09-02T16:33:43.000Z");
    the local export emits "2026-09-02 11:33:43". The Z is authoritative: a value
    carrying it needs no conversion whatever the column heading says.
    """
    value = (value or "").strip()
    if not value:
        return None, False

    is_utc = value.endswith("Z")
    cleaned = value[:-1] if is_utc else value
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(cleaned, fmt), is_utc
        except ValueError:
            continue
    return None, False


def _clean(value) -> Optional[str]:
    value = (value or "").strip()
    return value or None


def _parse_int(value) -> Optional[int]:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _find_vehicle(db: Session, drone_name: str) -> Optional[Vehicle]:
    """Match a BRINC drone name against the fleet.

    The export carries a short hyphenated serial ("l2d-0001-00001") while the
    fleet records the full airframe serial ("1914CL2D000100001") with the short
    form in provider_serial. provider_serial is therefore tried first and only
    then serial_number: some airframes were entered with the short serial in
    both fields, and one OR-query returns whichever row the database happens to
    reach first, which can attribute flights to the wrong airframe. Ordered by
    id so an ambiguous fleet at least resolves the same way twice.

    Never creates: an unmatched drone is reported instead.
    """
    name = (drone_name or "").strip()
    if not name:
        return None
    lowered = name.lower()
    for column in (Vehicle.provider_serial, Vehicle.serial_number):
        match = (
            db.query(Vehicle)
            .filter(func.lower(column) == lowered)
            .order_by(Vehicle.id)
            .first()
        )
        if match:
            return match
    return None


def _find_or_create_pilot(db: Session, name: str) -> tuple[Optional[Pilot], bool]:
    """Match a pilot by name, creating one when the name is new.

    A new name is created active, and marked in notes as having come from an
    import. There is no way to tell a genuinely new unit pilot from a vendor rep
    on site ("Pat (Vendor) Quinn") at import time, and active is the safer
    default of the two: ``status == "active"`` gates currency tracking,
    certification rollups, the dashboard's pilot figures, and the default view
    of the Pilot Hours and Pilot Activity reports, so creating them inactive
    would quietly drop a real pilot's flights out of all of it. A vendor rep in
    the roster is visible and one click to deactivate; a missing pilot is not
    visible at all. The names created are reported to the admin either way.

    An existing pilot is returned untouched, so importing never changes the
    status of somebody already on the roster.

    A blank name goes to the shared "Unknown" pilot, which stays inactive: it
    is a placeholder for an unattributed flight rather than a person, and it can
    never hold a certification or satisfy currency. The flight itself is real
    airframe time and stays visible for review.
    """
    value = (name or "").strip()
    if not value:
        unknown = db.query(Pilot).filter(func.lower(Pilot.first_name) == "unknown").first()
        if unknown:
            return unknown, False
        unknown = Pilot(first_name="Unknown", last_name="", status="inactive",
                        notes="Placeholder for BRINC flights exported without a user.")
        db.add(unknown)
        db.flush()
        return unknown, True

    first, _, last = value.partition(" ")
    pilot = (
        db.query(Pilot)
        .filter(func.lower(Pilot.first_name) == first.lower(),
                func.lower(Pilot.last_name) == last.lower())
        .first()
    )
    if pilot:
        return pilot, False
    pilot = Pilot(
        first_name=first, last_name=last, status="active",
        notes=(f"Created by the BRINC CSV import on {date.today():%Y-%m-%d}. "
               "Confirm this is a unit pilot and not a vendor or guest operator."),
    )
    db.add(pilot)
    db.flush()
    return pilot, True


def _dedupe_key(external_id: str) -> str:
    return str(external_id).upper().replace("-", "")


def _is_duplicate(db: Session, external_id: str) -> bool:
    """Has this flight already been imported?

    Matches on the normalised external id, the same rule the Skydio importer and
    the API sync use, so re-exporting an overlapping date range is safe and the
    caller does not have to trim it.
    """
    return (
        db.query(Flight)
        .filter(func.replace(func.upper(Flight.external_id), "-", "") == _dedupe_key(external_id))
        .first()
        is not None
    )


def _resolve_addresses(db: Session, addresses: set) -> tuple[dict, int]:
    """Resolve distinct launch addresses to coordinates.

    Geocoded once per distinct address rather than once per row - this export
    had 161 addressed rows across 18 distinct addresses, and a per-row lookup
    would be both slow and outside Nominatim's usage policy.

    Any address already resolved on an existing flight is reused for free before
    the network is touched at all. The network phase is then capped by a
    wall-clock budget; whatever is left over resolves on a later import, which
    backfills flights already stored without coordinates.

    Returns (address -> (lat, lon), count still unresolved).
    """
    resolved: dict = {}
    remaining = set(addresses)

    known = (
        db.query(Flight.takeoff_address, Flight.takeoff_lat, Flight.takeoff_lon)
        .filter(Flight.takeoff_address.in_(list(remaining)),
                Flight.takeoff_lat.isnot(None))
        .all()
    )
    for addr, lat, lon in known:
        if addr in remaining:
            resolved[addr] = (lat, lon)
            remaining.discard(addr)

    unresolved = 0
    deadline = time.monotonic() + GEOCODE_BUDGET_SECONDS
    for i, addr in enumerate(sorted(remaining)):
        if time.monotonic() >= deadline:
            deferred = len(remaining) - i
            unresolved += deferred
            logger.info("brinc_import: geocode budget spent, %d address(es) deferred", deferred)
            break
        if i:
            time.sleep(GEOCODE_INTERVAL_SECONDS)
        try:
            resp = httpx.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": addr, "format": "jsonv2", "limit": 1, "addressdetails": 0},
                headers={"User-Agent": "DroneUnitManager/1.0"},
                timeout=GEOCODE_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            hits = resp.json()
            if hits:
                resolved[addr] = (float(hits[0]["lat"]), float(hits[0]["lon"]))
            else:
                unresolved += 1
        except Exception as exc:
            # A geocode failure must never fail the import: the address is still
            # recorded, the flight just has no pin on the map.
            logger.warning("brinc_import: geocode failed for %r: %s", addr, exc)
            unresolved += 1

    return resolved, unresolved


def _backfill_coords(db: Session, coords: dict) -> int:
    """Put coordinates on BRINC flights imported earlier without them.

    Without this, a flight whose address failed to geocode, or fell outside the
    budget, would stay off the map forever: a later import carrying the same
    address skips the row as a duplicate and never revisits it.
    """
    filled = 0
    for addr, (lat, lon) in coords.items():
        filled += (
            db.query(Flight)
            .filter(Flight.data_source == "brinc_csv",
                    Flight.takeoff_address == addr,
                    Flight.takeoff_lat.is_(None))
            .update({"takeoff_lat": lat, "takeoff_lon": lon}, synchronize_session=False)
        )
    return filled


class _TimeSpec(NamedTuple):
    """How to read timestamps out of this particular export."""

    start_col: Optional[str]
    end_col: Optional[str]
    header_is_utc: bool
    zone: ZoneInfo


def _time_spec(db: Session, fieldnames) -> _TimeSpec:
    start_col = _find_time_column(fieldnames, "Start Time")
    return _TimeSpec(
        start_col=start_col,
        end_col=_find_time_column(fieldnames, "End Time"),
        header_is_utc=_header_declares_utc(start_col),
        zone=_local_zone(db),
    )


def _read_time(row: dict, column: Optional[str], spec: _TimeSpec) -> Optional[datetime]:
    value, is_utc = _parse_dt(row.get(column) if column else None)
    return _to_utc(value, is_utc or spec.header_is_utc, spec.zone)


def _timezone_warning(spec: _TimeSpec, newest: Optional[datetime]) -> Optional[str]:
    """Warn when the export's timezone is not the one configured here.

    BRINC exports in the agency's BRINC timezone; conversion uses this
    instance's display timezone. If those disagree, every imported time is
    silently hours out and nothing downstream can tell. Compared at the newest
    row, which is closest to when the export was taken and so the one the
    heading actually describes.
    """
    stated = _header_offset_hours(spec.start_col)
    if stated is None or newest is None:
        return None
    actual = spec.zone.utcoffset(newest)
    if actual is None or actual.total_seconds() / 3600 == stated:
        return None
    return (
        f"Export heading claims UTC{stated:+d}, but this instance's timezone "
        f"({spec.zone.key}) was UTC{int(actual.total_seconds() // 3600):+d} on "
        f"{newest.date()}. Imported times may be wrong by the difference. "
        f"Re-export from BRINC in UTC, or correct the timezone in Settings."
    )


def _accept_row(db: Session, row: dict, line_no: int, spec: _TimeSpec,
                seen: set, result: dict):
    """Decide whether a row is importable.

    Returns (external_id, vehicle, duration, takeoff, landing), or None having
    already recorded in ``result`` why the row was skipped.
    """
    external_id = _clean(row.get("Flight Id"))
    if not external_id:
        result["errors"].append(f"Row {line_no}: no Flight Id")
        return None

    # Against the database, and against earlier rows of this same file. The
    # session does not autoflush, so a row added moments ago is invisible to
    # the query and two copies in one file would both be written.
    key = _dedupe_key(external_id)
    if key in seen or _is_duplicate(db, external_id):
        result["flights_skipped"] += 1
        return None
    seen.add(key)

    drone = _clean(row.get("Drone Name")) or ""
    vehicle = _find_vehicle(db, drone)
    if not vehicle:
        result["unmatched_drones"][drone] = result["unmatched_drones"].get(drone, 0) + 1
        result["flights_skipped"] += 1
        return None

    duration = _parse_int(row.get("Flight Time (Seconds)"))
    if duration is None or duration < MINIMUM_DURATION_SECONDS:
        result["flights_skipped_zero_duration"] += 1
        result["flights_skipped"] += 1
        return None

    # No usable time means no date. Dating the flight "today" instead would file
    # it under the day of the import, where it would count towards this month on
    # the dashboard and in reports as a flight that never happened then.
    takeoff = _read_time(row, spec.start_col, spec)
    if takeoff is None:
        result["errors"].append(f"Row {line_no}: no usable start time")
        result["flights_skipped"] += 1
        return None

    return external_id, vehicle, duration, takeoff, _read_time(row, spec.end_col, spec)


def _build_flight(db: Session, row: dict, accepted, coords: dict, result: dict) -> Flight:
    external_id, vehicle, duration, takeoff, landing = accepted

    pilot, created = _find_or_create_pilot(db, row.get("User"))
    if created:
        result["pilots_created"] += 1
        # Named, not just counted. These go onto the active roster, and the
        # admin is the only one who can tell a new unit pilot from a vendor rep
        # or from a second spelling of someone already there ("Jonathan Reed"
        # against an existing "Jon Reed").
        result["pilots_created_names"].append(pilot.full_name.strip())

    address = _clean(row.get("Launch Address"))
    lat, lon = coords.get(address, (None, None)) if address else (None, None)

    return Flight(
        external_id=external_id,
        api_provider="brinc",
        data_source="brinc_csv",
        pilot_id=pilot.id if pilot else None,
        vehicle_id=vehicle.id,
        date=takeoff.date(),
        takeoff_time=takeoff,
        landing_time=landing,
        duration_seconds=duration,
        takeoff_address=address or "",
        takeoff_lat=lat,
        takeoff_lon=lon,
        # Empty in exports so far, mapped for when BRINC populates them.
        case_number=_clean(row.get("Case Id")),
        purpose=None,
        review_status="needs_review",
        pilot_confirmed=False,
    )


def import_brinc_csv(db: Session, file_bytes: bytes, geocode: bool = True) -> dict:
    """Import a BRINC flight-list CSV export."""
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    spec = _time_spec(db, reader.fieldnames)

    result = {
        "flights_imported": 0,
        "flights_skipped": 0,
        "flights_skipped_zero_duration": 0,
        "pilots_created": 0,
        "pilots_created_names": [],
        "unmatched_drones": {},
        "addresses_geocoded": 0,
        "addresses_failed": 0,
        "coordinates_backfilled": 0,
        "source_timezone": (spec.start_col or "unknown"),
        "timezone_used": spec.zone.key,
        "warnings": [],
        "errors": [],
    }

    coords = {}
    if geocode:
        addresses = {a for a in (_clean(r.get("Launch Address")) for r in rows) if a}
        if addresses:
            coords, result["addresses_failed"] = _resolve_addresses(db, addresses)
            result["addresses_geocoded"] = len(coords)
            result["coordinates_backfilled"] = _backfill_coords(db, coords)

    seen: set = set()
    # Tracked here rather than read back off the session: creating a pilot
    # flushes, which empties db.new, and the warning would then be judged
    # against whichever rows happened to follow the last flush.
    newest: Optional[datetime] = None
    for line_no, row in enumerate(rows, start=2):
        try:
            accepted = _accept_row(db, row, line_no, spec, seen, result)
            if not accepted:
                continue
            flight = _build_flight(db, row, accepted, coords, result)
            db.add(flight)
            result["flights_imported"] += 1
            if newest is None or flight.takeoff_time > newest:
                newest = flight.takeoff_time
        except Exception as exc:
            result["errors"].append(f"Row {line_no}: {exc}")

    if not spec.header_is_utc:
        warning = _timezone_warning(spec, newest)
        if warning:
            result["warnings"].append(warning)

    db.commit()
    result["imported"] = result["flights_imported"]
    return result
