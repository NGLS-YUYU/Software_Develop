"""TASK-010：基础数据 Excel 批量导入测试。

覆盖：学生/课程/成绩三类导入、模板下载、文件格式校验、数据校验、
业务关联校验、错误行报告、权限控制、成绩状态限制、ScoreService 计算复用、
GPA/排名不落库，以及 TASK-005~TASK-009 回归。
"""

import io
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import delete, or_, select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.course import Course
from app.models.grade import Grade, GradeStatus
from app.models.organization import Class, College, Major
from app.models.person import Student, Teacher
from app.models.role import Role, RoleCode, UserRole
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import Schedule, TeachingClass, TeachingTask
from app.models.term import AcademicTerm
from app.models.user import User, UserType

client = TestClient(app)
PREFIX = settings.API_V1_PREFIX
LOGIN = f"{PREFIX}/auth/login"

P = "__t10__"
PWD = "t10test123"
ADMIN_PWD = "admin123"
S1 = "2098-2098-1"  # 独立学期，避免与演示数据及其他测试冲突

STUDENT_HDRS = ["student_no", "name", "username", "college", "major", "class_name"]
COURSE_HDRS = [
    "course_code", "course_name", "college", "credits", "total_hours",
    "course_type", "assessment_type",
]
GRADE_HDRS = [
    "student_no", "teaching_class_code",
    "regular_score", "mid_score", "final_score",
    "mid_theory_score", "mid_practice_score",
    "final_theory_score", "final_practice_score",
]


