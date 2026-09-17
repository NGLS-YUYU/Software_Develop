"""add academic terms and bind teaching classes

Revision ID: a3f9c2e8b1d4
Revises: d81e869930fb
Create Date: 2026-09-18 10:00:00.000000

TASK-011：新增 academic_terms 表，teaching_classes 增加 term_id 外键，
并把「全局 code 唯一」调整为「(term_id, code) 唯一」。
兼容迁移：为既有教学班回填一个默认学期（旧数据兼容，非真实业务数据）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'a3f9c2e8b1d4'
down_revision: Union[str, Sequence[str], None] = 'd81e869930fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 新建 academic_terms 表
    op.create_table(
        'academic_terms',
        sa.Column('name', sa.String(length=50), nullable=False, comment='学期名称'),
        sa.Column('academic_year', sa.String(length=9), nullable=False, comment='学年，如 2026-2027'),
        sa.Column('semester', sa.SmallInteger(), nullable=False, comment='学期序号：1 或 2'),
        sa.Column('start_date', sa.Date(), nullable=False, comment='开始日期'),
        sa.Column('end_date', sa.Date(), nullable=False, comment='结束日期'),
        sa.Column('status', sa.String(length=20), server_default='PLANNED', nullable=False),
        sa.Column('id', mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='更新时间'),
        sa.CheckConstraint('semester IN (1,2)', name='ck_terms_semester'),
        sa.CheckConstraint("status IN ('PLANNED','ACTIVE','ENDED')", name='ck_terms_status'),
        sa.CheckConstraint('end_date > start_date', name='ck_terms_dates'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('academic_year', 'semester', name='uk_terms_year_sem'),
        comment='学期',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_0900_ai_ci',
        mysql_engine='InnoDB',
    )
    op.create_index('idx_terms_status', 'academic_terms', ['status'], unique=False)

    # 2. teaching_classes 增加 term_id（先允许 NULL，回填后再收紧）
    op.add_column(
        'teaching_classes',
        sa.Column('term_id', mysql.BIGINT(unsigned=True), nullable=True, comment='所属学期'),
    )

    # 3. 先建外键支撑索引，再建外键（MySQL 外键需要一个以 term_id 开头的索引）
    op.create_index('idx_tc_term', 'teaching_classes', ['term_id'], unique=False)
    op.create_foreign_key(
        'fk_tc_term', 'teaching_classes', 'academic_terms',
        ['term_id'], ['id'], ondelete='RESTRICT',
    )

    # 4. 兼容迁移：为既有教学班补一个默认学期（旧数据兼容使用的默认学期，非真实业务数据）
    op.execute(
        """
        INSERT INTO academic_terms
            (name, academic_year, semester, start_date, end_date, status, created_at, updated_at)
        SELECT '2026-2027学年第一学期（兼容默认）', '2026-2027', 1,
               '2026-09-01', '2027-01-15', 'PLANNED', NOW(), NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM academic_terms WHERE academic_year = '2026-2027' AND semester = 1
        )
        """
    )
    op.execute(
        """
        UPDATE teaching_classes tc
        SET tc.term_id = (
            SELECT id FROM academic_terms
            WHERE academic_year = '2026-2027' AND semester = 1
        )
        WHERE tc.term_id IS NULL
        """
    )

    # 5. 收紧为 NOT NULL
    op.alter_column(
        'teaching_classes', 'term_id',
        existing_type=mysql.BIGINT(unsigned=True), nullable=False,
    )

    # 6. 唯一性调整：去掉全局 code 唯一，改为 (term_id, code) 唯一
    op.drop_index('code', table_name='teaching_classes')
    op.create_index('uk_tc_term_code', 'teaching_classes', ['term_id', 'code'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    # 1. 先删外键（否则其依赖的索引无法删除）
    op.drop_constraint('fk_tc_term', 'teaching_classes', type_='foreignkey')
    op.drop_index('uk_tc_term_code', table_name='teaching_classes')
    op.create_index('code', 'teaching_classes', ['code'], unique=True)

    # 2. 移除 term_id
    op.alter_column(
        'teaching_classes', 'term_id',
        existing_type=mysql.BIGINT(unsigned=True), nullable=True,
    )
    op.drop_index('idx_tc_term', table_name='teaching_classes')
    op.drop_column('teaching_classes', 'term_id')

    # 3. 删除 academic_terms
    op.drop_index('idx_terms_status', table_name='academic_terms')
    op.drop_table('academic_terms')
