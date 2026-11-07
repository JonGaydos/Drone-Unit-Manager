"""clean flight battery serials

Skydio reports a battery serial with a leading dash (for example
"-k01-231117-1-00061") while battery records hold it without one, and the
per-flight refresh stored the raw form. Battery stats match flights on the
exact serial, so those flights were not counted. This strips the leading
dashes from flights.battery_serial, as ingestion now does; a value that was
only dashes becomes empty. The number of rows changed is logged.

Not reversible: the downgrade leaves serials as they are.

Revision ID: 0013_clean_flight_battery_serials
Revises: 0012_audit_identity
Create Date: 2026-11-05 12:00:00.000000

"""
import logging
from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0013_clean_flight_battery_serials'
down_revision: str | None = '0012_audit_identity'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    result = op.get_bind().execute(sa.text(
        "UPDATE flights SET battery_serial = NULLIF(LTRIM(battery_serial, '-'), '') "
        "WHERE battery_serial LIKE '-%'"))
    logger.info("Removed the leading dash from %d flight battery serials", result.rowcount)


def downgrade() -> None:
    # The dash was a provider artifact, so there is nothing to put back.
    pass
