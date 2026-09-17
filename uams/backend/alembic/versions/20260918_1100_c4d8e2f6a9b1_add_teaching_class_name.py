"""add teaching class name column and course index

Revision ID: c4d8e2f6a9b1
Revises: a3f9c2e8b1d4
Create Date: 2026-09-18 11:00:00.000000

TASK-012：teaching_classes 增加 name（展示名，区别于编号 code），
并为 course_id 增加独立索引（按课程过滤开课计划）。
顺带把 term_id 注释同步为与模型一致（TASK-011 迁移遗漏的注释差异）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = 'c4d8e2f6a9b1'
down_revision: Union[str, Sequence[str], None] = 'a3f9c2e8b1d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'teaching_classes',
        sa.Column(
            'name', sa.String(length=100), nullable=True,
            comment='教学班名称（展示用，区别于编号 code）',
        ),
    )
    op.create_index('idx_tc_course', 'teaching_classes', ['course_id'], unique=False)
    # 同步 term_id 注释（模型注释含「（TASK-011）」，历史迁移未写入）
    op.alter_column(
        'teaching_classes', 'term_id',
        existing_type=mysql.BIGINT(unsigned=True), nullable=False,
        comment='所属学期（TASK-011）',
    )


def downgrade() -> None:
    """Downgrade schema."""
    # idx_tc_course 被 fk_tc_course 外键用作支撑索引，须先删外键再删索引（同 TASK-011）
    op.drop_constraint('fk_tc_course', 'teaching_classes', type_='foreignkey')
    op.drop_index('idx_tc_course', table_name='teaching_classes')
    # 重建外键（MySQL 会自动创建同名的支撑索引）
    op.create_foreign_key(
        'fk_tc_course', 'teaching_classes', 'courses',
        ['course_id'], ['id'], ondelete='RESTRICT',
    )
    # 还原 term_id 注释
    op.alter_column(
        'teaching_classes', 'term_id',
        existing_type=mysql.BIGINT(unsigned=True), nullable=False,
        comment='所属学期',
    )
    op.drop_column('teaching_classes', 'name')
