"""rolling requirements

Adds flight_requirement_lapses (each lapse of a pilot on a rolling requirement,
with the day it started and, once current again, the day it ended) and
flight_requirement_excusals (a pilot excused from a rolling requirement until a
date). Drops the currency tables, currency_rule_models and currency_rules, with
their rows: currency is replaced by flight requirements. A restore of an older
backup that still holds them skips them.

Also adds users.dashboard_layout and users.analytics_layout (each user's own
arrangement, NULL = the default) and vehicles.hourly_operating_cost (NULL = not
set).

The downgrade recreates the currency tables empty; the dropped rows do not come
back. It drops the new tables and columns with their data.

Revision ID: 0018_rolling_requirements
Revises: 0017_flight_requirements
Create Date: 2026-11-20 12:00:00.000000

"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0018_rolling_requirements'
down_revision: str | None = '0017_flight_requirements'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KEEP_AUTOINCREMENT = {'sqlite_autoincrement': True}


def upgrade() -> None:
    op.create_table('flight_requirement_lapses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('requirement_id', sa.Integer(), nullable=False),
    sa.Column('pilot_id', sa.Integer(), nullable=False),
    sa.Column('lapsed_on', sa.Date(), nullable=False),
    sa.Column('recovered_on', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['pilot_id'], ['pilots.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requirement_id'], ['flight_requirements.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('requirement_id', 'pilot_id', 'lapsed_on'),
    sqlite_autoincrement=True,
    )
    op.create_index(op.f('ix_flight_requirement_lapses_pilot_id'), 'flight_requirement_lapses', ['pilot_id'], unique=False)
    op.create_index(op.f('ix_flight_requirement_lapses_requirement_id'), 'flight_requirement_lapses', ['requirement_id'], unique=False)
    op.create_table('flight_requirement_excusals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('requirement_id', sa.Integer(), nullable=False),
    sa.Column('pilot_id', sa.Integer(), nullable=False),
    sa.Column('excused_until', sa.Date(), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.Column('excused_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['excused_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['pilot_id'], ['pilots.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requirement_id'], ['flight_requirements.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('requirement_id', 'pilot_id'),
    sqlite_autoincrement=True,
    )
    op.create_index(op.f('ix_flight_requirement_excusals_pilot_id'), 'flight_requirement_excusals', ['pilot_id'], unique=False)
    op.create_index(op.f('ix_flight_requirement_excusals_requirement_id'), 'flight_requirement_excusals', ['requirement_id'], unique=False)

    op.drop_index(op.f('ix_currency_rule_models_rule_id'), table_name='currency_rule_models')
    op.drop_table('currency_rule_models')
    op.drop_table('currency_rules')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dashboard_layout', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('analytics_layout', sa.JSON(), nullable=True))
    with op.batch_alter_table('vehicles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hourly_operating_cost', sa.Float(), nullable=True))


def downgrade() -> None:
    # Dropping a column rebuilds the table; keep its AUTOINCREMENT (0014).
    with op.batch_alter_table('vehicles', schema=None, table_kwargs=KEEP_AUTOINCREMENT) as batch_op:
        batch_op.drop_column('hourly_operating_cost')
    with op.batch_alter_table('users', schema=None, table_kwargs=KEEP_AUTOINCREMENT) as batch_op:
        batch_op.drop_column('analytics_layout')
        batch_op.drop_column('dashboard_layout')

    op.create_table('currency_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('vehicle_model', sa.String(length=200), nullable=True),
    sa.Column('required_hours', sa.Float(), nullable=False),
    sa.Column('period_days', sa.Integer(), nullable=False),
    sa.Column('required_flights', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sqlite_autoincrement=True,
    )
    op.create_table('currency_rule_models',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rule_id', sa.Integer(), nullable=False),
    sa.Column('model', sa.String(length=200), nullable=False),
    sa.ForeignKeyConstraint(['rule_id'], ['currency_rules.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('rule_id', 'model'),
    sqlite_autoincrement=True,
    )
    op.create_index(op.f('ix_currency_rule_models_rule_id'), 'currency_rule_models', ['rule_id'], unique=False)

    op.drop_index(op.f('ix_flight_requirement_excusals_requirement_id'), table_name='flight_requirement_excusals')
    op.drop_index(op.f('ix_flight_requirement_excusals_pilot_id'), table_name='flight_requirement_excusals')
    op.drop_table('flight_requirement_excusals')
    op.drop_index(op.f('ix_flight_requirement_lapses_requirement_id'), table_name='flight_requirement_lapses')
    op.drop_index(op.f('ix_flight_requirement_lapses_pilot_id'), table_name='flight_requirement_lapses')
    op.drop_table('flight_requirement_lapses')
