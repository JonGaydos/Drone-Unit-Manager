"""The DJI / Litchi / Airdata flight-log importer.

This module had no test coverage at all, and it is the path that turns an
operator's uploaded file into permanent flight records. The cases below
concentrate on the failures that would be silent: a unit read as the wrong
unit, a duplicate imported twice, a flight row left behind with
``has_telemetry=True`` and no points.
"""

import json
from datetime import datetime

import pytest

from app.models.flight import Flight
from app.models.telemetry import TelemetryPoint
from app.models.vehicle import Vehicle
from app.services import flight_log_import as fli
from app.services.flight_log_import import (
    _build_telemetry_metadata,
    _convert_alt_units,
    _convert_speed_units,
    _parse_float,
    _parse_int,
    _parse_timestamp,
    detect_format,
    import_flight_log,
    parse_airdata_json,
    parse_csv_log,
    parse_dji_txt,
)

TAB = chr(9)


def _tsv(rows):
    return chr(10).join(TAB.join(str(c) for c in row) for row in rows)


DJI_HEADER = ["CUSTOM.date", "OSD.latitude", "OSD.longitude", "OSD.altitude [m]",
              "OSD.hSpeed [m/s]", "BATTERY:level[%]", "OSD.yaw", "GIMBAL.pitch"]

DJI_LOG = _tsv([
    DJI_HEADER,
    ["2026-05-01 10:00:00", 28.5, -81.4, 10.0, 3.0, 98, 180, -45],
    ["2026-05-01 10:00:30", 28.6, -81.5, 55.5, 12.5, 91, 190, -50],
    ["2026-05-01 10:01:00", 28.7, -81.6, 30.0, 4.0, 85, 200, -30],
])

AIRDATA_CSV = (
    "datetime(utc),latitude,longitude,height_above_takeoff(feet),speed(mph),"
    "battery_percent,compass_heading(degrees),satellites" + chr(10) +
    "2026-05-01 10:00:00,28.5,-81.4,32.8084,22.3694,98,180,12" + chr(10) +
    "2026-05-01 10:00:10,28.6,-81.5,65.6168,44.7388,95,190,13" + chr(10)
)


# 1. Format detection -------------------------------------------------------

def test_a_dji_log_is_detected():
    assert detect_format("DateTime(utc)" + TAB + "OSD.latitude" + TAB + "OSD.longitude") == "dji"


def test_an_airdata_csv_is_detected_by_its_height_column():
    assert detect_format(AIRDATA_CSV) == "airdata"


def test_a_litchi_csv_is_detected():
    assert detect_format("latitude,longitude,altitude,litchi_mission" + chr(10)) == "litchi"


def test_an_airdata_json_export_is_detected():
    content = json.dumps({"data": {"flight": {}, "flight_telemetry": {}}})
    assert detect_format(content) == "airdata_json"


def test_a_parrot_log_wins_over_the_json_check():
    """GUTMA logs are JSON too, so the order of the checks decides which parser
    runs. Parrot must be tested first or an ANAFI export falls through."""
    content = json.dumps({"exchange": {"message": {"flight_logging_keys": []}}})
    assert detect_format(content) == "parrot"


def test_plain_json_that_is_not_a_flight_log_is_not_claimed_as_airdata():
    assert detect_format(json.dumps({"data": {"something": 1}})) == "unknown"


def test_malformed_json_does_not_raise():
    assert detect_format("{not json at all") == "unknown"


def test_an_unrecognisable_file_is_unknown():
    assert detect_format("hello, this is not a flight log") == "unknown"


# 2. Value parsing ----------------------------------------------------------

@pytest.mark.parametrize("value", [None, "", "N/A", "abc"])
def test_a_missing_float_is_none_not_zero(value):
    """Zero is a real altitude and a real speed. Coercing a blank to 0.0 would
    put a ground-level reading into the record instead of leaving it empty."""
    assert _parse_float(value) is None


def test_a_genuine_zero_survives():
    assert _parse_float("0") == 0.0
    assert _parse_int("0") == 0


def test_an_int_column_holding_a_float_is_truncated():
    assert _parse_int("12.7") == 12


@pytest.mark.parametrize("raw,expected", [
    ("2026-05-01 10:00:00", datetime(2026, 5, 1, 10, 0, 0)),
    ("2026-05-01T10:00:00", datetime(2026, 5, 1, 10, 0, 0)),
    ("2026-05-01 10:00:00.500", datetime(2026, 5, 1, 10, 0, 0, 500000)),
    ("2026-05-01T10:00:00Z", datetime(2026, 5, 1, 10, 0, 0)),
    ("05/01/2026 10:00:00", datetime(2026, 5, 1, 10, 0, 0)),
    ("05/01/2026 10:00:00 AM", datetime(2026, 5, 1, 10, 0, 0)),
])
def test_every_declared_timestamp_format_parses(raw, expected):
    assert _parse_timestamp(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "not a time", "2026-13-45"])
