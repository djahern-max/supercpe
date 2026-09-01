"""text-first course packages

Revision ID: a1f3c7d92b40
Revises: e2c94b6a1d73
Create Date: 2026-09-01 09:00:00.000000

023: lesson packages gain a `kind`, and text packages gain the three
tables their contents normalize into.

Every existing row is a video package, which the server defaults say
without a backfill. `video_key`, `transcript`, and `measured_at` become
nullable so a text package can honestly have none, and paired CHECKs make
each one present exactly when the kind is video — so no existing row can
lose its video, and no text package can acquire one.

`questions.after_block` gains a sibling `after_section`. The old
"after_block iff review" CHECK is replaced by "exactly one placement iff
review", which is the same rule generalized from video blocks to guide
sections; every existing review question satisfies it unchanged.

Autogenerate writes no CHECK constraints; all of these are by hand.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1f3c7d92b40'
down_revision: Union[str, None] = 'e2c94b6a1d73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'lesson_packages',
        sa.Column(
            'kind', sa.String(), nullable=False, server_default='video'
        ),
    )
    op.add_column(
        'lesson_packages',
        sa.Column(
            'word_count_source',
            sa.String(),
            nullable=False,
            server_default='manifest',
        ),
    )
    op.alter_column('lesson_packages', 'video_key', nullable=True)
    op.alter_column('lesson_packages', 'transcript', nullable=True)
    op.alter_column('lesson_packages', 'measured_at', nullable=True)

    op.create_check_constraint(
        'ck_lesson_packages_kind',
        'lesson_packages',
        "kind IN ('video', 'text')",
    )
    op.create_check_constraint(
        'ck_lesson_packages_word_count_source',
        'lesson_packages',
        "word_count_source IN ('computed', 'manifest')",
    )
    op.create_check_constraint(
        'ck_lesson_packages_video_key_iff_video',
        'lesson_packages',
        "(kind = 'video') = (video_key IS NOT NULL)",
    )
    op.create_check_constraint(
        'ck_lesson_packages_transcript_iff_video',
        'lesson_packages',
        "(kind = 'video') = (transcript IS NOT NULL)",
    )
    op.create_check_constraint(
        'ck_lesson_packages_measured_at_iff_video',
        'lesson_packages',
        "(kind = 'video') = (measured_at IS NOT NULL)",
    )

    op.create_table(
        'package_sections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('package_id', sa.Integer(), nullable=False),
        sa.Column('section_key', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('file', sa.String(), nullable=False),
        sa.Column('markdown', sa.Text(), nullable=False),
        sa.Column('word_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['package_id'], ['lesson_packages.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'package_id', 'section_key', name='uq_package_sections_key'
        ),
        sa.UniqueConstraint(
            'package_id', 'position', name='uq_package_sections_position'
        ),
        sa.CheckConstraint(
            "role IN ('front_matter', 'body', 'glossary', 'appendix')",
            name='ck_package_sections_role',
        ),
        sa.CheckConstraint(
            'word_count >= 0',
            name='ck_package_sections_word_count_non_negative',
        ),
    )
    op.create_index(
        'ix_package_sections_package_id', 'package_sections', ['package_id']
    )

    op.create_table(
        'package_media',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('package_id', sa.Integer(), nullable=False),
        sa.Column('media_key', sa.String(), nullable=False),
        sa.Column('file', sa.String(), nullable=False),
        sa.Column('storage_key', sa.String(), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('after_section', sa.String(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('av_is_additional_learning', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ['package_id'], ['lesson_packages.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'package_id', 'media_key', name='uq_package_media_key'
        ),
        sa.UniqueConstraint(
            'package_id', 'position', name='uq_package_media_position'
        ),
        sa.CheckConstraint(
            'duration_seconds > 0', name='ck_package_media_duration_positive'
        ),
        # 7.02.7: a text package's media minutes always count, so a row
        # that does not claim additional learning cannot exist.
        sa.CheckConstraint(
            'av_is_additional_learning',
            name='ck_package_media_additional_learning',
        ),
    )
    op.create_index(
        'ix_package_media_package_id', 'package_media', ['package_id']
    )

    op.create_table(
        'glossary_terms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('package_id', sa.Integer(), nullable=False),
        sa.Column('term', sa.String(), nullable=False),
        sa.Column('definition', sa.Text(), nullable=False),
        sa.Column('section_key', sa.String(), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['package_id'], ['lesson_packages.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('package_id', 'term', name='uq_glossary_terms_term'),
        sa.UniqueConstraint(
            'package_id', 'position', name='uq_glossary_terms_position'
        ),
    )
    op.create_index(
        'ix_glossary_terms_package_id', 'glossary_terms', ['package_id']
    )

    op.add_column(
        'questions', sa.Column('after_section', sa.String(), nullable=True)
    )
    op.drop_constraint(
        'ck_questions_after_block_iff_review', 'questions', type_='check'
    )
    op.create_check_constraint(
        'ck_questions_placement_iff_review',
        'questions',
        "(kind = 'review') = "
        "(after_block IS NOT NULL OR after_section IS NOT NULL)",
    )
    op.create_check_constraint(
        'ck_questions_one_placement',
        'questions',
        'NOT (after_block IS NOT NULL AND after_section IS NOT NULL)',
    )


def downgrade() -> None:
    op.drop_constraint('ck_questions_one_placement', 'questions', type_='check')
    op.drop_constraint(
        'ck_questions_placement_iff_review', 'questions', type_='check'
    )
    op.create_check_constraint(
        'ck_questions_after_block_iff_review',
        'questions',
        "(kind = 'review') = (after_block IS NOT NULL)",
    )
    op.drop_column('questions', 'after_section')

    op.drop_index('ix_glossary_terms_package_id', table_name='glossary_terms')
    op.drop_table('glossary_terms')
    op.drop_index('ix_package_media_package_id', table_name='package_media')
    op.drop_table('package_media')
    op.drop_index('ix_package_sections_package_id', table_name='package_sections')
    op.drop_table('package_sections')

    # Downgrading past 023 with a text package stored would strip the
    # column that says it is one, so the NOT NULLs below would fail on it.
    # Deliberately not deleted here: a package row is program material
    # (9.02.1(7)) and a migration must not throw one away.
    op.drop_constraint(
        'ck_lesson_packages_measured_at_iff_video', 'lesson_packages',
        type_='check',
    )
    op.drop_constraint(
        'ck_lesson_packages_transcript_iff_video', 'lesson_packages',
        type_='check',
    )
    op.drop_constraint(
        'ck_lesson_packages_video_key_iff_video', 'lesson_packages',
        type_='check',
    )
    op.drop_constraint(
        'ck_lesson_packages_word_count_source', 'lesson_packages', type_='check'
    )
    op.drop_constraint('ck_lesson_packages_kind', 'lesson_packages', type_='check')
    op.alter_column('lesson_packages', 'measured_at', nullable=False)
    op.alter_column('lesson_packages', 'transcript', nullable=False)
    op.alter_column('lesson_packages', 'video_key', nullable=False)
    op.drop_column('lesson_packages', 'word_count_source')
    op.drop_column('lesson_packages', 'kind')
