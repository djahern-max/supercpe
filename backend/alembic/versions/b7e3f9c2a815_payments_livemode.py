"""payments livemode

Revision ID: b7e3f9c2a815
Revises: a1f3c7d92b40
Create Date: 2026-09-11 12:00:00.000000

026: Stripe's own `livemode` on each payment row, as reported on the
Checkout Session and re-stamped from the completion event, never
inferred from the key prefix. Nullable: rows that predate the column
keep NULL — there are none in production, and a guess would not be an
honest record.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7e3f9c2a815'
down_revision: Union[str, None] = 'a1f3c7d92b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'payments', sa.Column('livemode', sa.Boolean(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('payments', 'livemode')
