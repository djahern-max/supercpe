"""evaluations, policies, and audit exports

Revision ID: c8a15d20e9b4
Revises: b3e9c41a7f52
Create Date: 2026-08-29 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c8a15d20e9b4'
down_revision: Union[str, None] = 'b3e9c41a7f52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'evaluations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('completion_id', sa.Integer(), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('objectives_met', sa.SmallInteger(), nullable=False),
        sa.Column('prerequisites_appropriate', sa.SmallInteger(), nullable=False),
        sa.Column('materials_relevant', sa.SmallInteger(), nullable=False),
        sa.Column('time_appropriate', sa.SmallInteger(), nullable=False),
        sa.Column('instructors_effective', sa.SmallInteger(), nullable=True),
        sa.Column('comments', sa.Text(), server_default='', nullable=False),
        sa.Column('objectives_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(['completion_id'], ['completions.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('completion_id'),
        # Hand-written CHECKs: the 1-5 scale on the four rated elements,
        # and item 5 constrained null (self study has no instructors).
        sa.CheckConstraint('objectives_met BETWEEN 1 AND 5', name='ck_evaluations_objectives_met_scale'),
        sa.CheckConstraint('prerequisites_appropriate BETWEEN 1 AND 5', name='ck_evaluations_prerequisites_appropriate_scale'),
        sa.CheckConstraint('materials_relevant BETWEEN 1 AND 5', name='ck_evaluations_materials_relevant_scale'),
        sa.CheckConstraint('time_appropriate BETWEEN 1 AND 5', name='ck_evaluations_time_appropriate_scale'),
        sa.CheckConstraint('instructors_effective IS NULL', name='ck_evaluations_instructors_null'),
    )
    op.create_table(
        'evaluation_reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('reviewed_by_account_id', sa.Integer(), nullable=False),
        sa.Column('summary_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('note', sa.Text(), server_default='', nullable=False),
        sa.Column('informed_developer', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['reviewed_by_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'policy_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('effective_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by_account_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("kind IN ('registration', 'refund', 'complaint')", name='ck_policy_versions_kind'),
    )
    op.create_table(
        'audit_exports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('generated_by_account_id', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('storage_key', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['generated_by_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('audit_exports')
    op.drop_table('policy_versions')
    op.drop_table('evaluation_reviews')
    op.drop_table('evaluations')
