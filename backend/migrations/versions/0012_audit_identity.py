"""audit log username and imported flag

Adds audit_logs.user_username, the login name of whoever made the change, which
stays fixed if their display name changes later, and audit_logs.imported, which
marks entries that came from a restored backup.

Revision ID: 0012_audit_identity
Revises: 0011_role_permissions
Create Date: 2026-11-03 12:00:00.000000

"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012_audit_identity'
down_revision: str | None = '0011_role_permissions'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_username', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('imported', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_column('imported')
        batch_op.drop_column('user_username')
