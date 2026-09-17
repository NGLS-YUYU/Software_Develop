"""TASK-004：GPA 综合评价与排名测试。

覆盖：百分制→绩点、单课程贡献、学分加权 GPA、班级/专业排名、异常处理、
以及「Grade 表未新增 GPA 字段」的解耦约束。
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, text

from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models.course import Course
from app.models.grade import Grade, GradeStatus
from app.models.organization import Class, College, Major
from app.models.person import Student
from app.models.teaching import TeachingClass, TeachingTask
from app.models.term import AcademicTerm
from app.models.user import User, UserType
from app.services.gpa_service import (
    GpaService,
    NoCreditError,
    NoGradesError,
    ZeroCreditError,
    EmptyScoreError,
    course_grade_points,
    student_gpa,
    to_grade_point,
)
from app.services.ranking_service import RankingService

SEMESTER = "2026-2027-1"


# --- 1~5 百分制 → 绩点 ---


def test_90_score_gpa():
    assert to_grade_point(90) == Decimal("4.0")


def test_85_score_gpa():
    assert to_grade_point(85) == Decimal("3.5")


def test_80_score_gpa():
    assert to_grade_point(80) == Decimal("3.0")


def test_60_score_gpa():
    assert to_grade_point(60) == Decimal("2.0")


def test_fail_score_gpa():
    assert to_grade_point(59) == Decimal("0.0")


def test_single_course_contribution():
    # 3 学分、90 分 → 绩点 4.0 → 贡献 12.00
    assert course_grade_points(3, 90) == Decimal("12.00")


# --- 6~7 学分加权 GPA ---


def test_weighted_gpa_multiple_courses():
    gpa = student_gpa([(2, 90), (2, 85), (2, 80)])
    # (4.0*2 + 3.5*2 + 3.0*2) / 6 = 21/6 = 3.50
    assert gpa == Decimal("3.50")


def test_different_credit_influence():
    gpa = student_gpa([(4, 90), (1, 60)])
    # (4.0*4 + 2.0*1) / 5 = 18/5 = 3.60；高分课程学分更大 → 拉高 GPA
    assert gpa == Decimal("3.60")


# --- 10~11 异常 ---


def test_no_grades_error():
    with pytest.raises(NoGradesError):
        student_gpa([])


def test_no_credit_error():
    with pytest.raises(NoCreditError):
        student_gpa([(None, 90)])


def test_zero_credit_error():
    with pytest.raises(ZeroCreditError):
        student_gpa([(0, 90)])


def test_empty_score_error():
    with pytest.raises(EmptyScoreError):
        student_gpa([(3, None)])


# --- 8~9 排名（DB 集成）---

TEST_PREFIX = "__gpa_test__"


def _cleanup():
    with SessionLocal() as db:
        db.execute(
            delete(Grade).where(
                Grade.course_id.in_(
                    select(Course.id).where(Course.code.like(f"{TEST_PREFIX}course%"))
                )
            )
        )
        db.execute(delete(TeachingClass).where(TeachingClass.code.like(f"{TEST_PREFIX}tc%")))
        db.execute(delete(AcademicTerm).where(AcademicTerm.name.like(f"{TEST_PREFIX}term%")))
        db.execute(
            delete(TeachingTask).where(
                TeachingTask.course_id.in_(
                    select(Course.id).where(Course.code.like(f"{TEST_PREFIX}course%"))
                )
            )
        )
        db.execute(delete(Student).where(Student.student_no.like(f"{TEST_PREFIX}s%")))
        db.execute(delete(User).where(User.username.like(f"{TEST_PREFIX}s%")))
        db.execute(delete(Class).where(Class.code.like(f"{TEST_PREFIX}class%")))
        db.execute(delete(Major).where(Major.code.like(f"{TEST_PREFIX}major%")))
        db.execute(delete(Course).where(Course.code.like(f"{TEST_PREFIX}course%")))
        db.execute(delete(College).where(College.code.like(f"{TEST_PREFIX}college%")))
        db.commit()


@pytest.fixture
def ranking_env():
    """1 学院 / 1 专业 / 2 班级 / 3 学生 / 1 教学班 / 3 成绩，用完清理。"""
    _cleanup()
    with SessionLocal() as db:
        college = College(code=f"{TEST_PREFIX}college", name="GPA测试学院")
        db.add(college)
        db.flush()
        major = Major(
            code=f"{TEST_PREFIX}major", name="GPA测试专业", college_id=college.id
        )
        db.add(major)
        db.flush()
        cls_a = Class(
            code=f"{TEST_PREFIX}class_a", name="GPA测试班A",
            major_id=major.id, grade_year=2026,
        )
        cls_b = Class(
            code=f"{TEST_PREFIX}class_b", name="GPA测试班B",
            major_id=major.id, grade_year=2026,
        )
        db.add_all([cls_a, cls_b])
        db.flush()

        course = Course(
            code=f"{TEST_PREFIX}course", name="GPA测试课程", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("3.0"), total_hours=48,
            assessment_type="48",
        )
        db.add(course)
        db.flush()
        task = TeachingTask(
            semester=SEMESTER, course_id=course.id, college_id=college.id
        )
        db.add(task)
        db.flush()
        term = AcademicTerm(
            name=f"{TEST_PREFIX}term", academic_year="2101-2102", semester=1,
            start_date=date(2101, 9, 1), end_date=date(2102, 1, 15),
            status="PLANNED",
        )
        db.add(term)
        db.flush()
        tc = TeachingClass(
            code=f"{TEST_PREFIX}tc", task_id=task.id, course_id=course.id,
            semester=SEMESTER, capacity=40, term_id=term.id,
        )
        db.add(tc)
        db.flush()

        students = []
        for i, (no, cls_id) in enumerate(
            [(f"{TEST_PREFIX}s01", cls_a.id), (f"{TEST_PREFIX}s02", cls_a.id),
             (f"{TEST_PREFIX}s03", cls_b.id)]
        ):
            user = User(
                username=no, password_hash=hash_password("x123456"),
                real_name=f"GPA学生{i + 1}", user_type=UserType.STUDENT,
            )
            db.add(user)
            db.flush()
            stu = Student(
                user_id=user.id, student_no=no, class_id=cls_id,
                major_id=major.id, college_id=college.id, enrollment_year=2026,
            )
            db.add(stu)
            db.flush()
            students.append(stu)

        # 单课程成绩：S1=90→4.0，S2=85→3.5，S3=80→3.0
        for stu, score in zip(students, [90, 85, 80]):
            db.add(
                Grade(
                    student_id=stu.id, teaching_class_id=tc.id, course_id=course.id,
                    semester=SEMESTER, credits=course.credits,
                    regular_score=Decimal(score), total_score=Decimal(score),
                    status=GradeStatus.APPROVED,
                )
            )
        db.commit()

        yield {
            "class_a": cls_a.id, "class_b": cls_b.id, "major": major.id,
            "s1": students[0].id, "s2": students[1].id, "s3": students[2].id,
        }
    _cleanup()


def test_class_ranking(ranking_env):
    with SessionLocal() as db:
        rows = RankingService(db).class_ranking(ranking_env["class_a"])
    assert [r.student_id for r in rows] == [ranking_env["s1"], ranking_env["s2"]]
    assert rows[0].gpa == Decimal("4.00") and rows[0].ranking == 1
    assert rows[1].gpa == Decimal("3.50") and rows[1].ranking == 2
    assert rows[0].student_name == "GPA学生1"


def test_major_ranking(ranking_env):
    with SessionLocal() as db:
        rows = RankingService(db).major_ranking(ranking_env["major"])
    assert [r.student_id for r in rows] == [
        ranking_env["s1"], ranking_env["s2"], ranking_env["s3"],
    ]
    assert [r.ranking for r in rows] == [1, 2, 3]
    assert [r.gpa for r in rows] == [
        Decimal("4.00"), Decimal("3.50"), Decimal("3.00"),
    ]


def test_gpa_service_query(ranking_env):
    """GpaService.gpa_of 通过 APPROVED 成绩实时计算。"""
    with SessionLocal() as db:
        assert GpaService(db).gpa_of(ranking_env["s1"]) == Decimal("4.00")
        with pytest.raises(NoGradesError):
            GpaService(db).gpa_of(ranking_env["s3"] + 9999)  # 不存在 → 无成绩


# --- 12 解耦约束：Grade 表未新增 GPA 字段 ---


def test_grade_table_has_no_gpa_field():
    with engine.connect() as conn:
        cols = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'grades'"
                )
            )
        }
    assert "gpa" not in cols
    assert "ranking" not in cols
