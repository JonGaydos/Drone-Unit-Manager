from datetime import date, timedelta

from app.services.requirement_periods import (
    PeriodSpec,
    first_period,
    period_containing,
    periods_between,
)

D = date


def spec(period_type, start, **kw):
    kw.setdefault("end", None)
    kw.setdefault("recurring", True)
    return PeriodSpec(period_type=period_type, start=start, **kw)


def test_calendar_month():
    s = spec("calendar_month", D(2026, 10, 1))
    assert period_containing(s, D(2026, 10, 31)) == (D(2026, 10, 1), D(2026, 10, 31))
    assert period_containing(s, D(2026, 11, 1)) == (D(2026, 11, 1), D(2026, 11, 30))
    once = spec("calendar_month", D(2026, 10, 1), recurring=False)
    assert period_containing(once, D(2026, 11, 10)) is None


def test_calendar_quarter_and_year():
    q = spec("calendar_quarter", D(2026, 10, 1))
    assert period_containing(q, D(2026, 11, 15)) == (D(2026, 10, 1), D(2026, 12, 31))
    y = spec("calendar_year", D(2026, 1, 1))
    assert period_containing(y, D(2026, 11, 15)) == (D(2026, 1, 1), D(2026, 12, 31))


def test_fiscal_quarter_october_start():
    q = spec("fiscal_quarter", D(2026, 10, 1))
    assert period_containing(q, D(2027, 1, 5)) == (D(2027, 1, 1), D(2027, 3, 31))
    y = spec("fiscal_year", D(2025, 10, 1))
    assert period_containing(y, D(2026, 10, 1)) == (D(2026, 10, 1), D(2027, 9, 30))
    assert period_containing(y, D(2026, 9, 30)) == (D(2025, 10, 1), D(2026, 9, 30))


def test_fiscal_quarter_other_start_month():
    q = spec("fiscal_quarter", D(2026, 7, 1), fiscal_start_month=7)
    assert period_containing(q, D(2026, 8, 1)) == (D(2026, 7, 1), D(2026, 9, 30))


def test_monthly_window_rolls_into_next_month():
    s = spec("monthly_window", D(2026, 11, 19), window_start_day=19, window_end_day=5)
    assert period_containing(s, D(2026, 12, 3)) == (D(2026, 11, 19), D(2026, 12, 5))
    assert period_containing(s, D(2026, 12, 10)) is None
    assert period_containing(s, D(2026, 12, 19)) == (D(2026, 12, 19), D(2027, 1, 5))


def test_monthly_window_short_month():
    s = spec("monthly_window", D(2027, 1, 31), window_start_day=31, window_end_day=5)
    assert periods_between(s, D(2027, 1, 31), D(2027, 3, 5)) == [
        (D(2027, 1, 31), D(2027, 2, 5)),
        (D(2027, 2, 28), D(2027, 3, 5)),
    ]
    leap = spec("monthly_window", D(2028, 1, 30), window_start_day=30, window_end_day=28)
    assert periods_between(leap, D(2028, 1, 30), D(2028, 3, 28)) == [
        (D(2028, 1, 30), D(2028, 2, 28)),
        (D(2028, 2, 29), D(2028, 3, 28)),
    ]


def test_monthly_window_same_month():
    s = spec("monthly_window", D(2026, 11, 19), window_start_day=1, window_end_day=10)
    assert period_containing(s, D(2026, 12, 5)) == (D(2026, 12, 1), D(2026, 12, 10))
    assert period_containing(s, D(2026, 12, 11)) is None
    assert first_period(s) == (D(2026, 12, 1), D(2026, 12, 10))


