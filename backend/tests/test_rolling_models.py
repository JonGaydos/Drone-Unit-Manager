"""Rolling requirement tables and migration 0018: lapses, excusals, the currency
tables dropped, the layout and operating cost columns, backups and pilot merge."""

import io
import json
import zipfile
from datetime import date, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

import app.config
from app.config import settings as app_settings
from app.models.flight_requirement import (
    FlightRequirement, FlightRequirementExcusal, FlightRequirementLapse,
)
from app.models.pilot import Pilot
from app.models.user import User
from app.models.vehicle import Vehicle
from app.routers.backup import DATABASE_FILE, EXPORT_ORDER, build_backup_archive

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
BEFORE = "0017_flight_requirements"
AFTER = "0018_rolling_requirements"
NEW_TABLES = {"flight_requirement_lapses", "flight_requirement_excusals"}
CURRENCY_TABLES = {"currency_rules", "currency_rule_models"}
NEW_COLUMNS = [("users", "dashboard_layout"), ("users", "analytics_layout"),
               ("vehicles", "hourly_operating_cost")]
IMPORT_URL = "/api/backup/import"


def _config(url):
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _requirement(**extra):
    return FlightRequirement(name="Rolling", period_type="rolling", start_date=date(2026, 1, 1),
                             recurring=True, model_mode="all", time_mode="any", **extra)


def _columns(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def _create_sql(engine, table):
    with engine.connect() as conn:
        return conn.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).scalar()


@pytest.fixture
def migrated(tmp_path, monkeypatch):
    """A database at 0017 holding a user, a vehicle and a currency rule with a model."""
    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setattr(app.config.settings, "DATABASE_URL", url)
    cfg = _config(url)
    command.upgrade(cfg, BEFORE)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (username, password_hash, display_name, role, is_active, theme, token_version) "
            "VALUES ('kept', 'x', 'Kept', 'admin', 1, 'dark', 0)"))
        conn.execute(text(
            "INSERT INTO vehicles (serial_number, manufacturer, model, status, total_flight_hours, total_flights, "
            "created_at, updated_at) VALUES ('V-1', 'Acme', 'X10', 'active', 0, 0, '2026-01-01', '2026-01-01')"))
        conn.execute(text(
            "INSERT INTO currency_rules (name, required_hours, period_days, is_active, created_at) "
            "VALUES ('Monthly hour', 1.0, 30, 1, '2026-01-01')"))
        conn.execute(text("INSERT INTO currency_rule_models (rule_id, model) VALUES (1, 'X10')"))
    yield cfg, engine
    engine.dispose()


def test_upgrade_adds_new_tables_and_drops_currency(migrated):
    cfg, engine = migrated
    command.upgrade(cfg, AFTER)
    tables = set(inspect(engine).get_table_names())
    assert NEW_TABLES <= tables
    assert not CURRENCY_TABLES & tables


@pytest.mark.parametrize("table,column", NEW_COLUMNS)
def test_upgrade_adds_column(migrated, table, column):
    cfg, engine = migrated
    command.upgrade(cfg, AFTER)
    assert column in _columns(engine, table)


@pytest.mark.parametrize("table", sorted(NEW_TABLES))
def test_new_tables_use_autoincrement(migrated, table):
    cfg, engine = migrated
    command.upgrade(cfg, AFTER)
    assert "AUTOINCREMENT" in _create_sql(engine, table)


def test_downgrade_restores_empty_currency_tables_and_drops_new_tables(migrated):
    cfg, engine = migrated
    command.upgrade(cfg, AFTER)
    command.downgrade(cfg, BEFORE)
    tables = set(inspect(engine).get_table_names())
    assert CURRENCY_TABLES <= tables
    assert not NEW_TABLES & tables
    with engine.connect() as conn:
        counts = [conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in sorted(CURRENCY_TABLES)]
    assert counts == [0, 0]


@pytest.mark.parametrize("table,column", NEW_COLUMNS)
def test_downgrade_drops_column(migrated, table, column):
    cfg, engine = migrated
    command.upgrade(cfg, AFTER)
    command.downgrade(cfg, BEFORE)
    assert column not in _columns(engine, table)


@pytest.mark.parametrize("table", ["users", "vehicles", "currency_rules", "currency_rule_models"])
def test_downgrade_keeps_autoincrement(migrated, table):
    cfg, engine = migrated
    command.upgrade(cfg, AFTER)
    command.downgrade(cfg, BEFORE)
    assert "AUTOINCREMENT" in _create_sql(engine, table)


