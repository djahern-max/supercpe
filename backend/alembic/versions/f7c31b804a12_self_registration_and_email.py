"""self registration and email

Revision ID: f7c31b804a12
Revises: e5b7d9a3c1f8
Create Date: 2026-08-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f7c31b804a12'
down_revision: Union[str, None] = 'e5b7d9a3c1f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'accounts',
        sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column('accounts', sa.Column('state', sa.String(length=2), nullable=True))
    # Every existing account was created by an admin (or the CLI): the
    # hand-delivered initial password is the vouch, so they are verified
    # as of their creation. Only 017 self-registrations start unverified.
    op.execute('UPDATE accounts SET email_verified_at = created_at')
    op.create_check_constraint(
        'ck_accounts_state_code',
        'accounts',
        "state IS NULL OR state ~ '^[A-Z]{2}$'",
    )

    op.create_table(
        'email_verification_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
        # Hand-written CHECK: a token leaves the live state exactly one
        # way — consumed or superseded, never both.
        sa.CheckConstraint(
            'used_at IS NULL OR superseded_at IS NULL',
            name='ck_email_verification_tokens_one_ending',
        ),
    )

    op.create_table(
        'email_message',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('recipient', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('backend', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "backend IN ('console', 'smtp')",
            name='ck_email_message_backend',
        ),
    )


def downgrade() -> None:
    op.drop_table('email_message')
    op.drop_table('email_verification_tokens')
    op.drop_constraint('ck_accounts_state_code', 'accounts', type_='check')
    op.drop_column('accounts', 'state')
    op.drop_column('accounts', 'email_verified_at')
