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
        ("pilots", "phone_work", "ALTER TABLE pilots ADD COLUMN phone_work VARCHAR(50)"),
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
        # Folder support for documents
        ("documents", "folder_id", "ALTER TABLE documents ADD COLUMN folder_id INTEGER REFERENCES folders(id)"),
        # Audit trail: created_by_id and modified_by_id
        ("flights", "created_by_id", "ALTER TABLE flights ADD COLUMN created_by_id INTEGER REFERENCES users(id)"),
        ("flights", "modified_by_id", "ALTER TABLE flights ADD COLUMN modified_by_id INTEGER REFERENCES users(id)"),
        ("pilots", "created_by_id", "ALTER TABLE pilots ADD COLUMN created_by_id INTEGER REFERENCES users(id)"),
        ("pilots", "modified_by_id", "ALTER TABLE pilots ADD COLUMN modified_by_id INTEGER REFERENCES users(id)"),
        ("vehicles", "created_by_id", "ALTER TABLE vehicles ADD COLUMN created_by_id INTEGER REFERENCES users(id)"),
        ("vehicles", "modified_by_id", "ALTER TABLE vehicles ADD COLUMN modified_by_id INTEGER REFERENCES users(id)"),
        ("maintenance_records", "created_by_id", "ALTER TABLE maintenance_records ADD COLUMN created_by_id INTEGER REFERENCES users(id)"),
        ("maintenance_records", "modified_by_id", "ALTER TABLE maintenance_records ADD COLUMN modified_by_id INTEGER REFERENCES users(id)"),
        ("mission_logs", "created_by_id", "ALTER TABLE mission_logs ADD COLUMN created_by_id INTEGER REFERENCES users(id)"),
        ("mission_logs", "modified_by_id", "ALTER TABLE mission_logs ADD COLUMN modified_by_id INTEGER REFERENCES users(id)"),
        ("training_logs", "created_by_id", "ALTER TABLE training_logs ADD COLUMN created_by_id INTEGER REFERENCES users(id)"),
        ("training_logs", "modified_by_id", "ALTER TABLE training_logs ADD COLUMN modified_by_id INTEGER REFERENCES users(id)"),
        # Incident -> Activity Reports: report_type, impact_level, outcome_description
        ("incidents", "report_type", "ALTER TABLE incidents ADD COLUMN report_type VARCHAR(30) DEFAULT 'incident'"),
        ("incidents", "impact_level", "ALTER TABLE incidents ADD COLUMN impact_level VARCHAR(50)"),
        ("incidents", "outcome_description", "ALTER TABLE incidents ADD COLUMN outcome_description TEXT"),
        # Cost tracking fields
        ("flights", "operating_cost", "ALTER TABLE flights ADD COLUMN operating_cost REAL"),
        ("mission_logs", "total_cost", "ALTER TABLE mission_logs ADD COLUMN total_cost REAL"),
        ("mission_logs", "cost_breakdown", "ALTER TABLE mission_logs ADD COLUMN cost_breakdown TEXT"),
        ("training_logs", "total_cost", "ALTER TABLE training_logs ADD COLUMN total_cost REAL"),
        # Telemetry sync tracking
        ("flights", "telemetry_synced", "ALTER TABLE flights ADD COLUMN telemetry_synced BOOLEAN DEFAULT 0"),
        # Phase 0C: data_source for flights
        ("flights", "data_source", "ALTER TABLE flights ADD COLUMN data_source VARCHAR(30)"),
        # Phase 0 additional: flight tags
        ("flights", "tags", "ALTER TABLE flights ADD COLUMN tags TEXT"),
        # Email field for users (notification digest)
        ("users", "email", "ALTER TABLE users ADD COLUMN email VARCHAR(255)"),
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

        # Phase 0A: Rename skydio_vehicle_serial -> provider_serial
        if "vehicles" in inspector.get_table_names():
            existing = [c["name"] for c in inspector.get_columns("vehicles")]
            if "skydio_vehicle_serial" in existing and "provider_serial" not in existing:
                try:
                    conn.execute(text("ALTER TABLE vehicles RENAME COLUMN skydio_vehicle_serial TO provider_serial"))
                    conn.commit()
                    logger.info("Migration: Renamed vehicles.skydio_vehicle_serial to provider_serial")
                except Exception as e:
                    logger.warning("Rename column failed, trying fallback: %s", e)
                    conn.rollback()
                    try:
                        conn.execute(text("ALTER TABLE vehicles ADD COLUMN provider_serial VARCHAR(100)"))
                        conn.execute(text("UPDATE vehicles SET provider_serial = skydio_vehicle_serial"))
                        conn.commit()
                        logger.info("Migration: Added vehicles.provider_serial (fallback)")
                    except Exception as e2:
                        logger.warning("Fallback migration for provider_serial failed: %s", e2)
                        conn.rollback()

    # Telemetry DB migrations (separate database)
    from app.database import telemetry_engine
    telemetry_inspector = inspect(telemetry_engine)
    telemetry_migrations = [
        ("telemetry_points", "extra_data", "ALTER TABLE telemetry_points ADD COLUMN extra_data TEXT"),
        ("telemetry_points", "source", "ALTER TABLE telemetry_points ADD COLUMN source VARCHAR(30)"),
    ]
    with telemetry_engine.connect() as conn:
        for table, column, sql in telemetry_migrations:
            if table in telemetry_inspector.get_table_names():
                existing = [c["name"] for c in telemetry_inspector.get_columns(table)]
                if column not in existing:
                    try:
                        conn.execute(text(sql))
                        conn.commit()
                        logger.info("Telemetry migration: Added %s.%s", table, column)
                    except Exception as e:
                        logger.warning("Telemetry migration %s.%s failed: %s", table, column, e)
                        conn.rollback()
