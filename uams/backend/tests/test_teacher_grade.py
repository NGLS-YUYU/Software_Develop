"""TASK-005：教师成绩录入与提交测试。

覆盖：教师我的课程、越权防护、学生名单、草稿保存、非法成绩拒绝、
32/48 课时与理论+实践录入（含理论/实践总评回显）、补考录入与资格校验、
完整/不完整提交、SUBMITTED/APPROVED/REJECTED 状态流转、学生越权、跨教师越权。
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

P = "__t5__"
PWD = "t5test123"
SEMESTER = "2026-2027-1"


def _num(v):
    """把 Decimal/str/float 统一转 float，便于断言。"""
    return float(v) if v is not None else None


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
    """1 学院 / 1 专业 / 1 班级 / 2 课程(32/48) / 2 教师 / 3 学生 / 2 教学班 + 选课。"""
    _cleanup()
    with SessionLocal() as db:
        college = College(code=f"{P}college", name="T5学院")
        db.add(college)
        db.flush()
        major = Major(code=f"{P}major", name="T5专业", college_id=college.id)
        db.add(major)
        db.flush()
        klass = Class(
            code=f"{P}class", name="T5班", major_id=major.id, grade_year=2026
        )
        db.add(klass)
        db.flush()

        c32 = Course(
            code=f"{P}c32", name="T5两段课", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("2.0"), total_hours=32, theory_hours=32,
            assessment_type="32",
        )
        c48 = Course(
            code=f"{P}c48", name="T5三段课", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("3.0"), total_hours=48, theory_hours=48,
            assessment_type="48",
        )
        c48p = Course(
            code=f"{P}c48p", name="T5实践课", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("3.0"), total_hours=48,
            theory_hours=40, practice_hours=8, assessment_type="48",
        )
        db.add_all([c32, c48, c48p])
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

        ta_u = make_user(f"{P}t01", "教师甲", UserType.TEACHER, role_teacher)
        ta = Teacher(user_id=ta_u.id, teacher_no=f"{P}t01", college_id=college.id)
        tb_u = make_user(f"{P}t02", "教师乙", UserType.TEACHER, role_teacher)
        tb = Teacher(user_id=tb_u.id, teacher_no=f"{P}t02", college_id=college.id)
        db.add_all([ta, tb])
        db.flush()

        students = []
        for i in range(1, 4):
            no = f"{P}s0{i}"
            u = make_user(no, f"学生{i}", UserType.STUDENT, role_student)
            s = Student(
                user_id=u.id, student_no=no, class_id=klass.id,
                major_id=major.id, college_id=college.id, enrollment_year=2026,
            )
            db.add(s)
            db.flush()
            students.append(s)

        task32 = TeachingTask(
            semester=SEMESTER, course_id=c32.id, college_id=college.id,
            status="CONFIRMED",
        )
        task48 = TeachingTask(
            semester=SEMESTER, course_id=c48.id, college_id=college.id,
            status="CONFIRMED",
        )
        task48p = TeachingTask(
            semester=SEMESTER, course_id=c48p.id, college_id=college.id,
            status="CONFIRMED",
        )
        db.add_all([task32, task48, task48p])
        db.flush()

        term = AcademicTerm(
            name=f"{P}term", academic_year="2095-2096", semester=1,
            start_date=date(2095, 9, 1), end_date=date(2096, 1, 15),
            status="PLANNED",
        )
        db.add(term)
        db.flush()

        tca = TeachingClass(
            code=f"{P}tca", task_id=task32.id, course_id=c32.id,
            semester=SEMESTER, teacher_id=ta.id, capacity=40, term_id=term.id,
        )
        tcb = TeachingClass(
            code=f"{P}tcb", task_id=task48.id, course_id=c48.id,
            semester=SEMESTER, teacher_id=tb.id, capacity=40, term_id=term.id,
        )
        tcc = TeachingClass(
            code=f"{P}tcc", task_id=task48p.id, course_id=c48p.id,
            semester=SEMESTER, teacher_id=tb.id, capacity=40, term_id=term.id,
        )
        db.add_all([tca, tcb, tcc])
        db.flush()

        # S1、S2 选教师甲的两段课；S3 选教师乙的三段课与实践课
        for s in students[:2]:
            db.add(CourseSelection(
                student_id=s.id, teaching_class_id=tca.id, course_id=c32.id,
                semester=SEMESTER, status=SelectionState.SELECTED,
            ))
        db.add(CourseSelection(
            student_id=students[2].id, teaching_class_id=tcb.id, course_id=c48.id,
            semester=SEMESTER, status=SelectionState.SELECTED,
        ))
        db.add(CourseSelection(
            student_id=students[2].id, teaching_class_id=tcc.id, course_id=c48p.id,
            semester=SEMESTER, status=SelectionState.SELECTED,
        ))
        db.commit()

        yield {
            "tca": tca.id, "tcb": tcb.id, "tcc": tcc.id,
            "ta_uname": f"{P}t01", "tb_uname": f"{P}t02",
            "stu_uname": f"{P}s01",
            "s1_no": f"{P}s01", "s2_no": f"{P}s02", "s3_no": f"{P}s03",
        }
    _cleanup()


def _init_sheet(class_id: int, uname: str) -> list[dict]:
    r = client.post(
        f"{PREFIX}/grades/teaching-classes/{class_id}/init", headers=auth(uname)
    )
    assert r.status_code == 200, r.text
    return r.json()


def _save(class_id: int, uname: str, items: list[dict]):
    return client.put(
        f"{PREFIX}/grades",
        json={"teaching_class_id": class_id, "items": items},
        headers=auth(uname),
    )


def _grade_of(sheet: list[dict], student_no: str) -> dict:
    return next(x for x in sheet if x["student_no"] == student_no)


# --- 1 教师查看自己的课程 ---


def test_teacher_my_courses(env):
    r = client.get(f"{PREFIX}/teaching-classes/mine", headers=auth(env["ta_uname"]))
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert env["tca"] in ids
    assert env["tcb"] not in ids


# --- 2 教师不能查看其他教师课程 ---


def test_teacher_cannot_access_other_teacher_course(env):
    mine = client.get(f"{PREFIX}/teaching-classes/mine", headers=auth(env["ta_uname"]))
    assert env["tcb"] not in [c["id"] for c in mine.json()]

    # 通过 URL 篡改 class_id 访问他人成绩单 / 名单 → 403
    r1 = client.get(
        f"{PREFIX}/grades/teaching-classes/{env['tcb']}", headers=auth(env["ta_uname"])
    )
    assert r1.status_code == 403
    r2 = client.get(
        f"{PREFIX}/grades/teaching-classes/{env['tcb']}/students",
        headers=auth(env["ta_uname"]),
    )
    assert r2.status_code == 403


# --- 3 教师查看课程学生 ---


def test_teacher_view_roster(env):
    r = client.get(
        f"{PREFIX}/grades/teaching-classes/{env['tca']}/students",
        headers=auth(env["ta_uname"]),
    )
    assert r.status_code == 200
    rows = r.json()
    assert [x["student_no"] for x in rows] == [env["s1_no"], env["s2_no"]]
    assert all(x["entry_status"] == "NOT_ENTERED" for x in rows)


# --- 4 教师保存成绩草稿 ---


def test_save_draft(env):
    sheet = _init_sheet(env["tca"], env["ta_uname"])
    g = _grade_of(sheet, env["s1_no"])
    r = _save(env["tca"], env["ta_uname"], [{"grade_id": g["id"], "regular_score": 88}])
    assert r.status_code == 200
    row = _grade_of(r.json(), env["s1_no"])
    assert _num(row["regular_score"]) == 88.0
    assert row["total_score"] is None  # 成绩不完整 → 草稿
    assert row["status"] == "DRAFT"

    roster = client.get(
        f"{PREFIX}/grades/teaching-classes/{env['tca']}/students",
        headers=auth(env["ta_uname"]),
    ).json()
    assert _grade_of(roster, env["s1_no"])["entry_status"] == "DRAFT"


# --- 5 非法成绩拒绝 ---


def test_invalid_score_rejected(env):
    sheet = _init_sheet(env["tca"], env["ta_uname"])
    g = _grade_of(sheet, env["s1_no"])
    assert _save(
        env["tca"], env["ta_uname"], [{"grade_id": g["id"], "regular_score": 101}]
    ).status_code == 422
    assert _save(
        env["tca"], env["ta_uname"], [{"grade_id": g["id"], "regular_score": -1}]
    ).status_code == 422


# --- 6 32 小时课程成绩录入 ---


def test_32h_entry(env):
    sheet = _init_sheet(env["tca"], env["ta_uname"])
    g = _grade_of(sheet, env["s1_no"])
    r = _save(
        env["tca"], env["ta_uname"],
        [{"grade_id": g["id"], "regular_score": 90, "final_score": 85}],
    )
    assert r.status_code == 200
    row = _grade_of(r.json(), env["s1_no"])
    assert _num(row["total_score"]) == pytest.approx(86.0)  # 90*0.2 + 85*0.8
    assert row["status"] == "DRAFT"


# --- 7 48 小时课程成绩录入 ---


def test_48h_entry(env):
    sheet = _init_sheet(env["tcb"], env["tb_uname"])
    g = _grade_of(sheet, env["s3_no"])
    r = _save(
        env["tcb"], env["tb_uname"],
        [{"grade_id": g["id"], "regular_score": 90, "mid_score": 80,
          "final_score": 70}],
    )
    assert r.status_code == 200
    row = _grade_of(r.json(), env["s3_no"])
    assert _num(row["total_score"]) == pytest.approx(77.0)  # 90*0.2+80*0.3+70*0.5


# --- 8 理论+实践成绩录入 ---


def test_theory_practice_entry(env):
    sheet = _init_sheet(env["tcc"], env["tb_uname"])
    g = _grade_of(sheet, env["s3_no"])
    r = _save(
        env["tcc"], env["tb_uname"],
        [{
            "grade_id": g["id"], "regular_score": 90,
            "mid_theory_score": 80, "mid_practice_score": 90,      # mid=85
            "final_theory_score": 70, "final_practice_score": 90,  # final=80
        }],
    )
    assert r.status_code == 200
    row = _grade_of(r.json(), env["s3_no"])
    # 90*0.2 + 85*0.3 + 80*0.5 = 83.5
    assert _num(row["total_score"]) == pytest.approx(83.5)
    assert _num(row["mid_score"]) == pytest.approx(85.0)
    assert _num(row["final_score"]) == pytest.approx(80.0)
    # 侧分总评：理论 90*.2+80*.3+70*.5 = 77.0；实践 90*.2+90*.3+90*.5 = 90.0
    assert _num(row["theory_total_score"]) == pytest.approx(77.0)
    assert _num(row["practice_total_score"]) == pytest.approx(90.0)
    # 实践课：课程属性由后端下发（has_practice / practice_hours），非前端反推
    assert row["has_practice"] is True
    assert row["course_practice_hours"] == 8


# --- 8a 补考录入（教师 API 链路） ---


def test_makeup_entry_recomputes_and_caps(env):
    """32 学时：期末不及格 → 录补考 → 替换重算并按 60 封顶。"""
    sheet = _init_sheet(env["tca"], env["ta_uname"])
    g = _grade_of(sheet, env["s1_no"])
    r = _save(
        env["tca"], env["ta_uname"],
        [{"grade_id": g["id"], "regular_score": 60, "final_score": 55}],
    )
    assert r.status_code == 200
    row = _grade_of(r.json(), env["s1_no"])
    assert _num(row["total_score"]) == pytest.approx(56.0)  # 60*.2+55*.8
    assert row["is_passed"] is False

    r2 = _save(
        env["tca"], env["ta_uname"],
        [{"grade_id": g["id"], "theory_makeup_score": 80}],
    )
    assert r2.status_code == 200
    row2 = _grade_of(r2.json(), env["s1_no"])
    # 补考替换期末：60*.2+80*.8 = 76 → 补考通过按 60 封顶
    assert _num(row2["theory_total_score"]) == pytest.approx(60.0)
    assert _num(row2["total_score"]) == pytest.approx(60.0)
    assert _num(row2["grade_point"]) == pytest.approx(1.0)
    assert row2["is_passed"] is True
    assert row2["practice_total_score"] is None  # 无实践拆分


def test_makeup_below_60_fails(env):
    sheet = _init_sheet(env["tca"], env["ta_uname"])
    g = _grade_of(sheet, env["s1_no"])
    _save(
        env["tca"], env["ta_uname"],
        [{"grade_id": g["id"], "regular_score": 60, "final_score": 55}],
    )
    r = _save(
        env["tca"], env["ta_uname"],
        [{"grade_id": g["id"], "theory_makeup_score": 40}],
    )
    assert r.status_code == 200
    row = _grade_of(r.json(), env["s1_no"])
    assert _num(row["total_score"]) == pytest.approx(44.0)  # 60*.2+40*.8
    assert row["is_passed"] is False


def test_makeup_rejected_when_final_passed(env):
    """期末已及格仍录补考 → 400。"""
    sheet = _init_sheet(env["tca"], env["ta_uname"])
    g = _grade_of(sheet, env["s1_no"])
    _save(
        env["tca"], env["ta_uname"],
        [{"grade_id": g["id"], "regular_score": 60, "final_score": 60}],
    )
    r = _save(
        env["tca"], env["ta_uname"],
        [{"grade_id": g["id"], "theory_makeup_score": 80}],
    )
    assert r.status_code == 400
    assert r.json()["code"] == "SCORE_CALC_ERROR"


def test_makeup_rejected_without_final(env):
    sheet = _init_sheet(env["tca"], env["ta_uname"])
    g = _grade_of(sheet, env["s1_no"])
    r = _save(
        env["tca"], env["ta_uname"],
        [{"grade_id": g["id"], "regular_score": 60, "theory_makeup_score": 80}],
    )
    assert r.status_code == 400
    assert r.json()["code"] == "SCORE_CALC_ERROR"


# --- 9 完整成绩提交 ---


def test_submit_complete(env):
    sheet = _init_sheet(env["tca"], env["ta_uname"])
    items = [
        {"grade_id": x["id"], "regular_score": 90, "final_score": 85} for x in sheet
    ]
    _save(env["tca"], env["ta_uname"], items)
    r = client.post(
        f"{PREFIX}/grades/teaching-classes/{env['tca']}/submit",
        headers=auth(env["ta_uname"]),
    )
    assert r.status_code == 200
    assert r.json()["submitted"] == 2
    roster = client.get(
        f"{PREFIX}/grades/teaching-classes/{env['tca']}/students",
        headers=auth(env["ta_uname"]),
    ).json()
    assert all(x["entry_status"] == "SUBMITTED" for x in roster)


# --- 10 成绩不完整禁止提交 ---


def test_submit_incomplete_rejected(env):
    sheet = _init_sheet(env["tca"], env["ta_uname"])
    g = _grade_of(sheet, env["s1_no"])
    _save(env["tca"], env["ta_uname"],
          [{"grade_id": g["id"], "regular_score": 90, "final_score": 85}])
    r = client.post(
        f"{PREFIX}/grades/teaching-classes/{env['tca']}/submit",
        headers=auth(env["ta_uname"]),
    )
    assert r.status_code == 409
    assert r.json()["code"] == "RESOURCE_CONFLICT"


# --- 11 SUBMITTED 状态禁止修改 ---


def test_cannot_modify_submitted(env):
    sheet = _init_sheet(env["tca"], env["ta_uname"])
    items = [
        {"grade_id": x["id"], "regular_score": 90, "final_score": 85} for x in sheet
    ]
    _save(env["tca"], env["ta_uname"], items)
    client.post(
        f"{PREFIX}/grades/teaching-classes/{env['tca']}/submit",
        headers=auth(env["ta_uname"]),
    )
    g = _grade_of(sheet, env["s1_no"])
    r = _save(env["tca"], env["ta_uname"], [{"grade_id": g["id"], "regular_score": 88}])
    assert r.status_code == 409


# --- 12 APPROVED 状态禁止修改 ---


def test_cannot_modify_approved(env):
    sheet = _init_sheet(env["tca"], env["ta_uname"])
    items = [
        {"grade_id": x["id"], "regular_score": 90, "final_score": 85} for x in sheet
    ]
    _save(env["tca"], env["ta_uname"], items)
    client.post(
        f"{PREFIX}/grades/teaching-classes/{env['tca']}/submit",
        headers=auth(env["ta_uname"]),
    )
    r = client.post(
        f"{PREFIX}/grades/approve",
        json={"grade_ids": [x["id"] for x in sheet]},
        headers=auth("admin", "admin123"),
    )
    assert r.status_code == 200
    g = _grade_of(sheet, env["s1_no"])
    r2 = _save(env["tca"], env["ta_uname"], [{"grade_id": g["id"], "regular_score": 88}])
    assert r2.status_code == 409


# --- 13 REJECTED 状态允许修改 ---


def test_rejected_allows_modify(env):
    sheet = _init_sheet(env["tca"], env["ta_uname"])
    items = [
        {"grade_id": x["id"], "regular_score": 90, "final_score": 85} for x in sheet
    ]
    _save(env["tca"], env["ta_uname"], items)
    client.post(
        f"{PREFIX}/grades/teaching-classes/{env['tca']}/submit",
        headers=auth(env["ta_uname"]),
    )
    r = client.post(
        f"{PREFIX}/grades/reject",
        json={"grade_ids": [x["id"] for x in sheet], "reason": "成绩有误"},
        headers=auth("admin", "admin123"),
    )
    assert r.status_code == 200
    g = _grade_of(sheet, env["s1_no"])
    r2 = _save(
        env["tca"], env["ta_uname"],
        [{"grade_id": g["id"], "regular_score": 88, "final_score": 90}],
    )
    assert r2.status_code == 200
    row = _grade_of(r2.json(), env["s1_no"])
    assert _num(row["regular_score"]) == 88.0
    assert row["status"] == "DRAFT"  # 修改后回到草稿，可重新提交


# --- 14 学生不能调用教师成绩录入接口 ---


def test_student_cannot_save_grades(env):
    sheet = _init_sheet(env["tca"], env["ta_uname"])
    g = _grade_of(sheet, env["s1_no"])
    r = _save(env["tca"], env["stu_uname"], [{"grade_id": g["id"], "regular_score": 88}])
    assert r.status_code == 403


# --- 15 教师不能修改其他教师成绩 ---


def test_teacher_cannot_modify_other_grades(env):
    sheet = _init_sheet(env["tcb"], env["tb_uname"])
    g = _grade_of(sheet, env["s3_no"])
    r = _save(env["tcb"], env["ta_uname"], [{"grade_id": g["id"], "regular_score": 88}])
    assert r.status_code == 403
