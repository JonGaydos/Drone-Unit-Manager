"""flight requirements

Adds the flight requirement tables: requirements, their models, pilots and
purposes, saved period results, templates and sent notices. No data is copied.

Revision ID: 0017_flight_requirements
Revises: 0016_currency_rule_models
Create Date: 2026-11-19 18:00:00.000000

"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0017_flight_requirements'
down_revision: str | None = '0016_currency_rule_models'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('flight_requirements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.String(length=1000), nullable=True),
    sa.Column('period_type', sa.String(length=30), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('recurring', sa.Boolean(), nullable=False),
    sa.Column('window_start_day', sa.Integer(), nullable=True),
    sa.Column('window_end_day', sa.Integer(), nullable=True),
    sa.Column('span_length', sa.Integer(), nullable=True),
    sa.Column('span_unit', sa.String(length=10), nullable=True),
    sa.Column('every_months', sa.Integer(), nullable=True),
    sa.Column('target_minutes', sa.Integer(), nullable=True),
    sa.Column('target_flights', sa.Integer(), nullable=True),
    sa.Column('model_mode', sa.String(length=20), nullable=False),
    sa.Column('time_mode', sa.String(length=10), nullable=False),
    sa.Column('window_start_time', sa.Time(), nullable=True),
    sa.Column('window_end_time', sa.Time(), nullable=True),
    sa.Column('reminder_days', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('active_changed_at', sa.DateTime(), nullable=True),
    sa.Column('closed_through', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('modified_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['modified_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sqlite_autoincrement=True,
    )
    op.create_table('flight_requirement_templates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('settings', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('modified_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['modified_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name'),
    sqlite_autoincrement=True,
    )
    op.create_table('flight_requirement_models',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('requirement_id', sa.Integer(), nullable=False),
    sa.Column('model', sa.String(length=200), nullable=False),
    sa.ForeignKeyConstraint(['requirement_id'], ['flight_requirements.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('requirement_id', 'model'),
    sqlite_autoincrement=True,
    )
    op.create_index(op.f('ix_flight_requirement_models_requirement_id'), 'flight_requirement_models', ['requirement_id'], unique=False)
    op.create_table('flight_requirement_purposes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('requirement_id', sa.Integer(), nullable=False),
    sa.Column('purpose', sa.String(length=100), nullable=False),
    sa.ForeignKeyConstraint(['requirement_id'], ['flight_requirements.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('requirement_id', 'purpose'),
    sqlite_autoincrement=True,
    )
    op.create_index(op.f('ix_flight_requirement_purposes_requirement_id'), 'flight_requirement_purposes', ['requirement_id'], unique=False)
    op.create_table('flight_requirement_pilots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('requirement_id', sa.Integer(), nullable=False),
    sa.Column('pilot_id', sa.Integer(), nullable=False),
    sa.Column('added_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['pilot_id'], ['pilots.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requirement_id'], ['flight_requirements.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('requirement_id', 'pilot_id'),
    sqlite_autoincrement=True,
    )
    op.create_index(op.f('ix_flight_requirement_pilots_pilot_id'), 'flight_requirement_pilots', ['pilot_id'], unique=False)
    op.create_index(op.f('ix_flight_requirement_pilots_requirement_id'), 'flight_requirement_pilots', ['requirement_id'], unique=False)
    op.create_table('flight_requirement_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('requirement_id', sa.Integer(), nullable=False),
    sa.Column('pilot_id', sa.Integer(), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('period_end', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('totals', sa.JSON(), nullable=True),
    sa.Column('target_snapshot', sa.JSON(), nullable=True),
    sa.Column('excused', sa.Boolean(), nullable=True),
    sa.Column('excused_by_id', sa.Integer(), nullable=True),
    sa.Column('excused_reason', sa.String(length=500), nullable=True),
    sa.Column('saved_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['excused_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['pilot_id'], ['pilots.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requirement_id'], ['flight_requirements.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('requirement_id', 'pilot_id', 'period_start'),
    sqlite_autoincrement=True,
    )
    op.create_index(op.f('ix_flight_requirement_results_pilot_id'), 'flight_requirement_results', ['pilot_id'], unique=False)
    op.create_index(op.f('ix_flight_requirement_results_requirement_id'), 'flight_requirement_results', ['requirement_id'], unique=False)
    op.create_table('flight_requirement_notices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('requirement_id', sa.Integer(), nullable=False),
    sa.Column('pilot_id', sa.Integer(), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('sent_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['pilot_id'], ['pilots.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requirement_id'], ['flight_requirements.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('requirement_id', 'pilot_id', 'period_start', 'kind'),
    sqlite_autoincrement=True,
    )
    op.create_index(op.f('ix_flight_requirement_notices_pilot_id'), 'flight_requirement_notices', ['pilot_id'], unique=False)
    op.create_index(op.f('ix_flight_requirement_notices_requirement_id'), 'flight_requirement_notices', ['requirement_id'], unique=False)


def downgrade() -> None:
    op.drop_table('flight_requirement_notices')
    op.drop_table('flight_requirement_results')
    op.drop_table('flight_requirement_pilots')
    op.drop_table('flight_requirement_purposes')
    op.drop_table('flight_requirement_models')
    op.drop_table('flight_requirement_templates')
    op.drop_table('flight_requirements')
