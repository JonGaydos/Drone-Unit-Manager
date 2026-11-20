"""Each assigned pilot's progress on a flight requirement for one period.

``evaluate_period`` loads the period's flights once for every assigned pilot
and works out each pilot's totals per model, status and excusal. Only flights
that pass both count rules (reviewed, and counted toward unit totals) count;
unreviewed ones that would otherwise count are reported apart so a supervisor
can review them before the grace period ends.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, joinedload

from app.models.flight import Flight
from app.models.flight_requirement import FlightRequirement, FlightRequirementResult
from app.models.pilot import Pilot
from app.models.setting import Setting
from app.models.vehicle import Vehicle
from app.routers.currency import counted_flights_filter
from app.services.fleet_models import fleet_models, normalize_model
from app.services.flight_scope import counted_flight_clause
from app.services.local_time import display_zone, local_flight_date
from app.services.requirement_periods import Period
from app.services.requirement_time import (
    Interval, WindowSettings, flight_interval, minutes_inside, period_bounds, windows_for_period,
)

ALL_KEY = "*"
MET, ON_TRACK, PENDING_REVIEW, MISSED, EXCUSED = "met", "on_track", "pending_review", "missed", "excused"
AUTO_EXCUSE_REASON = "Added after the period started"
DEFAULT_GRACE_DAYS = 14
DEFAULT_FISCAL_START_MONTH = 10


@dataclass(frozen=True)
class UnitEvalSettings:
    """The unit settings evaluation needs, read once by ``unit_eval_settings``."""

    zone: ZoneInfo
    lat: float | None
    lon: float | None
    grace_days: int
    fiscal_start_month: int


@dataclass
class PilotProgress:
    pilot_id: int
    status: str
    totals: dict[str, dict]
    met_by_model: dict[str, bool]
    excluded_no_takeoff: int
    unreviewed_in_period: int
    excused: bool
    excused_reason: str | None


@dataclass(frozen=True)
class _Context:
    period: Period
    keys: list[str]
    key_map: dict[str, str] | None  # normalized model to totals key; None counts every flight
    purposes: frozenset[str]
    zone: tzinfo
    windows: list[Interval] | None  # None for any time of day
    clip: Interval

    def in_period(self, day: date) -> bool:
        return self.period[0] <= day <= self.period[1]


@dataclass
class _Tally:
    totals: dict[str, dict]
    excluded_no_takeoff: int = 0
    unreviewed_in_period: int = 0


def _float_or_none(value: str | None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or(value: str | None, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: int, low: int, high: int) -> int:
    return min(max(value, low), high)


def unit_eval_settings(db: Session) -> UnitEvalSettings:
    """Display zone, unit default location, grace days and fiscal start month.

    Blank or unreadable values fall back to no location, 14 grace days and an
    October fiscal year; grace days are kept to 0..60 and the month to 1..12.
    """
    keys = ("org_default_lat", "org_default_lon", "requirements_grace_days", "fiscal_year_start_month")
    values = dict(db.query(Setting.key, Setting.value).filter(Setting.key.in_(keys)).all())
    return UnitEvalSettings(
        zone=display_zone(db),
        lat=_float_or_none(values.get("org_default_lat")),
        lon=_float_or_none(values.get("org_default_lon")),
        grace_days=_clamp(_int_or(values.get("requirements_grace_days"), DEFAULT_GRACE_DAYS), 0, 60),
        fiscal_start_month=_clamp(_int_or(values.get("fiscal_year_start_month"), DEFAULT_FISCAL_START_MONTH), 1, 12),
    )


def assigned_pilots(db: Session, req: FlightRequirement) -> list[Pilot]:
    """The requirement's selected pilots that are active, or every active pilot."""
    query = db.query(Pilot).filter(Pilot.status == "active")
    if req.pilots:
        query = query.filter(Pilot.id.in_([row.pilot_id for row in req.pilots]))
    return query.order_by(Pilot.id).all()


