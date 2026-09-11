"""Unit coverage for the Skydio provider: pagination, response mapping, and the
error-logging hygiene added alongside the complexity refactor.

These don't touch the network -- _request is faked, or _paginate is replaced --
so they pin the refactored helpers' behavior exactly and prove that an error the
Skydio API returns is a one-line warning while an unexpected error keeps its
traceback.
"""

import logging

import httpx

from app.integrations.base import ProviderCredentials
from app.integrations.skydio import (
    SkydioProvider,
    _log_provider_error,
    _first_list_in_dict,
    _unwrap_telemetry_response,
    _telemetry_point_derived,
    _map_telemetry_point,
    _map_raw_flight,
)

CREDS = ProviderCredentials(api_token="t", token_id="id")


class _Resp:
    def __init__(self, body, status=200):
        self._body = body
        self.status_code = status

    def json(self):
        return self._body


def _http_error(status):
    request = httpx.Request("GET", "https://api.skydio.com/api/v0/x")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(str(status), request=request, response=response)


def _records(caplog, needle):
    return [r for r in caplog.records if needle in r.getMessage()]


# --- _log_provider_error ----------------------------------------------------

def test_log_provider_error_api_status_is_a_warning_without_traceback(caplog):
    with caplog.at_level(logging.DEBUG):
        _log_provider_error("sync widgets", _http_error(403))
    recs = _records(caplog, "sync widgets")
    assert recs and recs[0].levelno == logging.WARNING
    assert recs[0].exc_info is None
    assert "403" in recs[0].getMessage()


def test_log_provider_error_unexpected_keeps_full_traceback(caplog):
    with caplog.at_level(logging.DEBUG):
        _log_provider_error("sync widgets", ValueError("boom"))
    recs = _records(caplog, "sync widgets")
    assert recs and recs[0].levelno == logging.ERROR
    assert recs[0].exc_info is not None


# --- telemetry unwrap / mapping helpers -------------------------------------

def test_first_list_in_dict_direct_nested_and_missing():
    assert _first_list_in_dict({"telemetry": [1, 2]}) == [1, 2]
    assert _first_list_in_dict({"data": {"inner": [3]}}) == [3]
    assert _first_list_in_dict({"nope": 5}) is None


def test_unwrap_telemetry_response_shapes():
    assert _unwrap_telemetry_response({"data": {"flight_telemetry": [1]}}) == [1]
    assert _unwrap_telemetry_response({"points": [2, 3]}) == [2, 3]
    assert _unwrap_telemetry_response([9]) == [9]
    assert _unwrap_telemetry_response("nonsense") == []
    assert _unwrap_telemetry_response({"unknown": 1}) == []


def test_telemetry_point_derived_scales_battery_alt_and_speed():
    battery, alt, speed = _telemetry_point_derived(
        {"battery_percentage": 0.5, "height_above_takeoff": 30.0,
         "gps_velocity": [3.0, 4.0, 0.0]}, None)
    assert battery == 50.0          # 0-1 form scaled to percent
    assert alt == 30.0
    assert speed == 5.0             # sqrt(3^2 + 4^2)


def test_telemetry_point_derived_alt_from_gps_minus_ground():
    _, alt, _ = _telemetry_point_derived({"gps_altitude": 130.0}, 100.0)
    assert alt == 30.0


def test_telemetry_point_derived_all_absent_is_none():
    assert _telemetry_point_derived({}, None) == (None, None, None)


def test_map_telemetry_point_rejects_non_dict():
    assert _map_telemetry_point("x", None) is None


def test_map_telemetry_point_maps_expected_fields():
    out = _map_telemetry_point(
        {"timestamp_ms": 5, "gps_latitude": 28.5, "gps_longitude": -81.4,
         "height_above_takeoff": 10.0, "battery_percentage": 80,
         "gps_num_satellites_used": 12}, None)
    assert out["timestamp_ms"] == 5
    assert (out["lat"], out["lon"]) == (28.5, -81.4)
    assert out["altitude_m"] == 10.0
    assert out["battery_pct"] == 80     # already 0-100, left as-is
    assert out["satellites"] == 12


def test_map_raw_flight_parses_dates_and_computes_duration():
    out = _map_raw_flight({"flight_id": "F1",
                           "takeoff": "2025-06-01T13:00:00Z",
                           "landing": "2025-06-01T13:10:00Z"})
    assert out["external_id"] == "F1"
    assert out["date"] == "2025-06-01"
    assert out["duration_seconds"] == 600


# --- _paginate (refactored loop) --------------------------------------------

def _provider_with_pages(pages):
    provider = SkydioProvider()
    state = {"n": 0}

    def fake_request(method, url, creds, params=None, timeout=30.0):
        resp = pages[state["n"]]
        state["n"] += 1
        return resp

    provider._request = fake_request
    provider._calls = state
    return provider


def test_paginate_follows_cursor_then_stops():
    provider = _provider_with_pages([
        _Resp({"data": [{"id": 1}], "next_cursor": "c2"}),
        _Resp({"data": [{"id": 2}]}),      # no cursor -> stop
    ])
    assert provider._paginate("https://x/flights", CREDS) == [{"id": 1}, {"id": 2}]
    assert provider._calls["n"] == 2


def test_paginate_follows_has_more_offset():
    provider = _provider_with_pages([
        _Resp({"data": [{"id": 1}], "has_more": True}),
        _Resp({"data": [{"id": 2}], "has_more": False}),
    ])
    assert provider._paginate("https://x/y", CREDS) == [{"id": 1}, {"id": 2}]


def test_paginate_bare_list_is_the_whole_result():
    provider = SkydioProvider()
    provider._request = lambda *a, **k: _Resp([{"id": 1}, {"id": 2}])
    assert provider._paginate("https://x/y", CREDS) == [{"id": 1}, {"id": 2}]


def test_paginate_empty_items_stops():
    provider = SkydioProvider()
    provider._request = lambda *a, **k: _Resp({"data": []})
    assert provider._paginate("https://x/y", CREDS) == []


# --- sync_* error hygiene ---------------------------------------------------

def test_sync_media_warns_and_returns_empty_on_api_error(caplog):
    provider = SkydioProvider()
    def boom(*a, **k):
        raise _http_error(500)
    provider._paginate = boom
    with caplog.at_level(logging.DEBUG):
        assert provider.sync_media(CREDS) == []
    recs = _records(caplog, "sync Skydio media")
    assert recs and recs[0].levelno == logging.WARNING
    assert recs[0].exc_info is None


def test_sync_controllers_logs_error_with_traceback_on_bug(caplog):
    provider = SkydioProvider()
    def boom(*a, **k):
        raise ValueError("unexpected bug")
    provider._paginate = boom
    with caplog.at_level(logging.DEBUG):
        assert provider.sync_controllers(CREDS) == []
    recs = _records(caplog, "sync Skydio controllers")
    assert recs and recs[0].levelno == logging.ERROR
    assert recs[0].exc_info is not None
