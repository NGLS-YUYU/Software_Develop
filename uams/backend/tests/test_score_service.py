"""TASK-003：统一成绩计算服务测试。

覆盖：32/48/64 课时计算（含 20/30/50 权重回归）、理论+实践合并、
理论/实践侧总评、补考（资格校验/替换/60 封顶）、100/0 分边界、
缺失/非法异常、草稿容错、规则配置、考核结构由课程学时推导（FIX-009）。

FIX-009 关键变化：
- 考核结构（是否有期中/实践）由 ``Course.total_hours`` / ``Course.practice_hours``
  推导，不再信任手工存的 ``assessment_type``，也不再由成绩数据反推课程属性。
"""

from decimal import Decimal

import pytest

from app.models.course import AssessmentType, Course
from app.models.grade import Grade
from app.services.score_service import (
    WEIGHT_RULES,
    IncompleteScoreError,
    ScoreError,
    ScoreService,
)


def _course(total_hours: int, practice_hours: int = 0) -> Course:
    """按总学时/实践学时构造课程（考核结构由 total_hours 推导，无需 assessment_type）。"""
    return Course(
        code="X001", name="测试课程", college_id=1, course_type="REQUIRED",
        credits=Decimal("2.0"), total_hours=total_hours,
        theory_hours=total_hours - practice_hours, practice_hours=practice_hours,
    )


def _grade(
    regular=None, mid=None, final=None,
    mid_theory=None, mid_practice=None,
    final_theory=None, final_practice=None,
    theory_makeup=None, practice_makeup=None,
) -> Grade:
    return Grade(
        student_id=1, teaching_class_id=1, course_id=1, semester="2026-2027-1",
        credits=Decimal("2.0"),
        regular_score=regular, mid_score=mid, final_score=final,
        mid_theory_score=mid_theory, mid_practice_score=mid_practice,
        final_theory_score=final_theory, final_practice_score=final_practice,
        theory_makeup_score=theory_makeup, practice_makeup_score=practice_makeup,
    )


# --- 1~3 按课时计算 ---


def test_32h_course_calculation():
    g = _grade(regular=80, final=90)
    ScoreService.compute(_course(32), g)
    # 80*0.2 + 90*0.8 = 88.00
    assert g.total_score == Decimal("88.00")


def test_32h_legacy_weight_regression():
    """FIX-008 回归：32 学时「平时 87 / 期末 56」→ 62.20。

    已删除的课程级权重（regular_weight=0.4 / final_weight=0.6）会算出 68.40；
    本用例锁定 WEIGHT_RULES 为唯一口径。
    """
    g = _grade(regular=87, final=56)
    ScoreService.compute(_course(32), g)
    assert g.total_score == Decimal("62.20")
    assert g.total_score != Decimal("68.40")
    assert g.grade_point == Decimal("1.00")  # 60~64 → 1.0


def test_48h_course_calculation():
    g = _grade(regular=80, mid=85, final=90)
    ScoreService.compute(_course(48), g)
    # 80*0.2 + 85*0.3 + 90*0.5 = 86.50
    assert g.total_score == Decimal("86.50")


def test_64h_course_calculation():
    g = _grade(regular=70, mid=75, final=80)
    ScoreService.compute(_course(64), g)
    # 70*0.2 + 75*0.3 + 80*0.5 = 76.50
    assert g.total_score == Decimal("76.50")


def test_64h_legacy_weight_regression():
    """64 学时「平时 80 / 期中 70 / 期末 90」→ 82.00（20/30/50）。

    旧「40%平时 + 60%期末」口径会算出 86.00；本用例锁定三要素权重口径。
    """
    g = _grade(regular=80, mid=70, final=90)
    ScoreService.compute(_course(64), g)
    assert g.total_score == Decimal("82.00")
    assert g.total_score != Decimal("86.00")


# --- 4~5 理论+实践合并（实践课：拆分录入，合并值回写） ---


def test_mid_theory_practice_merge():
    g = _grade(regular=80, mid_theory=80, mid_practice=90,
               final_theory=90, final_practice=90)
    ScoreService.compute(_course(48, practice_hours=8), g)
    # mid=(80+90)/2=85；final=(90+90)/2=90；total=80*0.2+85*0.3+90*0.5=86.50
    assert g.total_score == Decimal("86.50")
    assert g.mid_score == Decimal("85.00")  # 合并值回写


def test_final_theory_practice_merge():
    g = _grade(regular=80, mid_theory=85, mid_practice=85,
               final_theory=70, final_practice=90)
    ScoreService.compute(_course(48, practice_hours=8), g)
    # final=(70+90)/2=80；total=80*0.2+85*0.3+80*0.5=81.50
    assert g.total_score == Decimal("81.50")
    assert g.final_score == Decimal("80.00")  # 合并值回写


