"""role permissions and document uploader

Adds role_permissions, which stores only the changes an admin makes to the
default permission grid, and documents.uploaded_by_id, the owner of a document
from now on. Existing documents keep a null uploader.

Revision ID: 0011_role_permissions
Revises: 0010_local_dates_for_spreadsheet_imports
Create Date: 2026-11-02 12:00:00.000000

"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011_role_permissions'
down_revision: str | None = '0010_local_dates_for_spreadsheet_imports'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'role_permissions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('permission_key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.String(length=10), nullable=False),
        sa.UniqueConstraint('role', 'permission_key', name='uq_role_permissions_role_key'),
    )
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('uploaded_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_documents_uploaded_by_id_users', 'users', ['uploaded_by_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_constraint('fk_documents_uploaded_by_id_users', type_='foreignkey')
        batch_op.drop_column('uploaded_by_id')
    op.drop_table('role_permissions')
