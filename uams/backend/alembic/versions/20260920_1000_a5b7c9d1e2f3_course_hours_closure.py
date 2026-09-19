"""课程学时 / 考核结构闭环（FIX-009）。

1. 新增 DB 约束 ck_courses_hours：理论 + 实践学时必须等于总学时。
2. 存量数据回填 assessment_type：按 total_hours 重新推导（修复历史课程
   assessment_type 与总学时漂移，如 total_hours=32 却存成 "64"）。

downgrade 仅移除约束与回填不可逆（回填结果与回退前一致），
不会破坏现有成绩数据。
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a5b7c9d1e2f3"
down_revision = "e2a1b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 学时守恒约束（FIX-009 §六）
    op.create_check_constraint(
        "ck_courses_hours",
        "courses",
        "theory_hours + practice_hours = total_hours",
    )

    # 2. 按总学时回填考核方式（FIX-009 §三：assessment_type 为总学时的派生缓存）
    op.execute(
        """
        UPDATE courses
        SET assessment_type = CASE
            WHEN total_hours <= 32 THEN '32'
            WHEN total_hours <= 48 THEN '48'
            ELSE '64'
        END
        WHERE assessment_type IS NULL
           OR assessment_type <> CASE
                WHEN total_hours <= 32 THEN '32'
                WHEN total_hours <= 48 THEN '48'
                ELSE '64'
              END
        """
    )


def downgrade() -> None:
    op.drop_constraint("ck_courses_hours", "courses", type_="check")
