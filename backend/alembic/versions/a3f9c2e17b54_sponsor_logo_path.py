"""sponsor logo path

Revision ID: a3f9c2e17b54
Revises: e7c2a9f4b130
Create Date: 2026-09-13 12:00:00.000000

032: `sponsor_profile.logo_path` (nullable) holds the storage key of the
uploaded certificate mark; null means the monogram. No row is rewritten.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3f9c2e17b54'
down_revision: Union[str, None] = 'e7c2a9f4b130'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'sponsor_profile', sa.Column('logo_path', sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('sponsor_profile', 'logo_path')
