"""The Parrot / GUTMA DX JSON parser (ANAFI exports).

Untested until now. The cases below concentrate on the encodings this format
uses that would otherwise pass straight through into the record: a "no fix"
sentinel of 500 degrees, a negative battery reading, and timestamps that are
offsets from a separate start time rather than absolute.
"""

import json
import math
from datetime import datetime

import pytest

from app.services.parrot_import import (
    _gutma_event_ts,
    _gutma_start_local,
    is_gutma,
    parse_gutma,
)

KEYS = ["timestamp", "gps_lat", "gps_lon", "product_gps_available", "altitude_ato",
        "speed_vx", "speed_vy", "angle_psi", "battery_percent",
        "product_gps_sat_used_count", "battery_voltage", "gps_amsl_altitude"]


def _row(ts, lat=28.5, lon=-81.4, fix=1, ato=10.0, vx=3.0, vy=4.0, psi=0.0,
         battery=90.0, sats=12, volts=12.4, amsl=30.0):
    return [ts, lat, lon, fix, ato, vx, vy, psi, battery, sats, volts, amsl]


def _log(items=None, events=None, start="2026-05-01T10:00:00", **flight_data):
    data = {"flight_id": "PARROT-1", "aircraft": {"serial_number": "PI-040"}}
    data.update(flight_data)
    logging = {"logging_start_dtg": start, "flight_logging_keys": KEYS,
               "flight_logging_items": items if items is not None else
               [_row(0.0), _row(30.0, ato=42.0), _row(60.0)]}
    if events is not None:
        logging["events"] = events
    return json.dumps({"exchange": {"message": {
        "flight_data": data, "flight_logging": logging}}})


# 1. Recognising the format -------------------------------------------------

def test_a_gutma_log_is_recognised_by_either_marker():
    assert is_gutma('{"message_type": "GUTMA_DX_JSON"}')
    assert is_gutma('{"flight_logging_keys": []}')


def test_an_unrelated_file_is_not_claimed():
    assert not is_gutma('{"data": {"flight": {}}}')


# 2. Envelope failures ------------------------------------------------------

def test_invalid_json_is_reported_not_raised():
    assert parse_gutma("{oops")["error"] == "Invalid JSON"


def test_json_without_the_gutma_envelope_is_reported():
    assert parse_gutma('{"hello": 1}')["error"] == "Not a GUTMA flight log"


def test_a_log_with_no_rows_is_reported():
    assert parse_gutma(_log(items=[]))["error"] == "No telemetry in GUTMA log"


# 3. Timestamps -------------------------------------------------------------

def test_row_timestamps_are_offsets_from_the_logging_start():
    """GUTMA rows carry seconds since `logging_start_dtg`, not wall-clock time.
    Read as absolute they land in 1970."""
    result = parse_gutma(_log())

    assert result["telemetry"][0]["timestamp"] == datetime(2026, 5, 1, 10, 0, 0)
    assert result["telemetry"][2]["timestamp"] == datetime(2026, 5, 1, 10, 1, 0)


def test_the_start_time_is_stored_as_local_wall_clock():
    """An offset in the header does not shift the stored time: these logs
    record local time and the app stores naive datetimes."""
    assert _gutma_start_local({"logging_start_dtg": "2026-05-01T10:00:00+02:00"}) == \
        datetime(2026, 5, 1, 10, 0, 0)


def test_a_missing_or_unparseable_start_time_is_none():
    assert _gutma_start_local({}) is None
    assert _gutma_start_local({"logging_start_dtg": "not a date"}) is None


def test_duration_comes_from_the_takeoff_and_landing_events_when_present():
    """The rows may start well before the aircraft leaves the ground. TOF/LND
    are the real boundaries."""
    events = [{"event_info": "TOF", "event_timestamp": 10.0},
              {"event_info": "LND", "event_timestamp": 50.0}]

    meta = parse_gutma(_log(events=events))["metadata"]

    assert meta["duration_seconds"] == 40
    assert meta["takeoff_time"] == datetime(2026, 5, 1, 10, 0, 10)
    assert meta["landing_time"] == datetime(2026, 5, 1, 10, 0, 50)


def test_duration_falls_back_to_the_first_and_last_row():
    assert parse_gutma(_log(events=[]))["metadata"]["duration_seconds"] == 60


def test_the_last_landing_event_wins():
    """A log can carry several LND events (a touch-and-go, or a bounce). The
    flight ends at the last one."""
    events = [{"event_info": "TOF", "event_timestamp": 0.0},
              {"event_info": "LND", "event_timestamp": 20.0},
              {"event_info": "LND", "event_timestamp": 55.0}]

    assert parse_gutma(_log(events=events))["metadata"]["duration_seconds"] == 55


def test_a_landing_event_before_takeoff_is_ignored():
    """Out-of-order events would otherwise produce a negative duration."""
    events = [{"event_info": "TOF", "event_timestamp": 40.0},
              {"event_info": "LND", "event_timestamp": 5.0}]

    meta = parse_gutma(_log(events=events))["metadata"]

    assert meta["duration_seconds"] == 20  # falls back to the last row, at 60s


