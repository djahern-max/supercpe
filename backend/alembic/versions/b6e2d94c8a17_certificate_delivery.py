"""certificate delivery

Revision ID: b6e2d94c8a17
Revises: a9d21c5b7e30
Create Date: 2026-08-31 12:00:00.000000

No verification-code backfill is needed: `completions.verification_token`
has been non-null, unique, and 256 bits since 010, and 019's public page
resolves it as the printed code. Existing (dev-only) completions verify by
that token with their PDFs unchanged — snapshots and stored certificates
are immutable, and production starts empty.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b6e2d94c8a17'
down_revision: Union[str, None] = 'a9d21c5b7e30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows backfill to 'pending' through the server default: no
    # email was ever attempted for them.
    op.add_column(
        'completions',
        sa.Column(
            'delivery_status',
            sa.String(),
            server_default='pending',
            nullable=False,
        ),
    )
    op.add_column(
        'completions',
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Hand-written CHECKs (autogenerate does not write them).
    op.create_check_constraint(
        'ck_completions_delivery_status',
        'completions',
        "delivery_status IN ('pending', 'sent', 'failed')",
    )
    op.create_check_constraint(
        'ck_completions_sent_has_timestamp',
        'completions',
        "(delivery_status = 'sent') = (delivered_at IS NOT NULL)",
    )

    op.add_column(
        'email_message',
        sa.Column('attachment_filename', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('email_message', 'attachment_filename')
    op.drop_constraint(
        'ck_completions_sent_has_timestamp', 'completions', type_='check'
    )
    op.drop_constraint(
        'ck_completions_delivery_status', 'completions', type_='check'
    )
    op.drop_column('completions', 'delivered_at')
    op.drop_column('completions', 'delivery_status')
