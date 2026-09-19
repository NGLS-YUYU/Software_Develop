"""统一成绩计算服务（TASK-003 / FIX-009）。

所有成绩计算集中于此（CLAUDE.md §21），禁止在 Route / Schema / Model / 前端中计算：
- 课程考核权重规则（``app.services.assessment.WEIGHT_RULES``，唯一来源）
- 考核结构（是否有期中 / 是否有实践）由课程属性推导，不由成绩数据反推
- 期中/期末理论+实践成绩合并
- 理论总评 / 实践总评（侧分总评）
- 补考规则（资格校验 / 替换 / 60 分封顶）
- 成绩总评 / 绩点 / 及格标记

调用链：API → GradeService → ScoreService → 计算结果。

计算口径（DATABASE.md §9.3）：
- 考核结构由 ``Course.total_hours``（期中）与 ``Course.practice_hours``（实践）决定
- 理论总评 = 平时×w.regular + 期中理论×w.mid + 期末理论×w.final
- 实践总评 = 平时×w.regular + 期中实践×w.mid + 期末实践×w.final（仅实践课）
- 成绩总评 = 实践课取 (理论总评 + 实践总评) / 2，否则 = 理论总评
- 补考：只允许对应期末分项 < 60 时录入；补考成绩替换对应期末分项重算；
  补考通过（≥60）的一侧总评按 60 封顶；结果仍由成绩总评 ≥ 60 判定
"""

from decimal import ROUND_HALF_UP, Decimal

from app.core.exceptions import BizError
from app.models.course import Course
from app.models.grade import PASS_SCORE, Grade, score_to_point
from app.services.assessment import WEIGHT_RULES, AssessmentProfile, profile_for

TWO_DEC = Decimal("0.01")


class ScoreError(BizError):
    """成绩计算异常。"""

    code = "SCORE_CALC_ERROR"
    message = "成绩计算失败"


class IncompleteScoreError(ScoreError):
    """成绩不完整（缺少必要成绩），草稿保存时可容忍。"""


class ScoreService:
    """统一成绩计算服务。"""

    # 权重唯一来源（test_score_consistency 等按此对照 DATABASE.md §9.3）
    WEIGHT_RULES = WEIGHT_RULES

    @classmethod
    def weights(cls, assessment_type: str | None) -> dict:
        """读取考核权重规则（兼容旧调用）；为空或非法时抛出异常。"""
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
    def _check_practice_fields(cls, profile: AssessmentProfile, grade: Grade) -> None:
        """实践学时 ↔ 实践成绩强关系（FIX-009 §七）。

        ``practice_hours == 0`` → 无实践考试，禁止出现任何实践成绩字段。
        ``practice_hours > 0`` 时缺失实践成绩由后续必要性检查处理（草稿可容忍）。
        """
        any_practice = (
            grade.mid_practice_score is not None
            or grade.final_practice_score is not None
            or grade.practice_makeup_score is not None
        )
        if not profile.has_practice and any_practice:
            raise ScoreError("课程无实践学时，不能录入实践成绩")

    @classmethod
    def _resolve_stage(
        cls, profile: AssessmentProfile, grade: Grade, label: str
    ) -> tuple[Decimal | None, Decimal | None]:
        """解析某阶段（期中/期末）的理论与实践原始分（FIX-009 §七）。

        返回 ``(theory_or_merged, practice_or_None)``：
        - 实践课：要求理论+实践成对；合并字段（mid_score/final_score）不作为输入，
          只作为计算结果回显。
        - 非实践课：只能使用合并字段，禁止出现理论/实践拆分。
        """
        if label == "期中":
            theory, practice, merged = (
                grade.mid_theory_score, grade.mid_practice_score, grade.mid_score
            )
        else:
            theory, practice, merged = (
                grade.final_theory_score, grade.final_practice_score, grade.final_score
            )

        if profile.has_practice:
            if theory is None and practice is None:
                # 实践课必须录入实践成绩，不接受只填合并字段
                if merged is not None:
                    raise ScoreError(
                        f"课程含实践学时，{label}必须分别录入理论/实践成绩"
                    )
                return None, None
            if (theory is None) != (practice is None):
                raise ScoreError(f"{label}理论成绩与实践成绩必须同时提供或同时为空")
            cls._check_range(theory, f"{label}理论成绩")
            cls._check_range(practice, f"{label}实践成绩")
            return theory, practice
        else:
            if theory is not None or practice is not None:
                raise ScoreError(f"课程无实践学时，不能录入{label}理论/实践拆分成绩")
            cls._check_range(merged, f"{label}成绩")
            return merged, None

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
        """按课程属性（总学时/实践学时）计算理论/实践总评与成绩总评，回写全部结果。

        返回保留两位小数的成绩总评；缺失或非法数据时抛出 ScoreError。
        """
        profile = profile_for(course)
        rule = profile.weights

        regular = grade.regular_score
        cls._check_range(regular, "平时成绩")

        # 实践学时 ↔ 实践成绩强关系（FIX-009 §七）
        cls._check_practice_fields(profile, grade)

        # 期中：无期中（32h）不得录入；有期中按 理论/实践 或 合并口径 解析
        if profile.has_midterm:
            mid_theory, mid_practice = cls._resolve_stage(profile, grade, "期中")
        else:
            if any(
                x is not None
                for x in (grade.mid_score, grade.mid_theory_score, grade.mid_practice_score)
            ):
                raise ScoreError("32 学时课程无期中考试，不能录入期中成绩")
            mid_theory = mid_practice = None

        final_theory, final_practice = cls._resolve_stage(profile, grade, "期末")

        # 补考资格校验（只针对不及格的期末分项）
        cls._check_makeup(grade)

        # 必要成绩缺失检查
        missing = []
        if regular is None:
            missing.append("平时成绩")
        if profile.has_midterm and mid_theory is None:
            missing.append("期中成绩")
        if final_theory is None:
            missing.append("期末成绩")
        if profile.has_practice and final_practice is None:
            missing.append("期末实践成绩")
        if missing:
            raise IncompleteScoreError(f"缺少必要成绩：{'、'.join(missing)}")

        # 期末分项：补考成绩优先替换（补考只针对不及格的期末分项）
        final_theory_eff = (
            grade.theory_makeup_score
            if grade.theory_makeup_score is not None
            else final_theory
        )
        final_practice_eff = (
            grade.practice_makeup_score
            if grade.practice_makeup_score is not None
            else final_practice
        )

        theory_total = cls._side_total(rule, regular, mid_theory, final_theory_eff)
        practice_total = (
            cls._side_total(rule, regular, mid_practice, final_practice_eff)
            if profile.has_practice
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
        # 合并值回写（实践课：理论/实践平均写入合并字段便于展示）
        if profile.has_midterm:
            if mid_practice is not None:
                grade.mid_score = ((mid_theory + mid_practice) / Decimal("2")).quantize(
                    TWO_DEC, ROUND_HALF_UP
                )
            else:
                grade.mid_score = mid_theory
        if final_practice is not None:
            grade.final_score = ((final_theory + final_practice) / Decimal("2")).quantize(
                TWO_DEC, ROUND_HALF_UP
            )
        else:
            grade.final_score = final_theory
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
