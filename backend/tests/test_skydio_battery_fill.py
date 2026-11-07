"""A Skydio flight-list import fills the battery of a flight it already has.

Skydio's API leaves ``battery_serial`` empty for X2 flights, but the CSV
export carries it in the Battery column. A row whose Flight ID matches an
existing flight with no battery gives that flight the row's battery and
nothing else. The fallback duplicate match (takeoff, pilot, vehicle) never
fills anything.
"""

import csv
import io
from datetime import date, datetime

import pytest
from openpyxl import Workbook

from app.models import AuditLog, Battery, Flight, Pilot, Vehicle
from app.services.excel_import import import_excel, import_skydio_csv

FLIGHT_ID = "Flight ID"
VEHICLE = "Vehicle"
PILOT = "Pilot"
TAKEOFF_COL = "Takeoff"
LOCAL_TAKEOFF = "Local Takeoff Time"
BATTERY = "Battery"
HEADER = [
    FLIGHT_ID, VEHICLE, PILOT, LOCAL_TAKEOFF, TAKEOFF_COL, "Takeoff Address",
    "Takeoff Latitude", "Takeoff Longitude", "Land", "Duration (seconds)", BATTERY,
    "Sensor Package", "Attachment (TOP)", "Attachment (BOTTOM)", "Attachment (LEFT)",
    "Attachment (RIGHT)", "Dock", "Dock Nickname", "Dock Serial", "Dock ID", "Controller",
    "Controller Serial", "Controller ID", "Linked Devices", "Axon Evidence", "Carrier(s)",
]

STORED_ID = "test-fill-0001"
ROW_ID = "TESTFILL0001"
VEHICLE_SERIAL = "SkydioX2-test1"
PILOT_EMAIL = "pat.tester@example.com"
TAKEOFF = datetime(2026, 3, 1, 12, 0, 0)
DASH_SERIAL = "-k99-990101-1-00001"
CLEAN_SERIAL = "k99-990101-1-00001"
KEPT_SERIAL = "k99-990101-1-00002"
FILLED = "batteries_filled"
SKIPPED = "flights_skipped"
STORED_ID_2 = "test-fill-0002"
ROW_ID_2 = "TESTFILL0002"
STORED_ID_3 = "test-fill-0003"
ROW_ID_3 = "TESTFILL0003"


def _row(**overrides):
    row = dict.fromkeys(HEADER, "")
    row.update({
        FLIGHT_ID: ROW_ID, VEHICLE: VEHICLE_SERIAL, PILOT: PILOT_EMAIL,
        LOCAL_TAKEOFF: "2026-03-01 07:00:00", TAKEOFF_COL: TAKEOFF.strftime("%Y-%m-%d %H:%M:%S"),
        "Takeoff Address": "1 Test Way", "Takeoff Latitude": "30.1", "Takeoff Longitude": "-85.1",
        "Land": "2026-03-01 12:10:00", "Duration (seconds)": "600", BATTERY: DASH_SERIAL,
        "Sensor Package": "SP-TEST-1", "Controller": "Test Controller",
    })
    row.update(overrides)
    return row


def _csv(*rows) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=HEADER)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


def _flight(db, external_id=STORED_ID, battery=None, **fields):
    flight = Flight(external_id=external_id, api_provider="skydio", date=date(2026, 3, 1),
                    duration_seconds=590, battery_serial=battery, sensor_package="SP-OLD", **fields)
    db.add(flight)
    db.commit()
    return flight


def _battery_of(db, flight_id):
    db.expire_all()
    return db.get(Flight, flight_id).battery_serial


@pytest.mark.parametrize("empty", [None, ""])
def test_an_empty_battery_is_filled_with_the_clean_serial(db, empty):
    flight = _flight(db, battery=empty)

    result = import_skydio_csv(db, _csv(_row()))

    assert _battery_of(db, flight.id) == CLEAN_SERIAL
    assert result[FILLED] == 1
    assert result[SKIPPED] == 1
    assert result["flights_imported"] == 0


def test_only_the_battery_changes(db):
    flight = _flight(db)

    import_skydio_csv(db, _csv(_row()))

    db.expire_all()
    stored = db.get(Flight, flight.id)
    assert stored.duration_seconds == 590
    assert stored.sensor_package == "SP-OLD"
    assert stored.takeoff_address is None


def test_a_battery_already_set_is_kept(db):
    flight = _flight(db, battery=KEPT_SERIAL)

    result = import_skydio_csv(db, _csv(_row()))

    assert _battery_of(db, flight.id) == KEPT_SERIAL
    assert result[FILLED] == 0


@pytest.mark.parametrize("placeholder", ["", "N/A", "-"])
def test_a_placeholder_battery_fills_nothing(db, placeholder):
    flight = _flight(db)

    result = import_skydio_csv(db, _csv(_row(**{BATTERY: placeholder})))

    assert _battery_of(db, flight.id) is None
    assert result[FILLED] == 0


