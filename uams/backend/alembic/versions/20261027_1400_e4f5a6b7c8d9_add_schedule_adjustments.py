"""add schedule adjustments (F-22)

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedule_adjustments",
        sa.Column("teaching_class_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("schedule_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("request_type", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("new_day_of_week", mysql.TINYINT(unsigned=True), nullable=True),
        sa.Column("new_start_period", mysql.TINYINT(unsigned=True), nullable=True),
        sa.Column("new_end_period", mysql.TINYINT(unsigned=True), nullable=True),
        sa.Column("new_start_week", mysql.TINYINT(unsigned=True), nullable=True),
        sa.Column("new_end_week", mysql.TINYINT(unsigned=True), nullable=True),
        sa.Column("new_week_type", sa.String(length=10), nullable=True),
        sa.Column("new_classroom_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("requested_by", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("reviewed_by", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("review_reason", sa.String(length=500), nullable=True),
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="更新时间"),
        sa.CheckConstraint("request_type IN ('CHANGE','CANCEL','ADD')", name="ck_adj_type"),
        sa.CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="ck_adj_status"),
        sa.ForeignKeyConstraint(["teaching_class_id"], ["teaching_classes.id"], name="fk_adj_class", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"], name="fk_adj_schedule", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["new_classroom_id"], ["classrooms.id"], name="fk_adj_room", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], name="fk_adj_requester", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], name="fk_adj_reviewer", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        comment="调停课申请",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index("idx_adj_status", "schedule_adjustments", ["status", "created_at"], unique=False)
    op.create_index("idx_adj_class", "schedule_adjustments", ["teaching_class_id"], unique=False)


def downgrade() -> None:
    op.drop_table("schedule_adjustments")
