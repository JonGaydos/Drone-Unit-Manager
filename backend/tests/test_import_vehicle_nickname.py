"""A Skydio export names each drone by its nickname, while sync stores the
hardware serial. The importer finds the synced drone by either."""

from app.models.vehicle import Vehicle
from app.services.excel_import import _find_or_create_vehicle

NICKNAME = "SkydioX10-zz01"
HW_SERIAL = "1668BR40FAZZ0001"


def _synced(db, nickname=NICKNAME, serial=HW_SERIAL):
    v = Vehicle(serial_number=serial, nickname=nickname, manufacturer="Skydio", model="X10")
    db.add(v)
    db.commit()
    return v


def test_a_nickname_finds_the_synced_drone(db):
    synced = _synced(db)
    found, created = _find_or_create_vehicle(db, NICKNAME)
    assert found.id == synced.id
    assert created is False


def test_the_nickname_match_ignores_case(db):
    synced = _synced(db)
    found, _ = _find_or_create_vehicle(db, NICKNAME.lower())
    assert found.id == synced.id


def test_no_new_vehicle_is_added_for_a_known_nickname(db):
    _synced(db)
    _find_or_create_vehicle(db, NICKNAME)
    assert db.query(Vehicle).count() == 1


def test_a_serial_match_wins_over_a_nickname_match(db):
    _synced(db, nickname="other-name", serial=NICKNAME)
    by_serial = db.query(Vehicle).filter_by(serial_number=NICKNAME).one()
    _synced(db, nickname=NICKNAME, serial="1668BR40FAZZ0002")
    found, _ = _find_or_create_vehicle(db, NICKNAME)
    assert found.id == by_serial.id


def test_an_unknown_drone_is_still_created(db):
    _synced(db)
    found, created = _find_or_create_vehicle(db, "SkydioX2-zz99")
    assert created is True
    assert found.serial_number == "SkydioX2-zz99"
