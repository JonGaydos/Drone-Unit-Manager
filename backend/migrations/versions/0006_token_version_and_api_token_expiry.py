"""token version and api token expiry

users.token_version is carried in every login token; bumping it on a password
change or reset, role change, deactivation or logout invalidates every token
issued before. Existing users start at 0, which matches tokens issued before
this migration (they carry no version and are read as 0), so nobody is logged
out by the upgrade itself.

api_tokens.expires_at lets an admin mint a token that stops working on its
own. Existing tokens keep working (null means never).

Revision ID: 0006_token_version_and_api_token_expiry
Revises: 0005_counts_toward_totals
Create Date: 2026-09-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006_token_version_and_api_token_expiry'
down_revision: Union[str, None] = '0005_counts_toward_totals'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('token_version', sa.Integer(),
                                     nullable=False, server_default='0'))
    op.add_column('api_tokens', sa.Column('expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('api_tokens', 'expires_at')
    op.drop_column('users', 'token_version')
