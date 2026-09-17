"""TASK-011：学期管理 + 学期开课管理 + 教学班学期绑定测试。

覆盖：学期的增删改查、状态流转（PLANNED → ACTIVE → ENDED 单向）、
单激活约束、(学年, 学期) 唯一、日期校验、教学班与学期绑定
（必填 term_id、已结束学期不可开课、按学期过滤）、以及
term:read / term:write 权限隔离（学生/教师只读，仅教务可维护）。
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
from app.models.organization import College, Major
from app.models.person import Student, Teacher
from app.models.role import Role, RoleCode, UserRole
from app.models.selection import CourseSelection
from app.models.teaching import TeachingClass, TeachingTask
from app.models.term import AcademicTerm, TermStatus
from app.models.user import User, UserType

client = TestClient(app)
PREFIX = settings.API_V1_PREFIX
LOGIN = f"{PREFIX}/auth/login"

P = "__t11__"
PWD = "t11test123"
ADMIN_PWD = "admin123"

# 演示数据中的进行中学期（seed_demo），单激活测试前需要临时降级
SEED_YEAR = "2026-2027"
SEED_SEM = 1


def auth(username: str, password: str = PWD) -> dict:
    r = client.post(LOGIN, json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def admin_auth() -> dict:
    return auth("admin", ADMIN_PWD)


def _term_payload(year: int = 2200, sem: int = 1, status: str | None = None,
                  **overrides) -> dict:
    d = {
        "name": f"{P}term{year}-{sem}",
        "academic_year": f"{year}-{year + 1}",
        "semester": sem,
        "start_date": f"{year}-09-01",
        "end_date": f"{year + 1}-01-15",
    }
    if status is not None:
        d["status"] = status
    d.update(overrides)
    return d


def _set_seed_active(active: bool) -> None:
    """临时把演示数据的进行中学期降级为 PLANNED（或恢复 ACTIVE）。

    TASK-011 约束「全系统最多一个 ACTIVE 学期」，而 seed_demo 已有一个
    ACTIVE 学期，会干扰单激活类测试；测试通过 ORM 直接改状态绕开接口校验。
    """
    with SessionLocal() as db:
        t = db.execute(
            select(AcademicTerm).where(
                AcademicTerm.academic_year == SEED_YEAR,
                AcademicTerm.semester == SEED_SEM,
            )
        ).scalar_one_or_none()
        if t is not None:
            t.status = TermStatus.ACTIVE if active else TermStatus.PLANNED
            db.commit()


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
        db.execute(delete(Major).where(Major.code.like(f"{P}%")))
        db.execute(delete(Course).where(Course.code.like(f"{P}%")))
        db.execute(delete(College).where(College.code.like(f"{P}%")))
        db.commit()


@pytest.fixture
def env():
    """1 学院 / 1 课程 / 1 教学任务 / 1 教师 / 1 学生账号 + 1 默认学期。

    默认学期用于教学班绑定类测试；学期 CRUD/状态类测试各自通过接口新建学期。
    教师/学生账号仅带角色（TASK-011 权限点），用于 term:read/term:write 隔离。
    """
    _cleanup()
    _set_seed_active(False)  # 降级演示 ACTIVE 学期，保证单激活测试可用
    with SessionLocal() as db:
        college = College(code=f"{P}college", name="T11学院")
        db.add(college)
        db.flush()

        course = Course(
            code=f"{P}course", name="T11课程", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("3.0"), total_hours=48,
            assessment_type="48",
        )
        db.add(course)
        db.flush()
        task = TeachingTask(
            semester="2102-2103-1", course_id=course.id, college_id=college.id,
            status="CONFIRMED",
        )
        db.add(task)
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
        make_user(f"{P}s01", "学生甲", UserType.STUDENT, role_student)

        term = AcademicTerm(
            name=f"{P}term", academic_year="2102-2103", semester=1,
            start_date=date(2102, 9, 1), end_date=date(2103, 1, 15),
            status="PLANNED",
        )
        db.add(term)
        db.flush()

        db.commit()

        yield {
            "college": college.id,
            "course": course.id,
            "task": task.id,
            "term": term.id,
            "ta_id": ta.id,
            "ta_uname": f"{P}ta",
            "s_uname": f"{P}s01",
        }
    _cleanup()
    _set_seed_active(True)  # 恢复演示 ACTIVE 学期


# =========================== 新增学期 ===========================


def test_admin_create_term(env):
    r = client.post(f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == f"{P}term2200-1"
    assert body["academic_year"] == "2200-2201"
    assert body["semester"] == 1
    assert body["start_date"] == "2200-09-01"
    assert body["end_date"] == "2201-01-15"
    assert body["status"] == "PLANNED"  # 默认 PLANNED
    assert body["teaching_class_count"] == 0


def test_create_term_with_active_status(env):
    r = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200, status="ACTIVE"),
        headers=admin_auth(),
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "ACTIVE"


def test_create_term_missing_name(env):
    r = client.post(
        f"{PREFIX}/terms",
        json={"academic_year": "2200-2201", "semester": 1,
              "start_date": "2200-09-01", "end_date": "2201-01-15"},
        headers=admin_auth(),
    )
    assert r.status_code == 422


def test_create_term_empty_academic_year(env):
    r = client.post(
        f"{PREFIX}/terms",
        json=_term_payload(2200, academic_year=""),
        headers=admin_auth(),
    )
    assert r.status_code == 422


def test_create_term_invalid_semester(env):
    r = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200, sem=3), headers=admin_auth()
    )
    assert r.status_code == 422


def test_create_term_invalid_dates(env):
    r = client.post(
        f"{PREFIX}/terms",
        json=_term_payload(2200, end_date="2200-08-31"),
        headers=admin_auth(),
    )
    assert r.status_code == 422


def test_create_duplicate_year_semester(env):
    assert client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth()
    ).status_code == 201
    r = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200, name=f"{P}term2200-1-dup"),
        headers=admin_auth(),
    )
    assert r.status_code == 409
    assert "学年" in r.json()["message"]


# =========================== 列表 / 详情 ===========================


def test_list_terms(env):
    tid = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth()
    ).json()["id"]
    rows = client.get(f"{PREFIX}/terms", headers=admin_auth()).json()
    ids = {x["id"] for x in rows["items"]}
    assert tid in ids
    assert all("teaching_class_count" in x for x in rows["items"])


def test_list_filter_by_academic_year(env):
    tid = client.post(
        f"{PREFIX}/terms", json=_term_payload(2300), headers=admin_auth()
    ).json()["id"]
    rows = client.get(
        f"{PREFIX}/terms", params={"academic_year": "2300-2301"},
        headers=admin_auth(),
    ).json()
    assert [x["id"] for x in rows["items"]] == [tid]


def test_list_filter_by_status(env):
    tid = client.post(
        f"{PREFIX}/terms", json=_term_payload(2300, status="ACTIVE"),
        headers=admin_auth(),
    ).json()["id"]
    rows = client.get(
        f"{PREFIX}/terms", params={"status": "ACTIVE"}, headers=admin_auth()
    ).json()
    assert tid in {x["id"] for x in rows["items"]}
    assert all(x["status"] == "ACTIVE" for x in rows["items"])


def test_get_term(env):
    tid = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth()
    ).json()["id"]
    r = client.get(f"{PREFIX}/terms/{tid}", headers=admin_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == tid
    assert body["name"] == f"{P}term2200-1"
    assert body["teaching_class_count"] == 0


def test_get_nonexistent_term(env):
    r = client.get(f"{PREFIX}/terms/99999999", headers=admin_auth())
    assert r.status_code == 404


# =========================== 修改学期 ===========================


def test_update_term_name(env):
    tid = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth()
    ).json()["id"]
    r = client.put(
        f"{PREFIX}/terms/{tid}", json={"name": f"{P}term2200-1-renamed"},
        headers=admin_auth(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == f"{P}term2200-1-renamed"


def test_update_term_dates(env):
    tid = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth()
    ).json()["id"]
    r = client.put(
        f"{PREFIX}/terms/{tid}",
        json={"start_date": "2200-09-15", "end_date": "2201-01-20"},
        headers=admin_auth(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["start_date"] == "2200-09-15"
    assert r.json()["end_date"] == "2201-01-20"


def test_update_term_conflicting_year_semester(env):
    client.post(f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth())
    tid_b = client.post(
        f"{PREFIX}/terms", json=_term_payload(2201), headers=admin_auth()
    ).json()["id"]
    r = client.put(
        f"{PREFIX}/terms/{tid_b}",
        json={"academic_year": "2200-2201", "semester": 1},
        headers=admin_auth(),
    )
    assert r.status_code == 409
    assert "学年" in r.json()["message"]


# =========================== 状态流转 ===========================


def test_activate_planned_term(env):
    tid = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth()
    ).json()["id"]
    r = client.post(f"{PREFIX}/terms/{tid}/activate", headers=admin_auth())
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ACTIVE"


def test_activate_ended_term_rejected(env):
    tid = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth()
    ).json()["id"]
    client.post(f"{PREFIX}/terms/{tid}/activate", headers=admin_auth())
    client.post(f"{PREFIX}/terms/{tid}/end", headers=admin_auth())
    r = client.post(f"{PREFIX}/terms/{tid}/activate", headers=admin_auth())
    assert r.status_code == 409
    assert "已结束" in r.json()["message"]


def test_end_active_term(env):
    tid = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth()
    ).json()["id"]
    client.post(f"{PREFIX}/terms/{tid}/activate", headers=admin_auth())
    r = client.post(f"{PREFIX}/terms/{tid}/end", headers=admin_auth())
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ENDED"


def test_end_planned_term_rejected(env):
    tid = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth()
    ).json()["id"]
    r = client.post(f"{PREFIX}/terms/{tid}/end", headers=admin_auth())
    assert r.status_code == 409
    assert "进行中" in r.json()["message"]


def test_end_ended_term_rejected(env):
    tid = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth()
    ).json()["id"]
    client.post(f"{PREFIX}/terms/{tid}/activate", headers=admin_auth())
    client.post(f"{PREFIX}/terms/{tid}/end", headers=admin_auth())
    r = client.post(f"{PREFIX}/terms/{tid}/end", headers=admin_auth())
    assert r.status_code == 409


def test_ended_term_cannot_change_status(env):
    tid = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth()
    ).json()["id"]
    client.post(f"{PREFIX}/terms/{tid}/activate", headers=admin_auth())
    client.post(f"{PREFIX}/terms/{tid}/end", headers=admin_auth())
    r = client.put(
        f"{PREFIX}/terms/{tid}", json={"status": "PLANNED"}, headers=admin_auth()
    )
    assert r.status_code == 409
    assert "已结束" in r.json()["message"]


def test_single_active_enforced(env):
    id_a = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth()
    ).json()["id"]
    id_b = client.post(
        f"{PREFIX}/terms", json=_term_payload(2201), headers=admin_auth()
    ).json()["id"]
    assert client.post(
        f"{PREFIX}/terms/{id_a}/activate", headers=admin_auth()
    ).status_code == 200
    r = client.post(f"{PREFIX}/terms/{id_b}/activate", headers=admin_auth())
    assert r.status_code == 409
    assert "进行中" in r.json()["message"]


def test_create_active_while_another_active(env):
    assert client.post(
        f"{PREFIX}/terms", json=_term_payload(2200, status="ACTIVE"),
        headers=admin_auth(),
    ).status_code == 201
    r = client.post(
        f"{PREFIX}/terms", json=_term_payload(2201, status="ACTIVE"),
        headers=admin_auth(),
    )
    assert r.status_code == 409


# =========================== 删除学期 ===========================


def test_delete_term_no_references(env):
    tid = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=admin_auth()
    ).json()["id"]
    r = client.delete(f"{PREFIX}/terms/{tid}", headers=admin_auth())
    assert r.status_code == 204
    assert client.get(
        f"{PREFIX}/terms/{tid}", headers=admin_auth()
    ).status_code == 404


def test_delete_term_with_teaching_classes_rejected(env):
    client.post(
        f"{PREFIX}/teaching-classes",
        json={"code": f"{P}tc1", "task_id": env["task"], "term_id": env["term"],
              "teacher_id": env["ta_id"], "capacity": 40},
        headers=admin_auth(),
    )
    r = client.delete(f"{PREFIX}/terms/{env['term']}", headers=admin_auth())
    assert r.status_code == 409
    assert "教学班" in r.json()["message"]


def test_delete_nonexistent_term(env):
    r = client.delete(f"{PREFIX}/terms/99999999", headers=admin_auth())
    assert r.status_code == 404


# =========================== 教学班与学期绑定 ===========================


def test_create_teaching_class_requires_term_id(env):
    r = client.post(
        f"{PREFIX}/teaching-classes",
        json={"code": f"{P}tc2", "task_id": env["task"], "capacity": 40},
        headers=admin_auth(),
    )
    assert r.status_code == 422


def test_create_teaching_class_in_ended_term_rejected(env):
    with SessionLocal() as db:
        term = db.get(AcademicTerm, env["term"])
        term.status = TermStatus.ENDED
        db.commit()
    r = client.post(
        f"{PREFIX}/teaching-classes",
        json={"code": f"{P}tc3", "task_id": env["task"], "term_id": env["term"],
              "teacher_id": env["ta_id"], "capacity": 40},
        headers=admin_auth(),
    )
    assert r.status_code == 409
    assert "已结束" in r.json()["message"]


def test_teaching_class_list_filter_by_term(env):
    r = client.post(
        f"{PREFIX}/teaching-classes",
        json={"code": f"{P}tc4", "task_id": env["task"], "term_id": env["term"],
              "teacher_id": env["ta_id"], "capacity": 40},
        headers=admin_auth(),
    )
    assert r.status_code == 201, r.text
    rows = client.get(
        f"{PREFIX}/teaching-classes", params={"term_id": env["term"]},
        headers=admin_auth(),
    ).json()
    assert f"{P}tc4" in {x["code"] for x in rows["items"]}
    other = client.get(
        f"{PREFIX}/teaching-classes", params={"term_id": env["term"] + 99999},
        headers=admin_auth(),
    ).json()
    assert f"{P}tc4" not in {x["code"] for x in other["items"]}


def test_teaching_class_out_includes_term(env):
    r = client.post(
        f"{PREFIX}/teaching-classes",
        json={"code": f"{P}tc5", "task_id": env["task"], "term_id": env["term"],
              "teacher_id": env["ta_id"], "capacity": 40},
        headers=admin_auth(),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["term_id"] == env["term"]
    assert body["term_name"] == f"{P}term"
    assert body["term_status"] == "PLANNED"


# =========================== 权限隔离 ===========================


def test_teacher_can_list_terms(env):
    r = client.get(f"{PREFIX}/terms", headers=auth(env["ta_uname"]))
    assert r.status_code == 200


def test_student_can_list_terms(env):
    r = client.get(f"{PREFIX}/terms", headers=auth(env["s_uname"]))
    assert r.status_code == 200


def test_teacher_can_get_term(env):
    r = client.get(f"{PREFIX}/terms/{env['term']}", headers=auth(env["ta_uname"]))
    assert r.status_code == 200
    assert r.json()["id"] == env["term"]


def test_teacher_cannot_create_term(env):
    r = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=auth(env["ta_uname"])
    )
    assert r.status_code == 403


def test_student_cannot_create_term(env):
    r = client.post(
        f"{PREFIX}/terms", json=_term_payload(2200), headers=auth(env["s_uname"])
    )
    assert r.status_code == 403


def test_teacher_cannot_update_term(env):
    r = client.put(
        f"{PREFIX}/terms/{env['term']}", json={"name": "越权修改"},
        headers=auth(env["ta_uname"]),
    )
    assert r.status_code == 403


def test_teacher_cannot_delete_term(env):
    r = client.delete(f"{PREFIX}/terms/{env['term']}", headers=auth(env["ta_uname"]))
    assert r.status_code == 403


def test_teacher_cannot_activate_term(env):
    r = client.post(
        f"{PREFIX}/terms/{env['term']}/activate", headers=auth(env["ta_uname"])
    )
    assert r.status_code == 403


def test_unauthenticated_denied(env):
    r = client.get(f"{PREFIX}/terms")
    assert r.status_code == 401
