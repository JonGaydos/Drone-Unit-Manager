"""Regression tests for the Area 9 staging-test fixes: import and sync
(backlog I-2 to I-5)."""

import csv
import io
from datetime import date

from app.models import Flight, Pilot
from app.services.excel_import import import_skydio_csv

HEADER = [
    "Flight ID", "Vehicle", "Pilot", "Local Takeoff Time", "Takeoff", "Takeoff Address",
    "Takeoff Latitude", "Takeoff Longitude", "Land", "Duration (seconds)", "Battery",
]


def _skydio_csv(*rows) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=HEADER)
    writer.writeheader()
    for flight_id, pilot in rows:
        writer.writerow({
            "Flight ID": flight_id, "Vehicle": "SkydioX2-area9", "Pilot": pilot,
            "Takeoff": "2026-03-01 12:00:00", "Land": "2026-03-01 12:10:00",
            "Duration (seconds)": "600", "Takeoff Address": "1 Test Way",
        })
    return out.getvalue().encode()


def _pilot_emails(db):
    db.expire_all()
    return {p.email for p in db.query(Pilot).all()}


# --- I-2: a duplicate-only import creates no pilots --------------------------

def test_duplicate_only_import_creates_no_pilot(db):
    db.add(Flight(external_id="AREA9DUP0001", api_provider="skydio", date=date(2026, 3, 1)))
    db.commit()
    before = _pilot_emails(db)

    result = import_skydio_csv(db, _skydio_csv(("area9-dup-0001", "new.person@example.com")))

    assert result["flights_skipped"] == 1
    assert result["flights_imported"] == 0
    assert result["pilots_created"] == 0
    assert _pilot_emails(db) == before


def test_pilot_is_created_once_for_imported_flights(db):
    result = import_skydio_csv(db, _skydio_csv(
        ("AREA9NEW0001", "sam.sample@example.com"),
        ("AREA9NEW0002", "sam.sample@example.com"),
    ))

    assert result["flights_imported"] == 2
    assert result["pilots_created"] == 1
    db.expire_all()
    pilot = db.query(Pilot).filter(Pilot.email == "sam.sample@example.com").one()
    assert pilot.first_name == "Sam"
    assert {f.pilot_id for f in db.query(Flight).all()} == {pilot.id}


def test_mixed_import_creates_only_the_pilot_who_flew(db):
    db.add(Flight(external_id="AREA9DUP0002", api_provider="skydio", date=date(2026, 3, 1)))
    db.commit()

    result = import_skydio_csv(db, _skydio_csv(
        ("AREA9DUP0002", "skipped.only@example.com"),
        ("AREA9NEW0003", "flew.once@example.com"),
    ))

    assert result["pilots_created"] == 1
    emails = _pilot_emails(db)
    assert "flew.once@example.com" in emails
    assert "skipped.only@example.com" not in emails