def test_a_fallback_duplicate_is_not_filled(db):
    pilot = Pilot(first_name="Pat", last_name="Tester", email=PILOT_EMAIL, status="active")
    vehicle = Vehicle(serial_number=VEHICLE_SERIAL, manufacturer="Skydio", model="X2E", status="active")
    db.add_all([pilot, vehicle])
    db.commit()
    flight = _flight(db, external_id="UNRELATED-ID", takeoff_time=TAKEOFF,
                     pilot_id=pilot.id, vehicle_id=vehicle.id)

    result = import_skydio_csv(db, _csv(_row()))

    assert _battery_of(db, flight.id) is None
    assert result[SKIPPED] == 1
    assert result[FILLED] == 0


def test_counts_cover_each_filled_row(db):
    _flight(db, external_id=STORED_ID_2)
    _flight(db, external_id=STORED_ID_3)
    rows = [_row(**{FLIGHT_ID: ROW_ID_2}), _row(**{FLIGHT_ID: ROW_ID_3, BATTERY: KEPT_SERIAL}),
            _row(**{FLIGHT_ID: "TESTFILL0004"})]

    result = import_skydio_csv(db, _csv(*rows))

    assert result[FILLED] == 2
    assert result[SKIPPED] == 2
    assert result["flights_imported"] == 1


def test_the_battery_record_counts_the_filled_flight(client, db, admin_headers):
    battery = Battery(serial_number=CLEAN_SERIAL, status="active")
    db.add(battery)
    db.commit()
    _flight(db)

    import_skydio_csv(db, _csv(_row()))

    resp = client.get(f"/api/batteries/{battery.id}/stats", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["total_flights"] == 1


def test_a_missing_battery_record_is_created(db):
    _flight(db)

    import_skydio_csv(db, _csv(_row()))

    assert [b.serial_number for b in db.query(Battery).all()] == [CLEAN_SERIAL]


def test_the_excel_skydio_sheet_fills_too(db):
    flight = _flight(db)
    wb = Workbook()
    ws = wb.active
    ws.title = "Skydio"
    ws.append(HEADER)
    ws.append([_row()[h] for h in HEADER])
    out = io.BytesIO()
    wb.save(out)

    result = import_excel(db, out.getvalue())

    assert _battery_of(db, flight.id) == CLEAN_SERIAL
    assert result[FILLED] == 1


def test_the_import_summary_records_the_filled_flight(client, db, admin_headers):
    flight = _flight(db)

    resp = client.post("/api/export/excel/import", headers=admin_headers,
                       files={"file": ("flights.csv", _csv(_row()))})

    assert resp.status_code == 200
    assert resp.json()[FILLED] == 1
    db.expire_all()
    entry = db.query(AuditLog).filter_by(action="import").one()
    flights = entry.changes["Flight"]
    assert flights["counts"]["update"] == 1
    assert flights["ids"] == [flight.id]


def test_the_oldest_flight_with_a_repeated_flight_id_is_filled(db):
    oldest = _flight(db, external_id=STORED_ID)
    newer = _flight(db, external_id=STORED_ID.upper())

    result = import_skydio_csv(db, _csv(_row()))

    assert _battery_of(db, oldest.id) == CLEAN_SERIAL
    assert _battery_of(db, newer.id) is None
    assert result[FILLED] == 1


@pytest.mark.parametrize("status", ["reviewed", "needs_review"])
def test_the_review_status_is_unchanged(db, status):
    flight = _flight(db, review_status=status)

    import_skydio_csv(db, _csv(_row()))

    db.expire_all()
    stored = db.get(Flight, flight.id)
    assert stored.battery_serial == CLEAN_SERIAL
    assert stored.review_status == status


def test_a_repeated_flight_id_in_the_csv_fills_once(db):
    flight = _flight(db)

    result = import_skydio_csv(db, _csv(_row(), _row(**{BATTERY: KEPT_SERIAL})))

    assert _battery_of(db, flight.id) == CLEAN_SERIAL
    assert result[FILLED] == 1


@pytest.mark.parametrize("csv_serial", [DASH_SERIAL, DASH_SERIAL.upper(), CLEAN_SERIAL.upper()])
def test_a_serial_differing_in_case_or_dash_uses_the_stored_record(db, csv_serial):
    stored_serial = CLEAN_SERIAL.upper()
    db.add(Battery(serial_number=stored_serial, status="active"))
    db.commit()
    flight = _flight(db)

    import_skydio_csv(db, _csv(_row(**{BATTERY: csv_serial})))

    assert [b.serial_number for b in db.query(Battery).all()] == [stored_serial]
    assert _battery_of(db, flight.id) == stored_serial


def test_a_whitespace_only_battery_counts_as_empty(db):
    flight = _flight(db, battery="   ")

    result = import_skydio_csv(db, _csv(_row()))

    assert _battery_of(db, flight.id) == CLEAN_SERIAL
    assert result[FILLED] == 1
