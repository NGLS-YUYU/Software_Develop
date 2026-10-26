"""add course_selections.source (FIX-002)

Revision ID: b1c2d3e4f5a6
Revises: a5b7c9d1e2f3
Create Date: 2026-10-26 12:00:00

仅新增可空字段，不回填历史数据：
  - 历史记录 source = NULL，界面显示“历史记录（未标记来源）”；
  - 新记录由 Service 写入 STUDENT / ADMIN_REQUIRED / ADMIN_MANUAL。
"""

from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "a5b7c9d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "course_selections",
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=True,
            comment="来源：STUDENT/ADMIN_REQUIRED/ADMIN_MANUAL；NULL 为历史未标记",
        ),
    )
    op.create_check_constraint(
        "ck_selection_source",
        "course_selections",
        "source IS NULL OR source IN "
        "('STUDENT','ADMIN_REQUIRED','ADMIN_MANUAL')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_selection_source", "course_selections", type_="check")
    op.drop_column("course_selections", "source")
