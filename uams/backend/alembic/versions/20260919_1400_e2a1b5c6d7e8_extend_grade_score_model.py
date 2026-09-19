"""扩展成绩模型：理论/实践总评 + 理论/实践补考。

成绩业务模型闭环（FIX-008 后续验收修正）：

1. 新增可编辑原始成绩字段：
   - theory_makeup_score   理论补考成绩
   - practice_makeup_score 实践补考成绩
2. 新增系统计算字段（只由 ScoreService 写入，教师/前端不可直接传值）：
   - theory_total_score    理论总评
   - practice_total_score  实践总评

业务规则见 DATABASE.md §9.3：
- 理论总评 = 平时×w.regular + 期中理论×w.mid + 期末理论×w.final（期末理论取补考成绩优先）
- 实践总评 = 平时×w.regular + 期中实践×w.mid + 期末实践×w.final（期末实践取补考成绩优先）
- 成绩总评 = 理论/实践拆分存在时取两侧平均，否则等于理论总评
- 补考通过（≥60）的一侧，其总评按 60 封顶；补考只允许在对应期末分项 < 60 时录入

存量数据回填：迁移前库中所有成绩均无理论/实践拆分（录入均为合并口径），
理论总评 = 总评，实践总评保持 NULL。

downgrade 会丢失理论/实践总评与补考成绩（历史存量无法从合并口径还原拆分），
回退后可由 seed_demo / 教师重新录入重建。
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e2a1b5c6d7e8"
down_revision = "e1b7c4a9f3d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "grades",
        sa.Column(
            "theory_total_score",
            sa.Numeric(5, 2),
            nullable=True,
            comment="理论总评，由后端统一计算",
        ),
    )
    op.add_column(
        "grades",
        sa.Column(
            "practice_total_score",
            sa.Numeric(5, 2),
            nullable=True,
            comment="实践总评，由后端统一计算",
        ),
    )
    op.add_column(
        "grades",
        sa.Column(
            "theory_makeup_score",
            sa.Numeric(5, 2),
            nullable=True,
            comment="理论补考成绩",
        ),
    )
    op.add_column(
        "grades",
        sa.Column(
            "practice_makeup_score",
            sa.Numeric(5, 2),
            nullable=True,
            comment="实践补考成绩",
        ),
    )
    op.create_check_constraint(
        "ck_grades_theory_total",
        "grades",
        "theory_total_score IS NULL OR theory_total_score BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        "ck_grades_practice_total",
        "grades",
        "practice_total_score IS NULL OR practice_total_score BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        "ck_grades_theory_makeup",
        "grades",
        "theory_makeup_score IS NULL OR theory_makeup_score BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        "ck_grades_practice_makeup",
        "grades",
        "practice_makeup_score IS NULL OR practice_makeup_score BETWEEN 0 AND 100",
    )

    # 存量数据回填：无理论/实践拆分的成绩，理论总评 = 总评
    op.execute(
        "UPDATE grades SET theory_total_score = total_score "
        "WHERE total_score IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_constraint("ck_grades_theory_total", "grades", type_="check")
    op.drop_constraint("ck_grades_practice_total", "grades", type_="check")
    op.drop_constraint("ck_grades_theory_makeup", "grades", type_="check")
    op.drop_constraint("ck_grades_practice_makeup", "grades", type_="check")
    op.drop_column("grades", "theory_total_score")
    op.drop_column("grades", "practice_total_score")
    op.drop_column("grades", "theory_makeup_score")
    op.drop_column("grades", "practice_makeup_score")
