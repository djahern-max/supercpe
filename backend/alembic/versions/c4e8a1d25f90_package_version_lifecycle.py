"""package version lifecycle

Revision ID: c4e8a1d25f90
Revises: 7ff10941feae
Create Date: 2026-09-15 12:00:00.000000

038: `lesson_packages.archived_at`, `media_purged_at`, and
`media_purged_by` (all nullable). Archive hides a superseded version and
refuses attaching it; purge records that the version's stored media files
were deleted after retention. The two CHECKs are hand-written
(autogenerate does not emit them): a purge names its admin, and only an
archived version can be purged. No row is rewritten.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8a1d25f90'
down_revision: Union[str, None] = '7ff10941feae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'lesson_packages',
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'lesson_packages',
        sa.Column('media_purged_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'lesson_packages',
        sa.Column('media_purged_by', sa.String(), nullable=True),
    )
    op.create_check_constraint(
        'ck_lesson_packages_purge_names_admin',
        'lesson_packages',
        '(media_purged_at IS NULL) = (media_purged_by IS NULL)',
    )
    op.create_check_constraint(
        'ck_lesson_packages_purge_requires_archive',
        'lesson_packages',
        'media_purged_at IS NULL OR archived_at IS NOT NULL',
    )


def downgrade() -> None:
    # The house rule is fix forward — this exists so the round-trip is
    # provable, not to be run.
    op.drop_constraint(
        'ck_lesson_packages_purge_requires_archive', 'lesson_packages'
    )
    op.drop_constraint('ck_lesson_packages_purge_names_admin', 'lesson_packages')
    op.drop_column('lesson_packages', 'media_purged_by')
    op.drop_column('lesson_packages', 'media_purged_at')
    op.drop_column('lesson_packages', 'archived_at')
