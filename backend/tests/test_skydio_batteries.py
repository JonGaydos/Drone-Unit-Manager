"""Skydio provider battery/flight serial mapping.

Skydio's ``/batteries`` endpoint returns the clean serial in ``battery_name``
and a leading-dash artifact in ``battery_serial`` (e.g. "k01-231025-1-01022"
vs "-k01-231025-1-01022"); its cycle counter is the ``cycles`` key. Flight
objects report ``battery_serial`` in the same dash form. The provider must
store clean serials (keeping the raw form in ``skydio_battery_serial``) and
map the real cycle count.
"""

import pytest

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


# Every other path that writes a flight's battery from Skydio data ----------

DASH_SERIAL = "-k01-251117-1-00007"
CLEAN_SERIAL = "k01-251117-1-00007"


@pytest.mark.parametrize("detail", [
    {"battery_serial": DASH_SERIAL},
    {"battery": DASH_SERIAL},
    {"battery": {"battery_serial": DASH_SERIAL}},
])
def test_flight_refresh_stores_the_clean_battery_serial(detail):
    from app.models.flight import Flight
    from app.routers.flights import _refresh_equipment
    flight = Flight()

    _refresh_equipment(flight, detail, [])

    assert flight.battery_serial == CLEAN_SERIAL


@pytest.mark.parametrize("key", ["battery_serial", "battery"])
def test_sync_enrichment_stores_the_clean_battery_serial(db, key):
    from app.models.flight import Flight
    from app.routers.sync import _apply_enrichment_detail
    flight = Flight()

    _apply_enrichment_detail(flight, {key: DASH_SERIAL}, db)

    assert flight.battery_serial == CLEAN_SERIAL


def test_sync_manager_enrichment_stores_the_clean_battery_serial():
    from app.models.flight import Flight
    from app.services.sync_manager import _enrich_flight_equipment
    flight = Flight()

    _enrich_flight_equipment(flight, {"battery_serial": DASH_SERIAL})

    assert flight.battery_serial == CLEAN_SERIAL


def test_csv_import_stores_the_clean_battery_serial(db):
    from app.models.flight import Flight
    from app.services.excel_import import import_skydio_csv
    csv_text = f"Flight ID,Vehicle,Pilot,Takeoff,Battery\nF1,X10-1,Jane Doe,2026-03-01 12:00:00,{DASH_SERIAL}\n"

    import_skydio_csv(db, csv_text.encode())

    assert db.query(Flight).one().battery_serial == CLEAN_SERIAL


def _battery_serials(path):
    import sqlite3
    conn = sqlite3.connect(path)
    try:
        return dict(conn.execute("SELECT id, battery_serial FROM flights ORDER BY id").fetchall())
    finally:
        conn.close()


def test_migration_strips_the_dash_from_stored_flight_batteries(tmp_path, monkeypatch):
    import sqlite3
    from alembic import command
    import app.config
    from tests.test_maintenance_batch8 import _alembic, _insert
    path = tmp_path / "m.db"
    url = f"sqlite:///{path.as_posix()}"
    monkeypatch.setattr(app.config.settings, "DATABASE_URL", url)
    config = _alembic(url)
    command.upgrade(config, "0012_audit_identity")
    conn = sqlite3.connect(path)
    for fid, serial in enumerate([DASH_SERIAL, "--k01-2", CLEAN_SERIAL, "h2090490d6221048", None, "-"], start=1):
        _insert(conn, "flights", id=fid, battery_serial=serial)
    conn.commit()
    conn.close()
    expected = {1: CLEAN_SERIAL, 2: "k01-2", 3: CLEAN_SERIAL, 4: "h2090490d6221048", 5: None, 6: None}

    command.upgrade(config, "head")
    assert _battery_serials(path) == expected

    command.downgrade(config, "0012_audit_identity")
    assert _battery_serials(path) == expected
    command.upgrade(config, "head")
    assert _battery_serials(path) == expected