def test_span_weeks_and_months():
    w = spec("span", D(2026, 11, 19), span_length=2, span_unit="weeks")
    assert first_period(w) == (D(2026, 11, 19), D(2026, 12, 2))
    assert period_containing(w, D(2026, 12, 3)) == (D(2026, 12, 3), D(2026, 12, 16))
    m = spec("span", D(2026, 11, 30), span_length=3, span_unit="months")
    assert first_period(m) == (D(2026, 11, 30), D(2027, 2, 27))
    d = spec("span", D(2026, 11, 19), span_length=10, span_unit="days", recurring=False)
    assert first_period(d) == (D(2026, 11, 19), D(2026, 11, 28))
    assert period_containing(d, D(2026, 11, 29)) is None


def test_every_n_months():
    s = spec("every_n_months", D(2026, 11, 1), every_months=2)
    assert first_period(s) == (D(2026, 11, 1), D(2026, 12, 31))
    assert period_containing(s, D(2027, 1, 20)) == (D(2027, 1, 1), D(2027, 2, 28))


def test_custom_range():
    s = spec("custom", D(2026, 12, 1), end=D(2026, 12, 24), recurring=True)
    assert period_containing(s, D(2026, 12, 10)) == (D(2026, 12, 1), D(2026, 12, 24))
    assert period_containing(s, D(2026, 12, 25)) is None


def test_recurring_end_date():
    s = spec("calendar_month", D(2026, 10, 1), end=D(2026, 12, 15))
    assert period_containing(s, D(2026, 12, 20)) == (D(2026, 12, 1), D(2026, 12, 31))
    assert period_containing(s, D(2027, 1, 5)) is None


def test_before_start_is_none():
    s = spec("calendar_month", D(2026, 10, 1))
    assert period_containing(s, D(2026, 9, 30)) is None
    w = spec("monthly_window", D(2026, 11, 19), window_start_day=19, window_end_day=5)
    assert period_containing(w, D(2026, 11, 1)) is None


def test_periods_between_tiles_without_gaps():
    s = spec("calendar_month", D(2026, 10, 1))
    got = periods_between(s, D(2026, 10, 15), D(2027, 1, 10))
    assert got == [
        (D(2026, 10, 1), D(2026, 10, 31)),
        (D(2026, 11, 1), D(2026, 11, 30)),
        (D(2026, 12, 1), D(2026, 12, 31)),
        (D(2027, 1, 1), D(2027, 1, 31)),
    ]


def test_rolling_window_end_capped_before_next_start():
    s = spec("monthly_window", D(2027, 1, 1), window_start_day=31, window_end_day=30)
    assert periods_between(s, D(2027, 1, 1), D(2027, 6, 29)) == [
        (D(2027, 1, 31), D(2027, 2, 27)),
        (D(2027, 2, 28), D(2027, 3, 30)),
        (D(2027, 3, 31), D(2027, 4, 29)),
        (D(2027, 4, 30), D(2027, 5, 30)),
        (D(2027, 5, 31), D(2027, 6, 29)),
    ]
    t = spec("monthly_window", D(2027, 1, 30), window_start_day=30, window_end_day=29)
    assert periods_between(t, D(2027, 1, 30), D(2027, 3, 29)) == [
        (D(2027, 1, 30), D(2027, 2, 27)),
        (D(2027, 2, 28), D(2027, 3, 29)),
    ]


def test_rolling_windows_x_to_x_minus_one_never_overlap_or_gap():
    for start_day, end_day in [(31, 30), (30, 29), (29, 28), (19, 18)]:
        for year in (2027, 2028):
            s = spec(
                "monthly_window",
                D(year, 1, 1),
                window_start_day=start_day,
                window_end_day=end_day,
            )
            got = periods_between(s, D(year, 1, 1), D(year + 2, 1, 1))[:24]
            assert len(got) == 24
            for (_, prev_end), (next_start, _) in zip(got, got[1:]):
                assert next_start == prev_end + timedelta(days=1)


def test_first_period_none_when_end_precedes_first_window():
    s = spec(
        "monthly_window",
        D(2026, 11, 20),
        end=D(2026, 12, 10),
        window_start_day=19,
        window_end_day=5,
    )
    assert first_period(s) is None
    assert period_containing(s, D(2026, 12, 25)) is None
