"""Flight requirements in the compliance score: who is out of standing, the
15-point part, the score breakdown and the compliance payload."""

import itertools
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.flight_requirement import (
    FlightRequirement, FlightRequirementLapse, FlightRequirementPilot, FlightRequirementResult,
)
from app.models.operating_authority import AUTHORITY_SCORE_CAP
from app.models.pilot import Pilot
from app.models.setting import Setting
from app.routers import dashboard
from app.routers.dashboard import _calc_compliance_score, _score_breakdown, _score_payload
from app.services import requirement_standing
from app.services.requirement_standing import pilots_not_in_standing

TODAY = date(2026, 11, 20)
LONG_AGO = datetime(2025, 1, 1, tzinfo=timezone.utc)
SEP = (date(2026, 9, 1), date(2026, 9, 30))
OCT = (date(2026, 10, 1), date(2026, 10, 31))
COMPLIANCE_URL = "/api/dashboard/compliance"
REQUIREMENTS_AREA = "Flight requirements"


@pytest.fixture(autouse=True)
def chicago(db, monkeypatch):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()
    monkeypatch.setattr(dashboard, "local_today", lambda _db: TODAY)


def _pilot(db, status="active"):
    pilot = Pilot(first_name="Test", last_name="Pilot", status=status, created_at=LONG_AGO)
    db.add(pilot)
    db.commit()
    return pilot


def _periodic(db, pilots=(), **extra):
    values = {"name": "Monthly 1 hr", "period_type": "calendar_month", "start_date": SEP[0],
              "recurring": True, "model_mode": "all", "time_mode": "any", "target_minutes": 60,
              "created_at": LONG_AGO}
    values.update(extra)
    req = FlightRequirement(**values, pilots=[FlightRequirementPilot(pilot_id=p.id, added_at=LONG_AGO)
                                              for p in pilots])
    db.add(req)
    db.commit()
    return req


def _rolling(db, pilots=(), **extra):
    return _periodic(db, pilots, name="Rolling 1 hr", period_type="rolling", recurring=False,
                     span_length=30, span_unit="days", start_date=date(2026, 1, 1), **extra)


def _saved(db, req, pilot, period, status, excused=None):
    db.add(FlightRequirementResult(requirement_id=req.id, pilot_id=pilot.id, period_start=period[0],
                                   period_end=period[1], status=status, totals={}, target_snapshot={},
                                   excused=excused, saved_at=LONG_AGO))
    db.commit()


def _lapse(db, req, pilot, lapsed_on=date(2026, 11, 1), recovered_on=None):
    db.add(FlightRequirementLapse(requirement_id=req.id, pilot_id=pilot.id, lapsed_on=lapsed_on,
                                  recovered_on=recovered_on))
    db.commit()


# Who is out of standing


def test_pilot_missed_on_one_requirement_and_lapsed_on_another_counts_once(db):
    pilot, other = _pilot(db), _pilot(db)
    periodic = _periodic(db)
    rolling = _rolling(db)
    _saved(db, periodic, pilot, OCT, "missed")
    _saved(db, periodic, other, OCT, "met")
    _lapse(db, rolling, pilot)

    assert pilots_not_in_standing(db, TODAY) == ({pilot.id}, 2)


def test_missed_latest_period_counts(db):
    pilot = _pilot(db)
    req = _periodic(db)
    _saved(db, req, pilot, SEP, "met")
    _saved(db, req, pilot, OCT, "missed")

    assert pilots_not_in_standing(db, TODAY)[0] == {pilot.id}


def test_open_lapse_counts(db):
    pilot = _pilot(db)
    _lapse(db, _rolling(db), pilot)

    assert pilots_not_in_standing(db, TODAY)[0] == {pilot.id}


def test_excused_miss_does_not_count(db):
    pilot = _pilot(db)
    _saved(db, _periodic(db), pilot, OCT, "missed", excused=True)

    assert pilots_not_in_standing(db, TODAY)[0] == set()


def test_closed_lapse_does_not_count(db):
    pilot = _pilot(db)
    _lapse(db, _rolling(db), pilot, recovered_on=date(2026, 11, 10))

    assert pilots_not_in_standing(db, TODAY)[0] == set()


def test_miss_stops_counting_once_a_newer_period_is_saved(db):
    pilot, other = _pilot(db), _pilot(db)
    req = _periodic(db)
    _saved(db, req, pilot, SEP, "missed")
    _saved(db, req, other, SEP, "met")
    # October is saved for the other pilot only (the first was not assigned then).
    _saved(db, req, other, OCT, "met")

    assert pilots_not_in_standing(db, TODAY)[0] == set()