# --- 4a 理论/实践侧总评 ---


def test_side_totals_theory_practice_split():
    """理论总评/实践总评分开计算，成绩总评取两侧平均。

    平时 80 / 期中理论 80 / 期中实践 90 / 期末理论 70 / 期末实践 90：
      理论总评 = 80*0.2 + 80*0.3 + 70*0.5 = 75.00
      实践总评 = 80*0.2 + 90*0.3 + 90*0.5 = 88.00
      成绩总评 = (75.00 + 88.00) / 2 = 81.50
    """
    g = _grade(regular=80, mid_theory=80, mid_practice=90,
               final_theory=70, final_practice=90)
    ScoreService.compute(_course(48, practice_hours=8), g)
    assert g.theory_total_score == Decimal("75.00")
    assert g.practice_total_score == Decimal("88.00")
    assert g.total_score == Decimal("81.50")
    assert g.mid_score == Decimal("85.00")
    assert g.final_score == Decimal("80.00")


def test_side_total_without_practice_split():
    """无实践拆分的课程：理论总评 = 成绩总评，实践总评为空。"""
    g = _grade(regular=80, mid=85, final=90)
    ScoreService.compute(_course(48), g)
    assert g.theory_total_score == Decimal("86.50")
    assert g.practice_total_score is None
    assert g.total_score == Decimal("86.50")


def test_32h_side_total_no_mid():
    g = _grade(regular=80, final=90)
    ScoreService.compute(_course(32), g)
    assert g.theory_total_score == Decimal("88.00")
    assert g.practice_total_score is None


# --- 4b 补考 ---


def test_makeup_replaces_failed_final_and_caps_total():
    """32 学时：平时 60 / 期末 55（不及格）/ 理论补考 80。

    补考替换期末重算：60*0.2 + 80*0.8 = 76.00 → 补考通过，理论总评按 60 封顶
    → 成绩总评 60.00，绩点 1.0，通过。
    """
    g = _grade(regular=60, final=55, theory_makeup=80)
    ScoreService.compute(_course(32), g)
    assert g.theory_total_score == Decimal("60.00")
    assert g.total_score == Decimal("60.00")
    assert g.grade_point == Decimal("1.0")
    assert g.is_passed is True


def test_makeup_below_60_still_fails():
    """补考 40 分：60*0.2 + 40*0.8 = 44.00，不封顶、不及格。"""
    g = _grade(regular=60, final=55, theory_makeup=40)
    ScoreService.compute(_course(32), g)
    assert g.theory_total_score == Decimal("44.00")
    assert g.total_score == Decimal("44.00")
    assert g.grade_point == Decimal("0.0")
    assert g.is_passed is False


def test_makeup_rejected_when_final_passed():
    """期末 60（已及格）仍录补考 → 拒绝。"""
    g = _grade(regular=60, final=60, theory_makeup=80)
    with pytest.raises(ScoreError, match="不及格"):
        ScoreService.compute(_course(32), g)


def test_makeup_rejected_without_final():
    """期末未录入时录补考 → 拒绝。"""
    g = _grade(regular=60, theory_makeup=80)
    with pytest.raises(ScoreError, match="已录入"):
        ScoreService.compute(_course(32), g)


def test_split_side_makeup_caps_only_remediated_side():
    """48 学时理论+实践：期末理论 55（不及格）/ 期末实践 70，理论补考 90。

      理论总评 = 80*0.2 + 85*0.3 + 90*0.5 = 86.50 → 补考通过封顶 60.00
      实践总评 = 80*0.2 + 85*0.3 + 70*0.5 = 76.50（不受封顶影响）
      成绩总评 = (60.00 + 76.50) / 2 = 68.25
    """
    g = _grade(regular=80, mid_theory=85, mid_practice=85,
               final_theory=55, final_practice=70, theory_makeup=90)
    ScoreService.compute(_course(48, practice_hours=8), g)
    assert g.theory_total_score == Decimal("60.00")
    assert g.practice_total_score == Decimal("76.50")
    assert g.total_score == Decimal("68.25")
    assert g.is_passed is True


def test_practice_makeup_requires_practice_final():
    """实践补考要求期末实践成绩已录入。"""
    g = _grade(regular=60, practice_makeup=80)
    with pytest.raises(ScoreError, match="期末实践"):
        ScoreService.compute(_course(48, practice_hours=8), g)


def test_makeup_out_of_range_raises():
    g = _grade(regular=60, final=55, theory_makeup=101)
    with pytest.raises(ScoreError, match="超出范围"):
        ScoreService.compute(_course(32), g)


# --- 6~7 边界 ---


