"""FIX-009：课程学时 / 考核结构闭环测试。

覆盖：
- 理论 + 实践 = 总学时（Schema 校验 / Service 校验）
- 考核方式由总学时唯一推导（32→两段式无期中；48/64→三段式有期中），教师/客户端不能自选
- 实践学时 ↔ 实践成绩强关系（Service 层，另见 test_score_service.py）
- 教学班通过 course_id 继承课程考核结构，不另存学时/权重
- 已存在提交/审核成绩的课程禁止修改考核决定属性（学时）
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.exceptions import Conflict, CourseHoursMismatch
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.course import Course
from app.models.grade import Grade, GradeStatus
from app.models.organization import Class, College, Major
from app.models.person import Student, Teacher
from app.models.role import Role, RoleCode, UserRole
from app.models.selection import CourseSelection
from app.models.teaching import TeachingClass, TeachingTask
from app.models.term import AcademicTerm
from app.models.user import User, UserType
from app.schemas.course import CourseCreate
from app.services.assessment import AssessmentProfile, derive_assessment_type, profile_for
from app.services.course import CourseService

client = TestClient(app)
PREFIX = settings.API_V1_PREFIX
LOGIN = f"{PREFIX}/auth/login"
P = "__f9__"
PWD = "f9test123"
SEMESTER = "2026-2027-1"


def auth(username: str, password: str = PWD) -> dict:
    r = client.post(LOGIN, json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# =========================== 纯单元：Schema / 推导 ===========================


def test_schema_rejects_hours_mismatch():
    """FIX-009 §五：理论 + 实践 ≠ 总学时 → Schema 直接拒绝，坏数据到不了 DB。"""
    with pytest.raises(ValidationError, match="必须等于总学时"):
        CourseCreate(
            code="X1", name="测试课程", college_id=1, course_type="REQUIRED",
            credits=Decimal("2.0"), total_hours=32,
            theory_hours=20, practice_hours=8,
        )


def test_schema_accepts_hours_sum():
    c = CourseCreate(
        code="X1", name="测试课程", college_id=1, course_type="REQUIRED",
        credits=Decimal("2.0"), total_hours=32, theory_hours=32, practice_hours=0,
    )
    assert c.theory_hours == 32 and c.practice_hours == 0


def test_derive_assessment_type_boundaries():
    assert derive_assessment_type(32) == "32"
    assert derive_assessment_type(48) == "48"
    assert derive_assessment_type(64) == "64"
    assert derive_assessment_type(40) == "48"  # 32 < 40 <= 48 → 三段式
    assert derive_assessment_type(56) == "64"  # > 48 → 三段式


def test_profile_weights_match_rules():
    """FIX-009 §二/§三：32h 两段式（无期中），48/64h 三段式（有期中）。"""
    p32 = profile_for(Course(total_hours=32, theory_hours=32, practice_hours=0))
    assert p32.has_midterm is False
    assert p32.regular == Decimal("0.2") and p32.mid is None and p32.final == Decimal("0.8")

    p48 = profile_for(Course(total_hours=48, theory_hours=48, practice_hours=0))
    assert p48.has_midterm is True
    assert p48.regular == Decimal("0.2") and p48.mid == Decimal("0.3") and p48.final == Decimal("0.5")

    p64 = profile_for(Course(total_hours=64, theory_hours=64, practice_hours=0))
    assert p64.has_midterm is True


def test_profile_for_derives_from_total_hours_not_stored_type():
    """FIX-009 §十四：考核结构由总学时推导，忽略手工存的 assessment_type。"""
    c = Course(
        code="X1", name="t", college_id=1, course_type="REQUIRED",
        credits=Decimal("2.0"), total_hours=32, theory_hours=16, practice_hours=16,
    )
    c.assessment_type = "64"  # 漂移值，应被忽略
    p = profile_for(c)
    assert isinstance(p, AssessmentProfile)
    assert p.assessment_type == "32"
    assert p.has_midterm is False
    assert p.has_practice is True


# =========================== 数据准备 / 清理 ===========================


def _cleanup() -> None:
    with SessionLocal() as db:
        test_courses = select(Course.id).where(Course.code.like(f"{P}%"))
        test_tcs = select(TeachingClass.id).where(TeachingClass.code.like(f"{P}%"))
        db.execute(delete(Grade).where(Grade.course_id.in_(test_courses)))
        db.execute(delete(CourseSelection).where(
            CourseSelection.teaching_class_id.in_(test_tcs)
        ))
        db.execute(delete(TeachingClass).where(TeachingClass.code.like(f"{P}%")))
        db.execute(delete(AcademicTerm).where(AcademicTerm.name.like(f"{P}%")))
        db.execute(delete(TeachingTask).where(
            TeachingTask.course_id.in_(test_courses)
        ))
        db.execute(delete(Student).where(Student.student_no.like(f"{P}%")))
        db.execute(delete(Teacher).where(Teacher.teacher_no.like(f"{P}%")))
        db.execute(delete(User).where(User.username.like(f"{P}%")))
        db.execute(delete(Class).where(Class.code.like(f"{P}%")))
        db.execute(delete(Major).where(Major.code.like(f"{P}%")))
        db.execute(delete(Course).where(Course.code.like(f"{P}%")))
        db.execute(delete(College).where(College.code.like(f"{P}%")))
        db.commit()


@pytest.fixture
def env():
    """学院 + 专业 + 班级 + 课程(48h 实践8) + 教师 + 学生 + 教学任务 + 学期 + 教学班。"""
    _cleanup()
    with SessionLocal() as db:
        college = College(code=f"{P}college", name="F9学院")
        db.add(college)
        db.flush()
        major = Major(code=f"{P}major", name="F9专业", college_id=college.id)
        db.add(major)
        db.flush()
        klass = Class(code=f"{P}class", name="F9班", major_id=major.id, grade_year=2026)
        db.add(klass)
        db.flush()

        c48p = Course(
            code=f"{P}c48p", name="F9实践课", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("3.0"), total_hours=48,
            theory_hours=40, practice_hours=8, assessment_type="48",
        )
        db.add(c48p)
        db.flush()

        role_teacher = db.execute(
            select(Role).where(Role.code == RoleCode.TEACHER)
        ).scalar_one()
        role_student = db.execute(
            select(Role).where(Role.code == RoleCode.STUDENT)
        ).scalar_one()

        t_u = User(username=f"{P}t", password_hash=hash_password(PWD),
                   real_name="F9教师", user_type=UserType.TEACHER)
        db.add(t_u)
        db.flush()
        db.add(UserRole(user_id=t_u.id, role_id=role_teacher.id))
        db.flush()
        teacher = Teacher(user_id=t_u.id, teacher_no=f"{P}t", college_id=college.id)
        db.add(teacher)
        db.flush()

        s_u = User(username=f"{P}s1", password_hash=hash_password(PWD),
                   real_name="F9学生", user_type=UserType.STUDENT)
        db.add(s_u)
        db.flush()
        db.add(UserRole(user_id=s_u.id, role_id=role_student.id))
        db.flush()
        student = Student(
            user_id=s_u.id, student_no=f"{P}s1", class_id=klass.id,
            major_id=major.id, college_id=college.id, enrollment_year=2026,
        )
        db.add(student)
        db.flush()

        task = TeachingTask(
            semester=SEMESTER, course_id=c48p.id, college_id=college.id,
            status="CONFIRMED",
        )
        db.add(task)
        db.flush()
        term = AcademicTerm(
            name=f"{P}term", academic_year="2095-2096", semester=1,
            start_date=date(2095, 9, 1), end_date=date(2096, 1, 15),
            status="PLANNED",
        )
        db.add(term)
        db.flush()
        tc = TeachingClass(
            code=f"{P}tc", task_id=task.id, course_id=c48p.id,
            semester=SEMESTER, teacher_id=teacher.id, capacity=40, term_id=term.id,
        )
        db.add(tc)
        db.commit()

        yield {
            "college_id": college.id,
            "course_48p_id": c48p.id,
            "tc_id": tc.id,
            "student_id": student.id,
            "t_uname": f"{P}t",
        }
    _cleanup()


# =========================== CourseService（DB） ===========================


def test_service_create_derives_assessment_type(env):
    """FIX-009 §三：创建课程时按总学时推导考核方式，忽略客户端传入值。"""
    with SessionLocal() as db:
        svc = CourseService(db)
        # 客户端强行传 assessment_type="32"，但 total_hours=48 → 应被推导为 "48"
        c = svc.create({
            "code": f"{P}c1", "name": "三段课", "college_id": env["college_id"],
            "course_type": "REQUIRED", "credits": Decimal("3.0"),
            "total_hours": 48, "theory_hours": 48, "practice_hours": 0,
            "assessment_type": "32",
        })
        assert c.assessment_type == "48"


def test_service_create_rejects_hours_mismatch(env):
    with SessionLocal() as db:
        svc = CourseService(db)
        with pytest.raises(CourseHoursMismatch):
            svc.create({
                "code": f"{P}c2", "name": "学时错课", "college_id": env["college_id"],
                "course_type": "REQUIRED", "credits": Decimal("2.0"),
                "total_hours": 32, "theory_hours": 20, "practice_hours": 8,
            })


def test_service_update_recomputes_assessment_type(env):
    with SessionLocal() as db:
        svc = CourseService(db)
        c = svc.create({
            "code": f"{P}c3", "name": "改学时课", "college_id": env["college_id"],
            "course_type": "REQUIRED", "credits": Decimal("2.0"),
            "total_hours": 32, "theory_hours": 32, "practice_hours": 0,
        })
        assert c.assessment_type == "32"
        # 总学时 32 → 48，考核方式应自动变为 48（三段式）
        svc.update(c.id, {"total_hours": 48, "theory_hours": 48, "practice_hours": 0})
        assert c.assessment_type == "48"


def test_service_blocks_hours_change_after_grades(env):
    """FIX-009 §十六：已有提交/审核成绩的课程禁止修改考核决定属性（学时）。"""
    with SessionLocal() as db:
        db.add(Grade(
            student_id=env["student_id"], teaching_class_id=env["tc_id"],
            course_id=env["course_48p_id"], semester=SEMESTER,
            credits=Decimal("3.0"), status=GradeStatus.APPROVED,
        ))
        db.commit()

        svc = CourseService(db)
        with pytest.raises(Conflict, match="不能修改学时"):
            svc.update(env["course_48p_id"], {
                "total_hours": 64, "theory_hours": 56, "practice_hours": 8,
            })


# =========================== 教学班继承（API） ===========================


def test_teaching_class_inherits_course_profile(env):
    """FIX-009 §十五：教学班通过 course_id 继承课程考核结构，不另存学时/权重。"""
    r = client.get(
        f"{PREFIX}/teaching-classes/{env['tc_id']}", headers=auth(env["t_uname"])
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # 课程为 48 学时、实践 8 学时 → 教学班 API 应继承并回显一致结构
    assert body["assessment_type"] == "48"
    assert body["has_midterm"] is True
    assert body["has_practice"] is True
    assert body["total_hours"] == 48
    assert body["theory_hours"] == 40
    assert body["practice_hours"] == 8