def test_inactive_pilot_does_not_count(db):
    pilot = _pilot(db, status="inactive")
    _saved(db, _periodic(db), pilot, OCT, "missed")
    _lapse(db, _rolling(db), pilot)

    assert pilots_not_in_standing(db, TODAY)[0] == set()


def test_switched_off_requirements_do_not_count(db):
    pilot = _pilot(db)
    _saved(db, _periodic(db, is_active=False), pilot, OCT, "missed")
    _lapse(db, _rolling(db, is_active=False), pilot)

    assert pilots_not_in_standing(db, TODAY) == (set(), 0)


def test_active_requirements_are_counted_periodic_and_rolling(db):
    _periodic(db)
    _rolling(db)
    _periodic(db, name="Off", is_active=False)

    assert pilots_not_in_standing(db, TODAY)[1] == 2


# The score


def test_no_active_requirement_means_no_deduction():
    assert _calc_compliance_score(10, 0, 0, 0, 0, 0, pilots_out_of_standing=4, requirements_active=0) == 100


def test_requirements_take_up_to_15_points():
    assert _calc_compliance_score(10, 0, 0, 0, 0, 0, pilots_out_of_standing=10, requirements_active=1) == 85


def test_requirement_deduction_is_the_share_of_pilots_out_of_standing():
    assert _calc_compliance_score(10, 0, 0, 0, 0, 0, pilots_out_of_standing=2, requirements_active=3) == 97


def test_no_pilots_means_no_requirement_deduction():
    assert _calc_compliance_score(0, 0, 0, 0, 0, 0, pilots_out_of_standing=0, requirements_active=1) == 100


def _score_before_requirements(pilots, exp_certs, vehicles, exp_regs, overdue, incidents,
                               authorities_expiring=0, authorities_expired_advisory=0,
                               authority_cap=False):
    """The score as it was before flight requirements took a part (commit ecbe7e0), kept
    verbatim to characterize the other parts."""
    deductions = 0
    if pilots > 0:
        deductions += (exp_certs / pilots) * 25
    if vehicles > 0:
        deductions += (exp_regs / vehicles) * 20
    deductions += min(overdue * 5, 20)
    deductions += min(incidents * 10, 20)
    if authorities_expired_advisory > 0:
        deductions += 10
    if authorities_expiring > 0:
        deductions += 5
    score = max(0, round(100 - deductions))
    if authority_cap:
        score = min(score, AUTHORITY_SCORE_CAP)
    return score


GRID = list(itertools.product(
    (0, 3, 7, 10),  # pilots
    (0, 1, 2, 3),  # pilots with expired certifications
    (0, 4, 6),  # vehicles
    (0, 1, 3),  # expired registrations
    (0, 1, 3, 5),  # overdue maintenance
    (0, 1, 2, 3),  # open incidents
    (0, 2),  # authorities expiring
    (0, 1),  # advisory authorities expired
    (False, True),  # grounding authority expired
))


def test_other_score_parts_are_unchanged():
    mismatches = []
    for pilots, certs, vehicles, regs, overdue, incidents, expiring, advisory, cap in GRID:
        old = _score_before_requirements(pilots, certs, vehicles, regs, overdue, incidents,
                                         expiring, advisory, cap)
        new = _calc_compliance_score(pilots, certs, vehicles, regs, overdue, incidents,
                                     authorities_expiring=expiring, authorities_expired_advisory=advisory,
                                     authority_cap=cap)
        if new != old:
            mismatches.append((pilots, certs, vehicles, regs, overdue, incidents, expiring, advisory, cap))
    assert mismatches == []


# The breakdown


def test_breakdown_names_every_part_in_order():
    parts = _score_breakdown(10, 0, 4, 0, 0, 0)
    assert [part["area"] for part in parts] == [
        "Certifications", "Registrations", "Maintenance", "Incidents", REQUIREMENTS_AREA, "Operating authority",
    ]