def test_a_single_row_log_has_no_duration():
    assert parse_gutma(_log(items=[_row(0.0)]))["metadata"]["duration_seconds"] is None


def test_an_event_type_that_is_absent_yields_no_timestamp():
    assert _gutma_event_ts([{"event_info": "TOF", "event_timestamp": 1.0}], "LND") is None


# 4. GPS fixes --------------------------------------------------------------

def test_a_row_without_a_gps_fix_has_no_coordinates():
    """The flag is the authority, not the value. A stale in-range coordinate
    reported before the fix looks perfectly plausible and would anchor the
    track somewhere the aircraft never was."""
    items = [_row(0.0, lat=28.5, lon=-81.4, fix=0), _row(10.0, lat=28.9, lon=-81.9)]

    telemetry = parse_gutma(_log(items=items))["telemetry"]

    assert telemetry[0]["lat"] is None
    assert telemetry[0]["lon"] is None
    assert telemetry[1]["lat"] == 28.9


def test_the_no_fix_sentinel_is_rejected_even_with_the_fix_flag_set():
    """Parrot writes 500 for "no reading". At face value it plots off the edge
    of the world."""
    telemetry = parse_gutma(_log(items=[_row(0.0, lat=500, lon=500, fix=1)]))["telemetry"]

    assert telemetry[0]["lat"] is None


def test_the_takeoff_point_is_the_first_row_that_actually_has_a_fix():
    items = [_row(0.0, fix=0), _row(10.0, fix=0), _row(20.0, lat=28.7, lon=-81.7)]

    meta = parse_gutma(_log(items=items))["metadata"]

    assert (meta["takeoff_lat"], meta["takeoff_lon"]) == (28.7, -81.7)


def test_the_landing_point_is_the_last_row_that_has_a_fix():
    """Scanned from the end, so the unfixed rows after touchdown do not erase
    where the aircraft came down."""
    items = [_row(0.0, lat=28.5, lon=-81.4), _row(10.0, lat=28.9, lon=-81.9), _row(20.0, fix=0)]

    meta = parse_gutma(_log(items=items))["metadata"]

    assert (meta["landing_lat"], meta["landing_lon"]) == (28.9, -81.9)


def test_a_log_with_no_fix_anywhere_still_parses():
    items = [_row(0.0, fix=0), _row(10.0, fix=0)]

    meta = parse_gutma(_log(items=items))["metadata"]

    assert meta["takeoff_lat"] is None
    assert meta["landing_lat"] is None


# 5. Derived telemetry ------------------------------------------------------

def test_horizontal_speed_is_the_magnitude_of_the_velocity_components():
    assert parse_gutma(_log())["telemetry"][0]["speed_mps"] == 5.0


def test_heading_is_converted_from_radians_and_normalised():
    """angle_psi is radians and can be negative; a heading of -90 degrees has
    to read as 270."""
    telemetry = parse_gutma(_log(items=[_row(0.0, psi=-math.pi / 2)]))["telemetry"]

    assert telemetry[0]["heading_deg"] == pytest.approx(270.0)


def test_a_negative_battery_reading_is_dropped():
    """The ANAFI reports -1 when it has no reading. Kept, it renders as a
    battery below empty."""
    telemetry = parse_gutma(_log(items=[_row(0.0, battery=-1.0)]))["telemetry"]

    assert telemetry[0]["battery_pct"] is None


def test_voltage_and_amsl_altitude_are_kept_as_extra_data():
    extra = parse_gutma(_log())["telemetry"][0]["extra_data"]

    assert extra["battery_voltage"] == 12.4
    assert extra["gps_amsl_altitude"] == 30.0


def test_the_maxima_are_the_highest_seen():
    meta = parse_gutma(_log())["metadata"]

    assert meta["max_altitude_m"] == 42.0
    assert meta["max_speed_mps"] == 5.0


def test_a_flight_that_never_left_the_ground_has_no_maxima():
    items = [_row(0.0, ato=0.0, vx=0.0, vy=0.0)]

    meta = parse_gutma(_log(items=items))["metadata"]

    assert meta["max_altitude_m"] is None
    assert meta["max_speed_mps"] is None


# 6. Identity ---------------------------------------------------------------

def test_the_aircraft_and_payload_serials_are_carried_through():
    """The vehicle serial is what the importer matches an airframe on, so a
    dropped one silently orphans the flight."""
    content = _log(payload=[{"serial_number": "CAM-7"}])

    meta = parse_gutma(content)["metadata"]

    assert meta["external_id"] == "PARROT-1"
    assert meta["vehicle_serial"] == "PI-040"
    assert meta["sensor_package"] == "CAM-7"


def test_a_log_with_no_payload_block_still_parses():
    assert parse_gutma(_log())["metadata"]["sensor_package"] is None


def test_a_short_row_does_not_raise():
    """Rows are positional. One cut short must yield None for the missing
    columns rather than failing the whole import."""
    telemetry = parse_gutma(_log(items=[[0.0, 28.5, -81.4, 1]]))["telemetry"]

    assert telemetry[0]["lat"] == 28.5
    assert telemetry[0]["altitude_m"] is None
    assert telemetry[0]["battery_pct"] is None
