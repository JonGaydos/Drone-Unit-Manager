"""Ids are never reused (H-3).

SQLite without AUTOINCREMENT hands out max(id) + 1, so deleting the newest row
frees its id for the next insert, and an audit entry naming the old record then
points at an unrelated one. Every table with a single integer key now uses
AUTOINCREMENT: fresh installs through the models, existing installs through a
migration that rebuilds each table with its rows, ids, indexes and foreign keys.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

import app.config
from app.database import Base
import app.models  # noqa: F401 - register all ORM models on Base.metadata
from app.models.pilot import Pilot

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
BEFORE = "0013_clean_flight_battery_serials"
FLAGS = "has_telemetry, telemetry_synced, review_status, pilot_confirmed"


def _config(url):
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _keyed_tables(engine):
    """Tables whose primary key is one integer column, with their CREATE sql."""
    inspector = inspect(engine)
    found = {}
    with engine.connect() as conn:
        for table in inspector.get_table_names():
            if table in ("alembic_version", "sqlite_sequence"):
                continue
            pk = inspector.get_pk_constraint(table)["constrained_columns"]
            cols = {c["name"]: c for c in inspector.get_columns(table)}
            if len(pk) == 1 and "INT" in str(cols[pk[0]]["type"]).upper():
                found[table] = conn.exec_driver_sql(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).scalar()
    return found


def _shape(engine):
    """Everything a rebuild must keep: columns, indexes, foreign keys, uniques."""
    inspector = inspect(engine)
    shape = {}
    for table in inspector.get_table_names():
        if table in ("alembic_version", "sqlite_sequence"):
            continue
        shape[table] = (
            [(c["name"], str(c["type"]), c["nullable"], c["default"]) for c in inspector.get_columns(table)],
            sorted((i["name"], tuple(i["column_names"]), bool(i["unique"])) for i in inspector.get_indexes(table)),
            sorted((tuple(f["constrained_columns"]), f["referred_table"], tuple(f["referred_columns"]),
                    tuple(sorted(f["options"].items()))) for f in inspector.get_foreign_keys(table)),
            sorted(tuple(u["column_names"]) for u in inspector.get_unique_constraints(table)),
            inspector.get_pk_constraint(table)["constrained_columns"],
        )
    return shape


def test_deleting_the_newest_row_does_not_free_its_id(db):
    db.add_all([Pilot(first_name="First", last_name="Pilot", status="active"),
                Pilot(first_name="Second", last_name="Pilot", status="active")])
    db.commit()
    newest = db.query(Pilot).filter_by(first_name="Second").one()
    used = newest.id
    db.delete(newest)
    db.commit()

    again = Pilot(first_name="Third", last_name="Pilot", status="active")
    db.add(again)
    db.commit()

    assert again.id > used


def test_fresh_install_tables_use_autoincrement(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(engine)
    try:
        tables = _keyed_tables(engine)
    finally:
        engine.dispose()
    assert "pilots" in tables and "flight_plans" in tables
    missing = sorted(t for t, sql in tables.items() if "AUTOINCREMENT" not in sql.upper())
    assert not missing, missing


def test_migration_rebuilds_tables_keeping_rows_ids_indexes_and_keys(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'existing.db'}"
    monkeypatch.setattr(app.config.settings, "DATABASE_URL", url)
    cfg = _config(url)
    command.upgrade(cfg, BEFORE)

    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("INSERT INTO pilots (id, first_name, last_name, status) VALUES "
                                 "(1, 'Ana', 'One', 'active'), (7, 'Ben', 'Seven', 'active')")
            conn.exec_driver_sql(f"INSERT INTO flights (id, pilot_id, external_id, {FLAGS}) VALUES "
                                 "(3, 7, 'EXT-3', 0, 0, 'approved', 0), (9, 1, 'EXT-9', 0, 0, 'approved', 0)")
        before_shape = _shape(engine)
        assert any("AUTOINCREMENT" not in sql.upper() for sql in _keyed_tables(engine).values())
    finally:
        engine.dispose()

    command.upgrade(cfg, "head")

    engine = create_engine(url)
    try:
        assert _shape(engine) == before_shape
        tables = _keyed_tables(engine)
        missing = sorted(t for t, sql in tables.items() if "AUTOINCREMENT" not in sql.upper())
        assert not missing, missing
        with engine.begin() as conn:
            assert conn.exec_driver_sql("SELECT id, last_name FROM pilots ORDER BY id").all() == [
                (1, "One"), (7, "Seven")]
            assert conn.exec_driver_sql("SELECT id, pilot_id, external_id FROM flights ORDER BY id").all() == [
                (3, 7, "EXT-3"), (9, 1, "EXT-9")]
            assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
            # The newest id is not handed out again after its row is deleted.
            conn.exec_driver_sql("DELETE FROM flights WHERE id = 9")
            conn.exec_driver_sql(f"INSERT INTO flights (pilot_id, {FLAGS}) VALUES (1, 0, 0, 'approved', 0)")
            assert conn.exec_driver_sql("SELECT max(id) FROM flights").scalar() == 10
    finally:
        engine.dispose()


def test_migrations_have_a_single_head():
    cfg = _config("sqlite://")
    assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1
