"""enrollments, completions, and certificates

Revision ID: b3e9c41a7f52
Revises: a1f4fe1dbd81
Create Date: 2026-08-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'b3e9c41a7f52'
down_revision: Union[str, None] = 'a1f4fe1dbd81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'enrollments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('enrolled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('created_by_account_id', sa.Integer(), nullable=True),
        sa.Column('package_versions', JSONB(), nullable=False),
        sa.CheckConstraint(
            "source IN ('admin', 'purchase')", name='ck_enrollments_source'
        ),
        sa.ForeignKeyConstraint(
            ['account_id'], ['accounts.id'], ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['course_id'], ['courses.id'], ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['created_by_account_id'], ['accounts.id'], ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    # "One active enrollment per (account, course)" depends on now(), so it
    # is enforced in the service; this index serves that lookup.
    op.create_index(
        'ix_enrollments_account_course',
        'enrollments',
        ['account_id', 'course_id'],
    )

    op.create_table(
        'lesson_progress',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('enrollment_id', sa.Integer(), nullable=False),
        sa.Column('package_id', sa.Integer(), nullable=False),
        sa.Column('furthest_seconds', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            'furthest_seconds >= 0',
            name='ck_lesson_progress_furthest_non_negative',
        ),
        sa.ForeignKeyConstraint(
            ['enrollment_id'], ['enrollments.id'], ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['package_id'], ['lesson_packages.id'], ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'enrollment_id', 'package_id', name='uq_lesson_progress_lesson'
        ),
    )

    op.create_table(
        'review_answers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('enrollment_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('choice_id', sa.Integer(), nullable=False),
        sa.Column('is_correct', sa.Boolean(), nullable=False),
        sa.Column('answered_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['enrollment_id'], ['enrollments.id'], ondelete='RESTRICT'
        ),
        # No ON DELETE, like attempt_answers: a package version whose
        # questions were answered cannot be deleted from under the record.
        sa.ForeignKeyConstraint(['question_id'], ['questions.id']),
        sa.ForeignKeyConstraint(['choice_id'], ['choices.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'enrollment_id', 'question_id', name='uq_review_answers_question'
        ),
    )

    op.create_table(
        'completions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('enrollment_id', sa.Integer(), nullable=False),
        sa.Column('attempt_id', sa.Integer(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('credit_awarded', sa.Numeric(4, 1), nullable=False),
        sa.Column('field_of_study', sa.String(), nullable=False),
        sa.Column('certificate_number', sa.String(), nullable=False),
        sa.Column('verification_token', sa.String(), nullable=False),
        sa.Column('certificate_snapshot', JSONB(), nullable=False),
        sa.Column('certificate_key', sa.String(), nullable=True),
        sa.Column(
            'certificate_rendered_at', sa.DateTime(timezone=True), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ['enrollment_id'], ['enrollments.id'], ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['attempt_id'], ['attempts.id'], ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('enrollment_id'),
        sa.UniqueConstraint('attempt_id'),
        sa.UniqueConstraint('certificate_number'),
        sa.UniqueConstraint('verification_token'),
    )

    op.create_table(
        'certificate_sequences',
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('last_number', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('year'),
    )

    # attempts gains its enrollment identity: the FK, the exactly-one-of
    # check (007's preview attempts all carry a preview_id, so the check
    # holds on existing rows), and the one-open-attempt partial index.
    op.create_foreign_key(
        'fk_attempts_enrollment_id',
        'attempts',
        'enrollments',
        ['enrollment_id'],
        ['id'],
        ondelete='RESTRICT',
    )
    op.create_check_constraint(
        'ck_attempts_enrollment_xor_preview',
        'attempts',
        '(enrollment_id IS NULL) != (preview_id IS NULL)',
    )
    op.create_index(
        'uq_attempts_one_open_per_enrollment',
        'attempts',
        ['enrollment_id'],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index('uq_attempts_one_open_per_enrollment', table_name='attempts')
    op.drop_constraint(
        'ck_attempts_enrollment_xor_preview', 'attempts', type_='check'
    )
    op.drop_constraint('fk_attempts_enrollment_id', 'attempts', type_='foreignkey')
    op.drop_table('certificate_sequences')
    op.drop_table('completions')
    op.drop_table('review_answers')
    op.drop_table('lesson_progress')
    op.drop_index('ix_enrollments_account_course', table_name='enrollments')
    op.drop_table('enrollments')
