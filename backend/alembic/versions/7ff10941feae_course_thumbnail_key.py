"""course thumbnail key

Revision ID: 7ff10941feae
Revises: a3f9c2e17b54
Create Date: 2026-09-14 19:53:27.163327

035: `courses.thumbnail_key` (nullable) holds the storage key of the
catalog artwork, `course-thumbnails/<course_code>/<sha256>.<ext>`; null
means the course has no artwork and its catalog card renders as text
alone. No row is rewritten.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ff10941feae'
down_revision: Union[str, None] = 'a3f9c2e17b54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'courses', sa.Column('thumbnail_key', sa.String(), nullable=True)
    )


def downgrade() -> None:
    # Drops the pointer only; the stored objects under
    # course-thumbnails/ are left where they are. The house rule is fix
    # forward — this exists so the round-trip is provable, not to be run.
    op.drop_column('courses', 'thumbnail_key')