def _models_present_at(db: Session, period_start: date) -> list[str]:
    """Fleet model names with a non-retired vehicle created on or before ``period_start`` (local)."""
    zone = display_zone(db)
    rows = db.query(Vehicle.model, Vehicle.created_at).filter(Vehicle.status != "retired").all()
    present = {
        normalize_model(model) for model, created_at in rows
        if created_at is None or local_flight_date(created_at, zone) <= period_start
    }
    return [m["name"] for m in fleet_models(db) if normalize_model(m["name"]) in present]


def scope_models(db: Session, req: FlightRequirement, period_start: date) -> list[str] | None:
    """The models a period counts, by their fleet display spelling.

    None means every flight counts (``all``, or ``combined`` with no models).
    ``each_all_active`` follows the fleet: a model joins the first period that
    starts on or after its first non-retired vehicle was added.
    """
    if req.model_mode == "each_all_active":
        return _models_present_at(db, period_start)
    if req.model_mode == "all" or not req.models:
        return None
    names = {normalize_model(m["name"]): m["name"] for m in fleet_models(db)}
    scoped: dict[str, str] = {}
    for row in req.models:
        key = normalize_model(row.model)
        scoped.setdefault(key, names.get(key, " ".join(row.model.split())))
    return sorted(scoped.values(), key=str.casefold)


def _windows(req: FlightRequirement, period: Period, settings: UnitEvalSettings) -> list[Interval] | None:
    if req.time_mode == "any":
        return None
    if req.time_mode == "night" and (settings.lat is None or settings.lon is None):
        return []
    window_settings = WindowSettings(zone=settings.zone, window_start=req.window_start_time,
                                     window_end=req.window_end_time, lat=settings.lat, lon=settings.lon)
    return windows_for_period(req.time_mode, period, window_settings)


def _context(req: FlightRequirement, period: Period, settings: UnitEvalSettings,
             models: list[str] | None) -> _Context:
    if models is None:
        keys, key_map = [ALL_KEY], None
    elif req.model_mode == "combined":
        keys, key_map = [ALL_KEY], dict.fromkeys((normalize_model(m) for m in models), ALL_KEY)
    else:
        keys, key_map = list(models), {normalize_model(m): m for m in models}
    purposes = frozenset(p.purpose.strip().casefold() for p in req.purposes if p.purpose.strip())
    return _Context(period=period, keys=keys, key_map=key_map, purposes=purposes, zone=settings.zone,
                    windows=_windows(req, period, settings), clip=period_bounds(period, settings.zone))


def _load_flights(db: Session, pilot_ids: list[int], ctx: _Context) -> list[tuple[Flight, bool]]:
    """Every counted-toward-totals flight of the pilots from the day before the
    period through its end, with whether it is reviewed, purpose-filtered."""
    first, last = ctx.period
    rows = (
        db.query(Flight, counted_flights_filter().label("reviewed"))
        .options(joinedload(Flight.vehicle))
        .filter(Flight.pilot_id.in_(pilot_ids), counted_flight_clause(),
                Flight.date >= first - timedelta(days=1), Flight.date <= last)
        .all()
    )
    return [(flight, bool(reviewed)) for flight, reviewed in rows
            if not ctx.purposes or (flight.purpose or "").strip().casefold() in ctx.purposes]


def _flight_key(flight: Flight, ctx: _Context) -> str | None:
    """The totals key a flight adds to, or None when its model is out of scope."""
    if ctx.key_map is None:
        return ALL_KEY
    return ctx.key_map.get(normalize_model(flight.vehicle.model if flight.vehicle else None))


def _amount(flight: Flight, ctx: _Context) -> tuple[float, int] | None:
    """Minutes and flights a flight adds, or None when it has no interval to place in a window."""
    if ctx.windows is None:
        if not ctx.in_period(flight.date):
            return 0.0, 0
        return (flight.duration_seconds or 0) / 60, 1
    interval = flight_interval(flight, ctx.zone)
    if interval is None:
        return None
    minutes = minutes_inside(interval, ctx.windows, ctx.clip)
    return minutes, 1 if minutes > 0 else 0


def _record(tally: _Tally, key: str, flight: Flight, reviewed: bool, ctx: _Context) -> None:
    amount = _amount(flight, ctx)
    if not reviewed:
        tally.unreviewed_in_period += amount is not None and amount[1] > 0
        return
    if amount is None:
        tally.excluded_no_takeoff += ctx.in_period(flight.date)
        return
    total = tally.totals[key]
    total["minutes"] += amount[0]
    total["flights"] += amount[1]


