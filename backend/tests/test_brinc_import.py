"""Tests for the BRINC flight-list CSV import.

Two things drive most of these: BRINC exports the same flights twice over
(a local-time export and a UTC one, in different timestamp formats) and the
same date range is expected to be re-exported weekly, so importing must be
idempotent.
"""

import time
from datetime import datetime

import pytest

from app.models.flight import Flight, FlightPurpose
from app.models.pilot import Pilot
from app.models.vehicle import Vehicle
from app.models.setting import Setting
from app.services.brinc_import import (
    _header_declares_utc,
    _parse_dt,
    import_brinc_csv,
    is_brinc_csv,
)

HEADER_LOCAL = ("Flight Id,Start Time (CDT / UTC-5),End Time (CDT / UTC-5),"
                "Flight Time (HH:MM:SS),Flight Time (Seconds),Drone Name,User,"
                "Location,Launch Address,Org Name,Case Id,Call Type")
# BRINC's real UTC export drops the timezone label entirely and switches the
# timestamps to ISO 8601 with a Z suffix.
HEADER_UTC = HEADER_LOCAL.replace(" (CDT / UTC-5)", "")

ADDRESS = "1 Example Rd, Example City, FL 32000, USA"


def _csv(rows, header=HEADER_LOCAL):
    body = "\n".join(rows)
    return f"{header}\n{body}\n".encode()


def _row_utc(flight_id="a896aacd-9c11-44db-815c-531a1a0b7e9a",
             start="2026-09-02T16:33:43.000Z", end="2026-09-02T16:44:41.000Z",
             seconds="658", drone="l2d-0001-00001", user="Alex Rivera",
             address=ADDRESS):
    return (f'{flight_id},{start},{end},00:10:58,{seconds},{drone},{user},,'
            f'"{address}",Example County Sheriffs Office,,')


def _row(flight_id="a896aacd-9c11-44db-815c-531a1a0b7e9a",
         start="2026-09-02 11:33:43", end="2026-09-02 11:44:41",
         seconds="658", drone="l2d-0001-00001", user="Alex Rivera",
         address=ADDRESS):
    return (f'{flight_id},{start},{end},00:10:58,{seconds},{drone},{user},,'
            f'"{address}",Example County Sheriffs Office,,')


@pytest.fixture
def fleet(db):
    """Two Lemurs matched by provider_serial, plus a known pilot."""
    db.add_all([
        Vehicle(serial_number="1914CL2D000100001", provider_serial="l2d-0001-00001",
                manufacturer="Brinc", model="LEMUR 2", nickname="Lemur #2", status="active"),
        Vehicle(serial_number="l2d-0002-00001", provider_serial="l2d-0002-00001",
                manufacturer="Brinc", model="LEMUR 2", nickname="Loaner", status="active"),
        Pilot(first_name="Alex", last_name="Rivera", status="active"),
    ])
    db.commit()


# --- Detection --------------------------------------------------------------


def test_detects_a_brinc_export_by_its_columns():
    assert is_brinc_csv({c.strip() for c in HEADER_LOCAL.split(",")})
    assert is_brinc_csv({c.strip() for c in HEADER_UTC.split(",")})


def test_does_not_claim_a_skydio_export():
    skydio = {"Flight ID", "Vehicle", "Pilot", "Takeoff", "Local Takeoff Time"}
    assert not is_brinc_csv(skydio)


def test_detection_survives_the_export_switching_to_utc():
    """Detection keys on stable columns, not the timestamp headings, which
    change wording when the export timezone is switched."""
    local = {c.strip() for c in HEADER_LOCAL.split(",")}
    utc = {c.strip() for c in HEADER_UTC.split(",")}
    assert local != utc, "the two headers should genuinely differ"
    assert is_brinc_csv(local)
    assert is_brinc_csv(utc)


# --- Timezone ---------------------------------------------------------------


@pytest.mark.parametrize("heading,declares_utc", [
    ("Start Time (UTC)", True),
    ("Start Time (CDT / UTC-5)", False),
    ("Start Time (CST / UTC-6)", False),
    ("Start Time", False),
    (None, False),
])
def test_header_utc_declaration(heading, declares_utc):
    assert _header_declares_utc(heading) is declares_utc


