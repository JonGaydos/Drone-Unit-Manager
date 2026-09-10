"""Embedded Alembic migrations must not silence the app's logging.

The app runs migrations at startup via command.upgrade. Alembic's env.py calls
fileConfig(alembic.ini), which -- unless told not to -- disables every existing
logger and drops the root level to WARN, so anything logged after the migrations
(the fresh-install backup token banner, "startup complete", etc.) never reaches
docker logs. main.py sets configure_logging=False to prevent that; this pins it.
If the guard regresses (fileConfig runs again), app_logger.disabled flips True
and this test fails.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_embedded_migration_keeps_app_logging(tmp_path):
    ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(ini.parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'm.db'}")
    cfg.attributes["configure_logging"] = False   # what app.main.lifespan sets

    root = logging.getLogger()
    prior = root.level
    root.setLevel(logging.INFO)
    app_logger = logging.getLogger("app.routers.backup")
    try:
        command.upgrade(cfg, "head")
        # The app's loggers survive the migration, so post-migration INFO logs
        # (the install token banner) still emit.
        assert app_logger.disabled is False
        assert root.level == logging.INFO
    finally:
        root.setLevel(prior)
