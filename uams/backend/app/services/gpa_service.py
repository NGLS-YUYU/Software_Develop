"""GPA 综合评价服务（TASK-004）。

GPA 属于对成绩的动态评价结果，**不写入数据库**：
    Grade（成绩事实） → gpa_service（实时计算） → ranking_service（排名）

本模块不修改任何数据模型，仅提供纯计算函数与只读查询。
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError
from app.models.grade import GRADE_POINT_TABLE, Grade, GradeStatus, score_to_point

# 百分制 → 绩点换算表（DATABASE.md §9.3，唯一权威来源）：
# 与 Grade.grade_point（ScoreService 落库）同一张表，禁止在此另设一套口径。
# 低于 60 一律 0。
GRADE_POINT_RULES: list[tuple[Decimal, Decimal]] = GRADE_POINT_TABLE

TWO_DEC = Decimal("0.01")


class GpaError(BizError):
    code = "GPA_CALC_ERROR"
    message = "GPA 计算失败"


class NoGradesError(GpaError):
    code = "GPA_NO_GRADES"
    message = "学生没有有效成绩"


class NoCreditError(GpaError):
    code = "GPA_NO_CREDIT"
    message = "课程无学分"


class ZeroCreditError(GpaError):
    code = "GPA_ZERO_CREDIT"
    message = "课程学分为 0"


class EmptyScoreError(GpaError):
    code = "GPA_EMPTY_SCORE"
    message = "成绩为空"


def to_grade_point(score: Decimal | float) -> Decimal:
    """百分制成绩 → 绩点（DATABASE.md §9.3：90→4.0，85→3.7，80→3.3，75→3.0，
    70→2.7，65→2.3，60→1.0，<60→0）。与 Grade.grade_point 落库口径同源。"""
    return score_to_point(score)


def course_grade_points(credit: Decimal | float, total_score: Decimal | float) -> Decimal:
    """单课程绩点贡献 = 绩点 × 学分。"""
    if credit is None:
        raise NoCreditError("课程无学分，无法计算绩点贡献")
    c = Decimal(str(credit))
    if c == 0:
        raise ZeroCreditError("课程学分为 0，无法计算绩点贡献")
    if total_score is None:
        raise EmptyScoreError("课程成绩为空，无法计算绩点贡献")
    return (to_grade_point(total_score) * c).quantize(TWO_DEC, ROUND_HALF_UP)


def student_gpa(entries: list[tuple[Decimal | None, Decimal | None]]) -> Decimal:
    """GPA = Σ(绩点 × 学分) / Σ学分；entries 为 (credit, total_score) 列表。"""
    if not entries:
        raise NoGradesError("该学生没有有效成绩，无法计算 GPA")
    weighted = Decimal("0")
    total_credit = Decimal("0")
    for credit, score in entries:
        if credit is None:
            raise NoCreditError("存在课程无学分")
        c = Decimal(str(credit))
        if c == 0:
            raise ZeroCreditError(f"存在课程学分为 0（成绩 {score}）")
        if score is None:
            raise EmptyScoreError(f"课程学分 {c} 的成绩为空")
        weighted += to_grade_point(score) * c
        total_credit += c
    if total_credit == 0:
        raise ZeroCreditError("总学分为 0，无法计算 GPA")
    return (weighted / total_credit).quantize(TWO_DEC, ROUND_HALF_UP)


class GpaService:
    """按学生读取有效成绩并实时计算 GPA（只读，不落库）。"""

    def __init__(self, db: Session):
        self.db = db

    def entries_of(self, student_id: int) -> list[tuple[Decimal, Decimal]]:
        """该学生的有效成绩：(credit, total_score)。有效 = 已审核通过且有总评。"""
        rows = self.db.execute(
            select(Grade.credits, Grade.total_score).where(
                Grade.student_id == student_id,
                Grade.status == GradeStatus.APPROVED,
                Grade.total_score.is_not(None),
            )
        ).all()
        return [(Decimal(str(c)), Decimal(str(s))) for c, s in rows]

    def gpa_of(self, student_id: int) -> Decimal:
        """学生 GPA；无有效成绩时抛 NoGradesError。"""
        return student_gpa(self.entries_of(student_id))
