"""drop teaching_classes.selected_count

Revision ID: d7e5a3f1c2b4
Revises: c4d8e2f6a9b1
Create Date: 2026-09-18 13:00:00.000000

TASK-013：删除 teaching_classes.selected_count 冗余计数列。
已选人数改由 CourseSelection 动态统计（COUNT），避免「计数与选课记录」
不一致的并发/事务问题（CLAUDE.md §19/§20）。
API 响应中的 selected_count 仍保留为输出字段，但不再落库。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = 'd7e5a3f1c2b4'
down_revision: Union[str, Sequence[str], None] = 'c4d8e2f6a9b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_tc_count', 'teaching_classes', type_='check')
    op.drop_column('teaching_classes', 'selected_count')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'teaching_classes',
        sa.Column(
            'selected_count',
            sa.SmallInteger(),
            server_default='0',
            nullable=False,
            comment='已选人数；必须在事务内与选课记录同步',
        ),
    )
    op.create_check_constraint('ck_tc_count', 'teaching_classes', 'selected_count >= 0')
