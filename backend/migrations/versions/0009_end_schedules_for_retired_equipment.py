"""end schedules for retired equipment

Retiring or deleting equipment now deactivates its maintenance schedules.
Schedules on equipment retired, damaged or deleted before that change are
still active, so they show as overdue and count against compliance. This
deactivates them; the count is logged. Schedules on organization-wide tasks
are not tied to equipment and are untouched.

Not reversible: the downgrade cannot tell which schedules this switched off.

Revision ID: 0009_end_schedules_for_retired_equipment
Revises: 0008_local_flight_dates
Create Date: 2026-09-23 01:00:00.000000

"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009_end_schedules_for_retired_equipment'
down_revision: Union[str, None] = '0008_local_flight_dates'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger(__name__)

# Schedule entity_type -> equipment table.
EQUIPMENT_TABLES = {
    'vehicle': 'vehicles',
    'battery': 'batteries',
    'controller': 'controllers',
    'dock': 'docks',
    'sensor': 'sensor_packages',
    'attachment': 'attachments',
    'other': 'other_equipment',
}


def upgrade() -> None:
    bind = op.get_bind()
    ended = 0
    for entity_type, table in EQUIPMENT_TABLES.items():
        result = bind.execute(sa.text(
            f"UPDATE maintenance_schedules SET is_active = 0 "
            f"WHERE is_active = 1 AND entity_type = :entity_type AND entity_id IS NOT NULL "
            f"AND entity_id NOT IN (SELECT id FROM {table} WHERE status NOT IN ('retired', 'damaged'))"
        ), {'entity_type': entity_type})
        ended += result.rowcount or 0
    logger.info("Deactivated %d maintenance schedules on retired, damaged or deleted equipment", ended)


def downgrade() -> None:
    # Nothing to undo safely: the schedules this switched off cannot be told
    # apart from ones switched off by hand, so they stay inactive.
    pass
