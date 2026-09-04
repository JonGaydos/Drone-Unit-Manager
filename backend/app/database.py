"""SQLAlchemy database engine, session factories, and dependency providers.

Uses two separate SQLite databases: a primary DB for application data and
a dedicated telemetry DB for high-volume flight telemetry records.
Both are configured with WAL journal mode for concurrent read performance.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base class for all primary application ORM models."""
    pass


# Primary application database engine (SQLite, WAL mode)
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite with FastAPI threads
    echo=False,
)

# Separate engine for telemetry data to isolate high-write-volume tables
telemetry_engine = create_engine(
    settings.TELEMETRY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL journal mode and foreign key enforcement on each connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@event.listens_for(telemetry_engine, "connect")
def set_telemetry_pragma(dbapi_connection, connection_record):
    """Enable WAL journal mode and foreign key enforcement for the telemetry DB."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
TelemetrySessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=telemetry_engine)


def get_db():
    """FastAPI dependency that provides a primary database session.

    Yields:
        A SQLAlchemy Session that is automatically closed after the request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_telemetry_db():
    """FastAPI dependency that provides a telemetry database session.

    Yields:
        A SQLAlchemy Session bound to the telemetry database.
    """
    db = TelemetrySessionLocal()
    try:
        yield db
    finally:
        db.close()
