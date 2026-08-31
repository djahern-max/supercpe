"""create jurisdiction policies

Revision ID: c4d7e81f2a90
Revises: b6e2d94c8a17
Create Date: 2026-08-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4d7e81f2a90'
down_revision: Union[str, None] = 'b6e2d94c8a17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 020: reference data the admin verifies board by board. Ships empty
    # on purpose — rows are created on first edit, never seeded, so no
    # increment ever displays without a source and a verification date.
    op.create_table(
        'jurisdiction_policies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('jurisdiction', sa.String(length=2), nullable=False),
        sa.Column(
            'credit_increment',
            sa.String(),
            server_default='unknown',
            nullable=False,
        ),
        sa.Column(
            'non_technical_cap_note',
            sa.Text(),
            server_default='',
            nullable=False,
        ),
        sa.Column('source', sa.Text(), server_default='', nullable=False),
        sa.Column('verified_on', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), server_default='', nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('jurisdiction'),
        # Hand-written CHECKs: the code shape, and 7.01's increments plus
        # the unverified default.
        sa.CheckConstraint(
            "jurisdiction ~ '^[A-Z]{2}$'",
            name='ck_jurisdiction_policies_code',
        ),
        sa.CheckConstraint(
            "credit_increment IN "
            "('one_fifth', 'one_half', 'whole', 'unknown')",
            name='ck_jurisdiction_policies_increment',
        ),
    )


def downgrade() -> None:
    op.drop_table('jurisdiction_policies')
