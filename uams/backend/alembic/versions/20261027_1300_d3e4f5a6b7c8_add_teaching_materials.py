"""add teaching materials (F-21)

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teaching_materials",
        sa.Column("teaching_class_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("file_size", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("uploaded_by", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False, comment="主键"),
        sa.ForeignKeyConstraint(["teaching_class_id"], ["teaching_classes.id"], name="fk_material_class", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], name="fk_material_uploader", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        comment="教学资料",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index("idx_materials_class", "teaching_materials", ["teaching_class_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("teaching_materials")