@pytest.mark.parametrize("raw,expected,is_utc", [
    ("2026-09-02T16:33:43.000Z", datetime(2026, 9, 2, 16, 33, 43), True),
    ("2026-09-02T16:33:43Z", datetime(2026, 9, 2, 16, 33, 43), True),
    ("2026-09-02 11:33:43", datetime(2026, 9, 2, 11, 33, 43), False),
    ("", None, False),
])
def test_parses_both_export_timestamp_formats(raw, expected, is_utc):
    """The UTC export emits ISO 8601 with milliseconds and a Z; the local export
    emits a plain space-separated timestamp."""
    assert _parse_dt(raw) == (expected, is_utc)


def test_a_utc_export_is_stored_as_is(client, db, fleet):
    import_brinc_csv(db, _csv([_row_utc()], header=HEADER_UTC), geocode=False)

    assert db.query(Flight).one().takeoff_time == datetime(2026, 9, 2, 16, 33, 43)


def test_local_timestamps_convert_through_a_real_timezone(client, db, fleet):
    """September is CDT (UTC-5): 11:33:43 local is 16:33:43 UTC."""
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()

    import_brinc_csv(db, _csv([_row()]), geocode=False)

    flight = db.query(Flight).one()
    assert flight.takeoff_time == datetime(2026, 9, 2, 16, 33, 43)
    assert flight.date == datetime(2026, 9, 2).date()


def test_a_winter_local_timestamp_uses_standard_time_not_the_header_label(client, db, fleet):
    """The whole reason local exports are not trusted flatly.

    BRINC emits true local wall-clock time but labels the column with whatever
    offset applied at export time. A file exported in September is headed
    "CDT / UTC-5" even for its December rows, which were really CST (UTC-6).
    Measured across both of the customer's exports: December through February
    are UTC-6, April onward UTC-5. Applying the label flatly puts winter flights
    an hour early.
    """
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()

    import_brinc_csv(db, _csv([_row(flight_id="winter-1",
                                    start="2025-12-29 12:13:16",
                                    end="2025-12-29 12:23:16")]), geocode=False)

    # 12:13:16 CST is 18:13:16 UTC, not the 17:13:16 the header would imply.
    assert db.query(Flight).one().takeoff_time == datetime(2025, 12, 29, 18, 13, 16)


def test_both_exports_of_the_same_flight_agree(client, db, fleet):
    """Local and UTC exports of one flight must land on the same instant."""
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()

    import_brinc_csv(db, _csv([_row(flight_id="same-1")]), geocode=False)
    from_local = db.query(Flight).one().takeoff_time
    db.query(Flight).delete()
    db.commit()

    import_brinc_csv(db, _csv([_row_utc(flight_id="same-1")], header=HEADER_UTC), geocode=False)
    assert db.query(Flight).one().takeoff_time == from_local


# --- Import behaviour -------------------------------------------------------


def test_imports_a_flight_with_its_fields(client, db, fleet):
    result = import_brinc_csv(db, _csv([_row()]), geocode=False)

    assert result["flights_imported"] == 1
    flight = db.query(Flight).one()
    assert flight.external_id == "a896aacd-9c11-44db-815c-531a1a0b7e9a"
    assert flight.duration_seconds == 658
    assert flight.takeoff_address == ADDRESS
    assert flight.data_source == "brinc_csv"
    assert flight.api_provider == "brinc"
    assert flight.review_status == "needs_review"


def test_the_short_serial_cross_references_the_full_airframe_serial(client, db, fleet):
    """The export says "l2d-0001-00001"; the fleet records
    "1914CL2D000100001" with the short form in provider_serial."""
    import_brinc_csv(db, _csv([_row()]), geocode=False)

    vehicle = db.query(Vehicle).filter(Vehicle.nickname == "Lemur #2").one()
    assert db.query(Flight).one().vehicle_id == vehicle.id


def test_a_known_pilot_is_matched_not_duplicated(client, db, fleet):
    import_brinc_csv(db, _csv([_row(user="Alex Rivera")]), geocode=False)

    assert db.query(Pilot).filter(Pilot.first_name == "Alex").count() == 1
    assert db.query(Flight).one().pilot_id is not None


def test_an_unknown_pilot_is_created(client, db, fleet):
    result = import_brinc_csv(db, _csv([_row(user="Pat (Vendor) Quinn")]), geocode=False)

    assert result["pilots_created"] == 1
    assert db.query(Pilot).filter(Pilot.first_name == "Pat").count() == 1


