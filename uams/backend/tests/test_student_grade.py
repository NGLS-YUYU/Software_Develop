"""TASK-007：学生成绩查询测试。

覆盖：学生查看本人 APPROVED 成绩、DRAFT/SUBMITTED/REJECTED/NOT_ENTERED 不可见、
越权防护（grade_id / student_id）、GPA 正确/加权/不及格计入/两位小数/不落库、
班级/专业排名正确且与 RankingService 一致、教师越权、学生反向越权。
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.course import Course
from app.models.grade import Grade, GradeStatus
from app.models.organization import Class, College, Major
from app.models.person import Student, Teacher
from app.models.role import Role, RoleCode, UserRole
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import TeachingClass, TeachingTask
from app.models.term import AcademicTerm
from app.models.user import User, UserType
from app.services.ranking_service import RankingService
from app.services.score_service import ScoreService

client = TestClient(app)
PREFIX = settings.API_V1_PREFIX
LOGIN = f"{PREFIX}/auth/login"

P = "__t7__"
PWD = "t7test123"
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
    """1 学院 / 1 专业 / 2 班级 / 2 课程(48/32) / 1 教师 / 4 学生 / 2 教学班 + 成绩。

    APPROVED 成绩（总评由 ScoreService 计算）：
      S1（A 班）：48 课 90(3 学分) + 32 课 80(2 学分) → GPA 3.72（§9.3 统一表）
      S2（A 班）：48 课 85(3 学分) + 32 课 90(2 学分) → GPA 3.82
      S3（B 班）：48 课 55(3 学分，不及格) + 32 课 80(2 学分) → GPA 1.32
      S4（A 班）：无成绩（NOT_ENTERED）
    """
    _cleanup()
    with SessionLocal() as db:
        college = College(code=f"{P}college", name="T7学院")
        db.add(college)
        db.flush()
        major = Major(code=f"{P}major", name="T7专业", college_id=college.id)
        db.add(major)
        db.flush()
        class_a = Class(code=f"{P}cla", name="T7A班", major_id=major.id, grade_year=2026)
        class_b = Class(code=f"{P}clb", name="T7B班", major_id=major.id, grade_year=2026)
        db.add_all([class_a, class_b])
        db.flush()

        c48 = Course(
            code=f"{P}c48", name="T7三段课", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("3.0"), total_hours=48, theory_hours=48,
            assessment_type="48",
        )
        c32 = Course(
            code=f"{P}c32", name="T7两段课", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("2.0"), total_hours=32, theory_hours=32,
            assessment_type="32",
        )
        db.add_all([c48, c32])
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

        by_no = {}
        for no, klass in [("s01", class_a), ("s02", class_a), ("s03", class_b),
                          ("s04", class_a)]:
            u = make_user(f"{P}{no}", f"学生{no[1:]}", UserType.STUDENT, role_student)
            s = Student(
                user_id=u.id, student_no=f"{P}{no}", class_id=klass.id,
                major_id=major.id, college_id=college.id, enrollment_year=2026,
            )
            db.add(s)
            db.flush()
            by_no[f"{P}{no}"] = s

        task48 = TeachingTask(
            semester=SEMESTER, course_id=c48.id, college_id=college.id,
            status="CONFIRMED",
        )
        task32 = TeachingTask(
            semester=SEMESTER, course_id=c32.id, college_id=college.id,
            status="CONFIRMED",
        )
        db.add_all([task48, task32])
        db.flush()

        term = AcademicTerm(
            name=f"{P}term", academic_year="2097-2098", semester=1,
            start_date=date(2097, 9, 1), end_date=date(2098, 1, 15),
            status="PLANNED",
        )
        db.add(term)
        db.flush()

        tc48 = TeachingClass(
            code=f"{P}tc48", task_id=task48.id, course_id=c48.id,
            semester=SEMESTER, teacher_id=teacher.id, capacity=40, term_id=term.id,
        )
        tc32 = TeachingClass(
            code=f"{P}tc32", task_id=task32.id, course_id=c32.id,
            semester=SEMESTER, teacher_id=teacher.id, capacity=40, term_id=term.id,
        )
        db.add_all([tc48, tc32])
        db.flush()

        for s in by_no.values():
            db.add(CourseSelection(
                student_id=s.id, teaching_class_id=tc48.id, course_id=c48.id,
                semester=SEMESTER, status=SelectionState.SELECTED,
            ))
            db.add(CourseSelection(
                student_id=s.id, teaching_class_id=tc32.id, course_id=c32.id,
                semester=SEMESTER, status=SelectionState.SELECTED,
            ))

        def add_grade(no, tc, course, regular, mid=None, final=None):
            g = Grade(
                student_id=by_no[f"{P}{no}"].id, teaching_class_id=tc.id,
                course_id=course.id, semester=SEMESTER, credits=course.credits,
                status=GradeStatus.APPROVED,
            )
            g.regular_score = Decimal(str(regular))
            if mid is not None:
                g.mid_score = Decimal(str(mid))
            if final is not None:
                g.final_score = Decimal(str(final))
            ScoreService.compute(course, g)
            db.add(g)
            db.flush()
            return g.id

        grades = {}
        grades[(f"{P}s01", f"{P}c48")] = add_grade("s01", tc48, c48, 90, 90, 90)
        grades[(f"{P}s02", f"{P}c48")] = add_grade("s02", tc48, c48, 85, 85, 85)
        grades[(f"{P}s03", f"{P}c48")] = add_grade("s03", tc48, c48, 55, 55, 55)
        grades[(f"{P}s01", f"{P}c32")] = add_grade("s01", tc32, c32, 80, final=80)
        grades[(f"{P}s02", f"{P}c32")] = add_grade("s02", tc32, c32, 90, final=90)
        grades[(f"{P}s03", f"{P}c32")] = add_grade("s03", tc32, c32, 80, final=80)

        db.commit()

        yield {
            "class_a": class_a.id, "class_b": class_b.id, "major": major.id,
            "t_uname": f"{P}t01",
            "s1_uname": f"{P}s01", "s2_uname": f"{P}s02",
            "s3_uname": f"{P}s03", "s4_uname": f"{P}s04",
            "s1_no": f"{P}s01", "s2_no": f"{P}s02",
            "s3_no": f"{P}s03", "s4_no": f"{P}s04",
            "s1_id": by_no[f"{P}s01"].id, "s2_id": by_no[f"{P}s02"].id,
            "s3_id": by_no[f"{P}s03"].id, "s4_id": by_no[f"{P}s04"].id,
            "c48_code": f"{P}c48", "c32_code": f"{P}c32",
            "grades": grades,
        }
    _cleanup()


def _my(uname: str) -> dict:
    r = client.get(f"{PREFIX}/grades/my", headers=auth(uname))
    assert r.status_code == 200, r.text
    return r.json()


def _flip(env, student_no: str, course_code: str, status: str) -> None:
    with SessionLocal() as db:
        g = db.get(Grade, env["grades"][(student_no, course_code)])
        g.status = status
        db.commit()


# --- 1 学生查询自己的 APPROVED 成绩 ---


def test_student_queries_own_approved_grades(env):
    data = _my(env["s1_uname"])
    items = data["items"]
    assert {x["course_code"] for x in items} == {env["c48_code"], env["c32_code"]}
    assert all(x["status"] == "APPROVED" for x in items)
    assert all(x["student_no"] == env["s1_no"] for x in items)
    # TASK-007 新增：考核方式随成绩明细返回
    assert all(x["assessment_type"] for x in items)


# --- 1b 学生 API 返回完整成绩模型字段 ---


def test_student_api_exposes_full_score_model(env):
    """成绩模型闭环：API 必须返回原始成绩 + 系统计算字段，无「后端有字段前端拿不到」。"""
    items = _my(env["s1_uname"])["items"]
    c48 = next(x for x in items if x["course_code"] == env["c48_code"])
    required_keys = {
        "regular_score", "mid_score", "mid_theory_score", "mid_practice_score",
        "final_score", "final_theory_score", "final_practice_score",
        "theory_makeup_score", "practice_makeup_score",
        "theory_total_score", "practice_total_score",
        "total_score", "credits", "grade_point", "is_passed",
        "assessment_type", "course_practice_hours",
    }
    for x in items:
        assert required_keys <= x.keys(), f"缺少成绩模型字段：{required_keys - x.keys()}"
    # 无实践拆分的课程：理论总评 = 成绩总评，实践总评为空
    assert c48["theory_total_score"] == c48["total_score"]
    assert c48["practice_total_score"] is None
    assert c48["theory_makeup_score"] is None
    assert c48["practice_makeup_score"] is None


# --- 2~4 非 APPROVED 成绩不可见 ---


def test_draft_grade_hidden(env):
    _flip(env, env["s1_no"], env["c32_code"], GradeStatus.DRAFT)
    items = _my(env["s1_uname"])["items"]
    assert [x["course_code"] for x in items] == [env["c48_code"]]


def test_submitted_grade_hidden(env):
    _flip(env, env["s1_no"], env["c32_code"], GradeStatus.SUBMITTED)
    items = _my(env["s1_uname"])["items"]
    assert [x["course_code"] for x in items] == [env["c48_code"]]


def test_rejected_grade_hidden(env):
    _flip(env, env["s1_no"], env["c32_code"], GradeStatus.REJECTED)
    items = _my(env["s1_uname"])["items"]
    assert [x["course_code"] for x in items] == [env["c48_code"]]


# --- 5 NOT_ENTERED 学生（无成绩）返回空 ---


def test_not_entered_student_returns_empty(env):
    data = _my(env["s4_uname"])
    assert data["items"] == []
    assert data["gpa"] is None
    assert data["class_rank"] is None
    assert data["major_rank"] is None


# --- 6 学生只能看到自己的成绩 ---


def test_student_sees_only_own_grades(env):
    nos = {x["student_no"] for x in _my(env["s1_uname"])["items"]}
    assert nos == {env["s1_no"]}
    assert env["s2_no"] not in nos and env["s3_no"] not in nos


# --- 7 学生不能通过 grade_id 访问他人成绩 ---


def test_grade_id_access_returns_404(env):
    """成绩详情接口不存在（404/405），且新增的删除接口同样无法越权（FIX-005）。

    FIX-005 增加了 DELETE /grades/{id}，因此 GET 同一路径由 404 变为 405
    （路由存在但方法不允许）——两者都表示「学生读不到这条成绩」。
    这里同时验证删除路径被权限拦截且数据未被破坏。
    """
    gid = env["grades"][(env["s2_no"], env["c48_code"])]
    r = client.get(f"{PREFIX}/grades/{gid}", headers=auth(env["s1_uname"]))
    assert r.status_code in (404, 405)
    assert r.status_code != 200

    r2 = client.delete(f"{PREFIX}/grades/{gid}", headers=auth(env["s1_uname"]))
    assert r2.status_code == 403
    with SessionLocal() as db:
        assert db.get(Grade, gid) is not None  # 他人成绩未被删除


# --- 8 student_id 查询参数被忽略，身份始终取自 token ---


def test_student_id_param_ignored(env):
    r = client.get(
        f"{PREFIX}/grades/my",
        params={"student_id": env["s2_id"]},
        headers=auth(env["s1_uname"]),
    )
    assert r.status_code == 200
    nos = {x["student_no"] for x in r.json()["items"]}
    assert nos == {env["s1_no"]}


# --- 9 GPA 正确 ---


def test_gpa_correct(env):
    assert _my(env["s1_uname"])["gpa"] == pytest.approx(3.72)


# --- 10 GPA 保留两位小数 ---


def test_gpa_two_decimal_places(env):
    gpa = _my(env["s1_uname"])["gpa"]
    assert gpa is not None
    assert Decimal(str(gpa)) == Decimal(str(gpa)).quantize(Decimal("0.01"))


# --- 11 GPA 不落库（grades 表无 gpa/class_rank/major_rank/ranking 字段） ---


def test_gpa_not_persisted(env):
    with engine.connect() as conn:
        cols = {r[0] for r in conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'grades'"
        ))}
    assert "gpa" not in cols
    assert "class_rank" not in cols
    assert "major_rank" not in cols
    assert "ranking" not in cols


# --- 12 班级排名正确 ---


def test_class_rank_correct(env):
    assert _my(env["s1_uname"])["class_rank"] == 2
    assert _my(env["s2_uname"])["class_rank"] == 1
    assert _my(env["s3_uname"])["class_rank"] == 1  # B 班仅一人


# --- 13 专业排名正确 ---


def test_major_rank_correct(env):
    assert _my(env["s1_uname"])["major_rank"] == 2
    assert _my(env["s3_uname"])["major_rank"] == 3


# --- 14 不同学分 GPA 按学分加权 ---


def test_gpa_weighted_by_credits(env):
    # S1：3 学分 90(4.0) + 2 学分 80(3.3) = (12+6.6)/5 = 3.72
    assert _my(env["s1_uname"])["gpa"] == pytest.approx(3.72)
    # S2：3 学分 85(3.7) + 2 学分 90(4.0) = (11.1+8)/5 = 3.82
    # 若不按学分加权（简单平均）应为 3.85，故 3.82 证明按学分加权
    assert _my(env["s2_uname"])["gpa"] == pytest.approx(3.82)


# --- 15 不及格成绩计入 GPA ---


def test_failed_grade_included_in_gpa(env):
    # S3：3 学分 55(不及格→0.0) + 2 学分 80(3.3) = (0+6.6)/5 = 1.32
    # 若排除不及格成绩，GPA 应为 3.3；1.32 证明不及格成绩计入 GPA
    assert _my(env["s3_uname"])["gpa"] == pytest.approx(1.32)


def test_summary_gpa_same_source_as_my(env):
    """/grades/mine/summary 与 /grades/my 必须同口径（含不及格 0.0），禁止双标准。"""
    my_gpa = _my(env["s3_uname"])["gpa"]
    r = client.get(
        f"{PREFIX}/grades/mine/summary", headers=auth(env["s3_uname"])
    )
    assert r.status_code == 200
    summary_gpa = r.json()["gpa"]
    assert summary_gpa is not None
    assert Decimal(str(summary_gpa)) == Decimal(str(my_gpa)) == Decimal("1.32")


# --- 16 排名与 RankingService 实时计算一致 ---


def test_rank_consistent_with_ranking_service(env):
    with SessionLocal() as db:
        rs = RankingService(db)
        class_rows = {r.student_id: r.ranking for r in rs.class_ranking(env["class_a"])}
        major_rows = {r.student_id: r.ranking for r in rs.major_ranking(env["major"])}
    data = _my(env["s1_uname"])
    assert data["class_rank"] == class_rows[env["s1_id"]]
    assert data["major_rank"] == major_rows[env["s1_id"]]


# --- 17 教师不能使用学生成绩查询接口 ---


def test_teacher_cannot_use_student_endpoint(env):
    r = client.get(f"{PREFIX}/grades/my", headers=auth(env["t_uname"]))
    assert r.status_code == 403


# --- 18 学生仍不能调用教师录入 / 教务审核接口 ---


def test_student_blocked_from_teacher_entry_and_review(env):
    gid = env["grades"][(env["s1_no"], env["c48_code"])]
    # 教师成绩录入
    r1 = client.put(
        f"{PREFIX}/grades",
        json={"teaching_class_id": -1, "items": []},
        headers=auth(env["s1_uname"]),
    )
    assert r1.status_code == 403
    # 教务审核通过 / 驳回
    r2 = client.post(
        f"{PREFIX}/grades/approve", json={"grade_ids": [gid]},
        headers=auth(env["s1_uname"]),
    )
    assert r2.status_code == 403
    r3 = client.post(
        f"{PREFIX}/grades/reject", json={"grade_ids": [gid], "reason": "越权"},
        headers=auth(env["s1_uname"]),
    )
    assert r3.status_code == 403
