"""TASK-013：教学安排与课表管理测试。

覆盖：教学安排的增删改查、参数校验、三类冲突（教师/教室/教学班自身）、
学期生命周期（PLANNED 可操作 / ACTIVE 可操作 / ENDED 只读）、
角色权限隔离（教务全量管理 / 教师本人 / 学生本人已选），
以及教师 /mine、学生 /my 与各过滤条件。
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
from app.models.organization import Class, Classroom, College, Major
from app.models.person import Student, Teacher
from app.models.role import Role, RoleCode, UserRole
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import Schedule, TeachingClass, TeachingTask
from app.models.term import AcademicTerm, TermStatus
from app.models.user import User, UserType

client = TestClient(app)
PREFIX = settings.API_V1_PREFIX
LOGIN = f"{PREFIX}/auth/login"

P = "__t13__"
PWD = "t13test123"
ADMIN_PWD = "admin123"
S_ACTIVE = "2098-2099-1"
S_PLANNED = "2098-2099-2"
S_ENDED = "2097-2098-1"


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
        db.execute(delete(TeachingTask).where(TeachingTask.course_id.in_(test_courses)))
        db.execute(delete(Classroom).where(Classroom.code.like(f"{P}%")))
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
    """3 课程 / 2 教师 / 4 学生 / 3 学期 / 3 教室 / 5 教学班。

    教学班：tc1(ta,ACTIVE) / tc2(ta,ACTIVE) / tc3(tb,ACTIVE)
           / tc4(ta,ENDED) / tc5(ta,PLANNED)；s01 已选 tc1。
    """
    _cleanup()
    with SessionLocal() as db:
        college = College(code=f"{P}college", name="T13学院")
        db.add(college)
        db.flush()
        major = Major(code=f"{P}major", name="T13专业", college_id=college.id)
        db.add(major)
        db.flush()
        class_a = Class(code=f"{P}cla", name="T13A班", major_id=major.id, grade_year=2026)
        class_b = Class(code=f"{P}clb", name="T13B班", major_id=major.id, grade_year=2026)
        db.add_all([class_a, class_b])
        db.flush()

        c1 = Course(code=f"{P}c1", name="T13课程一", college_id=college.id,
                    course_type="REQUIRED", credits=Decimal("3.0"), total_hours=48,
                    assessment_type="48")
        c2 = Course(code=f"{P}c2", name="T13课程二", college_id=college.id,
                    course_type="REQUIRED", credits=Decimal("2.0"), total_hours=32,
                    assessment_type="32")
        db.add_all([c1, c2])
        db.flush()

        role_teacher = db.execute(
            select(Role).where(Role.code == RoleCode.TEACHER)
        ).scalar_one()
        role_student = db.execute(
            select(Role).where(Role.code == RoleCode.STUDENT)
        ).scalar_one()

        def make_user(username, real_name, user_type, role):
            u = User(username=username, password_hash=hash_password(PWD),
                     real_name=real_name, user_type=user_type)
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
        db.add_all([ta, tb])
        db.flush()

        by_no = {}
        for no, klass in [("s01", class_a), ("s02", class_a),
                          ("s03", class_b), ("s04", class_b)]:
            u = make_user(f"{P}{no}", f"学生{no[1:]}", UserType.STUDENT, role_student)
            s = Student(user_id=u.id, student_no=f"{P}{no}", class_id=klass.id,
                        major_id=major.id, college_id=college.id, enrollment_year=2026)
            db.add(s)
            db.flush()
            by_no[f"{P}{no}"] = s

        # 3 个学期：ACTIVE / PLANNED / ENDED（学年+序号互不相同，满足唯一约束）
        term_active = AcademicTerm(
            name=f"{P}term_active", academic_year="2098-2099", semester=1,
            start_date=date(2098, 9, 1), end_date=date(2099, 1, 15),
            status=TermStatus.ACTIVE,
        )
        term_planned = AcademicTerm(
            name=f"{P}term_planned", academic_year="2098-2099", semester=2,
            start_date=date(2099, 2, 20), end_date=date(2099, 7, 5),
            status=TermStatus.PLANNED,
        )
        term_ended = AcademicTerm(
            name=f"{P}term_ended", academic_year="2097-2098", semester=1,
            start_date=date(2097, 9, 1), end_date=date(2098, 1, 15),
            status=TermStatus.ENDED,
        )
        db.add_all([term_active, term_planned, term_ended])
        db.flush()

        def make_task(course, semester):
            t = TeachingTask(semester=semester, course_id=course.id,
                             college_id=college.id, status="CONFIRMED")
            db.add(t)
            db.flush()
            return t

        task_c1 = make_task(c1, S_ACTIVE)
        task_c2 = make_task(c2, S_ACTIVE)
        task_c1_ended = make_task(c1, S_ENDED)
        task_c2_planned = make_task(c2, S_PLANNED)

        def make_tc(code, task, course, teacher, term, capacity=40):
            tc = TeachingClass(code=code, task_id=task.id, course_id=course.id,
                               semester=task.semester, teacher_id=teacher.id,
                               capacity=capacity, term_id=term.id)
            db.add(tc)
            db.flush()
            return tc

        tc1 = make_tc(f"{P}TC1", task_c1, c1, ta, term_active)
        tc2 = make_tc(f"{P}TC2", task_c2, c2, ta, term_active)
        tc3 = make_tc(f"{P}TC3", task_c1, c1, tb, term_active)
        tc4 = make_tc(f"{P}TC4", task_c1_ended, c1, ta, term_ended)
        tc5 = make_tc(f"{P}TC5", task_c2_planned, c2, ta, term_planned)

        # 教室：r01/r02 大教室，r_small 小教室（容量小于教学班）
        r01 = Classroom(code=f"{P}R01", building="一教", capacity=60, status="ACTIVE")
        r02 = Classroom(code=f"{P}R02", building="二教", capacity=60, status="ACTIVE")
        r_small = Classroom(code=f"{P}RS", building="三教", capacity=20, status="ACTIVE")
        db.add_all([r01, r02, r_small])
        db.flush()

        # s01 已选 tc1（用于学生课表 /my）
        db.add(CourseSelection(
            student_id=by_no[f"{P}s01"].id, teaching_class_id=tc1.id,
            course_id=c1.id, semester=S_ACTIVE, status=SelectionState.SELECTED,
        ))

        db.commit()

        yield {
            "term_active": term_active.id, "term_planned": term_planned.id,
            "term_ended": term_ended.id,
            "r01": r01.id, "r02": r02.id, "r_small": r_small.id,
            "r01_code": f"{P}R01",
            "tc1": tc1.id, "tc2": tc2.id, "tc3": tc3.id, "tc4": tc4.id,
            "tc5": tc5.id,
            "ta_id": ta.id, "tb_id": tb.id,
            "ta_uname": f"{P}ta", "tb_uname": f"{P}tb",
            "s1_uname": f"{P}s01", "s2_uname": f"{P}s02",
            "s3_uname": f"{P}s03", "s4_uname": f"{P}s04",
        }
    _cleanup()


def _payload(tc_id, room_id, day=1, sp=1, ep=2, sw=1, ew=16, wt="ALL"):
    return {
        "teaching_class_id": tc_id, "classroom_id": room_id,
        "day_of_week": day, "start_period": sp, "end_period": ep,
        "start_week": sw, "end_week": ew, "week_type": wt,
    }


def _create(env, payload):
    return client.post(f"{PREFIX}/teaching-schedules", json=payload,
                       headers=admin_auth())


# =========================== 创建 ===========================


def test_create_schedule_ok(env):
    r = _create(env, _payload(env["tc1"], env["r01"]))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["teaching_class_id"] == env["tc1"]
    assert body["classroom_id"] == env["r01"]
    assert body["classroom_code"] == env["r01_code"]
    assert body["day_of_week"] == 1 and body["start_period"] == 1
    # 富化字段：教学班/课程/教师/学期/教室
    assert body["teaching_class_code"] == f"{P}TC1"
    assert body["course_name"] == "T13课程一"
    assert body["teacher_name"] == "教师甲"
    assert body["term_id"] == env["term_active"]
    assert body["term_name"] == f"{P}term_active"


def test_create_schedule_day_of_week_invalid(env):
    r = _create(env, _payload(env["tc1"], env["r01"], day=8))
    assert r.status_code == 422


def test_create_schedule_period_invalid(env):
    r = _create(env, _payload(env["tc1"], env["r01"], sp=3, ep=2))
    assert r.status_code == 422


def test_create_schedule_week_type_invalid(env):
    r = _create(env, _payload(env["tc1"], env["r01"], wt="FOO"))
    assert r.status_code == 422


def test_create_schedule_classroom_not_found(env):
    r = _create(env, _payload(env["tc1"], 999999))
    assert r.status_code == 404
    assert "教室不存在" in r.json()["message"]


def test_create_schedule_tc_not_found(env):
    r = _create(env, _payload(999999, env["r01"]))
    assert r.status_code == 404


def test_create_schedule_classroom_capacity_small(env):
    r = _create(env, _payload(env["tc1"], env["r_small"]))
    assert r.status_code == 409
    assert "容量" in r.json()["message"]


# =========================== 三类冲突 ===========================


def test_create_teacher_conflict(env):
    assert _create(env, _payload(env["tc1"], env["r01"])).status_code == 201
    r = _create(env, _payload(env["tc2"], env["r02"]))  # 同为教师 ta
    assert r.status_code == 409
    assert r.json()["code"] == "TEACHING_SCHEDULE_TEACHER_CONFLICT"


def test_create_classroom_conflict(env):
    assert _create(env, _payload(env["tc1"], env["r01"])).status_code == 201
    r = _create(env, _payload(env["tc3"], env["r01"]))  # 不同教师 tb，同教室
    assert r.status_code == 409
    assert r.json()["code"] == "TEACHING_SCHEDULE_CLASSROOM_CONFLICT"


def test_create_class_self_conflict(env):
    assert _create(env, _payload(env["tc1"], env["r01"])).status_code == 201
    r = _create(env, _payload(env["tc1"], env["r02"]))  # 同一教学班重叠时段
    assert r.status_code == 409
    assert r.json()["code"] == "TEACHING_SCHEDULE_CLASS_CONFLICT"


# =========================== 学期生命周期 ===========================


def test_create_schedule_term_planned_ok(env):
    r = _create(env, _payload(env["tc5"], env["r01"]))
    assert r.status_code == 201


def test_create_schedule_term_ended(env):
    r = _create(env, _payload(env["tc4"], env["r01"]))
    assert r.status_code == 409
    assert r.json()["code"] == "TEACHING_SCHEDULE_TERM_ENDED"


def _insert_schedule(env, tc_id, room_id):
    """绕过 API 直接在 ENDED 学期教学班下插一条排课，用于测试只读语义。"""
    with SessionLocal() as db:
        tc = db.get(TeachingClass, tc_id)
        s = Schedule(teaching_class_id=tc_id, classroom_id=room_id,
                     semester=tc.semester, day_of_week=1, start_period=1,
                     end_period=2, start_week=1, end_week=16, week_type="ALL")
        db.add(s)
        db.commit()
        return s.id


def test_update_schedule_term_ended(env):
    sid = _insert_schedule(env, env["tc4"], env["r01"])
    r = client.put(f"{PREFIX}/teaching-schedules/{sid}",
                   json={"day_of_week": 2}, headers=admin_auth())
    assert r.status_code == 409
    assert r.json()["code"] == "TEACHING_SCHEDULE_TERM_ENDED"


def test_delete_schedule_term_ended(env):
    sid = _insert_schedule(env, env["tc4"], env["r01"])
    r = client.delete(f"{PREFIX}/teaching-schedules/{sid}", headers=admin_auth())
    assert r.status_code == 409
    assert r.json()["code"] == "TEACHING_SCHEDULE_TERM_ENDED"


# =========================== 修改 ===========================


def test_update_schedule_ok(env):
    sid = _create(env, _payload(env["tc1"], env["r01"])).json()["id"]
    r = client.put(f"{PREFIX}/teaching-schedules/{sid}",
                   json={"day_of_week": 3, "classroom_id": env["r02"]},
                   headers=admin_auth())
    assert r.status_code == 200, r.text
    assert r.json()["day_of_week"] == 3
    assert r.json()["classroom_id"] == env["r02"]


def test_update_schedule_no_self_conflict(env):
    """修改自身时须排除自己，仅换教室不应报冲突。"""
    sid = _create(env, _payload(env["tc1"], env["r01"])).json()["id"]
    r = client.put(f"{PREFIX}/teaching-schedules/{sid}",
                   json={"classroom_id": env["r02"]}, headers=admin_auth())
    assert r.status_code == 200
    assert r.json()["classroom_id"] == env["r02"]


def test_update_schedule_not_found(env):
    r = client.put(f"{PREFIX}/teaching-schedules/999999",
                   json={"day_of_week": 2}, headers=admin_auth())
    assert r.status_code == 404


def test_update_schedule_validation(env):
    sid = _create(env, _payload(env["tc1"], env["r01"])).json()["id"]
    r = client.put(f"{PREFIX}/teaching-schedules/{sid}",
                   json={"day_of_week": 0}, headers=admin_auth())
    assert r.status_code == 422


# =========================== 删除 / 查询 ===========================


def test_delete_schedule_ok(env):
    sid = _create(env, _payload(env["tc1"], env["r01"])).json()["id"]
    r = client.delete(f"{PREFIX}/teaching-schedules/{sid}", headers=admin_auth())
    assert r.status_code == 204
    g = client.get(f"{PREFIX}/teaching-schedules/{sid}", headers=admin_auth())
    assert g.status_code == 404


def test_delete_schedule_not_found(env):
    r = client.delete(f"{PREFIX}/teaching-schedules/999999", headers=admin_auth())
    assert r.status_code == 404


def test_get_schedule_detail(env):
    sid = _create(env, _payload(env["tc1"], env["r01"])).json()["id"]
    r = client.get(f"{PREFIX}/teaching-schedules/{sid}", headers=admin_auth())
    assert r.status_code == 200
    assert r.json()["id"] == sid
    assert r.json()["teaching_class_code"] == f"{P}TC1"


def test_list_schedules_admin(env):
    s1 = _create(env, _payload(env["tc1"], env["r01"])).json()["id"]
    s2 = _create(env, _payload(env["tc2"], env["r02"], day=2)).json()["id"]
    s3 = _create(env, _payload(env["tc3"], env["r01"], day=3)).json()["id"]
    r = client.get(f"{PREFIX}/teaching-schedules", headers=admin_auth())
    assert r.status_code == 200
    ids = {x["id"] for x in r.json()}
    assert {s1, s2, s3} <= ids


def test_list_filter_teaching_class(env):
    _create(env, _payload(env["tc1"], env["r01"]))
    _create(env, _payload(env["tc2"], env["r02"]))
    r = client.get(f"{PREFIX}/teaching-schedules",
                   params={"teaching_class_id": env["tc1"]}, headers=admin_auth())
    assert len(r.json()) == 1
    assert r.json()[0]["teaching_class_id"] == env["tc1"]


def test_list_filter_teacher(env):
    _create(env, _payload(env["tc1"], env["r01"]))
    _create(env, _payload(env["tc2"], env["r02"], day=2))
    _create(env, _payload(env["tc3"], env["r01"], day=3))
    r = client.get(f"{PREFIX}/teaching-schedules",
                   params={"teacher_id": env["ta_id"]}, headers=admin_auth())
    assert len(r.json()) == 2
    assert all(x["teacher_id"] == env["ta_id"] for x in r.json())


def test_list_filter_weekday(env):
    sid = _create(env, _payload(env["tc1"], env["r01"], day=5)).json()["id"]
    _create(env, _payload(env["tc2"], env["r02"], day=1))
    r = client.get(f"{PREFIX}/teaching-schedules",
                   params={"weekday": 5}, headers=admin_auth())
    assert all(x["day_of_week"] == 5 for x in r.json())
    assert sid in {x["id"] for x in r.json()}


def test_list_filter_classroom(env):
    _create(env, _payload(env["tc1"], env["r01"]))
    _create(env, _payload(env["tc2"], env["r02"]))
    r = client.get(f"{PREFIX}/teaching-schedules",
                   params={"classroom": env["r01_code"]}, headers=admin_auth())
    assert len(r.json()) == 1
    assert r.json()[0]["classroom_code"] == env["r01_code"]


def test_list_sorted_order(env):
    # 创建乱序：先周五后周一
    _create(env, _payload(env["tc1"], env["r01"], day=5, sp=1, ep=2))
    _create(env, _payload(env["tc2"], env["r02"], day=1, sp=3, ep=4))
    _create(env, _payload(env["tc3"], env["r01"], day=1, sp=1, ep=2))
    r = client.get(f"{PREFIX}/teaching-schedules", headers=admin_auth())
    keys = [(x["day_of_week"], x["start_period"], x["start_week"]) for x in r.json()]
    assert keys == sorted(keys)


# =========================== 权限 ===========================


def test_create_forbidden_teacher(env):
    r = client.post(f"{PREFIX}/teaching-schedules",
                    json=_payload(env["tc1"], env["r01"]),
                    headers=auth(env["ta_uname"]))
    assert r.status_code == 403


def test_create_forbidden_student(env):
    r = client.post(f"{PREFIX}/teaching-schedules",
                    json=_payload(env["tc1"], env["r01"]),
                    headers=auth(env["s1_uname"]))
    assert r.status_code == 403


def test_list_forbidden_teacher(env):
    r = client.get(f"{PREFIX}/teaching-schedules", headers=auth(env["ta_uname"]))
    assert r.status_code == 403


def test_get_forbidden_student(env):
    sid = _create(env, _payload(env["tc1"], env["r01"])).json()["id"]
    r = client.get(f"{PREFIX}/teaching-schedules/{sid}",
                   headers=auth(env["s1_uname"]))
    assert r.status_code == 403


# =========================== 教师 /mine ===========================


def test_teacher_mine(env):
    _create(env, _payload(env["tc1"], env["r01"]))
    _create(env, _payload(env["tc2"], env["r02"], day=2))
    _create(env, _payload(env["tc3"], env["r01"], day=3))  # tb 的，不应出现
    r = client.get(f"{PREFIX}/teaching-schedules/mine",
                   headers=auth(env["ta_uname"]))
    assert r.status_code == 200
    assert {x["teacher_id"] for x in r.json()} == {env["ta_id"]}
    assert len(r.json()) == 2


def test_teacher_mine_term_filter(env):
    _create(env, _payload(env["tc1"], env["r01"]))          # ACTIVE
    _create(env, _payload(env["tc5"], env["r02"], day=2))   # PLANNED
    r = client.get(f"{PREFIX}/teaching-schedules/mine",
                   params={"term_id": env["term_active"]},
                   headers=auth(env["ta_uname"]))
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["term_id"] == env["term_active"]


def test_teacher_mine_forbidden_student(env):
    r = client.get(f"{PREFIX}/teaching-schedules/mine",
                   headers=auth(env["s1_uname"]))
    assert r.status_code == 403


# =========================== 学生 /my ===========================


def test_student_my(env):
    _create(env, _payload(env["tc1"], env["r01"]))
    _create(env, _payload(env["tc2"], env["r02"], day=2))  # s01 未选，不应出现
    r = client.get(f"{PREFIX}/teaching-schedules/my",
                   headers=auth(env["s1_uname"]))
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["teaching_class_id"] == env["tc1"]


def test_student_my_empty(env):
    # s02 未选任何课，应返回空列表而非 404
    r = client.get(f"{PREFIX}/teaching-schedules/my",
                   headers=auth(env["s2_uname"]))
    assert r.status_code == 200
    assert r.json() == []


def test_student_my_term_filter(env):
    _create(env, _payload(env["tc1"], env["r01"]))
    r = client.get(f"{PREFIX}/teaching-schedules/my",
                   params={"term_id": env["term_active"]},
                   headers=auth(env["s1_uname"]))
    assert r.status_code == 200
    assert len(r.json()) == 1
    r2 = client.get(f"{PREFIX}/teaching-schedules/my",
                    params={"term_id": env["term_planned"]},
                    headers=auth(env["s1_uname"]))
    assert r2.json() == []


def test_student_my_forbidden_teacher(env):
    r = client.get(f"{PREFIX}/teaching-schedules/my",
                   headers=auth(env["ta_uname"]))
    assert r.status_code == 403
