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
        # Phone type for pilots
        ("pilots", "phone_type", "ALTER TABLE pilots ADD COLUMN phone_type VARCHAR(20)"),
        # Flight sensor/attachment fields
        ("flights", "sensor_package", "ALTER TABLE flights ADD COLUMN sensor_package VARCHAR(100)"),
        ("flights", "attachment_top", "ALTER TABLE flights ADD COLUMN attachment_top VARCHAR(100)"),
        ("flights", "attachment_bottom", "ALTER TABLE flights ADD COLUMN attachment_bottom VARCHAR(100)"),
        ("flights", "attachment_left", "ALTER TABLE flights ADD COLUMN attachment_left VARCHAR(100)"),
        ("flights", "attachment_right", "ALTER TABLE flights ADD COLUMN attachment_right VARCHAR(100)"),
        ("flights", "carrier", "ALTER TABLE flights ADD COLUMN carrier VARCHAR(200)"),
        # Nicknames for batteries and controllers
        ("batteries", "nickname", "ALTER TABLE batteries ADD COLUMN nickname VARCHAR(100)"),
        ("controllers", "nickname", "ALTER TABLE controllers ADD COLUMN nickname VARCHAR(100)"),
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