def auth(username: str, password: str = PWD) -> dict:
    r = client.post(LOGIN, json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def admin_auth() -> dict:
    return auth("admin", ADMIN_PWD)


def _xlsx(headers, rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _post_file(client_, path, headers, rows, auth_headers, filename="data.xlsx"):
    data = _xlsx(headers, rows)
    return client_.post(
        path,
        files={
            "file": (
                filename,
                data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=auth_headers,
    )


def _cleanup() -> None:
    with SessionLocal() as db:
        test_courses = select(Course.id).where(Course.code.like(f"{P}%"))
        test_tcs = select(TeachingClass.id).where(TeachingClass.code.like(f"{P}%"))
        test_students = select(Student.id).where(Student.student_no.like(f"{P}%"))
        db.execute(delete(Grade).where(or_(
            Grade.course_id.in_(test_courses),
            Grade.student_id.in_(test_students),
            Grade.teaching_class_id.in_(test_tcs),
        )))
        db.execute(delete(CourseSelection).where(or_(
            CourseSelection.teaching_class_id.in_(test_tcs),
            CourseSelection.student_id.in_(test_students),
        )))
        db.execute(delete(Schedule).where(Schedule.teaching_class_id.in_(test_tcs)))
        db.execute(delete(TeachingClass).where(TeachingClass.code.like(f"{P}%")))
        db.execute(delete(AcademicTerm).where(AcademicTerm.name.like(f"{P}%")))
        db.execute(delete(TeachingTask).where(TeachingTask.course_id.in_(test_courses)))
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
    """1 学院 / 2 专业 / 2 行政班 / 1 教师 / 2 学生 / 3 课程 / 3 教学班。

    s1 ∈ c1 且已选 tc32/tc48/tc64（SELECTED）；s2 ∈ c1 但未选任何教学班。
    课程：c32(两段式)、c48(三段式)、c64(三段式)。
    """
    _cleanup()
    with SessionLocal() as db:
        college = College(code=f"{P}col", name="T10学院")
        db.add(college)
        db.flush()
        m1 = Major(code=f"{P}m1", name="T10专业一", college_id=college.id)
        m2 = Major(code=f"{P}m2", name="T10专业二", college_id=college.id)
        db.add_all([m1, m2])
        db.flush()
        c1 = Class(code=f"{P}c1", name="T10一班", major_id=m1.id, grade_year=2026)
        c2 = Class(code=f"{P}c2", name="T10二班", major_id=m2.id, grade_year=2026)
        db.add_all([c1, c2])
        db.flush()

        c32 = Course(
            code=f"{P}c32", name="T10两段课", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("2.0"), total_hours=32,
            assessment_type="32",
        )
        c48 = Course(
            code=f"{P}c48", name="T10三段课", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("3.0"), total_hours=48,
            assessment_type="48",
        )
        c64 = Course(
            code=f"{P}c64", name="T10三段课二", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("4.0"), total_hours=64,
            assessment_type="64",
        )
        db.add_all([c32, c48, c64])
        db.flush()

        role_teacher = db.execute(
            select(Role).where(Role.code == RoleCode.TEACHER)
        ).scalar_one()
        role_student = db.execute(
            select(Role).where(Role.code == RoleCode.STUDENT)
        ).scalar_one()

        def make_user(username, real_name, user_type, role):
            u = User(
                username=username, password_hash=hash_password(PWD),
                real_name=real_name, user_type=user_type,
            )
            db.add(u)
            db.flush()
            if role is not None:
                db.add(UserRole(user_id=u.id, role_id=role.id))
            db.flush()
            return u

        ta_u = make_user(f"{P}t", "教师十", UserType.TEACHER, role_teacher)
        ta = Teacher(user_id=ta_u.id, teacher_no=f"{P}t", college_id=college.id)
        db.add(ta)
        db.flush()

        def make_student(no, klass, real_name):
            u = make_user(no, real_name, UserType.STUDENT, role_student)
            s = Student(
                user_id=u.id, student_no=no, class_id=klass.id,
                major_id=klass.major_id, college_id=college.id, enrollment_year=2026,
            )
            db.add(s)
            db.flush()
            return s

        s1 = make_student(f"{P}s1", c1, "学生十甲")
        s2 = make_student(f"{P}s2", c1, "学生十乙")

        term = AcademicTerm(
            name=f"{P}term", academic_year="2100-2101", semester=1,
            start_date=date(2100, 9, 1), end_date=date(2101, 1, 15),
            status="PLANNED",
        )
        db.add(term)
        db.flush()

        def make_tc(code, course):
            task = TeachingTask(
                semester=S1, course_id=course.id, college_id=college.id,
                status="CONFIRMED",
            )
            db.add(task)
            db.flush()
            tc = TeachingClass(
                code=code, task_id=task.id, course_id=course.id, semester=S1,
                teacher_id=ta.id, capacity=60, term_id=term.id,
            )
            db.add(tc)
            db.flush()
            return tc

        tc32 = make_tc(f"{P}TC32", c32)
        tc48 = make_tc(f"{P}TC48", c48)
        tc64 = make_tc(f"{P}TC64", c64)

        for tc in (tc32, tc48, tc64):
            db.add(CourseSelection(
                student_id=s1.id, teaching_class_id=tc.id,
                course_id=tc.course_id, semester=S1, status=SelectionState.SELECTED,
            ))
        db.commit()

        yield {
            "college_id": college.id, "college_name": college.name,
            "m1_id": m1.id, "m1_name": m1.name,
            "m2_id": m2.id, "m2_name": m2.name,
            "c1_id": c1.id, "c1_name": c1.name,
            "c2_id": c2.id, "c2_name": c2.name,
            "c32_id": c32.id, "c48_id": c48.id, "c64_id": c64.id,
            "tc32": tc32.id, "tc48": tc48.id, "tc64": tc64.id,
            "tc32_code": tc32.code, "tc48_code": tc48.code, "tc64_code": tc64.code,
            "ta_uname": f"{P}t",
            "s1_uname": f"{P}s1", "s2_uname": f"{P}s2",
            "s1_no": s1.student_no, "s2_no": s2.student_no,
            "s1_id": s1.id, "s2_id": s2.id,
        }
    _cleanup()


def _grade_of(student_id: int, tc_id: int) -> Grade | None:
    with SessionLocal() as db:
        return db.execute(
            select(Grade).where(
                Grade.student_id == student_id, Grade.teaching_class_id == tc_id
            )
        ).scalar_one_or_none()


def _put_grade(env, student_id: int, tc_id: int, status: str) -> None:
    """直接插入一条指定状态的成绩（用于状态覆盖测试）。"""
    with SessionLocal() as db:
        tc = db.get(TeachingClass, tc_id)
        db.add(Grade(
            student_id=student_id, teaching_class_id=tc_id,
            course_id=tc.course_id, semester=tc.semester,
            credits=Decimal("3.0"), regular_score=Decimal("50.00"),
            status=status,
        ))
        db.commit()


# =========================== 学生导入 ===========================


def test_admin_can_import_students(env):
    r = _post_file(client, f"{PREFIX}/imports/students", STUDENT_HDRS, [
        [f"{P}imp1", "张三", f"{P}imp1", "T10学院", "T10专业一", "T10一班"],
    ], admin_auth())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1 and body["success"] == 1 and body["failed"] == 0
    with SessionLocal() as db:
        s = db.execute(
            select(Student).where(Student.student_no == f"{P}imp1")
        ).scalar_one()
        assert s.user.username == f"{P}imp1"
        assert s.user.real_name == "张三"


def test_teacher_cannot_import_students(env):
    r = _post_file(client, f"{PREFIX}/imports/students", STUDENT_HDRS, [
        [f"{P}imp2", "张三", f"{P}imp2", "T10学院", "T10专业一", "T10一班"],
    ], auth(env["ta_uname"]))
    assert r.status_code == 403


def test_student_cannot_import_students(env):
    r = _post_file(client, f"{PREFIX}/imports/students", STUDENT_HDRS, [
        [f"{P}imp3", "张三", f"{P}imp3", "T10学院", "T10专业一", "T10一班"],
    ], auth(env["s1_uname"]))
    assert r.status_code == 403


def test_student_template_missing_field(env):
    bad_headers = ["student_no", "username", "college", "major", "class_name"]  # 缺 name
    r = _post_file(client, f"{PREFIX}/imports/students", bad_headers, [
        [f"{P}imp4", f"{P}imp4", "T10学院", "T10专业一", "T10一班"],
    ], admin_auth())
    assert r.status_code == 409
    assert "name" in r.json()["message"]


def test_student_no_duplicate(env):
    row = [f"{P}dup", "张三", f"{P}dup", "T10学院", "T10专业一", "T10一班"]
    first = _post_file(client, f"{PREFIX}/imports/students", STUDENT_HDRS, [row], admin_auth())
    assert first.json()["success"] == 1
    second = _post_file(client, f"{PREFIX}/imports/students", STUDENT_HDRS, [row], admin_auth())
    assert second.status_code == 200
    assert second.json()["failed"] == 1
    assert "已存在" in second.json()["errors"][0]["message"]


def test_username_duplicate(env):
    _post_file(client, f"{PREFIX}/imports/students", STUDENT_HDRS, [
        [f"{P}ua", "张三", f"{P}shared", "T10学院", "T10专业一", "T10一班"],
    ], admin_auth())
    r = _post_file(client, f"{PREFIX}/imports/students", STUDENT_HDRS, [
        [f"{P}ub", "李四", f"{P}shared", "T10学院", "T10专业一", "T10一班"],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert r.json()["errors"][0]["field"] == "username"
    assert "登录名已存在" in r.json()["errors"][0]["message"]


def test_college_not_exist(env):
    r = _post_file(client, f"{PREFIX}/imports/students", STUDENT_HDRS, [
        [f"{P}imp5", "张三", f"{P}imp5", "不存在的学院", "T10专业一", "T10一班"],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert "学院不存在" in r.json()["errors"][0]["message"]


def test_major_not_exist(env):
    r = _post_file(client, f"{PREFIX}/imports/students", STUDENT_HDRS, [
        [f"{P}imp6", "张三", f"{P}imp6", "T10学院", "不存在的专业", "T10一班"],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert "专业不存在" in r.json()["errors"][0]["message"]


def test_class_not_exist(env):
    r = _post_file(client, f"{PREFIX}/imports/students", STUDENT_HDRS, [
        [f"{P}imp7", "张三", f"{P}imp7", "T10学院", "T10专业一", "不存在的班"],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert "行政班不存在" in r.json()["errors"][0]["message"]


def test_class_major_mismatch(env):
    # class_name 用二班（属于专业二），但 major 填专业一
    r = _post_file(client, f"{PREFIX}/imports/students", STUDENT_HDRS, [
        [f"{P}imp8", "张三", f"{P}imp8", "T10学院", "T10专业一", "T10二班"],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert "行政班与专业不匹配" in r.json()["errors"][0]["message"]


# =========================== 课程导入 ===========================


def test_admin_can_import_courses(env):
    r = _post_file(client, f"{PREFIX}/imports/courses", COURSE_HDRS, [
        [f"{P}newc", "T10新课", "T10学院", 3.0, 48, "REQUIRED", "48"],
    ], admin_auth())
    assert r.status_code == 200, r.text
    assert r.json()["success"] == 1 and r.json()["failed"] == 0
    with SessionLocal() as db:
        c = db.execute(select(Course).where(Course.code == f"{P}newc")).scalar_one()
        assert c.assessment_type == "48"


def test_course_code_duplicate(env):
    row = [f"{P}dup", "T10重复课", "T10学院", 3.0, 48, "REQUIRED", "48"]
    _post_file(client, f"{PREFIX}/imports/courses", COURSE_HDRS, [row], admin_auth())
    r = _post_file(client, f"{PREFIX}/imports/courses", COURSE_HDRS, [row], admin_auth())
    assert r.json()["failed"] == 1
    assert "课程编号已存在" in r.json()["errors"][0]["message"]


def test_course_type_invalid(env):
    r = _post_file(client, f"{PREFIX}/imports/courses", COURSE_HDRS, [
        [f"{P}badtype", "T10类型课", "T10学院", 3.0, 48, "INVALID", "48"],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert "课程类型非法" in r.json()["errors"][0]["message"]


def test_assessment_type_invalid(env):
    r = _post_file(client, f"{PREFIX}/imports/courses", COURSE_HDRS, [
        [f"{P}badassess", "T10考核课", "T10学院", 3.0, 48, "REQUIRED", "99"],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert "考核方式非法" in r.json()["errors"][0]["message"]


def test_credits_invalid(env):
    r = _post_file(client, f"{PREFIX}/imports/courses", COURSE_HDRS, [
        [f"{P}badcredit", "T10学分课", "T10学院", 0, 48, "REQUIRED", "48"],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert "学分" in r.json()["errors"][0]["message"]


# =========================== 成绩导入 ===========================


def test_admin_can_import_grades(env):
    r = _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC48", 80, 70, 90, "", "", "", "", ""],
    ], admin_auth())
    assert r.status_code == 200, r.text
    assert r.json()["success"] == 1 and r.json()["failed"] == 0
    g = _grade_of(env["s1_id"], env["tc48"])
    assert g is not None and g.status == GradeStatus.DRAFT


def test_grade_student_not_exist(env):
    r = _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}nosuch", f"{P}TC48", 80, "", "", "", "", "", "", ""],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert "学生不存在" in r.json()["errors"][0]["message"]


def test_grade_teaching_class_not_exist(env):
    r = _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}NOSUCH", 80, "", "", "", "", "", "", ""],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert "教学班不存在" in r.json()["errors"][0]["message"]


def test_grade_student_not_in_class(env):
    # s2 未选任何教学班
    r = _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s2", f"{P}TC48", 80, "", "", "", "", "", "", ""],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert "学生不属于该教学班" in r.json()["errors"][0]["message"]


def test_grade_score_below_zero(env):
    r = _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC48", -1, "", "", "", "", "", "", ""],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert "超出范围" in r.json()["errors"][0]["message"]


def test_grade_score_above_hundred(env):
    r = _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC48", 101, "", "", "", "", "", "", ""],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert "超出范围" in r.json()["errors"][0]["message"]


def test_grade_draft_can_be_overwritten(env):
    _put_grade(env, env["s1_id"], env["tc48"], GradeStatus.DRAFT)
    r = _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC48", 80, 70, 90, "", "", "", "", ""],
    ], admin_auth())
    assert r.json()["success"] == 1
    g = _grade_of(env["s1_id"], env["tc48"])
    assert g.regular_score == Decimal("80.00")


def test_grade_rejected_can_be_overwritten(env):
    _put_grade(env, env["s1_id"], env["tc48"], GradeStatus.REJECTED)
    r = _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC48", 80, 70, 90, "", "", "", "", ""],
    ], admin_auth())
    assert r.json()["success"] == 1


def test_grade_submitted_cannot_be_overwritten(env):
    _put_grade(env, env["s1_id"], env["tc48"], GradeStatus.SUBMITTED)
    r = _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC48", 80, 70, 90, "", "", "", "", ""],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert "已提交" in r.json()["errors"][0]["message"]


def test_grade_approved_cannot_be_overwritten(env):
    _put_grade(env, env["s1_id"], env["tc48"], GradeStatus.APPROVED)
    r = _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC48", 80, 70, 90, "", "", "", "", ""],
    ], admin_auth())
    assert r.json()["failed"] == 1
    assert "已审核" in r.json()["errors"][0]["message"]


def test_incomplete_grade_saved_as_draft(env):
    r = _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC48", 80, "", "", "", "", "", "", ""],
    ], admin_auth())
    assert r.json()["success"] == 1
    g = _grade_of(env["s1_id"], env["tc48"])
    assert g.status == GradeStatus.DRAFT
    assert g.total_score is None  # 不完整 → 总评置空


def test_grade_uses_score_service(env):
    _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC48", 80, 70, 90, "", "", "", "", ""],
    ], admin_auth())
    g = _grade_of(env["s1_id"], env["tc48"])
    # 80*0.2 + 70*0.3 + 90*0.5 = 82.00
    assert float(g.total_score) == 82.0


def test_grade_32_hours(env):
    _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC32", 80, "", 90, "", "", "", "", ""],
    ], admin_auth())
    g = _grade_of(env["s1_id"], env["tc32"])
    # 80*0.2 + 90*0.8 = 88.00
    assert float(g.total_score) == 88.0


def test_grade_48_hours(env):
    _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC48", 80, 70, 90, "", "", "", "", ""],
    ], admin_auth())
    g = _grade_of(env["s1_id"], env["tc48"])
    assert float(g.total_score) == 82.0


def test_grade_64_hours(env):
    _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC64", 80, 70, 90, "", "", "", "", ""],
    ], admin_auth())
    g = _grade_of(env["s1_id"], env["tc64"])
    assert float(g.total_score) == 82.0


