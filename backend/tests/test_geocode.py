"""Geocode endpoint tests: auth gate and mocked Nominatim mapping.

Covers the real behavior of ``app.routers.geocode`` (GET ``/api/geocode?q=``):

* Requires authentication (401 without a Bearer token).
* A valid Nominatim result maps to ``{lat, lon, display_name}`` (200).
* An empty Nominatim result list maps to 404.
* Any upstream/network error maps to 502.
* A result with missing/non-numeric lat/lon maps to 404 (NOT 500) — the
  float parse is guarded, so malformed coordinates must not crash.

Nominatim is ALWAYS stubbed via the ``mock_httpx`` fixture (an
``httpx.MockTransport`` covering ``httpx.get``); no test hits the network.
"""

import httpx

GEOCODE_URL = "/api/geocode"
REVERSE_URL = "/api/geocode/reverse"


def test_geocode_requires_auth(client):
    """No token -> 401 (get_current_user rejects missing credentials)."""
    resp = client.get(GEOCODE_URL, params={"q": "Boston"})
    assert resp.status_code == 401


def test_geocode_result_maps_to_lat_lon_display_name(client, admin_headers, mock_httpx):
    """A valid Nominatim match returns 200 with parsed lat/lon/display_name."""
    def handler(request):
        assert "nominatim.openstreetmap.org" in str(request.url)
        return httpx.Response(
            200,
            json=[
                {
                    "lat": "42.3600825",
                    "lon": "-71.0588801",
                    "display_name": "Boston, Suffolk County, Massachusetts, USA",
                }
            ],
        )

    mock_httpx(handler)
    resp = client.get(GEOCODE_URL, params={"q": "Boston"}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "lat": 42.3600825,
        "lon": -71.0588801,
        "display_name": "Boston, Suffolk County, Massachusetts, USA",
    }


def test_geocode_empty_result_returns_404(client, admin_headers, mock_httpx):
    """An empty result list -> 404."""
    mock_httpx(lambda request: httpx.Response(200, json=[]))
    resp = client.get(GEOCODE_URL, params={"q": "nowhere-zzz"}, headers=admin_headers)
    assert resp.status_code == 404


def test_geocode_upstream_error_returns_502(client, admin_headers, mock_httpx):
    """A non-200 upstream response (raise_for_status raises) -> 502."""
    mock_httpx(lambda request: httpx.Response(503, text="service unavailable"))
    resp = client.get(GEOCODE_URL, params={"q": "Boston"}, headers=admin_headers)
    assert resp.status_code == 502


def test_geocode_bad_coordinates_returns_404_not_500(client, admin_headers, mock_httpx):
    """A result with non-numeric lat/lon -> 404 (graceful), NOT 500."""
    def handler(request):
        return httpx.Response(
            200,
            json=[{"lat": "not-a-number", "display_name": "Broken Place"}],
        )

    mock_httpx(handler)
    resp = client.get(GEOCODE_URL, params={"q": "Boston"}, headers=admin_headers)
    assert resp.status_code == 404


# --- reverse geocode (coords -> address) -----------------------------------

def test_reverse_requires_auth(client):
    resp = client.get(REVERSE_URL, params={"lat": 30.37, "lon": -86.2})
    assert resp.status_code == 401


def test_reverse_returns_the_display_name(client, admin_headers, mock_httpx):
    def handler(request):
        assert "nominatim.openstreetmap.org/reverse" in str(request.url)
        return httpx.Response(200, json={"display_name": "842 E State Hwy 20, Freeport, FL"})

    mock_httpx(handler)
    resp = client.get(REVERSE_URL, params={"lat": 30.371, "lon": -86.203}, headers=admin_headers)

    assert resp.status_code == 200
    assert resp.json() == {"lat": 30.371, "lon": -86.203, "display_name": "842 E State Hwy 20, Freeport, FL"}


def test_reverse_with_no_address_returns_404(client, admin_headers, mock_httpx):
    """Nominatim answers an ocean point with an error object, not a name."""
    mock_httpx(lambda request: httpx.Response(200, json={"error": "Unable to geocode"}))
    resp = client.get(REVERSE_URL, params={"lat": 0, "lon": 0}, headers=admin_headers)
    assert resp.status_code == 404


def test_reverse_upstream_error_returns_502(client, admin_headers, mock_httpx):
    mock_httpx(lambda request: httpx.Response(503, text="service unavailable"))
    resp = client.get(REVERSE_URL, params={"lat": 30.37, "lon": -86.2}, headers=admin_headers)
    assert resp.status_code == 502


def test_reverse_rejects_out_of_range_coordinates(client, admin_headers):
    """The Query bounds guard bad input before any upstream call (422)."""
    resp = client.get(REVERSE_URL, params={"lat": 200, "lon": -86.2}, headers=admin_headers)
    assert resp.status_code == 422