@pytest.mark.parametrize("inputs", [
    {"pilots": 7, "exp_certs": 2, "vehicles": 6, "exp_regs": 1, "overdue": 1, "incidents": 1,
     "pilots_out_of_standing": 3, "requirements_active": 2, "authorities_expiring": 1},
    {"pilots": 3, "exp_certs": 1, "vehicles": 4, "exp_regs": 3, "overdue": 5, "incidents": 3,
     "pilots_out_of_standing": 1, "requirements_active": 1, "authorities_expired_advisory": 1},
    {"pilots": 10, "exp_certs": 0, "vehicles": 0, "exp_regs": 0, "overdue": 0, "incidents": 0},
])
def test_breakdown_sums_to_the_points_lost(inputs):
    payload = _score_payload(inputs, None)
    lost = sum(part["points_lost"] for part in payload["score_breakdown"])
    assert abs(lost - (100 - payload["compliance_score"])) < 0.5


def test_breakdown_points_are_rounded_to_one_decimal():
    parts = _score_payload({"pilots": 3, "exp_certs": 1, "vehicles": 0, "exp_regs": 0, "overdue": 0,
                            "incidents": 0}, None)["score_breakdown"]
    assert parts[0]["points_lost"] == pytest.approx(8.3)


def test_requirements_entry_explains_the_part():
    parts = _score_breakdown(10, 0, 0, 0, 0, 0, pilots_out_of_standing=2, requirements_active=1)
    entry = next(part for part in parts if part["area"] == REQUIREMENTS_AREA)
    assert entry == {"area": REQUIREMENTS_AREA, "points_lost": 3.0,
                     "detail": "2 of 10 active pilots missed or lapsed on a flight requirement"}


def test_requirements_entry_without_active_requirements():
    parts = _score_breakdown(10, 0, 0, 0, 0, 0, pilots_out_of_standing=2, requirements_active=0)
    entry = next(part for part in parts if part["area"] == REQUIREMENTS_AREA)
    assert entry == {"area": REQUIREMENTS_AREA, "points_lost": 0, "detail": "No active flight requirements"}


def test_cap_adds_its_own_entry():
    reason = "Capped at 50: 1 operating authority expired"
    payload = _score_payload({"pilots": 10, "exp_certs": 2, "vehicles": 0, "exp_regs": 0, "overdue": 0,
                              "incidents": 0}, reason)
    assert payload["compliance_score"] == AUTHORITY_SCORE_CAP
    assert payload["score_breakdown"][-1] == {"area": "Operating authority cap", "points_lost": 45,
                                              "detail": reason}


def test_no_cap_entry_without_a_cap():
    payload = _score_payload({"pilots": 10, "exp_certs": 0, "vehicles": 0, "exp_regs": 0, "overdue": 0,
                              "incidents": 0}, None)
    assert len(payload["score_breakdown"]) == 6


# The compliance payload


def test_page_load_records_lapses_and_closes_due_periods(client, db, admin_headers):
    """A rolling requirement the pilot has never flown for lapses, and October of
    a monthly one closes as missed, both on the page load; the pilot counts once."""
    pilot = _pilot(db)
    _rolling(db, pilots=[pilot])
    _periodic(db, pilots=[pilot], start_date=OCT[0])

    body = client.get(COMPLIANCE_URL, headers=admin_headers).json()

    assert body["pilots_out_of_standing"] == 1
    assert body["requirements_active"] == 2
    assert body["compliance_score"] == 85
    assert body["requirements_score"] == 0.0


def test_page_load_records_a_rolling_lapse(client, db, admin_headers):
    pilot = _pilot(db)
    _rolling(db, pilots=[pilot])
    _pilot(db)

    body = client.get(COMPLIANCE_URL, headers=admin_headers).json()

    assert body["pilots_out_of_standing"] == 1


def test_a_racing_close_does_not_fail_the_page_load(client, db, admin_headers, monkeypatch):
    _periodic(db, pilots=[_pilot(db)], start_date=OCT[0])

    def racing(*_args):
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))

    monkeypatch.setattr(requirement_standing, "close_due_periods", racing)
    assert client.get(COMPLIANCE_URL, headers=admin_headers).status_code == 200


def test_payload_breakdown_matches_the_score(client, db, admin_headers):
    pilot = _pilot(db)
    _rolling(db, pilots=[pilot])
    _pilot(db)
    _pilot(db)

    body = client.get(COMPLIANCE_URL, headers=admin_headers).json()

    lost = sum(part["points_lost"] for part in body["score_breakdown"])
    assert lost == pytest.approx(100 - body["compliance_score"], abs=0.5)


def test_payload_without_requirements(client, admin_headers):
    body = client.get(COMPLIANCE_URL, headers=admin_headers).json()

    assert body["pilots_out_of_standing"] == 0
    assert body["requirements_active"] == 0
    assert body["requirements_score"] is None
