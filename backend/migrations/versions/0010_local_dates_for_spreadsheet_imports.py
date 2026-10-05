"""local dates for spreadsheet imports

0008 left spreadsheet imports alone because their timezone was not known. It
is: they come from Skydio's flight-list export, whose "Takeoff" column is UTC,
and the importer stored that value as the takeoff and its UTC day as the date.
An evening flight in the Americas therefore sits on the next day's date. This
redates those flights to the local day of takeoff, in the configured display
timezone, by the same rule as 0008 (whose helpers it reuses): only a row still
carrying the UTC day is changed, so a date someone corrected by hand is left
alone. The number of rows changed is logged.

Not reversible: the downgrade leaves dates as they are.

Revision ID: 0010_local_dates_for_spreadsheet_imports
Revises: 0009_end_schedules_for_retired_equipment
Create Date: 2026-10-05 15:00:00.000000

"""
import importlib.util
import logging
from pathlib import Path
from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010_local_dates_for_spreadsheet_imports'
down_revision: str | None = '0009_end_schedules_for_retired_equipment'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

# The Skydio flight-list importers: the Excel workbook and the CSV export.
SPREADSHEET_SOURCES = ('excel_import', 'skydio_csv')


def _local_dates_migration():
    """0008, for its timezone lookup and redating rule."""
    path = Path(__file__).with_name('0008_local_flight_dates.py')
    spec = importlib.util.spec_from_file_location('_migration_0008', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade() -> None:
    m0008 = _local_dates_migration()
    bind = op.get_bind()
    zone = m0008._zone(bind)
    rows = bind.execute(
        sa.text("SELECT id, date, takeoff_time FROM flights "
                "WHERE takeoff_time IS NOT NULL AND data_source IN :sources")
        .bindparams(sa.bindparam('sources', expanding=True)),
        {'sources': list(SPREADSHEET_SOURCES)},
    ).fetchall()
    changes = m0008._redated(rows, zone)
    logger.info("Redating %d of %d spreadsheet-imported flights to the local day of takeoff (%s)",
                len(changes), len(rows), zone.key)
    for flight_id, local_day in changes:
        bind.execute(sa.text("UPDATE flights SET date = :d WHERE id = :id"), {'d': local_day, 'id': flight_id})


def downgrade() -> None:
    # The UTC dates are recomputable from takeoff_time, but a downgrade has no
    # way to tell a redated row from one that was correct all along.
    pass
