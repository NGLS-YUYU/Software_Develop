"""统一成绩计算服务（TASK-003）。

所有成绩计算集中于此（CLAUDE.md §21），禁止在 Route / Schema / Model 中计算：
- 课程考核权重规则（WEIGHT_RULES）
- 期中/期末理论+实践成绩合并
- 总评计算

调用链：API → score_service → 计算结果。
"""

from decimal import ROUND_HALF_UP, Decimal

from app.core.exceptions import BizError
from app.models.course import AssessmentType, Course
from app.models.grade import PASS_SCORE, Grade, score_to_point

TWO_DEC = Decimal("0.01")

# 课程考核权重规则（TASK-003）：后续调整比例只需改这里
WEIGHT_RULES: dict[str, dict[str, Decimal | None]] = {
    AssessmentType.HOURS_32: {
        "regular": Decimal("0.2"),
        "mid": None,
        "final": Decimal("0.8"),
    },
    AssessmentType.HOURS_48: {
        "regular": Decimal("0.2"),
        "mid": Decimal("0.3"),
        "final": Decimal("0.5"),
    },
    AssessmentType.HOURS_64: {
        "regular": Decimal("0.2"),
        "mid": Decimal("0.3"),
        "final": Decimal("0.5"),
    },
}


class ScoreError(BizError):
    """成绩计算异常。"""

    code = "SCORE_CALC_ERROR"
    message = "成绩计算失败"


class IncompleteScoreError(ScoreError):
    """成绩不完整（缺少考核方式或必要成绩），草稿保存时可容忍。"""


class ScoreService:
    """统一成绩计算服务。"""

    @classmethod
    def weights(cls, assessment_type: str | None) -> dict:
        """读取考核权重规则；为空或非法时抛出异常。"""
        if not assessment_type:
            raise IncompleteScoreError(
                "课程未设置考核方式（assessment_type），无法计算总评"
            )
        rule = WEIGHT_RULES.get(assessment_type)
        if rule is None:
            raise ScoreError(f"非法考核方式：{assessment_type}（仅支持 32/48/64）")
        return rule

    @staticmethod
    def _check_range(value: Decimal | None, label: str) -> None:
        if value is not None and not (Decimal("0") <= value <= Decimal("100")):
            raise ScoreError(f"{label}超出范围（0-100）：{value}")

    @classmethod
    def merge_exam_score(
        cls,
        theory: Decimal | None,
        practice: Decimal | None,
        fallback: Decimal | None,
        label: str,
    ) -> Decimal | None:
        """理论+实践成绩合并。

        两者同时存在 → 取平均；同时为空 → 回退 fallback；仅一个存在 → 抛异常。
        """
        if theory is not None and practice is not None:
            cls._check_range(theory, f"{label}理论成绩")
            cls._check_range(practice, f"{label}实践成绩")
            return ((theory + practice) / Decimal("2")).quantize(
                TWO_DEC, ROUND_HALF_UP
            )
        if (theory is None) != (practice is None):
            raise ScoreError(f"{label}理论成绩与实践成绩必须同时提供或同时为空")
        return fallback

    @classmethod
    def compute(cls, course: Course, grade: Grade) -> Decimal:
        """按课程 assessment_type 计算总评，回写总评/绩点/及格标记。

        返回保留两位小数的总评；缺失或非法数据时抛出 ScoreError。
        """
        rule = cls.weights(course.assessment_type)

        regular = grade.regular_score
        cls._check_range(regular, "平时成绩")

        mid = cls.merge_exam_score(
            grade.mid_theory_score, grade.mid_practice_score, grade.mid_score, "期中"
        )
        cls._check_range(mid, "期中成绩")

        final = cls.merge_exam_score(
            grade.final_theory_score,
            grade.final_practice_score,
            grade.final_score,
            "期末",
        )
        cls._check_range(final, "期末成绩")

        # 必要成绩缺失检查
        missing = []
        if regular is None:
            missing.append("平时成绩")
        if final is None:
            missing.append("期末成绩")
        if rule["mid"] is not None and mid is None:
            missing.append("期中成绩")
        if missing:
            raise IncompleteScoreError(f"缺少必要成绩：{'、'.join(missing)}")

        total = regular * rule["regular"] + final * rule["final"]
        if rule["mid"] is not None:
            total += mid * rule["mid"]
        total = total.quantize(TWO_DEC, ROUND_HALF_UP)

        # 回写成绩对象
        grade.total_score = total
        grade.grade_point = score_to_point(total)
        grade.is_passed = total >= PASS_SCORE
        if grade.mid_theory_score is not None and grade.mid_practice_score is not None:
            grade.mid_score = mid
        if (
            grade.final_theory_score is not None
            and grade.final_practice_score is not None
        ):
            grade.final_score = final
        return total

    @classmethod
    def compute_for_draft(cls, course: Course, grade: Grade) -> Decimal | None:
        """草稿保存：成绩不完整时置空总评而不抛异常，其余校验照常。"""
        try:
            return cls.compute(course, grade)
        except IncompleteScoreError:
            grade.total_score = None
            grade.grade_point = None
            grade.is_passed = None
            return None
