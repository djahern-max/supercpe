"""waiting list invitations

Revision ID: e2c94b6a1d73
Revises: c4d7e81f2a90
Create Date: 2026-08-31 12:00:00.000000

021: two nullable columns on `waiting_list` recording the one promised
invitation per entry. No backfill: every existing row has never been
invited, which NULL already says. The rows remain not-CPE-records.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e2c94b6a1d73'
down_revision: Union[str, None] = 'c4d7e81f2a90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'waiting_list',
        sa.Column('invited_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'waiting_list',
        sa.Column('invitation_status', sa.String(), nullable=True),
    )
    # Hand-written CHECKs (autogenerate does not write them). NULL passes
    # the IN check, so the pair constraint carries both-or-neither.
    op.create_check_constraint(
        'ck_waiting_list_invitation_status',
        'waiting_list',
        "invitation_status IN ('sent', 'failed')",
    )
    op.create_check_constraint(
        'ck_waiting_list_invitation_pair',
        'waiting_list',
        '(invitation_status IS NULL) = (invited_at IS NULL)',
    )


def downgrade() -> None:
    op.drop_constraint(
        'ck_waiting_list_invitation_pair', 'waiting_list', type_='check'
    )
    op.drop_constraint(
        'ck_waiting_list_invitation_status', 'waiting_list', type_='check'
    )
    op.drop_column('waiting_list', 'invitation_status')
    op.drop_column('waiting_list', 'invited_at')