@pytest.mark.parametrize("table", ["users", "vehicles"])
def test_upgrade_keeps_autoincrement(migrated, table):
    cfg, engine = migrated
    command.upgrade(cfg, AFTER)
    assert "AUTOINCREMENT" in _create_sql(engine, table)


def _shape(engine, table):
    """Columns, indexes and foreign keys of a table, as a rebuild must keep them."""
    inspector = inspect(engine)
    return (
        [(c["name"], str(c["type"]), c["nullable"], c["default"]) for c in inspector.get_columns(table)],
        sorted((i["name"], tuple(i["column_names"]), bool(i["unique"])) for i in inspector.get_indexes(table)),
        sorted((tuple(f["constrained_columns"]), f["referred_table"]) for f in inspector.get_foreign_keys(table)),
    )


@pytest.mark.parametrize("table", ["users", "vehicles"])
def test_downgrade_rebuild_keeps_table_shape(migrated, table):
    cfg, engine = migrated
    before = _shape(engine, table)
    command.upgrade(cfg, AFTER)
    command.downgrade(cfg, BEFORE)
    engine.dispose()
    assert _shape(engine, table) == before


def test_round_trip_keeps_user_and_vehicle_rows(migrated):
    cfg, engine = migrated
    command.upgrade(cfg, AFTER)
    command.downgrade(cfg, BEFORE)
    with engine.connect() as conn:
        rows = [conn.execute(text("SELECT username FROM users")).scalar(),
                conn.execute(text("SELECT serial_number FROM vehicles")).scalar()]
    assert rows == ["kept", "V-1"]


def test_model_columns_default_to_none(db):
    user = User(username="u", password_hash="x", display_name="U")
    vehicle = Vehicle(serial_number="V-2", manufacturer="Acme", model="X10")
    db.add_all([user, vehicle])
    db.commit()
    assert [user.dashboard_layout, user.analytics_layout, vehicle.hourly_operating_cost] == [None, None, None]


def _seed(db):
    pilot = Pilot(first_name="Ann", last_name="Lee")
    db.add(pilot)
    db.commit()
    req = _requirement(
        lapses=[FlightRequirementLapse(pilot_id=pilot.id, lapsed_on=date(2026, 3, 1))],
        excusals=[FlightRequirementExcusal(pilot_id=pilot.id, excused_until=date(2026, 6, 1),
                                           reason="Leave")])
    db.add(req)
    db.commit()
    return pilot, req


def test_delete_requirement_deletes_lapses_and_excusals(db):
    _pilot, req = _seed(db)
    db.delete(req)
    db.commit()
    assert [db.query(FlightRequirementLapse).count(), db.query(FlightRequirementExcusal).count()] == [0, 0]


def test_delete_pilot_deletes_lapses_and_excusals(db):
    pilot, _req = _seed(db)
    db.execute(text("DELETE FROM pilots WHERE id = :id"), {"id": pilot.id})
    db.commit()
    assert [db.query(FlightRequirementLapse).count(), db.query(FlightRequirementExcusal).count()] == [0, 0]


def test_backup_manifest_counts_new_tables(db):
    _seed(db)
    _spooled, manifest = build_backup_archive(db, include_telemetry=False)
    assert {t: manifest["tables"][t] for t in NEW_TABLES} == dict.fromkeys(NEW_TABLES, 1)


def test_backup_has_no_currency_tables(db):
    _spooled, manifest = build_backup_archive(db, include_telemetry=False)
    assert not CURRENCY_TABLES & set(manifest["tables"])


def test_export_order_names_no_currency_table():
    assert not CURRENCY_TABLES & {name for name, _model in EXPORT_ORDER}


def _as_360_backup(tables):
    """Reshape a backup's tables the way 3.6.0 wrote them."""
    for name in NEW_TABLES:
        tables.pop(name)
    for table, column in NEW_COLUMNS:
        for row in tables[table]:
            row.pop(column)
    tables["currency_rules"] = [{
        "id": 1, "name": "Monthly hour", "description": None, "vehicle_model": "X10",
        "required_hours": 1.0, "period_days": 30, "required_flights": None, "is_active": True,
        "created_at": "2026-01-01T00:00:00"}]
    tables["currency_rule_models"] = [{"id": 1, "rule_id": 1, "model": "X10"}]


def _archive(db, edit):
    spooled, _manifest = build_backup_archive(db, include_telemetry=False)
    source = zipfile.ZipFile(spooled)
    tables = json.loads(source.read(DATABASE_FILE))
    edit(tables)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for name in source.namelist():
            target.writestr(name, json.dumps(tables) if name == DATABASE_FILE else source.read(name))
    return out.getvalue()


