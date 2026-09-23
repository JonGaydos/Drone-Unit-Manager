"""evidence soft delete, legal hold and upload digest

Photos and documents gain deleted_at / deleted_by_id (a delete now hides the
record and keeps the file until an admin purges it), legal_hold (blocks delete
and purge) and sha256 (the digest taken at upload; null for files uploaded
before this migration). Folders gain deleted_at.

Nothing existing changes: every current row is live, not on hold.

Revision ID: 0007_evidence_soft_delete
Revises: 0006_token_version_and_api_token_expiry
Create Date: 2026-09-22 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007_evidence_soft_delete'
down_revision: Union[str, None] = '0006_token_version_and_api_token_expiry'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVIDENCE_TABLES = ('photos', 'documents')


def upgrade() -> None:
    for table in EVIDENCE_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
            batch_op.add_column(sa.Column('deleted_by_id', sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column('legal_hold', sa.Boolean(), nullable=False, server_default='0'))
            batch_op.add_column(sa.Column('sha256', sa.String(length=64), nullable=True))
            batch_op.create_foreign_key(f'fk_{table}_deleted_by_id_users', 'users', ['deleted_by_id'], ['id'])
    op.add_column('folders', sa.Column('deleted_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('folders', 'deleted_at')
    for table in EVIDENCE_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f'fk_{table}_deleted_by_id_users', type_='foreignkey')
            batch_op.drop_column('sha256')
            batch_op.drop_column('legal_hold')
            batch_op.drop_column('deleted_by_id')
            batch_op.drop_column('deleted_at')
