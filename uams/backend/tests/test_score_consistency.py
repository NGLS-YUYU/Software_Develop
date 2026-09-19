"""FIX-008：成绩权重一致性治理测试。

验证「成绩计算规则只有一个权威来源」（成绩事实 → 绩点 → GPA → 排名同源）：

- Case 1  32 学时「平时 87 / 期末 56」→ 62.20（旧课程级权重 0.4/0.6 口径为 68.40）
- Case 5  GPA 基于修正后的 total_score
- Case 6  排名基于修正后的 GPA
- Case 7  成绩导入同样走统一规则
- 死字段 courses.regular_weight / final_weight 已从模型与数据库移除
- 全库成绩与 ``ScoreService.WEIGHT_RULES`` 一致

Case 2/3/4（64 学时 / 48 学时 / 理论+实践合并）的单元级断言见
``tests/test_score_service.py``，本文件不重复。

全部用例直连真实 MySQL，不使用 mock，不做假数据验证（CLAUDE.md §27/§29）。
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, inspect, select, text

from app.db.session import SessionLocal, engine
from app.models.course import AssessmentType, Course
from app.models.grade import Grade, GradeStatus
from app.models.organization import Class, College, Major
from app.models.person import Student, Teacher
from app.models.role import Role, RoleCode, UserRole
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import TeachingClass, TeachingTask
from app.models.term import AcademicTerm
from app.models.user import User, UserType
from app.core.security import hash_password
from app.services.gpa_service import GpaService, student_gpa
from app.services.grade import GradeService
from app.services.ranking_service import RankingService
from app.services.score_service import ScoreService

P = "__f8__"
PWD = "f8test123"
SEMESTER = "2026-2027-1"

# 旧口径（已删除的课程级权重）下的错误结果，用于回归断言
LEGACY_32H_TOTAL = Decimal("68.40")  # 87*0.4 + 56*0.6


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
    """1 学院 / 1 专业 / 1 班级 / 2 课程(32h 与 64h) / 1 教师 / 3 学生。

    tc32 上三名学生的成绩（全部经 ScoreService 统一计算）：
      s1：平时 90 / 期末 75 → 78.00（旧口径为 81.00，绩点 3.0，旧口径下为 3.3）
      s2：平时 87 / 期末 56 → 62.20（旧口径为 68.40）
      s3：平时 50 / 期末 50 → 50.00（不及格）
    """
    _cleanup()
    with SessionLocal() as db:
        college = College(code=f"{P}college", name="F8学院")
        db.add(college)
        db.flush()
        major = Major(code=f"{P}major", name="F8专业", college_id=college.id)
        db.add(major)
        db.flush()
        klass = Class(code=f"{P}class", name="F8班", major_id=major.id, grade_year=2026)
        db.add(klass)
        db.flush()

        c32 = Course(
            code=f"{P}c32", name="F8两段课", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("3.0"), total_hours=32,
            assessment_type=AssessmentType.HOURS_32,
        )
        c64 = Course(
            code=f"{P}c64", name="F8三段课", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("4.0"), total_hours=64,
            assessment_type=AssessmentType.HOURS_64,
        )
        db.add_all([c32, c64])
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

        t_u = make_user(f"{P}t01", "F8教师", UserType.TEACHER, role_teacher)
        teacher = Teacher(user_id=t_u.id, teacher_no=f"{P}t01", college_id=college.id)
        db.add(teacher)
        db.flush()

        students = {}
        for no in ("s1", "s2", "s3"):
            u = make_user(f"{P}{no}", f"学生{no[1:]}", UserType.STUDENT, role_student)
            s = Student(
                user_id=u.id, student_no=f"{P}{no}", class_id=klass.id,
                major_id=major.id, college_id=college.id, enrollment_year=2026,
            )
            db.add(s)
            db.flush()
            students[no] = s

        task32 = TeachingTask(
            semester=SEMESTER, course_id=c32.id, college_id=college.id,
            status="CONFIRMED",
        )
        task64 = TeachingTask(
            semester=SEMESTER, course_id=c64.id, college_id=college.id,
            status="CONFIRMED",
        )
        db.add_all([task32, task64])
        db.flush()

        term = AcademicTerm(
            name=f"{P}term", academic_year="2099-2100", semester=1,
            start_date=date(2099, 9, 1), end_date=date(2100, 1, 15),
            status="PLANNED",
        )
        db.add(term)
        db.flush()

        tc32 = TeachingClass(
            code=f"{P}tc32", task_id=task32.id, course_id=c32.id,
            semester=SEMESTER, teacher_id=teacher.id, capacity=40, term_id=term.id,
        )
        tc64 = TeachingClass(
            code=f"{P}tc64", task_id=task64.id, course_id=c64.id,
            semester=SEMESTER, teacher_id=teacher.id, capacity=40, term_id=term.id,
        )
        # 空教学班：仅用于导入链路验证，不影响上面的成绩与排名基线
        tc32b = TeachingClass(
            code=f"{P}tc32b", task_id=task32.id, course_id=c32.id,
            semester=SEMESTER, teacher_id=teacher.id, capacity=40, term_id=term.id,
        )
        db.add_all([tc32, tc64, tc32b])
        db.flush()

        for s in students.values():
            db.add(CourseSelection(
                student_id=s.id, teaching_class_id=tc32.id, course_id=c32.id,
                semester=SEMESTER, status=SelectionState.SELECTED,
            ))
        db.flush()

        # 成绩一律经统一计算入口写入（与生产链路一致）
        scores = {"s1": (90, 75), "s2": (87, 56), "s3": (50, 50)}
        for no, (reg, fin) in scores.items():
            g = Grade(
                student_id=students[no].id, teaching_class_id=tc32.id,
                course_id=c32.id, semester=SEMESTER, credits=c32.credits,
                regular_score=Decimal(str(reg)), final_score=Decimal(str(fin)),
                status=GradeStatus.APPROVED,
            )
            ScoreService.compute(c32, g)
            db.add(g)
        db.commit()

        yield {
            "db": db, "college": college, "major": major, "class": klass,
            "c32": c32, "c64": c64, "tc32": tc32, "tc64": tc64, "tc32b": tc32b,
            "teacher": teacher, "students": students,
        }
    _cleanup()


def _grade_of(env, no: str) -> Grade:
    with SessionLocal() as db:
        return db.execute(
            select(Grade).where(
                Grade.student_id == env["students"][no].id,
                Grade.teaching_class_id == env["tc32"].id,
            )
        ).scalar_one()


# --- Case 1：32 学时权重回归 ---


def test_case1_32h_total_is_new_rule(env):
    """平时 87 / 期末 56 → 62.20（87*0.2 + 56*0.8），不得为旧口径 68.40。"""
    g = _grade_of(env, "s2")
    assert g.total_score == Decimal("62.20")
    assert g.total_score != LEGACY_32H_TOTAL


def test_case1_grade_point_follows_corrected_total(env):
    """绩点由修正后的总评换算：62.20 → 1.00（旧口径 68.40 → 2.30）。"""
    g = _grade_of(env, "s2")
    assert g.grade_point == Decimal("1.00")
    assert g.is_passed is True


def test_case1_s1_total_uses_new_rule(env):
    """平时 90 / 期末 75 → 78.00（旧口径 81.00）。"""
    g = _grade_of(env, "s1")
    assert g.total_score == Decimal("78.00")
    assert g.total_score != Decimal("81.00")


def test_case1_failing_student_not_passed(env):
    g = _grade_of(env, "s3")
    assert g.total_score == Decimal("50.00")
    assert g.is_passed is False


# --- Case 5：GPA 基于修正后的 total_score ---


def test_case5_gpa_uses_corrected_total_score(env):
    """s1 总评 78.00 → 绩点 3.0（§9.3）→ GPA 3.00（若仍按旧 81.00 则为 3.30）。"""
    with SessionLocal() as db:
        gpa = GpaService(db).gpa_of(env["students"]["s1"].id)
    assert gpa == Decimal("3.00")
    assert gpa != Decimal("3.30")


def test_case5_gpa_matches_stored_total_scores(env):
    """GPA 必须由库中 total_score 推出，而不是任何重算/缓存值。"""
    with SessionLocal() as db:
        for no in ("s1", "s2", "s3"):
            sid = env["students"][no].id
            stored = db.execute(
                select(Grade.credits, Grade.total_score).where(
                    Grade.student_id == sid,
                    Grade.status == GradeStatus.APPROVED,
                )
            ).all()
            expected = student_gpa(
                [(Decimal(str(c)), Decimal(str(s))) for c, s in stored]
            )
            assert GpaService(db).gpa_of(sid) == expected


# --- Case 6：排名基于修正后的 GPA ---


def test_case6_class_ranking_follows_corrected_gpa(env):
    """排名顺序必须与修正后 GPA 一致：s1(3.00) > s2(1.00) > s3(0.00)。"""
    with SessionLocal() as db:
        items = RankingService(db).class_ranking(env["class"].id)
    got = [(i.student_id, i.gpa, i.ranking) for i in items]
    s = env["students"]
    assert got == [
        (s["s1"].id, Decimal("3.00"), 1),
        (s["s2"].id, Decimal("1.00"), 2),
        (s["s3"].id, Decimal("0.00"), 3),
    ]


def test_case6_ranking_consistent_with_gpa_service(env):
    """排名所用的 GPA 必须与 GpaService 同源。"""
    with SessionLocal() as db:
        items = RankingService(db).class_ranking(env["class"].id)
        for item in items:
            assert item.gpa == GpaService(db).gpa_of(item.student_id)


# --- Case 7：成绩导入走统一规则 ---


def test_case7_import_uses_unified_weight_rule(env):
    """导入 64 学时成绩：20/30/50 而非旧 40/60。"""
    with SessionLocal() as db:
        GradeService(db).import_scores([{
            "student_id": env["students"]["s1"].id,
            "teaching_class_id": env["tc64"].id,
            "scores": {
                "regular_score": Decimal("80"),
                "mid_score": Decimal("85"),
                "final_score": Decimal("90"),
            },
        }])
        g = db.execute(
            select(Grade).where(
                Grade.student_id == env["students"]["s1"].id,
                Grade.teaching_class_id == env["tc64"].id,
            )
        ).scalar_one()
        # 80*0.2 + 85*0.3 + 90*0.5 = 86.50（旧口径 80*0.4 + 90*0.6 = 86.00）
        assert g.total_score == Decimal("86.50")
        assert g.total_score != Decimal("86.00")
        assert g.grade_point == Decimal("3.70")


def test_case7_import_32h_uses_unified_weight_rule(env):
    """导入 32 学时成绩：20/80，结果为 62.20 而非旧口径 68.40。"""
    with SessionLocal() as db:
        GradeService(db).import_scores([{
            "student_id": env["students"]["s1"].id,
            "teaching_class_id": env["tc32b"].id,
            "scores": {
                "regular_score": Decimal("87"),
                "final_score": Decimal("56"),
            },
        }])
        g = db.execute(
            select(Grade).where(
                Grade.student_id == env["students"]["s1"].id,
                Grade.teaching_class_id == env["tc32b"].id,
            )
        ).scalar_one()
        assert g.total_score == Decimal("62.20")
        assert g.total_score != LEGACY_32H_TOTAL


# --- 死字段移除 ---


def test_dead_weight_fields_removed_from_model():
    """Course 模型不得再有 regular_weight / final_weight 列。"""
    cols = set(inspect(Course).columns.keys())
    assert "regular_weight" not in cols
    assert "final_weight" not in cols


def test_dead_weight_columns_removed_from_db():
    """数据库 courses 表必须已删除两列与 ck_courses_weight 约束。"""
    with engine.connect() as conn:
        cols = {
            r[0]
            for r in conn.execute(text(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'courses'"
            ))
        }
        checks = {
            r[0]
            for r in conn.execute(text(
                "SELECT CONSTRAINT_NAME FROM information_schema.CHECK_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA = DATABASE()"
            ))
        }
    assert "regular_weight" not in cols
    assert "final_weight" not in cols
    assert "ck_courses_weight" not in checks


def test_weight_rules_is_the_single_source():
    """权重唯一来源：WEIGHT_RULES 与 DATABASE.md §9.3 一致。"""
    assert ScoreService.weights(AssessmentType.HOURS_32) == {
        "regular": Decimal("0.2"), "mid": None, "final": Decimal("0.8"),
    }
    for at in (AssessmentType.HOURS_48, AssessmentType.HOURS_64):
        assert ScoreService.weights(at) == {
            "regular": Decimal("0.2"), "mid": Decimal("0.3"), "final": Decimal("0.5"),
        }


# --- 全库一致性 ---


def test_all_stored_grades_match_weight_rules():
    """真实库中每条有总评的成绩都必须等于按 WEIGHT_RULES 重算的结果。

    用 ScoreService 在「游离副本」上重算，既校验数据又避免重复实现计算逻辑；
    同时校验理论总评（含补考替换/封顶）与库中一致。
    """
    checked = 0
    with SessionLocal() as db:
        rows = db.execute(
            select(Grade, Course).join(Course, Course.id == Grade.course_id).where(
                Grade.total_score.is_not(None)
            )
        ).all()
        assert rows, "数据库中无成绩数据，无法验证一致性"
        for g, course in rows:
            probe = Grade(
                student_id=g.student_id, teaching_class_id=g.teaching_class_id,
                course_id=g.course_id, semester=g.semester, credits=g.credits,
                regular_score=g.regular_score,
                mid_score=g.mid_score, final_score=g.final_score,
                mid_theory_score=g.mid_theory_score,
                mid_practice_score=g.mid_practice_score,
                final_theory_score=g.final_theory_score,
                final_practice_score=g.final_practice_score,
                theory_makeup_score=g.theory_makeup_score,
                practice_makeup_score=g.practice_makeup_score,
            )
            expected = ScoreService.compute(course, probe)
            assert g.total_score == expected, (
                f"grade id={g.id}（课程 {course.code}，考核方式 "
                f"{course.assessment_type}）：库中 {g.total_score} ≠ 重算 {expected}"
            )
            assert g.theory_total_score == probe.theory_total_score, (
                f"grade id={g.id}（课程 {course.code}）：库中理论总评 "
                f"{g.theory_total_score} ≠ 重算 {probe.theory_total_score}"
            )
            checked += 1
    assert checked > 0
