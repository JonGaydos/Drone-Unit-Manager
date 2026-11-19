"""Currency rule models: migration 0016, cascade and backups."""

import json
import zipfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

import app.config
from app.models.currency_rule import CurrencyRule, CurrencyRuleModel
from app.routers.backup import DATABASE_FILE, build_backup_archive
from tests.test_permissions_backup import _archive, _restore

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
BEFORE = "0015_drop_geofences"
AFTER = "0016_currency_rule_models"


def _config(url):
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _rule_row(rule_id, vehicle_model):
    return {"id": rule_id, "name": f"Rule {rule_id}", "vehicle_model": vehicle_model,
            "required_hours": 1.0, "period_days": 90, "is_active": True}


def _upgraded_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setattr(app.config.settings, "DATABASE_URL", url)
    cfg = _config(url)
    command.upgrade(cfg, BEFORE)
    engine = create_engine(url)
    with engine.begin() as conn:
        for rid, vm in [(1, "X10"), (2, " X2E "), (3, ""), (4, None)]:
            conn.exec_driver_sql(
                "INSERT INTO currency_rules (id, name, vehicle_model, required_hours, period_days, is_active, created_at)"
                " VALUES (?, ?, ?, 1, 90, 1, '2026-01-01 00:00:00')", (rid, f"Rule {rid}", vm))
    command.upgrade(cfg, AFTER)
    return cfg, engine


def test_migration_copies_vehicle_model(tmp_path, monkeypatch):
    _, engine = _upgraded_db(tmp_path, monkeypatch)
    try:
        with engine.connect() as conn:
            rows = conn.exec_driver_sql(
                "SELECT rule_id, model FROM currency_rule_models ORDER BY rule_id").all()
    finally:
        engine.dispose()
    assert rows == [(1, "X10"), (2, "X2E")]


def test_migration_downgrade_restores_first_model(tmp_path, monkeypatch):
    cfg, engine = _upgraded_db(tmp_path, monkeypatch)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("DELETE FROM currency_rule_models WHERE rule_id = 1")
            conn.exec_driver_sql("INSERT INTO currency_rule_models (rule_id, model) VALUES (2, 'LEMUR 2')")
        command.downgrade(cfg, BEFORE)
        with engine.connect() as conn:
            rows = conn.exec_driver_sql("SELECT id, vehicle_model FROM currency_rules ORDER BY id").all()
    finally:
        engine.dispose()
    assert rows == [(1, None), (2, "LEMUR 2"), (3, None), (4, None)]


def test_delete_rule_deletes_models(db):
    rule = CurrencyRule(name="R", required_hours=1, period_days=30,
                        models=[CurrencyRuleModel(model="Beta"), CurrencyRuleModel(model="alpha")])
    db.add(rule)
    db.commit()
    assert rule.model_names == ["alpha", "Beta"]
    db.delete(rule)
    db.commit()
    assert db.query(CurrencyRuleModel).count() == 0


def test_backup_includes_rule_models(db):
    db.add(CurrencyRule(name="R", required_hours=1, period_days=30, models=[CurrencyRuleModel(model="X10")]))
    db.commit()
    _spooled, manifest = build_backup_archive(db, include_telemetry=False)
    assert manifest["tables"]["currency_rule_models"] == 1


def test_restore_pre_0016_backup_backfills(client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    def edit(tables):
        tables["currency_rules"] = [_rule_row(1, "X10")]
        tables.pop("currency_rule_models", None)

    _restore(client, admin_headers, _archive(db, edit), tmp_path, monkeypatch)

    db.expire_all()
    assert [(m.rule_id, m.model) for m in db.query(CurrencyRuleModel).all()] == [(1, "X10")]


def test_restore_new_backup_keeps_all_aircraft(client, db, admin_user, admin_headers, tmp_path, monkeypatch):
    def edit(tables):
        tables["currency_rules"] = [_rule_row(1, "X10")]
        tables["currency_rule_models"] = []

    _restore(client, admin_headers, _archive(db, edit), tmp_path, monkeypatch)

    db.expire_all()
    assert db.query(CurrencyRuleModel).count() == 0
    assert db.query(CurrencyRule).count() == 1