def test_360_backup_with_currency_tables_restores(client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    db.add(Vehicle(serial_number="V-3", manufacturer="Acme", model="X10", hourly_operating_cost=40.0))
    db.commit()
    _seed(db)
    archive = _archive(db, _as_360_backup)
    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(app_settings, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)

    resp = client.post(IMPORT_URL, headers=admin_headers, data={"confirm_restore": "REPLACE ALL DATA"},
                       files={"file": ("b.zip", archive, "application/zip")})

    assert resp.status_code == 200, resp.text
    db.expire_all()
    restored = [db.query(Vehicle).one().hourly_operating_cost, db.query(FlightRequirementLapse).count(),
                db.query(Pilot).one().last_name]
    assert restored == [None, 0, "Lee"]


def _merge_pair(db):
    source = Pilot(first_name="Bea", last_name="Dup")
    target = Pilot(first_name="Ann", last_name="Keep")
    db.add_all([source, target])
    req = _requirement()
    db.add(req)
    db.commit()
    return source, target, req


def _merge(client, headers, source, target):
    target_id = target.id
    resp = client.post(f"/api/pilots/{target_id}/merge", headers=headers, json={"source_id": source.id})
    assert resp.status_code == 200, resp.text
    return target_id


def test_merge_moves_lapses_and_excusals(client, db, admin_headers):
    source, target, req = _merge_pair(db)
    db.add(FlightRequirementLapse(requirement_id=req.id, pilot_id=source.id, lapsed_on=date(2026, 3, 1)))
    db.add(FlightRequirementExcusal(requirement_id=req.id, pilot_id=source.id, excused_until=date(2026, 6, 1)))
    db.commit()
    target_id = _merge(client, admin_headers, source, target)
    db.expire_all()
    moved = [[r.pilot_id for r in db.query(m).all()] for m in (FlightRequirementLapse, FlightRequirementExcusal)]
    assert moved == [[target_id], [target_id]]


def test_merge_keeps_target_lapse_on_same_day(client, db, admin_headers):
    source, target, req = _merge_pair(db)
    day = date(2026, 3, 1)
    db.add(FlightRequirementLapse(requirement_id=req.id, pilot_id=source.id, lapsed_on=day))
    db.add(FlightRequirementLapse(requirement_id=req.id, pilot_id=target.id, lapsed_on=day,
                                  recovered_on=date(2026, 3, 9)))
    db.add(FlightRequirementLapse(requirement_id=req.id, pilot_id=source.id, lapsed_on=date(2026, 5, 1)))
    db.commit()
    target_id = _merge(client, admin_headers, source, target)
    db.expire_all()
    rows = db.query(FlightRequirementLapse).order_by(FlightRequirementLapse.lapsed_on).all()
    assert [(r.pilot_id, r.lapsed_on, r.recovered_on) for r in rows] == [
        (target_id, day, date(2026, 3, 9)), (target_id, date(2026, 5, 1), None)]


def test_merge_keeps_target_excusal(client, db, admin_headers):
    source, target, req = _merge_pair(db)
    db.add(FlightRequirementExcusal(requirement_id=req.id, pilot_id=source.id, excused_until=date(2026, 6, 1)))
    db.add(FlightRequirementExcusal(requirement_id=req.id, pilot_id=target.id, excused_until=date(2026, 4, 1)))
    db.commit()
    target_id = _merge(client, admin_headers, source, target)
    db.expire_all()
    rows = db.query(FlightRequirementExcusal).all()
    assert [(r.pilot_id, r.excused_until) for r in rows] == [(target_id, date(2026, 4, 1))]


def test_lapse_unique_per_requirement_pilot_and_day(db):
    pilot, req = _seed(db)
    db.add(FlightRequirementLapse(requirement_id=req.id, pilot_id=pilot.id, lapsed_on=date(2026, 3, 1)))
    with pytest.raises(Exception, match="UNIQUE"):
        db.commit()
    db.rollback()


def test_excusal_unique_per_requirement_and_pilot(db):
    pilot, req = _seed(db)
    db.add(FlightRequirementExcusal(requirement_id=req.id, pilot_id=pilot.id, excused_until=date(2026, 9, 1)))
    with pytest.raises(Exception, match="UNIQUE"):
        db.commit()
    db.rollback()


def test_lapse_stamps_are_set(db):
    _seed(db)
    lapse = db.query(FlightRequirementLapse).one()
    assert all(isinstance(v, datetime) for v in (lapse.created_at, lapse.updated_at))
