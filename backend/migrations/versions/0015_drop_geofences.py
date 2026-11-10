"""drop geofences

The geofence feature is removed: it had an API but no screen to manage zones,
so the table is dropped with its rows. A restore of an older backup that still
holds a geofences table skips it.

The downgrade recreates the empty table; the dropped rows do not come back.

Revision ID: 0015_drop_geofences
Revises: 0014_autoincrement_ids
Create Date: 2026-11-09 12:00:00.000000

"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0015_drop_geofences'
down_revision: str | None = '0014_autoincrement_ids'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table('geofences')


def downgrade() -> None:
    op.create_table('geofences',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('zone_type', sa.String(length=50), nullable=False),
    sa.Column('geometry_type', sa.String(length=20), nullable=False),
    sa.Column('center_lat', sa.Float(), nullable=True),
    sa.Column('center_lon', sa.Float(), nullable=True),
    sa.Column('radius_m', sa.Float(), nullable=True),
    sa.Column('polygon_points', sa.JSON(), nullable=True),
    sa.Column('max_altitude_m', sa.Float(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('source', sa.String(length=50), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sqlite_autoincrement=True,
    )