def test_a_blank_pilot_goes_to_unknown_rather_than_being_dropped(client, db, fleet):
    """These are real airframe hours; they stay visible for review."""
    result = import_brinc_csv(db, _csv([_row(user="")]), geocode=False)

    assert result["flights_imported"] == 1
    pilot = db.query(Pilot).filter(Pilot.id == db.query(Flight).one().pilot_id).one()
    assert pilot.first_name == "Unknown"


# --- Duration floor ---------------------------------------------------------


def test_zero_second_rows_are_skipped(client, db, fleet):
    """BRINC writes a row whenever a session opens, so a real 218-row export
    carried 69 rows whose end time equalled their start. Importing those would
    inflate the flight count with entries that never left the ground."""
    result = import_brinc_csv(db, _csv([
        _row(flight_id="artifact-1", seconds="0",
             start="2026-09-02 11:33:43", end="2026-09-02 11:33:43"),
        _row(flight_id="real-1", seconds="658"),
    ]), geocode=False)

    assert result["flights_imported"] == 1
    assert result["flights_skipped_zero_duration"] == 1
    assert result["flights_skipped"] == 1
    assert db.query(Flight).one().external_id == "real-1"


def test_a_one_second_flight_is_kept(client, db, fleet):
    """One second is the floor, not the first value excluded."""
    result = import_brinc_csv(db, _csv([_row(seconds="1")]), geocode=False)

    assert result["flights_imported"] == 1
    assert result["flights_skipped_zero_duration"] == 0
    assert db.query(Flight).one().duration_seconds == 1


def test_a_row_with_no_duration_at_all_is_skipped(client, db, fleet):
    result = import_brinc_csv(db, _csv([_row(seconds="")]), geocode=False)

    assert result["flights_imported"] == 0
    assert result["flights_skipped_zero_duration"] == 1


# --- The requirement that re-importing is safe ------------------------------


def test_reimporting_the_same_export_changes_nothing(client, db, fleet):
    """The whole point: exporting an overlapping date range next week must not
    duplicate anything, so no date trimming is needed."""
    first = import_brinc_csv(db, _csv([_row()]), geocode=False)
    second = import_brinc_csv(db, _csv([_row()]), geocode=False)

    assert first["flights_imported"] == 1
    assert second["flights_imported"] == 0
    assert second["flights_skipped"] == 1
    assert db.query(Flight).count() == 1


def test_a_larger_second_export_imports_only_the_new_rows(client, db, fleet):
    old = _row(flight_id="aaaa-1111", start="2026-09-01 09:00:00", end="2026-09-01 09:10:00")
    new = _row(flight_id="bbbb-2222", start="2026-09-03 09:00:00", end="2026-09-03 09:10:00")

    import_brinc_csv(db, _csv([old]), geocode=False)
    result = import_brinc_csv(db, _csv([old, new]), geocode=False)

    assert result["flights_imported"] == 1
    assert result["flights_skipped"] == 1
    assert db.query(Flight).count() == 2


# --- What it refuses to invent ----------------------------------------------


def test_an_unknown_drone_is_reported_never_created(client, db, fleet):
    result = import_brinc_csv(db, _csv([_row(drone="l2d-9999-99999")]), geocode=False)

    assert result["flights_imported"] == 0
    assert result["unmatched_drones"] == {"l2d-9999-99999": 1}
    assert db.query(Vehicle).filter(Vehicle.serial_number == "l2d-9999-99999").count() == 0


def test_the_import_never_creates_flight_purposes(client, db, fleet):
    """Auto-creating purposes from import values is how "CPTEd" became a
    permanent option alongside "CPTED"."""
    import_brinc_csv(db, _csv([_row()]), geocode=False)

    assert db.query(FlightPurpose).count() == 0
    assert db.query(Flight).one().purpose is None


def test_one_bad_row_does_not_abort_the_rest(client, db, fleet):
    bad = ",".join([""] * 12)          # no Flight Id
    good = _row(flight_id="cccc-3333")

    result = import_brinc_csv(db, _csv([bad, good]), geocode=False)

    assert result["flights_imported"] == 1
    assert result["errors"]


# --- Geocoding --------------------------------------------------------------


