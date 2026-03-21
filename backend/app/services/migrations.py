"""Startup migration script for adding new columns to existing tables."""
import logging
from sqlalchemy import text, inspect
from app.database import engine

logger = logging.getLogger(__name__)


def run_migrations():
    """Add new columns to existing tables if they don't exist."""
    inspector = inspect(engine)

    migrations = [
        # Phase 3: User-Pilot linking
        ("users", "pilot_id", "ALTER TABLE users ADD COLUMN pilot_id INTEGER REFERENCES pilots(id)"),
        # Phase 4: Photos
        ("pilots", "photo_url", "ALTER TABLE pilots ADD COLUMN photo_url VARCHAR(500)"),
        ("vehicles", "photo_url", "ALTER TABLE vehicles ADD COLUMN photo_url VARCHAR(500)"),
    ]

    with engine.connect() as conn:
        for table, column, sql in migrations:
            if table in inspector.get_table_names():
                existing = [c["name"] for c in inspector.get_columns(table)]
                if column not in existing:
                    try:
                        conn.execute(text(sql))
                        conn.commit()
                        logger.info("Migration: Added %s.%s", table, column)
                    except Exception as e:
                        logger.warning("Migration %s.%s failed: %s", table, column, e)
                        conn.rollback()
