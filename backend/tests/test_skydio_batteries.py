"""Skydio provider battery/flight serial mapping.

Skydio's ``/batteries`` endpoint returns the clean serial in ``battery_name``
and a leading-dash artifact in ``battery_serial`` (e.g. "k01-231025-1-01022"
vs "-k01-231025-1-01022"); its cycle counter is the ``cycles`` key. Flight
objects report ``battery_serial`` in the same dash form. The provider must
store clean serials (keeping the raw form in ``skydio_battery_serial``) and
map the real cycle count.
"""

from app.integrations.skydio import SkydioProvider, _map_raw_flight

RAW_BATTERIES = [
    {  # X10 pack: clean name, dash-prefixed serial
        "battery_name": "k01-231025-1-01022",
        "battery_serial": "-k01-231025-1-01022",
        "cycles": 33,
        "flight_count": 60,
    },
    {  # hex pack: name and serial identical, no dash
        "battery_name": "m2090490d58b0226",
        "battery_serial": "m2090490d58b0226",
        "cycles": 17,
    },
    {  # no name: fall back to the stripped serial
        "battery_serial": "-g00-210719-1-00255",
        "cycles": 8,
    },
]


def test_sync_batteries_stores_clean_serials_and_cycles(monkeypatch):
    provider = SkydioProvider()
    monkeypatch.setattr(provider, "_paginate", lambda url, creds, **kw: RAW_BATTERIES)

    out = provider.sync_batteries(creds=None)

    assert [b["serial_number"] for b in out] == [
        "k01-231025-1-01022",
        "m2090490d58b0226",
        "g00-210719-1-00255",
    ]
    # Raw dash form kept for API correlation
    assert [b["skydio_battery_serial"] for b in out] == [
        "-k01-231025-1-01022",
        "m2090490d58b0226",
        "-g00-210719-1-00255",
    ]
    assert [b["cycle_count"] for b in out] == [33, 17, 8]


def test_map_raw_flight_strips_battery_serial_dash():
    mapped = _map_raw_flight({
        "flight_id": "ABC123",
        "battery_serial": "-k01-231117-1-00061",
        "vehicle_serial": "SkydioX10-bk7n",
    })

    assert mapped["battery_serial"] == "k01-231117-1-00061"
    assert mapped["external_id"] == "ABC123"


def test_map_raw_flight_leaves_hex_serial_alone():
    mapped = _map_raw_flight({
        "flight_id": "DEF456",
        "battery_serial": "h2090490d6221048",
    })

    assert mapped["battery_serial"] == "h2090490d6221048"
