"""accounts sessions and site mode

Revision ID: a1f4fe1dbd81
Revises: eadb4ff2d315
Create Date: 2026-08-29 08:51:29.899820

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f4fe1dbd81'
down_revision: Union[str, None] = 'eadb4ff2d315'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), server_default='', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('must_change_password', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('failed_logins', sa.Integer(), server_default='0', nullable=False),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by_account_id', sa.Integer(), nullable=True),
        sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role IN ('participant', 'reviewer', 'admin')",
            name='ck_accounts_role',
        ),
        sa.ForeignKeyConstraint(
            ['created_by_account_id'], ['accounts.id'], ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )
    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_agent', sa.String(), server_default='', nullable=False),
        sa.Column('ip', sa.String(), server_default='', nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_table(
        'site_mode_changes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('from_mode', sa.String(), nullable=False),
        sa.Column('to_mode', sa.String(), nullable=False),
        sa.Column('changed_by_account_id', sa.Integer(), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('note', sa.Text(), server_default='', nullable=False),
        sa.CheckConstraint(
            "from_mode IN ('coming_soon', 'open')",
            name='ck_site_mode_changes_from_mode',
        ),
        sa.CheckConstraint(
            "to_mode IN ('coming_soon', 'open')",
            name='ck_site_mode_changes_to_mode',
        ),
        sa.ForeignKeyConstraint(
            ['changed_by_account_id'], ['accounts.id'], ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    # 008 rows keep recorded_by = 'admin' and a null account; only rows
    # recorded from 009 on set this.
    op.add_column(
        'course_reviews',
        sa.Column('recorded_by_account_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_course_reviews_recorded_by_account_id',
        'course_reviews',
        'accounts',
        ['recorded_by_account_id'],
        ['id'],
        ondelete='RESTRICT',
    )
    # The server_default sets the existing singleton row to coming_soon.
    op.add_column(
        'sponsor_profile',
        sa.Column(
            'site_mode', sa.String(), server_default='coming_soon', nullable=False
        ),
    )
    op.create_check_constraint(
        'ck_sponsor_profile_site_mode',
        'sponsor_profile',
        "site_mode IN ('coming_soon', 'open')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_sponsor_profile_site_mode', 'sponsor_profile', type_='check')
    op.drop_column('sponsor_profile', 'site_mode')
    op.drop_constraint(
        'fk_course_reviews_recorded_by_account_id', 'course_reviews', type_='foreignkey'
    )
    op.drop_column('course_reviews', 'recorded_by_account_id')
    op.drop_table('site_mode_changes')
    op.drop_table('sessions')
    op.drop_table('accounts')