def test_an_unparseable_timestamp_is_none(raw):
    assert _parse_timestamp(raw) is None


# 3. Units ------------------------------------------------------------------

def test_a_feet_column_is_converted_to_metres():
    """The highest-consequence silent error in this file: 400 feet recorded as
    400 metres would put a lawful flight over every ceiling in the reports."""
    assert _convert_alt_units(328.084, "height_above_takeoff(feet)") == pytest.approx(100.0, abs=0.01)


def test_a_metric_column_is_left_alone():
    assert _convert_alt_units(100.0, "altitude(m)") == 100.0


def test_an_mph_column_is_converted_to_metres_per_second():
    assert _convert_speed_units(22.3694, "speed(mph)") == pytest.approx(10.0, abs=0.01)


def test_a_metric_speed_column_is_left_alone():
    assert _convert_speed_units(10.0, "speed(m/s)") == 10.0


@pytest.mark.parametrize("convert", [_convert_alt_units, _convert_speed_units])
def test_a_missing_value_stays_missing_through_conversion(convert):
    assert convert(None, "height_above_takeoff(feet)") is None


def test_an_airdata_csv_reads_its_speed_column():
    """"speed_mph" never matched Airdata's "speed(mph)", so every Airdata CSV
    imported with no speed at all."""
    result = parse_csv_log(AIRDATA_CSV, "airdata")

    assert result["telemetry"][0]["speed_mps"] == pytest.approx(10.0, abs=0.01)
    assert result["metadata"]["max_speed_mps"] == pytest.approx(20.0, abs=0.01)


def test_an_airdata_csv_reads_its_height_in_metres():
    result = parse_csv_log(AIRDATA_CSV, "airdata")

    assert result["telemetry"][0]["altitude_m"] == pytest.approx(10.0, abs=0.01)
    assert result["metadata"]["max_altitude_m"] == pytest.approx(20.0, abs=0.01)


# 4. The DJI parser ---------------------------------------------------------

def test_a_dji_log_yields_points_and_metadata():
    result = parse_dji_txt(DJI_LOG)

    assert result["error"] is None
    assert len(result["telemetry"]) == 3
    meta = result["metadata"]
    assert meta["date"] == datetime(2026, 5, 1).date()
    assert meta["duration_seconds"] == 60
    assert meta["max_altitude_m"] == 55.5
    assert meta["max_speed_mps"] == 12.5
    assert meta["takeoff_lat"] == 28.5
    assert meta["takeoff_lon"] == -81.4


def test_dji_gimbal_columns_land_in_extra_data():
    point = parse_dji_txt(DJI_LOG)["telemetry"][0]

    assert point["extra_data"] == {"gimbal_pitch": -45.0}


def test_a_null_island_row_is_dropped():
    """0,0 is how these logs encode "no fix". Kept, it draws a track line to
    the Gulf of Guinea on every map."""
    log = _tsv([DJI_HEADER,
                ["2026-05-01 10:00:00", 0, 0, 10, 1, 90, 0, 0],
                ["2026-05-01 10:00:10", 28.5, -81.4, 10, 1, 90, 0, 0]])

    telemetry = parse_dji_txt(log)["telemetry"]

    assert len(telemetry) == 1
    assert telemetry[0]["lat"] == 28.5


def test_a_row_with_fewer_columns_than_the_header_is_skipped():
    log = _tsv([DJI_HEADER, ["2026-05-01 10:00:00"], ["2026-05-01 10:00:10", 28.5, -81.4]])

    assert len(parse_dji_txt(log)["telemetry"]) == 1


def test_a_dji_log_without_coordinates_is_an_error():
    assert parse_dji_txt(_tsv([["CUSTOM.date", "BATTERY:level[%]"], ["x", "1"]]))["error"]


def test_a_one_line_file_is_an_error():
    assert parse_dji_txt("just a header")["error"] == "File too short"


# 5. The CSV parser ---------------------------------------------------------

def test_a_csv_with_no_headers_is_an_error():
    assert parse_csv_log("", "airdata")["error"] == "No CSV headers found"


def test_a_csv_without_coordinates_is_an_error():
    assert parse_csv_log("battery,altitude" + chr(10) + "90,10", "airdata")["error"]


