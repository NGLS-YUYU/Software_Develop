"""TASK-008：教学班基础管理测试。

覆盖：教务处创建教学班（课程/教师/教师身份/唯一性校验）、教务/教师/学生
数据权限隔离、教学班学生名单（含专业与行政班）、教务处添加/移除学生、
同一学生多教学班、不同课程/学期教学班共存、以及 TASK-005/006/007 回归。
"""

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
from app.models.user import User, UserType

client = TestClient(app)
PREFIX = settings.API_V1_PREFIX
LOGIN = f"{PREFIX}/auth/login"

P = "__t8__"
PWD = "t8test123"
ADMIN_PWD = "admin123"
S1 = "2026-2027-1"
S2 = "2026-2027-2"


def auth(username: str, password: str = PWD) -> dict:
    r = client.post(LOGIN, json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def admin_auth() -> dict:
    return auth("admin", ADMIN_PWD)


def _cleanup() -> None:
    with SessionLocal() as db:
        test_courses = select(Course.id).where(Course.code.like(f"{P}%"))
        test_tcs = select(TeachingClass.id).where(TeachingClass.code.like(f"{P}%"))
        db.execute(delete(Grade).where(Grade.course_id.in_(test_courses)))
        db.execute(delete(CourseSelection).where(
            CourseSelection.teaching_class_id.in_(test_tcs)
        ))
        db.execute(delete(TeachingClass).where(TeachingClass.code.like(f"{P}%")))
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
    """2 课程 / 2 教师 / 1 非教师身份的教师 / 4 学生（2 个行政班）/ 3 教学任务 / 3 教学班 + 选课。"""
    _cleanup()
    with SessionLocal() as db:
        college = College(code=f"{P}college", name="T8学院")
        db.add(college)
        db.flush()
        major = Major(code=f"{P}major", name="T8专业", college_id=college.id)
        db.add(major)
        db.flush()
        class_a = Class(code=f"{P}cla", name="T8行政A班", major_id=major.id, grade_year=2026)
        class_b = Class(code=f"{P}clb", name="T8行政B班", major_id=major.id, grade_year=2026)
        db.add_all([class_a, class_b])
        db.flush()

        c1 = Course(
            code=f"{P}c1", name="T8课程一", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("3.0"), total_hours=48,
            assessment_type="48",
        )
        c2 = Course(
            code=f"{P}c2", name="T8课程二", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("2.0"), total_hours=32,
            assessment_type="32",
        )
        db.add_all([c1, c2])
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

        ta_u = make_user(f"{P}ta", "教师甲", UserType.TEACHER, role_teacher)
        ta = Teacher(user_id=ta_u.id, teacher_no=f"{P}ta", college_id=college.id)
        tb_u = make_user(f"{P}tb", "教师乙", UserType.TEACHER, role_teacher)
        tb = Teacher(user_id=tb_u.id, teacher_no=f"{P}tb", college_id=college.id)
        # 非教师身份的"教师"：账号是学生类型，但存在 Teacher 档案（用于身份校验测试）
        bad_u = make_user(f"{P}tbad", "身份异常", UserType.STUDENT, role_student)
        bad_t = Teacher(user_id=bad_u.id, teacher_no=f"{P}tbad", college_id=college.id)
        db.add_all([ta, tb, bad_t])
        db.flush()

        by_no = {}
        for no, klass in [("s01", class_a), ("s02", class_a), ("s03", class_b),
                          ("s04", class_b)]:
            u = make_user(f"{P}{no}", f"学生{no[1:]}", UserType.STUDENT, role_student)
            s = Student(
                user_id=u.id, student_no=f"{P}{no}", class_id=klass.id,
                major_id=major.id, college_id=college.id, enrollment_year=2026,
            )
            db.add(s)
            db.flush()
            by_no[f"{P}{no}"] = s

        def make_task(course, semester):
            t = TeachingTask(
                semester=semester, course_id=course.id, college_id=college.id,
                status="CONFIRMED",
            )
            db.add(t)
            db.flush()
            return t

        task_c1 = make_task(c1, S1)
        task_c2 = make_task(c2, S1)
        task_c1_s2 = make_task(c1, S2)

        def make_tc(code, task, course, teacher, capacity=40):
            tc = TeachingClass(
                code=code, task_id=task.id, course_id=course.id,
                semester=task.semester, teacher_id=teacher.id, capacity=capacity,
            )
            db.add(tc)
            db.flush()
            return tc

        tca1 = make_tc(f"{P}A01", task_c1, c1, ta)
        tca2 = make_tc(f"{P}A02", task_c2, c2, ta)
        tcb1 = make_tc(f"{P}B01", task_c1, c1, tb)

        def select_into(tc, stu):
            db.add(CourseSelection(
                student_id=stu.id, teaching_class_id=tc.id, course_id=tc.course_id,
                semester=tc.semester, status=SelectionState.SELECTED,
            ))

        # 同一学生 s01 属于两个教学班；s02 属于 tca1
        select_into(tca1, by_no[f"{P}s01"])
        select_into(tca2, by_no[f"{P}s01"])
        select_into(tca1, by_no[f"{P}s02"])
        tca1.selected_count = 2
        tca2.selected_count = 1

        db.commit()

        yield {
            "major": major.id,
            "task_c1": task_c1.id, "task_c2": task_c2.id,
            "task_c1_s2": task_c1_s2.id,
            "tca1": tca1.id, "tca2": tca2.id, "tcb1": tcb1.id,
            "tca1_code": f"{P}A01", "tca2_code": f"{P}A02", "tcb1_code": f"{P}B01",
            "c1_code": f"{P}c1", "c2_code": f"{P}c2",
            "ta_id": ta.id, "tb_id": tb.id, "bad_teacher_id": bad_t.id,
            "ta_uname": f"{P}ta", "tb_uname": f"{P}tb",
            "s1_uname": f"{P}s01", "s2_uname": f"{P}s02",
            "s3_uname": f"{P}s03", "s4_uname": f"{P}s04",
            "s1_id": by_no[f"{P}s01"].id, "s2_id": by_no[f"{P}s02"].id,
            "s3_id": by_no[f"{P}s03"].id, "s4_id": by_no[f"{P}s04"].id,
        }
    _cleanup()


def _create_class(env, code, task_id, teacher_id, capacity=40):
    return client.post(
        f"{PREFIX}/teaching-classes",
        json={"code": code, "task_id": task_id, "teacher_id": teacher_id,
              "capacity": capacity},
        headers=admin_auth(),
    )


# --- 1 ADMIN 创建教学班 ---


def test_admin_create_class(env):
    r = _create_class(env, f"{P}NEW1", env["task_c1"], env["ta_id"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["code"] == f"{P}NEW1"
    assert body["course_code"] == env["c1_code"]
    assert body["course_name"]
    assert body["teacher_name"] == "教师甲"
    assert body["semester"] == S1


# --- 2 不存在课程（教学任务）不能创建 ---


def test_create_nonexistent_course(env):
    r = _create_class(env, f"{P}NO1", 99999999, env["ta_id"])
    assert r.status_code == 404


# --- 3 不存在教师不能创建 ---


def test_create_nonexistent_teacher(env):
    r = _create_class(env, f"{P}NO2", env["task_c1"], 99999999)
    assert r.status_code == 404


# --- 4 非教师身份不能作为教学班教师 ---


def test_create_non_teacher_identity(env):
    r = _create_class(env, f"{P}NO3", env["task_c1"], env["bad_teacher_id"])
    assert r.status_code == 409


# --- 5 重复教学班不能创建 ---


def test_create_duplicate_class(env):
    code = f"{P}DUP1"
    assert _create_class(env, code, env["task_c1"], env["ta_id"]).status_code == 201
    r = _create_class(env, code, env["task_c2"], env["tb_id"])
    assert r.status_code == 409


# --- 6 ADMIN 查看教学班列表 ---


def test_admin_list_classes(env):
    r = client.get(f"{PREFIX}/teaching-classes", headers=admin_auth())
    assert r.status_code == 200
    items = r.json()["items"]
    codes = {x["code"] for x in items}
    assert {env["tca1_code"], env["tca2_code"], env["tcb1_code"]} <= codes
    for x in items:
        assert x["course_code"] and x["course_name"]
        assert x["semester"]
        assert "selected_count" in x
    # 教师信息可读
    assert any(x["code"] == env["tca1_code"] and x["teacher_name"] == "教师甲"
               for x in items)


# --- 7 TEACHER 查看自己的教学班 ---


def test_teacher_list_own_classes(env):
    r = client.get(f"{PREFIX}/teaching-classes/mine", headers=auth(env["ta_uname"]))
    assert r.status_code == 200
    codes = {x["code"] for x in r.json()}
    assert codes == {env["tca1_code"], env["tca2_code"]}
    assert env["tcb1_code"] not in codes


# --- 8 TEACHER 不能查看其他教师教学班学生 ---


def test_teacher_cannot_view_other_teacher_students(env):
    r = client.get(
        f"{PREFIX}/teaching-classes/{env['tcb1']}/students",
        headers=auth(env["ta_uname"]),
    )
    assert r.status_code == 403


# --- 9 TEACHER 不能通过 class_id 越权修改其他教学班 ---


def test_teacher_cannot_modify_other_teacher_class(env):
    r = client.put(
        f"{PREFIX}/teaching-classes/{env['tcb1']}",
        json={"capacity": 10},
        headers=auth(env["ta_uname"]),
    )
    assert r.status_code == 403


# --- 10 查看教学班学生（含专业与行政班） ---


def test_view_class_students(env):
    r = client.get(
        f"{PREFIX}/teaching-classes/{env['tca1']}/students",
        headers=admin_auth(),
    )
    assert r.status_code == 200
    rows = r.json()
    assert {x["student_no"] for x in rows} == {f"{P}s01", f"{P}s02"}
    for x in rows:
        assert x["real_name"]
        assert x["major"]  # 专业（TASK-008 新增）
        assert x["class_name"] == "T8行政A班"  # 行政班，非教学班


# --- 11 ADMIN 添加学生 ---


def test_admin_add_student(env):
    r = client.post(
        f"{PREFIX}/teaching-classes/{env['tca1']}/students",
        json={"student_id": env["s3_id"]},
        headers=admin_auth(),
    )
    assert r.status_code == 201, r.text
    rows = client.get(
        f"{PREFIX}/teaching-classes/{env['tca1']}/students", headers=admin_auth()
    ).json()
    assert {x["student_no"] for x in rows} == {f"{P}s01", f"{P}s02", f"{P}s03"}


# --- 12 ADMIN 删除学生 ---


def test_admin_remove_student(env):
    r = client.delete(
        f"{PREFIX}/teaching-classes/{env['tca1']}/students/{env['s2_id']}",
        headers=admin_auth(),
    )
    assert r.status_code == 204
    rows = client.get(
        f"{PREFIX}/teaching-classes/{env['tca1']}/students", headers=admin_auth()
    ).json()
    assert {x["student_no"] for x in rows} == {f"{P}s01"}


# --- 13 教师不能添加学生 ---


def test_teacher_cannot_add_student(env):
    r = client.post(
        f"{PREFIX}/teaching-classes/{env['tca1']}/students",
        json={"student_id": env["s3_id"]},
        headers=auth(env["ta_uname"]),
    )
    assert r.status_code == 403


# --- 14 教师不能删除学生 ---


def test_teacher_cannot_remove_student(env):
    r = client.delete(
        f"{PREFIX}/teaching-classes/{env['tca1']}/students/{env['s2_id']}",
        headers=auth(env["ta_uname"]),
    )
    assert r.status_code == 403


# --- 15 学生不能管理教学班 ---


def test_student_cannot_manage_classes(env):
    # 创建教学班
    r1 = client.post(
        f"{PREFIX}/teaching-classes",
        json={"code": f"{P}ST1", "task_id": env["task_c1"], "teacher_id": env["ta_id"],
              "capacity": 40},
        headers=auth(env["s1_uname"]),
    )
    assert r1.status_code == 403
    # 添加/删除学生
    r2 = client.post(
        f"{PREFIX}/teaching-classes/{env['tca1']}/students",
        json={"student_id": env["s3_id"]}, headers=auth(env["s1_uname"]),
    )
    assert r2.status_code == 403
    r3 = client.delete(
        f"{PREFIX}/teaching-classes/{env['tca1']}/students/{env['s2_id']}",
        headers=auth(env["s1_uname"]),
    )
    assert r3.status_code == 403


# --- 16 学生不能查看其他学生教学班关系（学生名单） ---


def test_student_cannot_view_other_student_relationship(env):
    r = client.get(
        f"{PREFIX}/teaching-classes/{env['tca1']}/students",
        headers=auth(env["s1_uname"]),
    )
    assert r.status_code == 403


# --- 17 同一学生可以属于多个教学班 ---


def test_same_student_in_multiple_classes(env):
    r = client.get(
        f"{PREFIX}/course-selections/mine", headers=auth(env["s1_uname"])
    )
    assert r.status_code == 200
    tc_ids = {x["teaching_class_id"] for x in r.json()}
    assert tc_ids == {env["tca1"], env["tca2"]}


# --- 18 不同课程教学班可以共存 ---


def test_different_course_classes_coexist(env):
    # 教师甲名下已有课程一、课程二两个教学班，可共存
    r = client.get(f"{PREFIX}/teaching-classes/mine", headers=auth(env["ta_uname"]))
    items = r.json()
    by_code = {x["code"]: x for x in items}
    assert by_code[env["tca1_code"]]["course_code"] == env["c1_code"]
    assert by_code[env["tca2_code"]]["course_code"] == env["c2_code"]


# --- 19 不同学期相同教学班代码符合现有唯一规则（全局唯一 → 409） ---


def test_same_code_across_semester_unique(env):
    code = f"{P}SEM"
    assert _create_class(env, code, env["task_c1"], env["ta_id"]).status_code == 201
    r = _create_class(env, code, env["task_c1_s2"], env["ta_id"])
    assert r.status_code == 409  # code 全局唯一，跨学期同码被拒


# --- 20 TASK-005 我的授课课程接口继续通过 ---


def test_regression_my_classes(env):
    r = client.get(f"{PREFIX}/teaching-classes/mine", headers=auth(env["ta_uname"]))
    assert r.status_code == 200
    assert {x["code"] for x in r.json()} == {env["tca1_code"], env["tca2_code"]}


# --- 21 TASK-005 教师成绩权限继续通过 ---


def test_regression_teacher_grade_permission(env):
    # 本人教学班可查看成绩名单，他人教学班被拒
    ok = client.get(
        f"{PREFIX}/grades/teaching-classes/{env['tca1']}/students",
        headers=auth(env["ta_uname"]),
    )
    assert ok.status_code == 200
    denied = client.get(
        f"{PREFIX}/grades/teaching-classes/{env['tcb1']}/students",
        headers=auth(env["ta_uname"]),
    )
    assert denied.status_code == 403


# --- 22 TASK-006 审核接口继续通过 ---


def test_regression_grade_review(env):
    r = client.get(f"{PREFIX}/grades/pending", headers=admin_auth())
    assert r.status_code == 200
    denied = client.get(f"{PREFIX}/grades/pending", headers=auth(env["ta_uname"]))
    assert denied.status_code == 403


# --- 23 TASK-007 学生成绩查询继续通过 ---


def test_regression_student_grade_query(env):
    r = client.get(f"{PREFIX}/grades/my", headers=auth(env["s1_uname"]))
    assert r.status_code == 200
    assert set(r.json().keys()) == {"items", "gpa", "class_rank", "major_rank"}