def test_addresses_are_geocoded_once_per_distinct_value(client, db, fleet, monkeypatch):
    """161 addressed rows across 19 distinct addresses must not be 161 lookups."""
    calls = []

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return [{"lat": "30.36", "lon": "-86.24"}]

    def fake_get(url, **kwargs):
        calls.append(kwargs["params"]["q"])
        return _Resp()

    monkeypatch.setattr("app.services.brinc_import.httpx.get", fake_get)
    monkeypatch.setattr("app.services.brinc_import.GEOCODE_INTERVAL_SECONDS", 0)

    rows = [_row(flight_id=f"row-{i}", address=ADDRESS) for i in range(5)]
    result = import_brinc_csv(db, _csv(rows), geocode=True)

    assert len(calls) == 1, f"geocoded {len(calls)} times for one distinct address"
    assert result["addresses_geocoded"] == 1
    assert all(f.takeoff_lat == pytest.approx(30.36) for f in db.query(Flight).all())


def test_a_geocode_failure_still_imports_the_flight(client, db, fleet, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("nominatim unreachable")

    monkeypatch.setattr("app.services.brinc_import.httpx.get", boom)
    monkeypatch.setattr("app.services.brinc_import.GEOCODE_INTERVAL_SECONDS", 0)

    result = import_brinc_csv(db, _csv([_row()]), geocode=True)

    assert result["flights_imported"] == 1
    assert result["addresses_failed"] == 1
    flight = db.query(Flight).one()
    assert flight.takeoff_address == ADDRESS      # address kept
    assert flight.takeoff_lat is None             # just no pin


def test_an_address_already_resolved_is_reused_without_a_lookup(client, db, fleet, monkeypatch):
    """A second import of the same site should not hit the network again."""
    db.add(Flight(date=datetime(2026, 8, 1).date(), takeoff_address=ADDRESS,
                  takeoff_lat=30.36, takeoff_lon=-86.24))
    db.commit()

    def boom(*a, **k):
        raise AssertionError("should not have geocoded a known address")

    monkeypatch.setattr("app.services.brinc_import.httpx.get", boom)

    import_brinc_csv(db, _csv([_row()]), geocode=True)

    imported = db.query(Flight).filter(Flight.external_id.isnot(None)).one()
    assert imported.takeoff_lat == pytest.approx(30.36)


# --- Endpoint routing -------------------------------------------------------


def test_the_existing_importer_endpoint_detects_a_brinc_export(client, db, fleet, admin_headers):
    """No second importer: the same Settings upload recognises the format."""
    resp = client.post(
        "/api/export/flights/import/log",
        headers=admin_headers,
        files={"file": ("brinc.csv", _csv([_row()]), "text/csv")},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["format_detected"] == "brinc_csv"
    assert resp.json()["flights_imported"] == 1


def test_a_skydio_export_still_routes_to_the_skydio_importer(client, db, admin_headers):
    """The BRINC sniff runs first, so prove it does not swallow Skydio files."""
    header = "Flight ID,Vehicle,Pilot,Local Takeoff Time,Flight Duration (seconds)"
    body = f"{header}\nabc-1,X10-1,Jane Doe,2026-09-02 11:33:43,658\n".encode()

    resp = client.post(
        "/api/export/flights/import/log",
        headers=admin_headers,
        files={"file": ("skydio.csv", body, "text/csv")},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["format_detected"] == "skydio_csv"


# --- Writing to a live database ---------------------------------------------


def test_the_same_flight_twice_in_one_file_is_imported_once(client, db, fleet):
    """The session does not autoflush, so rows added moments ago are invisible
    to the duplicate query. Two weekly exports concatenated into one file, or
    any repeat inside a single export, would otherwise double the airtime."""
    result = import_brinc_csv(db, _csv([_row(flight_id="same"),
                                        _row(flight_id="same")]), geocode=False)

    assert result["flights_imported"] == 1
    assert result["flights_skipped"] == 1
    assert db.query(Flight).count() == 1


def test_the_in_file_check_is_normalised_like_the_database_one(client, db, fleet):
    """Hyphens and case are stripped for the database comparison; the same
    flight written two ways in one file is still one flight."""
    result = import_brinc_csv(db, _csv([_row(flight_id="ab-cd-01"),
                                        _row(flight_id="ABCD01")]), geocode=False)

    assert result["flights_imported"] == 1
    assert db.query(Flight).count() == 1


def test_pilots_created_by_the_import_are_active_and_marked(client, db, fleet):
    """A new name cannot be told from a vendor rep at import time, and active is
    the safer of the two defaults: inactive would drop a real pilot's flights
    out of currency, the dashboard, and the default view of two reports. The
    note is what lets the admin find them again."""
    import_brinc_csv(db, _csv([_row(user="Pat (Vendor) Quinn")]), geocode=False)

    pilot = db.query(Pilot).filter(Pilot.first_name == "Pat").one()
    assert pilot.status == "active"
    assert "BRINC CSV import" in (pilot.notes or "")


def test_the_unknown_placeholder_pilot_stays_inactive(client, db, fleet):
    """Not a person: it can never hold a certification or satisfy currency, so
    it must not count towards either."""
    import_brinc_csv(db, _csv([_row(user="")]), geocode=False)

    assert db.query(Pilot).filter(Pilot.first_name == "Unknown").one().status == "inactive"


def test_an_existing_pilot_is_left_completely_alone(client, db, fleet):
    """Importing must not change the status or notes of somebody already on the
    roster, in either direction."""
    retired = Pilot(first_name="Dana", last_name="Reed", status="inactive",
                    notes="Left the unit in March.")
    db.add(retired)
    db.commit()

    import_brinc_csv(db, _csv([_row(flight_id="a", user="Alex Rivera"),
                               _row(flight_id="b", user="Dana Reed")]), geocode=False)

    assert db.query(Pilot).filter(Pilot.first_name == "Alex").one().status == "active"
    dana = db.query(Pilot).filter(Pilot.first_name == "Dana").one()
    assert dana.status == "inactive", "an import reactivated a pilot who had left"
    assert dana.notes == "Left the unit in March."


def test_provider_serial_wins_over_another_vehicle_s_serial_number(client, db, fleet):
    """Some airframes were entered with the short serial in serial_number, so a
    single OR-query returns whichever row the database reaches first. Here the
    decoy is the earlier row, which is exactly the case that misattributes.
    """
    db.add_all([
        Vehicle(id=90, serial_number="l2d-7777-00007", manufacturer="Brinc",
                model="LEMUR 2", nickname="Retired shell", status="retired"),
        Vehicle(id=91, serial_number="1914CL2D777700007", provider_serial="l2d-7777-00007",
                manufacturer="Brinc", model="LEMUR 2", nickname="The one that flew",
                status="active"),
    ])
    db.commit()

    import_brinc_csv(db, _csv([_row(drone="l2d-7777-00007")]), geocode=False)

    assert db.query(Flight).one().vehicle_id == 91


def test_a_row_with_no_usable_time_is_skipped_not_dated_today(client, db, fleet):
    """Falling back to today would file the flight under the day of the import,
    where it counts towards this month on the dashboard and in reports."""
    result = import_brinc_csv(db, _csv([_row(flight_id="notime", start="", end=""),
                                        _row(flight_id="fine")]), geocode=False)

    assert result["flights_imported"] == 1
    assert result["errors"]
    flight = db.query(Flight).one()
    assert flight.external_id == "fine"
    assert flight.date == datetime(2026, 9, 2).date()


# --- Geocoding is bounded and recoverable -----------------------------------


def _fake_geocoder(monkeypatch, hits=(("30.36", "-86.24"),), delay=0.0):
    """Patch Nominatim with a canned answer; returns the list of queries made."""
    calls = []

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"lat": lat, "lon": lon} for lat, lon in hits]

    def fake_get(url, **kwargs):
        calls.append(kwargs["params"]["q"])
        if delay:
            time.sleep(delay)
        return _Resp()

    monkeypatch.setattr("app.services.brinc_import.httpx.get", fake_get)
    monkeypatch.setattr("app.services.brinc_import.GEOCODE_INTERVAL_SECONDS", 0)
    return calls


def test_a_previously_unpinned_flight_is_backfilled_on_the_next_import(client, db, fleet,
                                                                       monkeypatch):
    """A flight whose address failed to geocode would otherwise stay off the map
    forever: the next import skips its row as a duplicate and never revisits it.
    """
    def boom(*a, **k):
        raise RuntimeError("nominatim unreachable")

    monkeypatch.setattr("app.services.brinc_import.httpx.get", boom)
    monkeypatch.setattr("app.services.brinc_import.GEOCODE_INTERVAL_SECONDS", 0)
    import_brinc_csv(db, _csv([_row()]), geocode=True)
    assert db.query(Flight).one().takeoff_lat is None

    _fake_geocoder(monkeypatch)
    result = import_brinc_csv(db, _csv([_row()]), geocode=True)

    assert result["flights_imported"] == 0        # still a duplicate
    assert result["coordinates_backfilled"] == 1
    assert db.query(Flight).one().takeoff_lat == pytest.approx(30.36)


def test_the_backfill_only_touches_brinc_flights_missing_coordinates(client, db, fleet,
                                                                     monkeypatch):
    """It must not overwrite coordinates a pilot or another importer set."""
    db.add(Flight(date=datetime(2026, 8, 1).date(), data_source="manual",
                  takeoff_address=ADDRESS, takeoff_lat=1.0, takeoff_lon=2.0))
    db.commit()

    _fake_geocoder(monkeypatch)
    import_brinc_csv(db, _csv([_row()]), geocode=True)

    manual = db.query(Flight).filter(Flight.data_source == "manual").one()
    assert (manual.takeoff_lat, manual.takeoff_lon) == (1.0, 2.0)


def test_geocoding_stops_at_its_time_budget(client, db, fleet, monkeypatch):
    """A slow Nominatim must not hold the upload open past the proxy's read
    timeout. The unresolved addresses are reported and resolve on a later run.
    """
    calls = _fake_geocoder(monkeypatch, delay=0.05)
    monkeypatch.setattr("app.services.brinc_import.GEOCODE_BUDGET_SECONDS", 0.12)

    rows = [_row(flight_id=f"row-{i}", address=f"{i} Test St, Anywhere FL")
            for i in range(20)]
    result = import_brinc_csv(db, _csv(rows), geocode=True)

    assert len(calls) < 20, "the budget did not stop the network phase"
    assert result["addresses_failed"] == 20 - len(calls)
    assert result["flights_imported"] == 20, "flights import regardless of geocoding"


# --- Timezone misconfiguration ----------------------------------------------


def test_a_local_export_from_a_different_zone_is_flagged(client, db, fleet):
    """BRINC exports in the agency's BRINC timezone; conversion uses this
    instance's. If they disagree every time is silently hours out."""
    db.add(Setting(key="display_timezone", value="America/New_York"))
    db.commit()

    result = import_brinc_csv(db, _csv([_row()]), geocode=False)

    assert result["warnings"], "a UTC-5 heading against an Eastern instance went unflagged"
    assert "America/New_York" in result["warnings"][0]
    assert result["timezone_used"] == "America/New_York"


def test_a_matching_zone_is_not_flagged(client, db, fleet):
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()

    result = import_brinc_csv(db, _csv([_row()]), geocode=False)

    assert result["warnings"] == []


def test_the_warning_is_judged_at_the_newest_row(client, db, fleet):
    """Creating a pilot flushes the session, so the pending-object list is not a
    safe place to look for the newest flight. Judged against a December row this
    file would be flagged for a UTC-6 mismatch that is only daylight saving.
    """
    db.add(Setting(key="display_timezone", value="America/Chicago"))
    db.commit()

    result = import_brinc_csv(db, _csv([
        # Newest row first, flown by someone already on the roster.
        _row(flight_id="sept", user="Alex Rivera"),
        # Older row whose new pilot forces a flush partway through the file.
        _row(flight_id="dec", user="Brand New Person",
             start="2025-12-29 12:13:16", end="2025-12-29 12:23:16"),
    ]), geocode=False)

    assert result["flights_imported"] == 2
    assert result["warnings"] == [], "flagged a daylight-saving difference as a misconfiguration"


def test_the_names_of_created_pilots_are_reported(client, db, fleet):
    """A spelling the roster does not already carry makes a second entry for one
    person; the admin has to be told who, not just how many."""
    result = import_brinc_csv(db, _csv([_row(flight_id="a", user="Pat (Vendor) Quinn"),
                                        _row(flight_id="b", user="Alex Rivera")]),
                              geocode=False)

    assert result["pilots_created"] == 1
    assert result["pilots_created_names"] == ["Pat (Vendor) Quinn"]


def test_a_utc_export_is_never_flagged(client, db, fleet):
    """A UTC export needs no conversion, so the instance's zone is irrelevant."""
    db.add(Setting(key="display_timezone", value="Australia/Sydney"))
    db.commit()

    result = import_brinc_csv(db, _csv([_row_utc()], header=HEADER_UTC), geocode=False)

    assert result["warnings"] == []
    assert db.query(Flight).one().takeoff_time == datetime(2026, 9, 2, 16, 33, 43)
