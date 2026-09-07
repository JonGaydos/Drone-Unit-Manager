"""The "Refresh from API" button follows the drone, not the import source.

A flight refreshes only when its drone has a connected provider API. Skydio
drones do; BRINC drones do not. The catch is import source: a Skydio drone's
flights can arrive through Airdata or Excel, and those still have to refresh --
the capability belongs to the vehicle, not to how the row got in. So the gate
resolves the provider from the vehicle first (api_provider, then manufacturer)
and only falls back to the flight's recorded provider.

can_refresh on the flight payload drives whether the button is enabled; the
endpoint enforces the same rule server-side so a disabled button cannot be
worked around.
"""

from datetime import date

import pytest

from app.models.flight import Flight
from app.models.setting import Setting
from app.models.vehicle import Vehicle

REFRESH = "/api/flights/{}/refresh"
NO_API = "no connected API"


def _vehicle(db, **kw):
    kw.setdefault("model", "X")
    v = Vehicle(**kw)
    db.add(v)
    db.commit()
    return v


def _flight(db, **kw):
    kw.setdefault("date", date(2025, 6, 1))
    f = Flight(**kw)
    db.add(f)
    db.commit()
    return f


def _get(client, headers, flight_id):
    return client.get(f"/api/flights/{flight_id}", headers=headers).json()


# --- can_refresh follows the drone -----------------------------------------

def test_a_skydio_drone_can_refresh(client, db, admin_headers):
    v = _vehicle(db, serial_number="SKY-1", manufacturer="Skydio", api_provider="skydio")
    f = _flight(db, vehicle_id=v.id, external_id="flight-abc", api_provider="skydio")

    assert _get(client, admin_headers, f.id)["can_refresh"] is True


def test_a_brinc_drone_cannot_refresh(client, db, admin_headers):
    v = _vehicle(db, serial_number="BRC-1", manufacturer="BRINC")
    f = _flight(db, vehicle_id=v.id, external_id="brinc-123", api_provider="brinc")

    assert _get(client, admin_headers, f.id)["can_refresh"] is False


def test_a_skydio_drone_imported_from_airdata_still_refreshes(client, db, admin_headers):
    """The point of following the drone: the flight's provider is airdata, but
    the vehicle is a Skydio, so the Skydio API can still look it up."""
    v = _vehicle(db, serial_number="SKY-2", manufacturer="Skydio", api_provider="skydio")
    f = _flight(db, vehicle_id=v.id, external_id="flight-xyz", api_provider="airdata")

    assert _get(client, admin_headers, f.id)["can_refresh"] is True


def test_manufacturer_alone_is_enough_when_api_provider_is_unset(client, db, admin_headers):
    v = _vehicle(db, serial_number="SKY-3", manufacturer="Skydio", api_provider=None)
    f = _flight(db, vehicle_id=v.id, external_id="flight-3", api_provider="airdata")

    assert _get(client, admin_headers, f.id)["can_refresh"] is True


def test_no_external_id_means_no_refresh_even_for_a_skydio(client, db, admin_headers):
    """Without an external id there is nothing to look the flight up by."""
    v = _vehicle(db, serial_number="SKY-4", manufacturer="Skydio", api_provider="skydio")
    f = _flight(db, vehicle_id=v.id, external_id=None, api_provider="skydio")

    assert _get(client, admin_headers, f.id)["can_refresh"] is False


def test_no_vehicle_falls_back_to_the_flight_provider(client, db, admin_headers):
    f = _flight(db, vehicle_id=None, external_id="loose-1", api_provider="skydio")

    assert _get(client, admin_headers, f.id)["can_refresh"] is True


# --- the endpoint enforces the same rule -----------------------------------

def test_refreshing_a_brinc_flight_is_rejected(client, db, admin_headers):
    v = _vehicle(db, serial_number="BRC-2", manufacturer="BRINC")
    f = _flight(db, vehicle_id=v.id, external_id="brinc-999", api_provider="brinc")

    r = client.post(REFRESH.format(f.id), headers=admin_headers)

    assert r.status_code == 400
    assert NO_API in r.json()["detail"]


def test_refreshing_a_skydio_flight_needs_configured_creds(client, db, admin_headers):
    """A refreshable drone with the API not set up fails on the credentials,
    not on the drone -- a distinct message so the admin knows which to fix."""
    v = _vehicle(db, serial_number="SKY-5", manufacturer="Skydio", api_provider="skydio")
    f = _flight(db, vehicle_id=v.id, external_id="flight-5", api_provider="skydio")

    r = client.post(REFRESH.format(f.id), headers=admin_headers)

    assert r.status_code == 400
    assert "not configured" in r.json()["detail"]


def test_a_configured_skydio_flight_reaches_the_provider(client, db, admin_headers, monkeypatch):
    """With the drone refreshable and creds present, the request gets past both
    guards and calls the provider. A None detail surfaces as 502, which proves
    resolution worked rather than being blocked at the gate."""
    from app.integrations.skydio import SkydioProvider

    monkeypatch.setattr(SkydioProvider, "get_flight_detail", lambda self, creds, fid: None)
    db.add(Setting(key="skydio_api_token", value="tok"))
    db.commit()

    v = _vehicle(db, serial_number="SKY-6", manufacturer="Skydio", api_provider="skydio")
    f = _flight(db, vehicle_id=v.id, external_id="flight-6", api_provider="skydio")

    r = client.post(REFRESH.format(f.id), headers=admin_headers)

    assert r.status_code == 502


def test_refresh_without_an_external_id_is_rejected(client, db, admin_headers):
    v = _vehicle(db, serial_number="SKY-7", manufacturer="Skydio", api_provider="skydio")
    f = _flight(db, vehicle_id=v.id, external_id=None, api_provider="skydio")

    r = client.post(REFRESH.format(f.id), headers=admin_headers)

    assert r.status_code == 400
    assert "external ID" in r.json()["detail"]
