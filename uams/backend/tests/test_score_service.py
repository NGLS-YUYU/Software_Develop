"""TASK-003：统一成绩计算服务测试。

覆盖：32/48/64 课时计算、理论+实践合并、100/0 分边界、缺失/非法异常、规则配置。
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


def _course(assessment_type: str | None) -> Course:
    c = Course(
        code="X001", name="测试课程", college_id=1, course_type="REQUIRED",
        credits=Decimal("2.0"), total_hours=48,
    )
    if assessment_type is not None:
        c.assessment_type = assessment_type
    return c


def _grade(
    regular=None, mid=None, final=None,
    mid_theory=None, mid_practice=None,
    final_theory=None, final_practice=None,
) -> Grade:
    return Grade(
        student_id=1, teaching_class_id=1, course_id=1, semester="2026-2027-1",
        credits=Decimal("2.0"),
        regular_score=regular, mid_score=mid, final_score=final,
        mid_theory_score=mid_theory, mid_practice_score=mid_practice,
        final_theory_score=final_theory, final_practice_score=final_practice,
    )


# --- 1~3 按课时计算 ---


def test_32h_course_calculation():
    g = _grade(regular=80, final=90)
    ScoreService.compute(_course(AssessmentType.HOURS_32), g)
    # 80*0.2 + 90*0.8 = 88.00
    assert g.total_score == Decimal("88.00")


def test_48h_course_calculation():
    g = _grade(regular=80, mid=85, final=90)
    ScoreService.compute(_course(AssessmentType.HOURS_48), g)
    # 80*0.2 + 85*0.3 + 90*0.5 = 86.50
    assert g.total_score == Decimal("86.50")


def test_64h_course_calculation():
    g = _grade(regular=70, mid=75, final=80)
    ScoreService.compute(_course(AssessmentType.HOURS_64), g)
    # 70*0.2 + 75*0.3 + 80*0.5 = 76.50
    assert g.total_score == Decimal("76.50")


# --- 4~5 理论+实践合并 ---


def test_mid_theory_practice_merge():
    g = _grade(regular=80, mid_theory=80, mid_practice=90, final=90)
    ScoreService.compute(_course(AssessmentType.HOURS_48), g)
    # mid=(80+90)/2=85；total=80*0.2+85*0.3+90*0.5=86.50
    assert g.total_score == Decimal("86.50")
    assert g.mid_score == Decimal("85.00")  # 合并值回写


def test_final_theory_practice_merge():
    g = _grade(regular=80, mid=85, final_theory=70, final_practice=90)
    ScoreService.compute(_course(AssessmentType.HOURS_48), g)
    # final=(70+90)/2=80；total=80*0.2+85*0.3+80*0.5=81.50
    assert g.total_score == Decimal("81.50")
    assert g.final_score == Decimal("80.00")  # 合并值回写


# --- 6~7 边界 ---


def test_100_boundary():
    g = _grade(regular=100, mid=100, final=100)
    ScoreService.compute(_course(AssessmentType.HOURS_64), g)
    assert g.total_score == Decimal("100.00")


def test_0_boundary():
    g = _grade(regular=0, mid=0, final=0)
    ScoreService.compute(_course(AssessmentType.HOURS_64), g)
    assert g.total_score == Decimal("0.00")


# --- 8~9 异常处理 ---


def test_missing_score_raises():
    """32 课时缺少 final_score → 异常。"""
    g = _grade(regular=80)
    with pytest.raises(IncompleteScoreError):
        ScoreService.compute(_course(AssessmentType.HOURS_32), g)


def test_missing_mid_raises():
    """48 课时缺少 mid_score → 异常。"""
    g = _grade(regular=80, final=90)
    with pytest.raises(IncompleteScoreError):
        ScoreService.compute(_course(AssessmentType.HOURS_48), g)


def test_invalid_assessment_type_raises():
    g = _grade(regular=80, mid=85, final=90)
    with pytest.raises(ScoreError, match="非法考核方式"):
        ScoreService.compute(_course("99"), g)


def test_missing_assessment_type_raises():
    g = _grade(regular=80, mid=85, final=90)
    with pytest.raises(IncompleteScoreError, match="assessment_type"):
        ScoreService.compute(_course(None), g)


def test_theory_practice_incomplete_raises():
    """final_theory 存在而 final_practice 为空 → 异常。"""
    g = _grade(regular=80, mid=85, final_theory=70)
    with pytest.raises(ScoreError, match="必须同时"):
        ScoreService.compute(_course(AssessmentType.HOURS_48), g)


def test_out_of_range_raises():
    g = _grade(regular=101, mid=85, final=90)
    with pytest.raises(ScoreError, match="超出范围"):
        ScoreService.compute(_course(AssessmentType.HOURS_48), g)


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
    result = ScoreService.compute_for_draft(_course(AssessmentType.HOURS_32), g)
    assert result is None
    assert g.total_score is None
    assert g.is_passed is None