def test_grade_theory_practice_merge(env):
    _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC48", 80, "", "", 70, 80, 90, 80],
    ], admin_auth())
    g = _grade_of(env["s1_id"], env["tc48"])
    # mid = (70+80)/2 = 75；final = (90+80)/2 = 85
    # 80*0.2 + 75*0.3 + 85*0.5 = 81.00
    assert float(g.total_score) == 81.0
    assert float(g.mid_score) == 75.0
    assert float(g.final_score) == 85.0


def test_import_does_not_write_gpa(env):
    _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC48", 80, 70, 90, "", "", "", "", ""],
    ], admin_auth())
    with SessionLocal() as db:
        s = db.get(Student, env["s1_id"])
        assert s.gpa is None  # GPA 只在审核通过时重算，导入不写


def test_import_does_not_write_ranking(env):
    # 排名由 RankingService 实时计算，模型上不存在 ranking 字段
    assert not hasattr(Grade, "ranking")
    assert not hasattr(Student, "ranking")


# =========================== 权限 ===========================


def test_teacher_cannot_batch_import(env):
    r = _post_file(client, f"{PREFIX}/imports/courses", COURSE_HDRS, [
        [f"{P}tcforbidden", "T10禁课", "T10学院", 3.0, 48, "REQUIRED", "48"],
    ], auth(env["ta_uname"]))
    assert r.status_code == 403


