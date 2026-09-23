"""local flight dates

Flights synced or imported with a UTC takeoff were dated by the UTC day, so an
evening flight in the Americas landed on the next day's date. This redates
them to the local day of takeoff, in the configured display timezone.

Only rows that still carry the UTC day are changed, so a date someone corrected
by hand is left alone. Manual entries (the user typed the date), Parrot logs
(stored in local wall-clock time) and spreadsheet imports (timezone not known)
are not touched. The number of rows changed is logged.

Not reversible: the downgrade leaves dates as they are.

Revision ID: 0008_local_flight_dates
Revises: 0007_evidence_soft_delete
Create Date: 2026-09-22 23:40:00.000000

"""
import logging
import os
from datetime import datetime, timezone
from typing import Sequence, Union
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008_local_flight_dates'
down_revision: Union[str, None] = '0007_evidence_soft_delete'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger(__name__)

# Data sources whose takeoff_time is stored as naive UTC.
UTC_SOURCES = ('skydio_api', 'brinc_csv', 'dji_log', 'airdata_json', 'airdata_csv', 'litchi_csv', 'csv_import')
DEFAULT_TIMEZONE = 'America/Chicago'


def _zone(bind) -> ZoneInfo:
    name = bind.execute(sa.text("SELECT value FROM settings WHERE key = 'display_timezone'")).scalar()
    try:
        return ZoneInfo(name or os.environ.get('TZ') or DEFAULT_TIMEZONE)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _redated(rows, zone) -> list[tuple[int, str]]:
    """(id, local date) for each row still dated by its UTC day."""
    changes = []
    for flight_id, flight_date, takeoff in rows:
        takeoff = datetime.fromisoformat(str(takeoff))
        utc_day = takeoff.date()
        local_day = takeoff.replace(tzinfo=timezone.utc).astimezone(zone).date()
        if local_day != utc_day and str(flight_date) == utc_day.isoformat():
            changes.append((flight_id, local_day.isoformat()))
    return changes


def upgrade() -> None:
    bind = op.get_bind()
    zone = _zone(bind)
    rows = bind.execute(
        sa.text("SELECT id, date, takeoff_time FROM flights "
                "WHERE takeoff_time IS NOT NULL AND data_source IN :sources")
        .bindparams(sa.bindparam('sources', expanding=True)),
        {'sources': list(UTC_SOURCES)},
    ).fetchall()
    changes = _redated(rows, zone)
    logger.info("Redating %d of %d flights to the local day of takeoff (%s)", len(changes), len(rows), zone.key)
    for flight_id, local_day in changes:
        bind.execute(sa.text("UPDATE flights SET date = :d WHERE id = :id"), {'d': local_day, 'id': flight_id})


def downgrade() -> None:
    # The UTC dates are recomputable from takeoff_time, but a downgrade has no
    # way to tell a redated row from one that was correct all along.
    pass
