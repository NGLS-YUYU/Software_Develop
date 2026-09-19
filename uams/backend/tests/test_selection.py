"""TASK-009：必修课预安排 + 选修课自主选课测试。

覆盖：必修课预排（学院/专业/行政班范围、幂等、选修课不可预排）、
学生自主选课/退课（仅选修、重复、同课程多教学班、越权）、
必修课不可自主选择/退选、数据隔离、以及 TASK-005/006/007/008 回归。
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.course import Course
from app.models.grade import Grade
from app.models.organization import Class, College, Major
from app.models.person import Student, Teacher
from app.models.role import Role, RoleCode, UserRole
from app.models.selection import CourseSelection, SelectionPeriod, SelectionState
from app.models.teaching import TeachingClass, TeachingTask
from app.models.term import AcademicTerm, TermStatus
from app.models.user import User, UserType

client = TestClient(app)
PREFIX = settings.API_V1_PREFIX
LOGIN = f"{PREFIX}/auth/login"

P = "__t9__"
PWD = "t9test123"
ADMIN_PWD = "admin123"
S1 = "2099-2099-1"  # 独立学期，避免与演示数据及其他测试冲突


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
        db.execute(delete(AcademicTerm).where(AcademicTerm.name.like(f"{P}%")))
        db.execute(delete(TeachingTask).where(
            TeachingTask.course_id.in_(test_courses)
        ))
        db.execute(delete(SelectionPeriod).where(SelectionPeriod.name.like(f"{P}%")))
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
    """1 学院 / 2 专业 / 4 行政班 / 1 教师 / 4 学生 / 3 课程 / 4 教学班 + 选课时间窗口。

    范围结构：m1(c1,c2) + m2(c3,c4)，s01∈c1, s02∈c2, s03∈c3, s04∈c4。
    课程：req(必修)、elec(选修)、elec2(选修)。
    教学班：R01(必修)、E01/E02(elec 同课程两个班)、E201(elec2)。
    """
    _cleanup()
    with SessionLocal() as db:
        college = College(code=f"{P}college", name="T9学院")
        db.add(college)
        db.flush()
        m1 = Major(code=f"{P}m1", name="T9专业一", college_id=college.id)
        m2 = Major(code=f"{P}m2", name="T9专业二", college_id=college.id)
        db.add_all([m1, m2])
        db.flush()
        c1 = Class(code=f"{P}c1", name="T9一1班", major_id=m1.id, grade_year=2026)
        c2 = Class(code=f"{P}c2", name="T9一2班", major_id=m1.id, grade_year=2026)
        c3 = Class(code=f"{P}c3", name="T9二1班", major_id=m2.id, grade_year=2026)
        c4 = Class(code=f"{P}c4", name="T9二2班", major_id=m2.id, grade_year=2026)
        db.add_all([c1, c2, c3, c4])
        db.flush()

        req = Course(
            code=f"{P}req", name="T9必修课", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("3.0"), total_hours=48, theory_hours=48,
            assessment_type="48",
        )
        elec = Course(
            code=f"{P}elec", name="T9选修课", college_id=college.id,
            course_type="ELECTIVE", credits=Decimal("2.0"), total_hours=32, theory_hours=32,
            assessment_type="32",
        )
        elec2 = Course(
            code=f"{P}elec2", name="T9选修课二", college_id=college.id,
            course_type="ELECTIVE", credits=Decimal("1.0"), total_hours=32, theory_hours=32,
            assessment_type="32",
        )
        db.add_all([req, elec, elec2])
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
        db.add(ta)
        db.flush()

        by_no = {}
        for no, klass in [("s01", c1), ("s02", c2), ("s03", c3), ("s04", c4)]:
            u = make_user(f"{P}{no}", f"学生{no[1:]}", UserType.STUDENT, role_student)
            s = Student(
                user_id=u.id, student_no=f"{P}{no}", class_id=klass.id,
                major_id=klass.major_id, college_id=college.id, enrollment_year=2026,
            )
            db.add(s)
            db.flush()
            by_no[f"{P}{no}"] = s

        def make_task(course):
            t = TeachingTask(
                semester=S1, course_id=course.id, college_id=college.id,
                status="CONFIRMED",
            )
            db.add(t)
            db.flush()
            return t

        task_req = make_task(req)
        task_elec = make_task(elec)
        task_elec2 = make_task(elec2)

        # 进行中的学期（TASK-011：只有 ACTIVE 学期允许学生选课）
        term = AcademicTerm(
            name=f"{P}term", academic_year="2099-2100", semester=1,
            start_date=date(2099, 9, 1), end_date=date(2100, 1, 15),
            status=TermStatus.ACTIVE,
        )
        db.add(term)
        db.flush()

        def make_tc(code, task, course, selection_status="OPEN"):
            tc = TeachingClass(
                code=code, task_id=task.id, course_id=course.id, semester=S1,
                teacher_id=ta.id, capacity=40, selection_status=selection_status,
                term_id=term.id,
            )
            db.add(tc)
            db.flush()
            return tc

        r01 = make_tc(f"{P}R01", task_req, req)
        e01 = make_tc(f"{P}E01", task_elec, elec)
        e02 = make_tc(f"{P}E02", task_elec, elec)
        e201 = make_tc(f"{P}E201", task_elec2, elec2)

        # 选课时间窗口（当前学期，开放中）
        now = datetime.now()
        db.add(SelectionPeriod(
            semester=S1, name=f"{P}period",
            start_time=now - timedelta(days=1), end_time=now + timedelta(days=1),
            status="ACTIVE",
        ))

        db.commit()

        yield {
            "college_id": college.id,
            "term": term.id,
            "m1_id": m1.id, "m2_id": m2.id,
            "c1_id": c1.id, "c2_id": c2.id, "c3_id": c3.id, "c4_id": c4.id,
            "req_id": req.id, "elec_id": elec.id, "elec2_id": elec2.id,
            "req_code": f"{P}req", "elec_code": f"{P}elec", "elec2_code": f"{P}elec2",
            "r01": r01.id, "e01": e01.id, "e02": e02.id, "e201": e201.id,
            "r01_code": f"{P}R01", "e01_code": f"{P}E01",
            "e02_code": f"{P}E02", "e201_code": f"{P}E201",
            "ta_uname": f"{P}ta",
            "s1_uname": f"{P}s01", "s2_uname": f"{P}s02",
            "s3_uname": f"{P}s03", "s4_uname": f"{P}s04",
            "s1_id": by_no[f"{P}s01"].id, "s2_id": by_no[f"{P}s02"].id,
            "s3_id": by_no[f"{P}s03"].id, "s4_id": by_no[f"{P}s04"].id,
        }
    _cleanup()


def _assign(client_headers, class_id, scope: dict) -> "object":
    return client.post(
        f"{PREFIX}/teaching-classes/{class_id}/assign-required",
        json=scope, headers=client_headers,
    )


# --- 1 ADMIN 可以预排必修课 ---


def test_admin_can_assign_required(env):
    r = _assign(admin_auth(), env["r01"], {"class_id": env["c1_id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matched"] == 1
    assert body["assigned"] == 1
    assert body["skipped"] == 0


# --- 2 TEACHER 不能预排必修课 ---


def test_teacher_cannot_assign_required(env):
    r = _assign(auth(env["ta_uname"]), env["r01"], {"class_id": env["c1_id"]})
    assert r.status_code == 403


# --- 3 STUDENT 不能预排必修课 ---


def test_student_cannot_assign_required(env):
    r = _assign(auth(env["s1_uname"]), env["r01"], {"class_id": env["c1_id"]})
    assert r.status_code == 403


# --- 4 必修课预排成功（学生进入 CourseSelection） ---


def test_assign_required_creates_selection(env):
    r = _assign(admin_auth(), env["r01"], {"class_id": env["c1_id"]})
    assert r.status_code == 200
    rows = client.get(
        f"{PREFIX}/teaching-classes/{env['r01']}/students", headers=admin_auth()
    ).json()
    assert {x["student_no"] for x in rows} == {f"{P}s01"}


# --- 5 学院范围预排 ---


def test_assign_required_by_college(env):
    r = _assign(admin_auth(), env["r01"], {"college_id": env["college_id"]})
    assert r.status_code == 200, r.text
    assert r.json()["assigned"] == 4  # s01~s04 全部


# --- 6 专业范围预排 ---


def test_assign_required_by_major(env):
    r = _assign(admin_auth(), env["r01"], {"major_id": env["m1_id"]})
    assert r.status_code == 200, r.text
    assert r.json()["assigned"] == 2  # s01、s02


# --- 7 行政班范围预排 ---


def test_assign_required_by_class(env):
    r = _assign(admin_auth(), env["r01"], {"class_id": env["c2_id"]})
    assert r.status_code == 200, r.text
    assert r.json()["assigned"] == 1  # s02


# --- 8 预排不会产生重复 CourseSelection ---


def test_assign_required_idempotent(env):
    first = _assign(admin_auth(), env["r01"], {"major_id": env["m1_id"]})
    assert first.status_code == 200
    assert first.json()["assigned"] == 2
    second = _assign(admin_auth(), env["r01"], {"major_id": env["m1_id"]})
    assert second.status_code == 200
    assert second.json()["assigned"] == 0
    assert second.json()["skipped"] == 2
    with SessionLocal() as db:
        n = db.execute(
            select(func.count()).select_from(CourseSelection).where(
                CourseSelection.teaching_class_id == env["r01"],
                CourseSelection.status == SelectionState.SELECTED,
            )
        ).scalar()
    assert n == 2  # 无重复记录


# --- 9 教务不能用预排接口安排选修课 ---


def test_cannot_assign_elective(env):
    r = _assign(admin_auth(), env["e01"], {"class_id": env["c1_id"]})
    assert r.status_code == 409
    assert "选修" in r.json()["message"]


# --- 10 学生可以选择选修课 ---


def test_student_can_select_elective(env):
    r = client.post(
        f"{PREFIX}/course-selections",
        json={"teaching_class_id": env["e01"]},
        headers=auth(env["s1_uname"]),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["teaching_class_id"] == env["e01"]
    assert body["student_id"] == env["s1_id"]
    assert body["course_type"] == "ELECTIVE"


# --- 11 学生不能选择必修课 ---


def test_student_cannot_select_required(env):
    r = client.post(
        f"{PREFIX}/course-selections",
        json={"teaching_class_id": env["r01"]},
        headers=auth(env["s1_uname"]),
    )
    assert r.status_code == 409
    assert "必修" in r.json()["message"]


# --- 12 学生不能通过 student_id 给别人选课 ---


def test_student_cannot_select_for_others(env):
    r = client.post(
        f"{PREFIX}/course-selections",
        json={"teaching_class_id": env["e01"], "student_id": env["s3_id"]},
        headers=auth(env["s1_uname"]),
    )
    assert r.status_code == 201, r.text
    assert r.json()["student_id"] == env["s1_id"]  # 身份取自 JWT，忽略 student_id
    # 学生 B 名下没有任何选课记录
    mine_b = client.get(
        f"{PREFIX}/course-selections/mine", headers=auth(env["s3_uname"])
    ).json()
    assert mine_b == []


# --- 13 学生重复选择同一教学班失败 ---


def test_student_duplicate_selection(env):
    h = auth(env["s1_uname"])
    assert client.post(
        f"{PREFIX}/course-selections", json={"teaching_class_id": env["e01"]}, headers=h
    ).status_code == 201
    r = client.post(
        f"{PREFIX}/course-selections", json={"teaching_class_id": env["e01"]}, headers=h
    )
    assert r.status_code == 409


# --- 14 学生不能同时选择同一课程不同教学班 ---


def test_student_cannot_select_same_course_other_class(env):
    h = auth(env["s1_uname"])
    assert client.post(
        f"{PREFIX}/course-selections", json={"teaching_class_id": env["e01"]}, headers=h
    ).status_code == 201
    r = client.post(
        f"{PREFIX}/course-selections", json={"teaching_class_id": env["e02"]}, headers=h
    )
    assert r.status_code == 409


# --- 15 学生可以退选选修课 ---


def test_student_can_drop_elective(env):
    h = auth(env["s1_uname"])
    created = client.post(
        f"{PREFIX}/course-selections", json={"teaching_class_id": env["e01"]}, headers=h
    )
    assert created.status_code == 201
    sel_id = created.json()["id"]
    r = client.delete(f"{PREFIX}/course-selections/{sel_id}", headers=h)
    assert r.status_code == 204
    mine = client.get(f"{PREFIX}/course-selections/mine", headers=h).json()
    assert all(x["teaching_class_id"] != env["e01"] for x in mine)


# --- 16 学生不能退选必修课 ---


def test_student_cannot_drop_required(env):
    # 教务处先把必修课预排给学生
    assert _assign(admin_auth(), env["r01"], {"class_id": env["c1_id"]}).status_code == 200
    h = auth(env["s1_uname"])
    mine = client.get(f"{PREFIX}/course-selections/mine", headers=h).json()
    req_sel = next(x for x in mine if x["teaching_class_id"] == env["r01"])
    assert req_sel["course_type"] == "REQUIRED"
    r = client.delete(f"{PREFIX}/course-selections/{req_sel['id']}", headers=h)
    assert r.status_code == 409


# --- 17 学生只能操作自己的选课 ---


def test_student_cannot_drop_others_selection(env):
    h1 = auth(env["s1_uname"])
    created = client.post(
        f"{PREFIX}/course-selections", json={"teaching_class_id": env["e01"]}, headers=h1
    )
    assert created.status_code == 201
    sel_id = created.json()["id"]
    # 学生 B 删除学生 A 的选课记录 -> 403
    r = client.delete(
        f"{PREFIX}/course-selections/{sel_id}", headers=auth(env["s2_uname"])
    )
    assert r.status_code == 403


# --- 18 学生可以查看自己的选课 ---


def test_student_view_own_selections(env):
    h = auth(env["s1_uname"])
    client.post(
        f"{PREFIX}/course-selections", json={"teaching_class_id": env["e01"]}, headers=h
    )
    client.post(
        f"{PREFIX}/course-selections", json={"teaching_class_id": env["e201"]}, headers=h
    )
    mine = client.get(f"{PREFIX}/course-selections/mine", headers=h).json()
    assert {x["teaching_class_id"] for x in mine} == {env["e01"], env["e201"]}
    for x in mine:
        assert x["student_id"] == env["s1_id"]
        assert x["course_type"] == "ELECTIVE"


# --- 19 学生可以查看可选选修课（不含必修） ---


def test_student_available_only_elective(env):
    rows = client.get(
        f"{PREFIX}/course-selections/available", params={"semester": S1},
        headers=auth(env["s1_uname"]),
    ).json()
    codes = {x["code"] for x in rows}
    assert codes == {env["e01_code"], env["e02_code"], env["e201_code"]}
    assert env["r01_code"] not in codes  # 必修课不出现在可选列表


# --- 20 已选课程不会继续出现在可选列表（含同课程其他教学班） ---


def test_selected_not_in_available(env):
    h = auth(env["s1_uname"])
    client.post(
        f"{PREFIX}/course-selections", json={"teaching_class_id": env["e01"]}, headers=h
    )
    rows = client.get(
        f"{PREFIX}/course-selections/available", params={"semester": S1}, headers=h
    ).json()
    codes = {x["code"] for x in rows}
    assert env["e01_code"] not in codes          # 已选教学班
    assert env["e02_code"] not in codes          # 同课程其他教学班
    assert env["e201_code"] in codes             # 不同选修课仍可选


# --- 21 教师不能修改学生选课 ---


def test_teacher_cannot_modify_selection(env):
    h = auth(env["ta_uname"])
    r_post = client.post(
        f"{PREFIX}/course-selections", json={"teaching_class_id": env["e01"]}, headers=h
    )
    assert r_post.status_code == 403
    r_del = client.delete(f"{PREFIX}/course-selections/1", headers=h)
    assert r_del.status_code == 403


# --- 22 退选不会删除已有 Grade ---


def test_drop_does_not_delete_grade(env):
    h = auth(env["s1_uname"])
    created = client.post(
        f"{PREFIX}/course-selections", json={"teaching_class_id": env["e01"]}, headers=h
    )
    sel_id = created.json()["id"]
    with SessionLocal() as db:
        db.add(Grade(
            student_id=env["s1_id"], teaching_class_id=env["e01"],
            course_id=env["elec_id"], semester=S1, credits=Decimal("2.0"),
        ))
        db.commit()
    r = client.delete(f"{PREFIX}/course-selections/{sel_id}", headers=h)
    assert r.status_code == 204
    with SessionLocal() as db:
        n = db.execute(
            select(func.count()).select_from(Grade).where(
                Grade.student_id == env["s1_id"],
                Grade.teaching_class_id == env["e01"],
            )
        ).scalar()
    assert n == 1  # 成绩记录仍存在


# --- 23 TASK-008 教学班管理继续通过 ---


def test_regression_teaching_class_management(env):
    r = client.get(f"{PREFIX}/teaching-classes", headers=admin_auth())
    assert r.status_code == 200
    codes = {x["code"] for x in r.json()["items"]}
    assert {env["r01_code"], env["e01_code"]} <= codes


# --- 24 TASK-005 教师成绩录入继续通过 ---


def test_regression_teacher_grade_entry(env):
    r = client.get(f"{PREFIX}/teaching-classes/mine", headers=auth(env["ta_uname"]))
    assert r.status_code == 200
    codes = {x["code"] for x in r.json()}
    assert {env["r01_code"], env["e01_code"], env["e02_code"], env["e201_code"]} <= codes


# --- 25 TASK-006 教务审核继续通过 ---


def test_regression_grade_review(env):
    assert client.get(f"{PREFIX}/grades/pending", headers=admin_auth()).status_code == 200


# --- 26 TASK-007 学生成绩查询继续通过 ---


def test_regression_student_grade_query(env):
    r = client.get(f"{PREFIX}/grades/my", headers=auth(env["s1_uname"]))
    assert r.status_code == 200
    assert set(r.json().keys()) == {"items", "gpa", "class_rank", "major_rank"}


# --- 27 非进行中的学期不能选课（TASK-011） ---


def test_cannot_select_in_non_active_term(env):
    with SessionLocal() as db:
        term = db.get(AcademicTerm, env["term"])
        term.status = TermStatus.PLANNED
        db.commit()
    r = client.post(
        f"{PREFIX}/course-selections",
        json={"teaching_class_id": env["e01"]},
        headers=auth(env["s1_uname"]),
    )
    assert r.status_code == 409
    assert "学期" in r.json()["message"]


# --- 28 已结束的学期不能退课（TASK-011） ---


def test_cannot_drop_in_ended_term(env):
    h = auth(env["s1_uname"])
    created = client.post(
        f"{PREFIX}/course-selections", json={"teaching_class_id": env["e01"]}, headers=h
    )
    assert created.status_code == 201
    sel_id = created.json()["id"]
    with SessionLocal() as db:
        term = db.get(AcademicTerm, env["term"])
        term.status = TermStatus.ENDED
        db.commit()
    r = client.delete(f"{PREFIX}/course-selections/{sel_id}", headers=h)
    assert r.status_code == 409
    assert "学期" in r.json()["message"]


# =========================== TASK-012：容量与并发 ===========================


# --- 29 教学班已满时选课被拒（TEACHING_CLASS_FULL） ---


def test_select_full_class_rejected(env):
    with SessionLocal() as db:
        tc = db.get(TeachingClass, env["e01"])
        tc.capacity = 1
        # TASK-013：容量以 CourseSelection 动态统计为准，不再设置 selected_count
        db.add(CourseSelection(
            student_id=env["s2_id"], teaching_class_id=env["e01"],
            course_id=tc.course_id, semester=tc.semester,
        ))
        db.commit()
    r = client.post(
        f"{PREFIX}/course-selections",
        json={"teaching_class_id": env["e01"]},
        headers=auth(env["s1_uname"]),
    )
    assert r.status_code == 409
    assert r.json()["code"] == "TEACHING_CLASS_FULL"


# --- 30 并发选课不超卖（容量边界 + 行级锁） ---


def test_concurrent_selection_no_oversell(env):
    from concurrent.futures import ThreadPoolExecutor

    from app.core.exceptions import Conflict
    from app.services.selection import SelectionService

    # 把 e01 容量压到 2，4 名学生并发抢
    with SessionLocal() as db:
        tc = db.get(TeachingClass, env["e01"])
        tc.capacity = 2
        db.commit()

    def attempt(sid: int) -> int:
        with SessionLocal() as db:
            stu = db.get(Student, sid)
            try:
                SelectionService(db).select_course(stu, env["e01"])
                return 201
            except Conflict:
                return 409

    sids = [env["s1_id"], env["s2_id"], env["s3_id"], env["s4_id"]]
    with ThreadPoolExecutor(max_workers=4) as ex:
        codes = list(ex.map(attempt, sids))

    assert sorted(codes) == [201, 201, 409, 409]

    # 计数一致：实际 SELECTED 数 == 容量，未超卖（TASK-013：动态统计，不再读 selected_count）
    with SessionLocal() as db:
        actual = db.execute(
            select(func.count()).select_from(CourseSelection).where(
                CourseSelection.teaching_class_id == env["e01"],
                CourseSelection.status == SelectionState.SELECTED,
            )
        ).scalar()
    assert actual == 2

