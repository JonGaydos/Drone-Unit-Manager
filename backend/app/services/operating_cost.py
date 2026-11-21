"""Flight operating cost: a typed cost wins, otherwise an estimate from the
aircraft's hourly rate. The estimate is worked out when read, never stored, so
a changed rate also changes past flights' estimates."""

from sqlalchemy import func

from app.models.flight import Flight
from app.models.vehicle import Vehicle


def estimate_operating_cost(flight) -> float | None:
    """Duration hours x the vehicle's hourly rate, rounded to cents, or None
    when the flight has a typed cost, no vehicle, no rate or no duration."""
    if flight.operating_cost is not None or not flight.duration_seconds:
        return None
    rate = flight.vehicle.hourly_operating_cost if flight.vehicle else None
    if rate is None:
        return None
    return round(flight.duration_seconds / 3600 * rate, 2)


def flight_cost_sql():
    """SQL for one flight's shown cost (typed, else estimate). Needs Vehicle
    joined on Flight.vehicle_id."""
    estimate = func.round(Flight.duration_seconds * Vehicle.hourly_operating_cost / 3600.0, 2)
    return func.coalesce(Flight.operating_cost, estimate)


def format_cost(value: float | None, estimated: bool = False) -> str:
    """A report cell: two decimals, marked "(est.)" when estimated, blank when
    there is no cost."""
    if value is None:
        return ""
    text = f"{value:.2f}"
    return f"{text} (est.)" if estimated else text
