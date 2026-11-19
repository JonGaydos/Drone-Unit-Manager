"""Flight requirement tables: migration 0017, cascade, backups and settings keys."""

from datetime import date, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

import app.config
from app.models.flight_requirement import (
    FlightRequirement, FlightRequirementModel, FlightRequirementNotice, FlightRequirementPilot,
    FlightRequirementPurpose, FlightRequirementResult, FlightRequirementTemplate,
)
from app.models.pilot import Pilot
from app.routers.backup import build_backup_archive

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
BEFORE = "0016_currency_rule_models"
AFTER = "0017_flight_requirements"
TABLES = [
    "flight_requirements", "flight_requirement_models", "flight_requirement_pilots",
    "flight_requirement_purposes", "flight_requirement_results", "flight_requirement_templates",
    "flight_requirement_notices",
]
SETTINGS_KEYS = ["requirements_grace_days", "fiscal_year_start_month"]


def _config(url):
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _requirement(**extra):
    return FlightRequirement(name="R", period_type="calendar_month", start_date=date(2026, 1, 1),
                             recurring=True, model_mode="all", time_mode="any", **extra)


def test_migration_upgrades_and_downgrades(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setattr(app.config.settings, "DATABASE_URL", url)
    cfg = _config(url)
    command.upgrade(cfg, BEFORE)
    engine = create_engine(url)
    try:
        assert not set(TABLES) & set(inspect(engine).get_table_names())
        command.upgrade(cfg, AFTER)
        assert set(TABLES) <= set(inspect(engine).get_table_names())
        command.downgrade(cfg, BEFORE)
        assert not set(TABLES) & set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_delete_requirement_deletes_children_and_results(db):
    pilot = Pilot(first_name="Ann", last_name="Lee")
    db.add(pilot)
    db.commit()
    req = _requirement(
        models=[FlightRequirementModel(model="X10")],
        pilots=[FlightRequirementPilot(pilot_id=pilot.id)],
        purposes=[FlightRequirementPurpose(purpose="Training")])
    db.add(req)
    db.commit()
    db.add(FlightRequirementResult(requirement_id=req.id, pilot_id=pilot.id,
                                   period_start=date(2026, 1, 1), period_end=date(2026, 1, 31)))
    db.add(FlightRequirementNotice(requirement_id=req.id, pilot_id=pilot.id, period_start=date(2026, 1, 1),
                                   kind="assigned", sent_at=datetime(2026, 1, 2)))
    db.commit()
    db.delete(req)
    db.commit()
    for model in (FlightRequirementModel, FlightRequirementPilot, FlightRequirementPurpose,
                  FlightRequirementResult):
        assert db.query(model).count() == 0, model.__name__


def test_backup_includes_requirement_tables(db):
    pilot = Pilot(first_name="Ann", last_name="Lee")
    db.add(pilot)
    db.commit()
    req = _requirement(models=[FlightRequirementModel(model="X10")],
                       pilots=[FlightRequirementPilot(pilot_id=pilot.id)],
                       purposes=[FlightRequirementPurpose(purpose="Training")])
    db.add(req)
    db.add(FlightRequirementTemplate(name="T", settings={}))
    db.commit()
    db.add(FlightRequirementResult(requirement_id=req.id, pilot_id=pilot.id,
                                   period_start=date(2026, 1, 1), period_end=date(2026, 1, 31)))
    db.add(FlightRequirementNotice(requirement_id=req.id, pilot_id=pilot.id, period_start=date(2026, 1, 1),
                                   kind="assigned", sent_at=datetime(2026, 1, 2)))
    db.commit()
    _spooled, manifest = build_backup_archive(db, include_telemetry=False)
    assert {t: manifest["tables"][t] for t in TABLES} == dict.fromkeys(TABLES, 1)


@pytest.mark.parametrize("key,value", [("requirements_grace_days", "14"), ("fiscal_year_start_month", "10")])
def test_settings_keys_admin_writes_pilot_reads(client, admin_headers, pilot_headers, key, value):
    assert client.put("/api/settings", headers=admin_headers, json={"key": key, "value": value}).status_code == 200
    resp = client.get(f"/api/settings/{key}", headers=pilot_headers)
    assert resp.status_code == 200
    assert resp.json()["value"] == value
