"""counts toward totals

Separates "is this person on the roster" from "is this the unit's own activity".

A pilot who leaves still flew the flights they flew, so an inactive pilot keeps
counting. A vendor or guest operator never was the unit's activity, so their
flights should not inflate the unit's numbers even while their account is live.
Those are two different questions and pilot.status only answered the first.

Revision ID: 0005_counts_toward_totals
Revises: 0004_operating_authority
Create Date: 2026-09-04 22:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005_counts_toward_totals'
down_revision: Union[str, None] = '0004_operating_authority'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Everything already recorded is the unit's own activity until an admin says
    # otherwise, so both columns backfill to true rather than defaulting to a
    # silent exclusion of history.
    op.add_column('pilots', sa.Column('counts_toward_totals', sa.Boolean(),
                                      nullable=False, server_default=sa.true()))
    op.add_column('flights', sa.Column('counts_toward_totals', sa.Boolean(),
                                       nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column('flights', 'counts_toward_totals')
    op.drop_column('pilots', 'counts_toward_totals')