def test_unmapped_csv_columns_are_kept_as_extra_data():
    csv_text = ("latitude,longitude,altitude(m),wind_speed,notes" + chr(10) +
                "28.5,-81.4,10,4.5,windy" + chr(10))

    extra = parse_csv_log(csv_text, "airdata")["telemetry"][0]["extra_data"]

    assert extra["wind_speed"] == 4.5
    assert extra["notes"] == "windy"


def test_extra_data_is_capped():
    """A wide export must not put an unbounded blob on every telemetry row."""
    extras = [f"col{i}" for i in range(50)]
    csv_text = ("latitude,longitude," + ",".join(extras) + chr(10) +
                "28.5,-81.4," + ",".join(str(i) for i in range(50)) + chr(10))

    extra = parse_csv_log(csv_text, "airdata")["telemetry"][0]["extra_data"]

    assert len(extra) == 30


# 6. Metadata from points ---------------------------------------------------

def test_metadata_from_an_empty_track_is_all_empty():
    meta = _build_telemetry_metadata([], None)

    assert meta["duration_seconds"] is None
    assert meta["max_altitude_m"] is None
    assert meta["max_speed_mps"] is None
    assert meta["takeoff_lat"] is None


def test_the_maxima_are_the_highest_seen_not_the_last():
    points = [
        {"lat": 1.0, "lon": 2.0, "altitude_m": 50.0, "speed_mps": 9.0,
         "timestamp": datetime(2026, 5, 1, 10, 0, 0)},
        {"lat": 1.1, "lon": 2.1, "altitude_m": 5.0, "speed_mps": 1.0,
         "timestamp": datetime(2026, 5, 1, 10, 2, 0)},
    ]

    meta = _build_telemetry_metadata(points, points[0]["timestamp"])

    assert meta["max_altitude_m"] == 50.0
    assert meta["max_speed_mps"] == 9.0
    assert meta["duration_seconds"] == 120
    assert (meta["takeoff_lat"], meta["takeoff_lon"]) == (1.0, 2.0)


# 7. The Airdata JSON parser ------------------------------------------------

def _airdata_json(**telemetry_overrides):
    telemetry = {
        "gps": {"data": [[28.5, -81.4], [28.6, -81.5]],
                "timestamps": ["2026-05-01 10:00:00", "2026-05-01 10:00:10"]},
        "height_above_takeoff": {"data": [10.0, 25.0]},
        "battery_percentage": {"data": [0.98, 0.91]},
        "velocity": {"data": [[3.0, 4.0, 0.0], [6.0, 8.0, 0.0]]},
        "gps_num_satellites": {"data": [12, 13]},
    }
    telemetry.update(telemetry_overrides)
    return json.dumps({"data": {
        "flight": {"flight_id": "AD-123", "takeoff": "2026-05-01 10:00:00",
                   "landing": "2026-05-01 10:05:00", "vehicle_serial": "SN-9",
                   "takeoff_latitude": 28.5, "takeoff_longitude": -81.4},
        "flight_telemetry": telemetry}})


def test_airdata_json_yields_points_and_metadata():
    result = parse_airdata_json(_airdata_json())

    assert result["error"] is None
    assert len(result["telemetry"]) == 2
    assert result["metadata"]["external_id"] == "AD-123"
    assert result["metadata"]["duration_seconds"] == 300


def test_a_fractional_battery_reading_is_scaled_to_a_percentage():
    """Airdata sends 0.98 for 98%. Stored raw it reads as a dead battery."""
    assert parse_airdata_json(_airdata_json())["telemetry"][0]["battery_pct"] == 98.0


def test_a_battery_already_in_percent_is_left_alone():
    content = _airdata_json(battery_percentage={"data": [98.0, 91.0]})

    assert parse_airdata_json(content)["telemetry"][0]["battery_pct"] == 98.0


def test_the_velocity_vector_becomes_a_scalar_speed():
    assert parse_airdata_json(_airdata_json())["telemetry"][0]["speed_mps"] == 5.0


def test_channels_shorter_than_the_gps_track_do_not_truncate_it():
    """The channels are independent arrays and are not guaranteed to line up."""
    content = _airdata_json(height_above_takeoff={"data": [10.0]})

    telemetry = parse_airdata_json(content)["telemetry"]

    assert len(telemetry) == 2
    assert telemetry[1]["altitude_m"] is None


def test_invalid_json_is_reported_not_raised():
    assert parse_airdata_json("{oops")["error"].startswith("Invalid JSON")


def test_json_with_no_flight_block_is_an_error():
    assert parse_airdata_json(json.dumps({"data": {}}))["error"] == "No flight data found"


