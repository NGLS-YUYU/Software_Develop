"""add grade change logs (F-03)

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-10-27 12:00:00

仅新增成绩变更历史表；不回填、不修改已有成绩。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "grade_change_logs",
        sa.Column("grade_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("student_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("teaching_class_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("course_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("before_snapshot", sa.Text(), nullable=False),
        sa.Column("after_snapshot", sa.Text(), nullable=False),
        sa.Column("operated_by", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("operated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False, comment="主键"),
        sa.CheckConstraint(
            "action IN ('SUBMIT','APPROVE','REJECT','UN_APPROVE','CORRECT','TEACHER_EDIT')",
            name="ck_grade_change_action",
        ),
        sa.ForeignKeyConstraint(["grade_id"], ["grades.id"], name="fk_gcl_grade", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operated_by"], ["users.id"], name="fk_gcl_operator", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        comment="成绩变更历史",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index("idx_grade_change_grade", "grade_change_logs", ["grade_id", "operated_at"], unique=False)
    op.create_index("idx_grade_change_student", "grade_change_logs", ["student_id", "operated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_grade_change_student", table_name="grade_change_logs")
    op.drop_index("idx_grade_change_grade", table_name="grade_change_logs")
    op.drop_table("grade_change_logs")
