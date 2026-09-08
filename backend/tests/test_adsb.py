"""ADS-B proxy tests: provider, request shape, mapping, and failure handling.

The app proxies adsb.lol (an open ``/v2/point`` feed) after airplanes.live
began returning 403 to server-side callers. These cover that the proxy targets
adsb.lol with a descriptive User-Agent, maps the readsb ``ac`` records to the
app's shape, drops positionless aircraft, and degrades to an empty result
rather than an error when the upstream fails.

httpx is stubbed via ``mock_httpx``; no test hits the network.
"""

import httpx
import pytest

import app.routers.adsb as adsb

NEARBY = "/api/adsb/nearby"


@pytest.fixture(autouse=True)
def _reset_cache():
    """The proxy caches globally; clear it so tests do not see each other's
    aircraft (and so the failure test cannot return a prior test's stale data)."""
    adsb._cache = {"data": None, "timestamp": 0, "key": ""}
    yield
    adsb._cache = {"data": None, "timestamp": 0, "key": ""}


def _v2(ac):
    return {"ac": ac, "msg": "No error", "now": 1_700_000_000_000, "total": len(ac)}


def test_nearby_requires_auth(client):
    assert client.get(NEARBY, params={"lat": 30, "lon": -86, "radius_nm": 50}).status_code == 401


def test_it_queries_adsb_lol_with_a_user_agent(client, admin_headers, mock_httpx):
    seen = {}

    def handler(request):
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        seen["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, json=_v2([]))

    mock_httpx(handler)
    r = client.get(NEARBY, params={"lat": 30.37, "lon": -86.2, "radius_nm": 100}, headers=admin_headers)

    assert r.status_code == 200
    assert seen["host"] == "api.adsb.lol"
    assert seen["path"] == "/v2/point/30.37/-86.2/100"
    assert "DroneUnitManager" in seen["ua"]


def test_records_map_to_the_apps_shape(client, admin_headers, mock_httpx):
    ac = [{
        "hex": "a1b2c3", "flight": "N123AB  ", "r": "N123AB", "t": "C172",
        "lat": 30.4, "lon": -86.1, "alt_baro": 3500, "alt_geom": 3600,
        "gs": 110.5, "track": 275.0, "baro_rate": -64, "squawk": "1200",
        "emergency": "none", "category": "A1", "seen": 2.1,
    }]
    mock_httpx(lambda request: httpx.Response(200, json=_v2(ac)))

    r = client.get(NEARBY, params={"lat": 30.4, "lon": -86.1, "radius_nm": 50}, headers=admin_headers)
    body = r.json()

    assert body["count"] == 1
    a = body["aircraft"][0]
    assert a["icao"] == "A1B2C3"          # hex upper-cased
    assert a["callsign"] == "N123AB"       # flight trimmed
    assert a["aircraft_type"] == "C172"
    assert a["lat"] == 30.4 and a["lon"] == -86.1
    assert a["alt_baro"] == 3500
    assert a["track"] == 275.0


def test_aircraft_without_a_position_are_dropped(client, admin_headers, mock_httpx):
    ac = [
        {"hex": "aaa", "lat": 30.4, "lon": -86.1},
        {"hex": "bbb", "lat": None, "lon": -86.1},   # no lat
        {"hex": "ccc"},                                 # no position at all
    ]
    mock_httpx(lambda request: httpx.Response(200, json=_v2(ac)))

    body = client.get(NEARBY, params={"lat": 30.4, "lon": -86.1, "radius_nm": 50}, headers=admin_headers).json()

    assert body["count"] == 1
    assert body["aircraft"][0]["icao"] == "AAA"


def test_a_403_from_the_provider_yields_an_empty_result_not_an_error(client, admin_headers, mock_httpx):
    """The failure that started this: airplanes.live returned 403. The proxy
    must answer 200 with no aircraft (and surface the reason) rather than 5xx,
    so the map shows 'no aircraft' instead of breaking."""
    mock_httpx(lambda request: httpx.Response(403, text="Please contact us"))

    r = client.get(NEARBY, params={"lat": 30.4, "lon": -86.1, "radius_nm": 50}, headers=admin_headers)

    assert r.status_code == 200
    body = r.json()
    assert body["aircraft"] == []
    assert body["count"] == 0
    assert body.get("error")