def test_student_cannot_batch_import(env):
    r = _post_file(client, f"{PREFIX}/imports/grades", GRADE_HDRS, [
        [f"{P}s1", f"{P}TC48", 80, "", "", "", "", "", "", ""],
    ], auth(env["s1_uname"]))
    assert r.status_code == 403


# =========================== 模板下载 ===========================


def test_student_template_download(env):
    r = client.get(f"{PREFIX}/imports/templates/students", headers=admin_auth())
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # xlsx zip 魔数


def test_course_template_download(env):
    r = client.get(f"{PREFIX}/imports/templates/courses", headers=admin_auth())
    assert r.status_code == 200
    assert r.content[:2] == b"PK"


def test_grade_template_download(env):
    r = client.get(f"{PREFIX}/imports/templates/grades", headers=admin_auth())
    assert r.status_code == 200
    assert r.content[:2] == b"PK"


# =========================== 文件格式 ===========================


def test_non_xlsx_rejected(env):
    r = _post_file(client, f"{PREFIX}/imports/students", STUDENT_HDRS, [
        [f"{P}imp9", "张三", f"{P}imp9", "T10学院", "T10专业一", "T10一班"],
    ], admin_auth(), filename="data.csv")
    assert r.status_code == 409
    assert "xlsx" in r.json()["message"]


def test_error_contains_row_number(env):
    r = _post_file(client, f"{PREFIX}/imports/students", STUDENT_HDRS, [
        [f"{P}ok1", "张三", f"{P}ok1", "T10学院", "T10专业一", "T10一班"],
        [f"{P}bad", "李四", f"{P}bad", "不存在的学院", "T10专业一", "T10一班"],
    ], admin_auth())
    assert r.json()["total"] == 2
    assert r.json()["success"] == 1
    assert r.json()["failed"] == 1
    err = r.json()["errors"][0]
    assert isinstance(err["row"], int) and err["row"] == 3
    assert "field" in err and "message" in err
