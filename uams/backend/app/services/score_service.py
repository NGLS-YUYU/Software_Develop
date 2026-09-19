"""统一成绩计算服务（TASK-003）。

所有成绩计算集中于此（CLAUDE.md §21），禁止在 Route / Schema / Model / 前端中计算：
- 课程考核权重规则（WEIGHT_RULES）
- 期中/期末理论+实践成绩合并
- 理论总评 / 实践总评（侧分总评）
- 补考规则（资格校验 / 替换 / 60 分封顶）
- 成绩总评 / 绩点 / 及格标记

调用链：API → GradeService → ScoreService → 计算结果。

计算口径（DATABASE.md §9.3）：
- 理论总评 = 平时×w.regular + 期中理论×w.mid + 期末理论×w.final
- 实践总评 = 平时×w.regular + 期中实践×w.mid + 期末实践×w.final（无实践拆分时为空）
- 成绩总评 = 存在实践拆分时 (理论总评 + 实践总评) / 2，否则 = 理论总评
  （与「期中/期末先取理论+实践平均再加权」口径数学等价）
- 补考：只允许对应期末分项 < 60 时录入；补考成绩替换对应期末分项重算；
  补考通过（≥60）的一侧总评按 60 封顶；结果仍由成绩总评 ≥ 60 判定
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
    def _side_total(
        cls,
        rule: dict,
        regular: Decimal,
        mid: Decimal,
        final: Decimal,
    ) -> Decimal:
        """单侧（理论/实践）加权总评：平时 + 期中 + 期末按课程权重。"""
        total = regular * rule["regular"] + final * rule["final"]
        if rule["mid"] is not None:
            total += mid * rule["mid"]
        return total.quantize(TWO_DEC, ROUND_HALF_UP)

    @classmethod
    def _check_makeup(cls, grade: Grade) -> None:
        """补考资格校验：补考成绩只允许对应期末分项不及格时录入。"""
        cls._check_range(grade.theory_makeup_score, "理论补考成绩")
        cls._check_range(grade.practice_makeup_score, "实践补考成绩")
        if grade.theory_makeup_score is not None:
            base = (
                grade.final_theory_score
                if grade.final_theory_score is not None
                else grade.final_score
            )
            if base is None:
                raise ScoreError("理论补考成绩要求期末理论成绩已录入")
            if base >= PASS_SCORE:
                raise ScoreError("理论补考只允许在期末理论成绩不及格时录入")
        if grade.practice_makeup_score is not None:
            if grade.final_practice_score is None:
                raise ScoreError("实践补考成绩要求期末实践成绩已录入")
            if grade.final_practice_score >= PASS_SCORE:
                raise ScoreError("实践补考只允许在期末实践成绩不及格时录入")

    @classmethod
    def compute(cls, course: Course, grade: Grade) -> Decimal:
        """按课程 assessment_type 计算理论/实践总评与成绩总评，回写全部计算结果。

        返回保留两位小数的成绩总评；缺失或非法数据时抛出 ScoreError。
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

        # 补考资格校验（只针对不及格的期末分项）
        cls._check_makeup(grade)

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

        # 理论/实践侧原始分：未拆分时期中并入合并口径，期末取补考成绩优先
        theory_mid = (
            grade.mid_theory_score
            if grade.mid_theory_score is not None
            else grade.mid_score
        )
        practice_mid = (
            grade.mid_practice_score
            if grade.mid_practice_score is not None
            else grade.mid_score
        )
        final_theory = (
            grade.theory_makeup_score
            if grade.theory_makeup_score is not None
            else (
                grade.final_theory_score
                if grade.final_theory_score is not None
                else grade.final_score
            )
        )
        final_practice = (
            grade.practice_makeup_score
            if grade.practice_makeup_score is not None
            else (
                grade.final_practice_score
                if grade.final_practice_score is not None
                else grade.final_score
            )
        )
        has_practice = (
            grade.mid_practice_score is not None
            or grade.final_practice_score is not None
            or grade.practice_makeup_score is not None
        )

        theory_total = cls._side_total(rule, regular, theory_mid, final_theory)
        practice_total = (
            cls._side_total(rule, regular, practice_mid, final_practice)
            if has_practice
            else None
        )

        # 补考通过（≥60）的一侧，总评按 60 封顶（补考最高记 60）
        if (
            grade.theory_makeup_score is not None
            and grade.theory_makeup_score >= PASS_SCORE
        ):
            theory_total = min(theory_total, PASS_SCORE)
        if (
            practice_total is not None
            and grade.practice_makeup_score is not None
            and grade.practice_makeup_score >= PASS_SCORE
        ):
            practice_total = min(practice_total, PASS_SCORE)

        total = (
            ((theory_total + practice_total) / Decimal("2")).quantize(
                TWO_DEC, ROUND_HALF_UP
            )
            if practice_total is not None
            else theory_total
        )

        # 回写成绩对象
        grade.theory_total_score = theory_total
        grade.practice_total_score = practice_total
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
        """草稿保存：成绩不完整时置空全部计算结果而不抛异常，其余校验照常。"""
        try:
            return cls.compute(course, grade)
        except IncompleteScoreError:
            grade.theory_total_score = None
            grade.practice_total_score = None
            grade.total_score = None
            grade.grade_point = None
            grade.is_passed = None
            return None