def test_a_flight_with_no_gps_channel_is_an_error():
    content = _airdata_json(gps={"data": [], "timestamps": []})

    assert parse_airdata_json(content)["error"] == "No GPS data in telemetry"


# 8. The import itself ------------------------------------------------------

def test_an_import_creates_the_flight_and_its_telemetry(db, telemetry_db):
    result = import_flight_log(DJI_LOG.encode(), db, telemetry_db, user_id=None)

    assert result["error"] is None
    assert result["points_imported"] == 3
    flight = db.query(Flight).one()
    assert flight.id == result["flight_id"]
    assert flight.data_source == "dji_log"
    assert flight.has_telemetry is True
    assert flight.review_status == "needs_review"
    assert flight.pilot_confirmed is False
    assert telemetry_db.query(TelemetryPoint).filter(
        TelemetryPoint.flight_id == flight.id).count() == 3


def test_the_same_file_imported_twice_creates_one_flight(db, telemetry_db):
    content = _airdata_json().encode()
    first = import_flight_log(content, db, telemetry_db)

    second = import_flight_log(content, db, telemetry_db)

    assert second["skipped"] is True
    assert second["flight_id"] == first["flight_id"]
    assert second["points_imported"] == 0
    assert db.query(Flight).count() == 1


def test_the_duplicate_check_ignores_case_and_dashes(db, telemetry_db):
    """Providers are inconsistent about how they punctuate their own ids, and
    the same flight arriving as "ad123" must not land a second time."""
    import_flight_log(_airdata_json().encode(), db, telemetry_db)
    variant = _airdata_json().replace('"AD-123"', '"ad123"').encode()

    assert import_flight_log(variant, db, telemetry_db)["skipped"] is True
    assert db.query(Flight).count() == 1


def test_an_import_links_a_vehicle_by_its_provider_serial(db, telemetry_db):
    vehicle = Vehicle(serial_number="LOCAL-1", manufacturer="Airdata", model="X",
                      provider_serial="SN-9")
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    import_flight_log(_airdata_json().encode(), db, telemetry_db)

    assert db.query(Flight).one().vehicle_id == vehicle.id


def test_an_import_links_a_vehicle_by_its_own_serial_number(db, telemetry_db):
    vehicle = Vehicle(serial_number="SN-9", manufacturer="Airdata", model="X")
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    import_flight_log(_airdata_json().encode(), db, telemetry_db)

    assert db.query(Flight).one().vehicle_id == vehicle.id


def test_an_unmatched_serial_still_imports_the_flight(db, telemetry_db):
    import_flight_log(_airdata_json().encode(), db, telemetry_db)

    flight = db.query(Flight).one()
    assert flight.vehicle_id is None


def test_a_file_with_no_telemetry_creates_nothing(db, telemetry_db):
    content = _airdata_json(gps={"data": [], "timestamps": []}).encode()

    result = import_flight_log(content, db, telemetry_db)

    assert result["error"]
    assert result["flight_id"] is None
    assert db.query(Flight).count() == 0


def test_an_unreadable_file_creates_nothing(db, telemetry_db):
    result = import_flight_log(b"this is not a flight log at all", db, telemetry_db)

    assert result["error"]
    assert db.query(Flight).count() == 0


def test_a_failed_telemetry_insert_leaves_no_phantom_flight(db, telemetry_db, monkeypatch):
    """The flight is written before its points. Without the rollback the table
    keeps a row claiming has_telemetry=True with nothing behind it, which then
    shows on the map as an empty track."""
    def boom(*args, **kwargs):
        raise RuntimeError("telemetry db is gone")

    monkeypatch.setattr(fli, "_create_telemetry_points", boom)

    with pytest.raises(RuntimeError):
        import_flight_log(DJI_LOG.encode(), db, telemetry_db)

    db.expire_all()
    assert db.query(Flight).count() == 0


def test_an_explicit_format_hint_overrides_detection(db, telemetry_db):
    """The uploader can name the format, and that has to win: a DJI export
    whose header drifted would otherwise fall through to the CSV fallback."""
    result = import_flight_log(DJI_LOG.encode(), db, telemetry_db, format_hint="dji")

    assert result["format_detected"] == "dji"
    assert result["points_imported"] == 3


def test_an_unsupported_hint_is_refused(db, telemetry_db):
    result = import_flight_log(DJI_LOG.encode(), db, telemetry_db, format_hint="skydio")

    assert result["error"] == "Unsupported format: skydio"
    assert db.query(Flight).count() == 0
