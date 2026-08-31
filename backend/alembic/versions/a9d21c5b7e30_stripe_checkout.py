"""stripe checkout

Revision ID: a9d21c5b7e30
Revises: f7c31b804a12
Create Date: 2026-08-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a9d21c5b7e30'
down_revision: Union[str, None] = 'f7c31b804a12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'courses', sa.Column('price_cents', sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        'ck_courses_price_positive',
        'courses',
        'price_cents IS NULL OR price_cents > 0',
    )

    op.add_column(
        'enrollments',
        sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'enrollments',
        sa.Column('voided_by_account_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_enrollments_voided_by_account_id',
        'enrollments',
        'accounts',
        ['voided_by_account_id'],
        ['id'],
        ondelete='RESTRICT',
    )
    # Hand-written CHECK: a void always records who did it.
    op.create_check_constraint(
        'ck_enrollments_void_names_admin',
        'enrollments',
        '(voided_at IS NULL) = (voided_by_account_id IS NULL)',
    )

    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('stripe_checkout_session_id', sa.String(), nullable=False),
        sa.Column('stripe_payment_intent_id', sa.String(), nullable=True),
        sa.Column('checkout_url', sa.String(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stripe_checkout_session_id'),
        # Hand-written CHECKs (autogenerate does not write them).
        sa.CheckConstraint(
            "status IN ('pending', 'paid', 'refunded', 'expired')",
            name='ck_payments_status',
        ),
        sa.CheckConstraint(
            'amount_cents > 0', name='ck_payments_amount_positive'
        ),
    )

    op.create_table(
        'stripe_webhook_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stripe_event_id', sa.String(), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stripe_event_id'),
    )


def downgrade() -> None:
    op.drop_table('stripe_webhook_events')
    op.drop_table('payments')
    op.drop_constraint('ck_enrollments_void_names_admin', 'enrollments', type_='check')
    op.drop_constraint('fk_enrollments_voided_by_account_id', 'enrollments', type_='foreignkey')
    op.drop_column('enrollments', 'voided_by_account_id')
    op.drop_column('enrollments', 'voided_at')
    op.drop_constraint('ck_courses_price_positive', 'courses', type_='check')
    op.drop_column('courses', 'price_cents')
