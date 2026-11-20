"""Period math for flight requirements.

Pure functions, no database. A PeriodSpec describes how a requirement's periods
are laid out; period_containing, periods_between and first_period answer which
inclusive (start, end) periods exist. Recurring periods are generated one by
one from an anchor, so consecutive periods never overlap. Calendar, fiscal, span
and every-N-months periods tile with no gap; monthly windows leave gaps by design
(19 to 5 leaves the 6th to the 18th).
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Iterator, Literal

PeriodType = Literal[
    "calendar_month",
    "calendar_quarter",
    "calendar_year",
    "fiscal_quarter",
    "fiscal_year",
    "monthly_window",
    "span",
    "custom",
    "every_n_months",
]

Period = tuple[date, date]


@dataclass(frozen=True)
class PeriodSpec:
    period_type: PeriodType
    start: date
    end: date | None
    recurring: bool
    window_start_day: int | None = None
    window_end_day: int | None = None
    span_length: int | None = None
    span_unit: Literal["days", "weeks", "months"] | None = None
    every_months: int | None = None
    fiscal_start_month: int = 10


def _add_months(d: date, months: int) -> date:
    """Add calendar months, clamping the day to the target month's length."""
    year, month0 = divmod(d.year * 12 + d.month - 1 + months, 12)
    month = month0 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _clamped(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _months_period(anchor: date, length: int, k: int) -> Period:
    first = _add_months(anchor, k * length)
    last = _add_months(anchor, (k + 1) * length) - timedelta(days=1)
    return first, last


def _calendar_anchor(spec: PeriodSpec) -> tuple[date, int]:
    """First-of-month anchor and length in months of the period holding start."""
    month = spec.start.month
    if spec.period_type == "calendar_month":
        first_month, length = month, 1
    elif spec.period_type == "calendar_quarter":
        first_month, length = (month - 1) // 3 * 3 + 1, 3
    elif spec.period_type == "calendar_year":
        first_month, length = 1, 12
    else:
        length = 3 if spec.period_type == "fiscal_quarter" else 12
        offset = (month - spec.fiscal_start_month) % 12
        first_month = (month - offset % length - 1) % 12 + 1
    year = spec.start.year - (1 if first_month > month else 0)
    return date(year, first_month, 1), length


def _nth_calendar(spec: PeriodSpec, k: int) -> Period:
    anchor, length = _calendar_anchor(spec)
    return _months_period(anchor, length, k)


def _nth_every_n_months(spec: PeriodSpec, k: int) -> Period:
    return _months_period(spec.start, spec.every_months or 1, k)


def _nth_span(spec: PeriodSpec, k: int) -> Period:
    length = spec.span_length or 1
    if spec.span_unit == "months":
        return _months_period(spec.start, length, k)
    days = length * (7 if spec.span_unit == "weeks" else 1)
    first = spec.start + timedelta(days=k * days)
    return first, first + timedelta(days=days - 1)


def _nth_window(spec: PeriodSpec, k: int) -> Period:
    start_day = spec.window_start_day or 1
    end_day = spec.window_end_day or start_day
    year, month = spec.start.year, spec.start.month
    if _clamped(year, month, start_day) < spec.start:
        month += 1
    index = year * 12 + month - 1 + k
    year, month = index // 12, index % 12 + 1
    first = _clamped(year, month, start_day)
    if end_day >= start_day:
        return first, _clamped(year, month, end_day)
    end_index = index + 1
    last = _clamped(end_index // 12, end_index % 12 + 1, end_day)
    next_start = _clamped(end_index // 12, end_index % 12 + 1, start_day)
    if last >= next_start:
        last = next_start - timedelta(days=1)
    return first, last


def _nth_custom(spec: PeriodSpec, _k: int) -> Period:
    return spec.start, spec.end or spec.start


_NTH: dict[str, Callable[[PeriodSpec, int], Period]] = {
    "calendar_month": _nth_calendar,
    "calendar_quarter": _nth_calendar,
    "calendar_year": _nth_calendar,
    "fiscal_quarter": _nth_calendar,
    "fiscal_year": _nth_calendar,
    "monthly_window": _nth_window,
    "span": _nth_span,
    "every_n_months": _nth_every_n_months,
    "custom": _nth_custom,
}


def _periods(spec: PeriodSpec) -> Iterator[Period]:
    """Yield periods in order, stopping per the one-time and end-date rules."""
    nth = _NTH[spec.period_type]
    recurring = spec.recurring and spec.period_type != "custom"
    k = 0
    while True:
        period = nth(spec, k)
        if k > 0 and not recurring:
            return
        if recurring and spec.end is not None and period[0] > spec.end:
            return
        yield period
        k += 1


def first_period(spec: PeriodSpec) -> Period | None:
    return next(_periods(spec), None)


def period_containing(spec: PeriodSpec, day: date) -> Period | None:
    for first, last in _periods(spec):
        if day < first:
            return None
        if day <= last:
            return first, last
    return None


def periods_between(spec: PeriodSpec, first: date, last: date) -> list[Period]:
    found: list[Period] = []
    for p_first, p_last in _periods(spec):
        if p_first > last:
            break
        if p_last >= first:
            found.append((p_first, p_last))
    return found