def _reaches(total: dict, req: FlightRequirement) -> bool:
    if req.target_minutes is not None and total["minutes"] < req.target_minutes:
        return False
    return req.target_flights is None or total["flights"] >= req.target_flights


def _status(met: bool, excused: bool, period_end: date, today: date, grace_days: int) -> str:
    if met:
        return MET
    if excused:
        return EXCUSED
    if today <= period_end:
        return ON_TRACK
    if today <= period_end + timedelta(days=grace_days):
        return PENDING_REVIEW
    return MISSED


def _joined_on(pilot: Pilot, added_at: datetime | None, zone: tzinfo) -> date | None:
    """The later of the pilot's creation and assignment, as local dates."""
    days = [local_flight_date(moment, zone) for moment in (pilot.created_at, added_at) if moment is not None]
    return max(days, default=None)


def _excusals(db: Session, req: FlightRequirement, pilots: list[Pilot], period_start: date,
              zone: tzinfo) -> dict[int, tuple[bool, str | None]]:
    """Per pilot, whether excused and why: a stored override wins, else a pilot
    who joined after both the period start and the requirement's creation is
    excused automatically. Assignment rows written when the requirement was
    created carry its creation time, so they do not excuse anyone."""
    overrides = {
        row.pilot_id: row for row in db.query(FlightRequirementResult).filter(
            FlightRequirementResult.requirement_id == req.id,
            FlightRequirementResult.period_start == period_start,
            FlightRequirementResult.excused.isnot(None),
        )
    }
    added = {row.pilot_id: row.added_at for row in req.pilots}
    created = local_flight_date(req.created_at, zone)
    cutoff = max(period_start, created) if created is not None else period_start
    result: dict[int, tuple[bool, str | None]] = {}
    for pilot in pilots:
        row = overrides.get(pilot.id)
        if row is not None:
            result[pilot.id] = (bool(row.excused), row.excused_reason if row.excused else None)
            continue
        joined = _joined_on(pilot, added.get(pilot.id), zone)
        late = joined is not None and joined > cutoff
        result[pilot.id] = (late, AUTO_EXCUSE_REASON if late else None)
    return result


def evaluate_period(db: Session, req: FlightRequirement, period: tuple[date, date], today: date,
                    grace_days: int) -> dict[int, PilotProgress]:
    """Progress of every assigned pilot on ``req`` for ``period``, keyed by pilot id.

    Totals are ``{"minutes": float, "flights": int}`` per model display name,
    or under ``"*"`` for all aircraft and combined models. With no models in
    scope there is nothing to meet, so the status follows the date. ``excused`` is the
    excusal decision; it shows as the status only when the target is not met.
    """
    pilots = assigned_pilots(db, req)
    if not pilots:
        return {}
    settings = unit_eval_settings(db)
    ctx = _context(req, period, settings, scope_models(db, req, period[0]))
    tallies = {p.id: _Tally(totals={k: {"minutes": 0, "flights": 0} for k in ctx.keys}) for p in pilots}
    for flight, reviewed in _load_flights(db, list(tallies), ctx):
        key = _flight_key(flight, ctx)
        if key is not None:
            _record(tallies[flight.pilot_id], key, flight, reviewed, ctx)
    excusals = _excusals(db, req, pilots, period[0], settings.zone)
    progress: dict[int, PilotProgress] = {}
    for pilot_id, tally in tallies.items():
        met_by_model = {key: _reaches(total, req) for key, total in tally.totals.items()}
        excused, reason = excusals[pilot_id]
        progress[pilot_id] = PilotProgress(
            pilot_id=pilot_id,
            status=_status(bool(met_by_model) and all(met_by_model.values()), excused, period[1], today, grace_days),
            totals=tally.totals, met_by_model=met_by_model,
            excluded_no_takeoff=tally.excluded_no_takeoff,
            unreviewed_in_period=tally.unreviewed_in_period,
            excused=excused, excused_reason=reason,
        )
    return progress