def test_100_boundary():
    g = _grade(regular=100, mid=100, final=100)
    ScoreService.compute(_course(64), g)
    assert g.total_score == Decimal("100.00")


def test_0_boundary():
    g = _grade(regular=0, mid=0, final=0)
    ScoreService.compute(_course(64), g)
    assert g.total_score == Decimal("0.00")


# --- 8~9 异常处理 ---


def test_missing_score_raises():
    """32 课时缺少 final_score → 异常。"""
    g = _grade(regular=80)
    with pytest.raises(IncompleteScoreError):
        ScoreService.compute(_course(32), g)


def test_missing_mid_raises():
    """48 课时缺少 mid_score → 异常。"""
    g = _grade(regular=80, final=90)
    with pytest.raises(IncompleteScoreError):
        ScoreService.compute(_course(48), g)


def test_assessment_type_derived_from_total_hours():
    """FIX-009：考核结构由总学时推导，不信任手工存的 assessment_type。

    即使把 assessment_type 硬写成 "64"，32 学时课程仍按两段式（无期中）计算，
    且录入期中成绩会被拒绝。
    """
    c = _course(32)
    c.assessment_type = "64"  # 漂移值，应被忽略
    g = _grade(regular=80, final=90)
    ScoreService.compute(c, g)
    assert g.total_score == Decimal("88.00")  # 20/80，非三段式
    # 且 32 学时课程不能录期中
    g2 = _grade(regular=80, mid=85, final=90)
    with pytest.raises(ScoreError, match="无期中"):
        ScoreService.compute(c, g2)


def test_assessment_type_not_required():
    """FIX-009：assessment_type 无需手工维护，未设置时仍能按总学时计算。"""
    c = _course(64)  # 不设置 assessment_type
    g = _grade(regular=70, mid=75, final=80)
    ScoreService.compute(c, g)
    assert g.total_score == Decimal("76.50")


def test_theory_practice_incomplete_raises():
    """实践课：final_theory 存在而 final_practice 为空 → 异常。"""
    g = _grade(regular=80, mid_theory=80, mid_practice=80, final_theory=70)
    with pytest.raises(ScoreError, match="必须同时"):
        ScoreService.compute(_course(48, practice_hours=8), g)


def test_out_of_range_raises():
    g = _grade(regular=101, mid=85, final=90)
    with pytest.raises(ScoreError, match="超出范围"):
        ScoreService.compute(_course(48), g)


# --- FIX-009 §七：实践学时 ↔ 实践成绩强关系 ---


def test_practice_scores_forbidden_without_practice_hours():
    """practice_hours=0 时禁止录入任何实践成绩字段。"""
    g = _grade(regular=80, mid=85, final_theory=70, final_practice=90)
    with pytest.raises(ScoreError, match="无实践学时"):
        ScoreService.compute(_course(48), g)


def test_practice_scores_required_with_practice_hours():
    """practice_hours>0 时缺失期末实践成绩 → 不完整（IncompleteScoreError）。"""
    # 期中理论/实践齐全，但期末理论/实践都缺失 → 缺少必要成绩
    g = _grade(regular=80, mid_theory=80, mid_practice=80)
    with pytest.raises(IncompleteScoreError, match="期末实践"):
        ScoreService.compute(_course(48, practice_hours=8), g)


# --- 10 规则配置读取 ---


def test_weight_rules_configured():
    two_part = {"regular": Decimal("0.2"), "mid": None, "final": Decimal("0.8")}
    three_part = {
        "regular": Decimal("0.2"), "mid": Decimal("0.3"), "final": Decimal("0.5"),
    }
    assert WEIGHT_RULES[AssessmentType.HOURS_32] == two_part
    assert WEIGHT_RULES[AssessmentType.HOURS_48] == three_part
    assert WEIGHT_RULES[AssessmentType.HOURS_64] == three_part


def test_draft_tolerates_incomplete():
    """草稿保存：成绩不完整时置空总评而不抛异常。"""
    g = _grade(regular=80)  # 缺 final
    result = ScoreService.compute_for_draft(_course(32), g)
    assert result is None
    assert g.total_score is None
    assert g.is_passed is None


def test_draft_incomplete_nulls_side_totals():
    """草稿不完整时理论/实践总评也必须置空，避免残留旧计算结果。"""
    g = _grade(regular=80, mid=85, final=90)
    ScoreService.compute(_course(48), g)
    assert g.theory_total_score == Decimal("86.50")  # 先完整算一次

    g.final_score = None  # 清空期末 → 缺少必要成绩
    result = ScoreService.compute_for_draft(_course(48), g)
    assert result is None
    assert g.theory_total_score is None
    assert g.practice_total_score is None
    assert g.total_score is None
    assert g.grade_point is None
