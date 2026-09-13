"""google sign-in

Revision ID: e7c2a9f4b130
Revises: d4b8e2a7c029
Create Date: 2026-09-12 18:00:00.000000

030: `accounts.google_sub` (nullable, unique, set once) holds Google's
stable `sub` for a linked Google account, and `accounts.password_hash`
becomes nullable so a Google-created account can exist with no
password. No other change; no row is rewritten.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e7c2a9f4b130'
down_revision: Union[str, None] = 'd4b8e2a7c029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'accounts', sa.Column('google_sub', sa.String(), nullable=True)
    )
    op.create_unique_constraint(
        'uq_accounts_google_sub', 'accounts', ['google_sub']
    )
    op.alter_column(
        'accounts', 'password_hash', existing_type=sa.String(), nullable=True
    )


def downgrade() -> None:
    # A Google-only account has no password_hash; the column cannot go
    # back to NOT NULL while one exists. The house rule is fix forward.
    op.alter_column(
        'accounts', 'password_hash', existing_type=sa.String(), nullable=False
    )
    op.drop_constraint('uq_accounts_google_sub', 'accounts', type_='unique')
    op.drop_column('accounts', 'google_sub')
