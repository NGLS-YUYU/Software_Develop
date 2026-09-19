"""drop courses.regular_weight / final_weight

Revision ID: e1b7c4a9f3d2
Revises: d7e5a3f1c2b4
Create Date: 2026-09-19 09:00:00.000000

FIX-008：删除 courses 表上的成绩权重死字段。

背景
----
`regular_weight` / `final_weight`（默认 0.40 / 0.60，含 CHECK 两值和为 1）
是 V0.1 遗留设计，TASK-002/003 之后**已无任何生产逻辑引用**：

    总评唯一计算入口 = services/score_service.py::ScoreService.compute
    权重唯一来源     = ScoreService.WEIGHT_RULES（按 assessment_type 取：
                       "32" → 20/80；"48"/"64" → 20/30/50）

两套口径并存造成误导（默认 40/60 与实际 20/80 不一致），故删除死字段，
使 `WEIGHT_RULES` 成为唯一权威来源。

影响面（已核实）
----------------
- 无 Service / API / Repository 引用（全后端 grep 仅命中 model 与 schema）；
- 前端 Courses.vue 的权重滑块与 types 定义依赖本字段，同一 FIX 中一并移除；
- 库中无外键引用 courses 的这两列。

回滚
----
downgrade 会以 0.40 / 0.60 默认值重建两列并恢复 CHECK 约束，
但**不回填历史值**（原值已丢失，且删除前全部为默认 0.40 / 0.60）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1b7c4a9f3d2'
down_revision: Union[str, Sequence[str], None] = 'd7e5a3f1c2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_courses_weight', 'courses', type_='check')
    op.drop_column('courses', 'regular_weight')
    op.drop_column('courses', 'final_weight')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'courses',
        sa.Column(
            'regular_weight',
            sa.Numeric(precision=3, scale=2),
            server_default='0.40',
            nullable=False,
            comment='平时成绩权重',
        ),
    )
    op.add_column(
        'courses',
        sa.Column(
            'final_weight',
            sa.Numeric(precision=3, scale=2),
            server_default='0.60',
            nullable=False,
            comment='期末成绩权重',
        ),
    )
    op.create_check_constraint(
        'ck_courses_weight', 'courses', 'regular_weight + final_weight = 1.00'
    )
