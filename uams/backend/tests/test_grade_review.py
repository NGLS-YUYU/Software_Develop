"""TASK-006：教务处成绩审核测试。

覆盖：待审核列表权限、审核通过/驳回、非法状态流转（APPROVED/DRAFT/REJECTED/NOT_ENTERED
禁止审核）、审核通过后教师不可修改、驳回后可修改并重新提交、教师/学生越权防护。
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.course import Course
from app.models.grade import Grade
from app.models.organization import Class, College, Major
from app.models.person import Student, Teacher
from app.models.role import Role, RoleCode, UserRole
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import TeachingClass, TeachingTask
from app.models.term import AcademicTerm
from app.models.user import User, UserType

client = TestClient(app)
PREFIX = settings.API_V1_PREFIX
LOGIN = f"{PREFIX}/auth/login"

P = "__t6__"
PWD = "t6test123"
ADMIN_PWD = "admin123"
SEMESTER = "2026-2027-1"


def auth(username: str, password: str = PWD) -> dict:
    r = client.post(LOGIN, json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


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
        db.execute(delete(Student).where(Student.student_no.like(f"{P}s%")))
        db.execute(delete(Teacher).where(Teacher.teacher_no.like(f"{P}t%")))
        db.execute(delete(User).where(User.username.like(f"{P}%")))
        db.execute(delete(Class).where(Class.code.like(f"{P}%")))
        db.execute(delete(Major).where(Major.code.like(f"{P}%")))
        db.execute(delete(Course).where(Course.code.like(f"{P}%")))
        db.execute(delete(College).where(College.code.like(f"{P}%")))
        db.commit()


@pytest.fixture
def env():
    """1 课程(32h) / 1 教师 / 2 学生 / 1 教学班 + 选课。"""
    _cleanup()
    with SessionLocal() as db:
        college = College(code=f"{P}college", name="T6学院")
        db.add(college)
        db.flush()
        major = Major(code=f"{P}major", name="T6专业", college_id=college.id)
        db.add(major)
        db.flush()
        klass = Class(
            code=f"{P}class", name="T6班", major_id=major.id, grade_year=2026
        )
        db.add(klass)
        db.flush()

        course = Course(
            code=f"{P}c32", name="T6审核课", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("2.0"), total_hours=32, theory_hours=32,
            assessment_type="32",
        )
        db.add(course)
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
            db.add(UserRole(user_id=u.id, role_id=role.id))
            db.flush()
            return u

        t_u = make_user(f"{P}t01", "教师甲", UserType.TEACHER, role_teacher)
        teacher = Teacher(user_id=t_u.id, teacher_no=f"{P}t01", college_id=college.id)
        db.add(teacher)
        db.flush()

        students = []
        for i in range(1, 3):
            no = f"{P}s0{i}"
            u = make_user(no, f"学生{i}", UserType.STUDENT, role_student)
            s = Student(
                user_id=u.id, student_no=no, class_id=klass.id,
                major_id=major.id, college_id=college.id, enrollment_year=2026,
            )
            db.add(s)
            db.flush()
            students.append(s)

        task = TeachingTask(
            semester=SEMESTER, course_id=course.id, college_id=college.id,
            status="CONFIRMED",
        )
        db.add(task)
        db.flush()
        term = AcademicTerm(
            name=f"{P}term", academic_year="2096-2097", semester=1,
            start_date=date(2096, 9, 1), end_date=date(2097, 1, 15),
            status="PLANNED",
        )
        db.add(term)
        db.flush()
        tc = TeachingClass(
            code=f"{P}tc", task_id=task.id, course_id=course.id,
            semester=SEMESTER, teacher_id=teacher.id, capacity=40, term_id=term.id,
        )
        db.add(tc)
        db.flush()
        for s in students:
            db.add(CourseSelection(
                student_id=s.id, teaching_class_id=tc.id, course_id=course.id,
                semester=SEMESTER, status=SelectionState.SELECTED,
            ))
        db.commit()

        yield {
            "tc": tc.id,
            "t_uname": f"{P}t01",
            "stu_uname": f"{P}s01",
            "s1_no": f"{P}s01", "s2_no": f"{P}s02",
        }
    _cleanup()


def _init_sheet(env) -> list[dict]:
    r = client.post(
        f"{PREFIX}/grades/teaching-classes/{env['tc']}/init",
        headers=auth(env["t_uname"]),
    )
    assert r.status_code == 200, r.text
    return r.json()


def _save(env, items: list[dict]):
    return client.put(
        f"{PREFIX}/grades",
        json={"teaching_class_id": env["tc"], "items": items},
        headers=auth(env["t_uname"]),
    )


def _submit(env):
    return client.post(
        f"{PREFIX}/grades/teaching-classes/{env['tc']}/submit",
        headers=auth(env["t_uname"]),
    )


def _approve(grade_ids: list[int], uname: str = "admin", pwd: str = ADMIN_PWD):
    return client.post(
        f"{PREFIX}/grades/approve",
        json={"grade_ids": grade_ids},
        headers=auth(uname, pwd),
    )


def _reject(grade_ids: list[int], reason: str = "成绩有误",
            uname: str = "admin", pwd: str = ADMIN_PWD):
    return client.post(
        f"{PREFIX}/grades/reject",
        json={"grade_ids": grade_ids, "reason": reason},
        headers=auth(uname, pwd),
    )


def _gid(sheet: list[dict], student_no: str) -> int:
    return next(x["id"] for x in sheet if x["student_no"] == student_no)


def _submit_all(env) -> list[dict]:
    """初始化学期 → 给两名学生录入完整成绩 → 提交，返回成绩单。"""
    sheet = _init_sheet(env)
    items = [
        {"grade_id": x["id"], "regular_score": 90, "final_score": 85} for x in sheet
    ]
    _save(env, items)
    assert _submit(env).status_code == 200
    return sheet


# --- 1 ADMIN 可以查看待审核成绩 ---


def test_admin_view_pending(env):
    sheet = _submit_all(env)
    r = client.get(
        f"{PREFIX}/grades/pending", headers=auth("admin", ADMIN_PWD)
    )
    assert r.status_code == 200
    rows = r.json()
    assert {x["id"] for x in rows} == {x["id"] for x in sheet}
    assert all(x["status"] == "SUBMITTED" for x in rows)
    # 审核列表需展示教学班与教师
    assert all(x["teaching_class_code"] for x in rows)
    assert all(x["teacher_name"] for x in rows)


# --- 2 TEACHER 不能查看审核列表 ---


def test_teacher_cannot_view_pending(env):
    _submit_all(env)
    r = client.get(f"{PREFIX}/grades/pending", headers=auth(env["t_uname"]))
    assert r.status_code == 403
    assert r.json()["code"] == "PERM_DENIED"


# --- 3 STUDENT 不能查看审核列表 ---


def test_student_cannot_view_pending(env):
    _submit_all(env)
    r = client.get(f"{PREFIX}/grades/pending", headers=auth(env["stu_uname"]))
    assert r.status_code == 403


# --- 4 SUBMITTED 可以审核通过 ---


def test_submitted_can_approve(env):
    sheet = _submit_all(env)
    gid = _gid(sheet, env["s1_no"])
    r = _approve([gid])
    assert r.status_code == 200
    assert r.json()["approved"] == 1
    rows = client.get(f"{PREFIX}/grades/pending", headers=auth("admin", ADMIN_PWD)).json()
    assert gid not in [x["id"] for x in rows]  # 已不再待审核


# --- 5 SUBMITTED 可以驳回 ---


def test_submitted_can_reject(env):
    sheet = _submit_all(env)
    gid = _gid(sheet, env["s1_no"])
    r = _reject([gid], "成绩录入有误")
    assert r.status_code == 200
    assert r.json()["rejected"] == 1


# --- 6 APPROVED 不能再次通过 ---


def test_approved_cannot_reapprove(env):
    sheet = _submit_all(env)
    gid = _gid(sheet, env["s1_no"])
    assert _approve([gid]).status_code == 200
    r = _approve([gid])
    assert r.status_code == 409


# --- 7 APPROVED 不能驳回 ---


def test_approved_cannot_reject(env):
    sheet = _submit_all(env)
    gid = _gid(sheet, env["s1_no"])
    assert _approve([gid]).status_code == 200
    r = _reject([gid])
    assert r.status_code == 409


# --- 8 DRAFT 不能审核 ---


def test_draft_cannot_review(env):
    sheet = _init_sheet(env)
    gid = _gid(sheet, env["s1_no"])
    _save(env, [{"grade_id": gid, "regular_score": 90}])  # 部分成绩 → DRAFT
    assert _approve([gid]).status_code == 409
    assert _reject([gid]).status_code == 409


# --- 9 REJECTED 不能审核 ---


def test_rejected_cannot_review(env):
    sheet = _submit_all(env)
    gid = _gid(sheet, env["s1_no"])
    assert _reject([gid]).status_code == 200
    assert _approve([gid]).status_code == 409
    assert _reject([gid]).status_code == 409


# --- 10 NOT_ENTERED 不能审核 ---


def test_not_entered_cannot_review(env):
    sheet = _init_sheet(env)  # 未录入任何成绩 → NOT_ENTERED
    gid = _gid(sheet, env["s1_no"])
    assert _approve([gid]).status_code == 409
    assert _reject([gid]).status_code == 409


# --- 11 审核通过后教师不能修改 ---


def test_teacher_cannot_modify_after_approve(env):
    sheet = _submit_all(env)
    gid = _gid(sheet, env["s1_no"])
    assert _approve([gid]).status_code == 200
    r = _save(env, [{"grade_id": gid, "regular_score": 80}])
    assert r.status_code == 409


# --- 12 驳回后教师可以修改 ---


def test_teacher_can_modify_after_reject(env):
    sheet = _submit_all(env)
    gid = _gid(sheet, env["s1_no"])
    assert _reject([gid]).status_code == 200
    r = _save(env, [{"grade_id": gid, "regular_score": 80, "final_score": 90}])
    assert r.status_code == 200
    row = next(x for x in r.json() if x["id"] == gid)
    assert row["status"] == "DRAFT"


# --- 13 驳回后可以重新提交 ---


def test_rejected_can_resubmit(env):
    sheet = _submit_all(env)
    gid = _gid(sheet, env["s1_no"])
    assert _reject([gid]).status_code == 200
    _save(env, [{"grade_id": gid, "regular_score": 80, "final_score": 90}])
    r = _submit(env)
    assert r.status_code == 200


# --- 14 教师不能 approve ---


def test_teacher_cannot_approve(env):
    sheet = _submit_all(env)
    gid = _gid(sheet, env["s1_no"])
    r = _approve([gid], uname=env["t_uname"], pwd=PWD)
    assert r.status_code == 403


# --- 15 教师不能 reject ---


def test_teacher_cannot_reject(env):
    sheet = _submit_all(env)
    gid = _gid(sheet, env["s1_no"])
    r = _reject([gid], uname=env["t_uname"], pwd=PWD)
    assert r.status_code == 403


# --- 16 学生不能 approve ---


def test_student_cannot_approve(env):
    sheet = _submit_all(env)
    gid = _gid(sheet, env["s1_no"])
    r = _approve([gid], uname=env["stu_uname"], pwd=PWD)
    assert r.status_code == 403


# --- 17 学生不能 reject ---


def test_student_cannot_reject(env):
    sheet = _submit_all(env)
    gid = _gid(sheet, env["s1_no"])
    r = _reject([gid], uname=env["stu_uname"], pwd=PWD)
    assert r.status_code == 403


# --- 18 审核接口后端权限校验（RBAC 隔离） ---


def test_approve_permission_isolation(env):
    admin_perms = set(client.post(
        LOGIN, json={"username": "admin", "password": ADMIN_PWD}
    ).json()["permissions"])
    teacher_perms = set(client.post(
        LOGIN, json={"username": env["t_uname"], "password": PWD}
    ).json()["permissions"])
    student_perms = set(client.post(
        LOGIN, json={"username": env["stu_uname"], "password": PWD}
    ).json()["permissions"])

    assert "grade:approve" in admin_perms
    assert "grade:approve" not in teacher_perms
    assert "grade:approve" not in student_perms
