"""create waiting list

Revision ID: e5b7d9a3c1f8
Revises: c8a15d20e9b4
Create Date: 2026-08-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5b7d9a3c1f8'
down_revision: Union[str, None] = 'c8a15d20e9b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'waiting_list',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('state', sa.String(length=2), nullable=False),
        sa.Column('firm', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('removed_reason', sa.Text(), nullable=True),
        sa.Column('source', sa.String(), server_default='coming_soon', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        # Hand-written CHECKs: the stored email form (lowercased, trimmed),
        # the two-letter jurisdiction shape (membership in the 55 codes is
        # validated in services.waiting_list against US_JURISDICTIONS),
        # and a removal reason only on a removed row.
        sa.CheckConstraint("state ~ '^[A-Z]{2}$'", name='ck_waiting_list_state_code'),
        sa.CheckConstraint('email = lower(btrim(email))', name='ck_waiting_list_email_form'),
        sa.CheckConstraint(
            'removed_reason IS NULL OR removed_at IS NOT NULL',
            name='ck_waiting_list_reason_requires_removal',
        ),
    )


def downgrade() -> None:
    op.drop_table('waiting_list')
