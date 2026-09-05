"""Schema-parity and import smoke tests.

Verifies that the application's hand-maintained Alembic migrations stay in sync
with the SQLAlchemy models, so a freshly migrated database matches what
``Base.metadata.create_all`` would build. A drift here (a table or column that
exists in one but not the other) means production deployments, which run
``alembic upgrade head`` on startup, would diverge from the ORM the code uses.

How Alembic is pointed at a throwaway DB
----------------------------------------
``migrations/env.py`` resolves the database URL from
``app.config.settings.DATABASE_URL`` (it calls
``config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)``, overriding
whatever ``alembic.ini`` holds). So these tests monkeypatch
``settings.DATABASE_URL`` to a temp SQLite file before invoking
``alembic.command.upgrade``; nothing touches the real ``backend/data`` DBs.

Scope
-----
Alembic migrates only the PRIMARY database (``Base.metadata``). The telemetry
database (``TelemetryBase`` / ``telemetry_points``) has its own engine and is
created via ``create_all`` at startup, not by Alembic, so it is intentionally
out of scope for the migration-parity comparison.

What is compared
----------------
Table names (excluding Alembic's bookkeeping ``alembic_version`` table), and for
each shared table the column names and nullability. Column TYPE affinity is
compared leniently (reflected SQLite type string) and reported as informational
on mismatch rather than failing the test, because SQLite renders several
SQLAlchemy types (Date, DateTime, JSON, Boolean) down to the same affinities and
a strict type assert would be brittle without indicating real drift.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

import app.config
from app.database import Base
import app.models  # noqa: F401 - register all ORM models on Base.metadata

# Absolute path to the migrations directory, so Alembic resolves its scripts
# regardless of the test process's current working directory.
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _alembic_config(db_url):
    """Build an Alembic Config targeting the migrations dir and the given URL.

    The ``sqlalchemy.url`` set here is informational only: ``env.py`` re-reads
    the URL from ``settings.DATABASE_URL`` at run time, so callers must also
    monkeypatch that. Both are set for clarity and belt-and-suspenders.
    """
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _columns(engine):
    """Return ``{table: {column: (nullable, type_str)}}`` for a reflected DB.

    Excludes Alembic's ``alembic_version`` bookkeeping table.
    """
    inspector = inspect(engine)
    result = {}
    for table in inspector.get_table_names():
        if table == "alembic_version":
            continue
        result[table] = {
            col["name"]: (col["nullable"], str(col["type"]))
            for col in inspector.get_columns(table)
        }
    return result


def test_alembic_head_matches_create_all(tmp_path, monkeypatch):
    """``alembic upgrade head`` builds the same schema as ``create_all``."""
    # Schema A: fresh temp DB built by running migrations to head. env.py reads
    # the URL from settings.DATABASE_URL, so patch that to the temp file.
    alembic_db = tmp_path / "alembic.db"
    alembic_url = f"sqlite:///{alembic_db}"
    monkeypatch.setattr(app.config.settings, "DATABASE_URL", alembic_url)
    command.upgrade(_alembic_config(alembic_url), "head")

    # Schema B: a second fresh temp DB built directly from the ORM metadata.
    create_all_db = tmp_path / "create_all.db"
    create_all_engine = create_engine(f"sqlite:///{create_all_db}")
    Base.metadata.create_all(bind=create_all_engine)

    alembic_engine = create_engine(alembic_url)
    try:
        alembic_schema = _columns(alembic_engine)
        create_all_schema = _columns(create_all_engine)
    finally:
        alembic_engine.dispose()
        create_all_engine.dispose()

    # 1. Same set of tables.
    alembic_tables = set(alembic_schema)
    create_all_tables = set(create_all_schema)
    only_in_alembic = alembic_tables - create_all_tables
    only_in_create_all = create_all_tables - alembic_tables
    assert not only_in_alembic, (
        "Table drift: present in alembic head but not create_all: "
        f"{sorted(only_in_alembic)}"
    )
    assert not only_in_create_all, (
        "Table drift: present in create_all but not alembic head: "
        f"{sorted(only_in_create_all)}"
    )

    # 2. Same column names + nullability per shared table.
    column_diffs = []
    for table in sorted(alembic_tables & create_all_tables):
        a_cols = alembic_schema[table]
        b_cols = create_all_schema[table]
        only_in_a = set(a_cols) - set(b_cols)
        only_in_b = set(b_cols) - set(a_cols)
        if only_in_a or only_in_b:
            column_diffs.append(
                f"  {table}: only in alembic={sorted(only_in_a)}, "
                f"only in create_all={sorted(only_in_b)}"
            )
            continue
        for col in sorted(a_cols):
            a_nullable = a_cols[col][0]
            b_nullable = b_cols[col][0]
            if a_nullable != b_nullable:
                column_diffs.append(
                    f"  {table}.{col}: nullable alembic={a_nullable}, "
                    f"create_all={b_nullable}"
                )
    assert not column_diffs, "Column drift between alembic head and create_all:\n" + "\n".join(
        column_diffs
    )


def test_app_main_imports():
    """Importing the app module succeeds and exposes the FastAPI ``app``."""
    import app.main

    assert app.main.app is not None


def test_alembic_upgrade_head_is_idempotent(tmp_path, monkeypatch):
    """Re-running ``upgrade head`` on a migrated DB is a no-op at head."""
    db_path = tmp_path / "idempotent.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setattr(app.config.settings, "DATABASE_URL", db_url)
    cfg = _alembic_config(db_url)

    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            first = conn.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar()
    finally:
        engine.dispose()

    # Second run must not raise and must leave the revision unchanged.
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            second = conn.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar()
    finally:
        engine.dispose()

    assert first == second
    assert second is not None
