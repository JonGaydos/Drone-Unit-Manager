"""currency rule models

A currency rule can name several vehicle models, held in currency_rule_models.
Each rule's single vehicle_model is copied over as one row (trimmed, blanks
skipped). The vehicle_model column stays, unused, until a later release drops it.

The downgrade puts the first model (case-insensitive order) back in
vehicle_model; a rule with no models gets NULL (all aircraft). Extra models on
a multi-model rule are lost.

Revision ID: 0016_currency_rule_models
Revises: 0015_drop_geofences
Create Date: 2026-11-19 12:00:00.000000

"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0016_currency_rule_models'
down_revision: str | None = '0015_drop_geofences'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
    op.execute(
        "INSERT INTO currency_rule_models (rule_id, model) "
        "SELECT id, trim(vehicle_model) FROM currency_rules "
        "WHERE vehicle_model IS NOT NULL AND trim(vehicle_model) <> ''")


def downgrade() -> None:
    op.execute(
        "UPDATE currency_rules SET vehicle_model = ("
        "SELECT model FROM currency_rule_models m WHERE m.rule_id = currency_rules.id "
        "ORDER BY lower(model) LIMIT 1)")
    op.drop_index(op.f('ix_currency_rule_models_rule_id'), table_name='currency_rule_models')
    op.drop_table('currency_rule_models')
