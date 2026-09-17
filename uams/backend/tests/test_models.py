"""TASK-002：数据库模型字段完整性测试。

验证五大核心模型具备需求字段（需求字段名映射到本项目实际命名），
并确认新增列与 CHECK 约束已在数据库中生效。
"""

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.db.session import engine
from app.models.course import Course
from app.models.grade import Grade
from app.models.person import Student, Teacher
from app.models.user import User


def _cols(model) -> set[str]:
    return set(inspect(model).columns.keys())


# --- 字段完整性（需求名 → 项目实际列名）---


def test_user_required_fields():
    cols = _cols(User)
    # id / username / password(password_hash) / role(user_type) / created_time(created_at)
    assert {"id", "username", "password_hash", "user_type", "created_at"} <= cols
    # 学生/教师与用户通过反向外键关联（students.user_id / teachers.user_id → users.id）
    assert "user_id" in _cols(Student)
    assert "user_id" in _cols(Teacher)


def test_student_required_fields():
    cols = _cols(Student)
    # student_no / name(user.real_name) / major(major_id) / class_name(class_id)
    assert {"student_no", "major_id", "class_id", "enrollment_year"} <= cols


def test_teacher_required_fields():
    cols = _cols(Teacher)
    # teacher_no / name(user.real_name) / department(college_id)
    assert {"teacher_no", "college_id"} <= cols


def test_course_required_fields():
    cols = _cols(Course)
    # course_no(code) / course_name(name) / credit(credits) / hours(total_hours)
    # type(course_type) / assessment_type
    assert {
        "code", "name", "credits", "total_hours", "course_type", "assessment_type",
    } <= cols


def test_grade_required_fields():
    cols = _cols(Grade)
    # student_id / course_id / usual_score(regular_score) / mid_score
    # final_score / total_score
    assert {
        "student_id", "course_id", "regular_score", "mid_score",
        "final_score", "total_score",
    } <= cols
    # 理论/实践拆分（TASK-002 补充）
    assert {
        "mid_theory_score", "mid_practice_score",
        "final_theory_score", "final_practice_score",
    } <= cols


# --- 迁移已生效：新增列确实存在于数据库 ---


def test_new_columns_exist_in_db():
    """TASK-002 迁移后的新列必须在实际数据库中可见。"""
    with engine.connect() as conn:
        course_cols = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'courses'"
                )
            )
        }
        grade_cols = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'grades'"
                )
            )
        }
    assert "assessment_type" in course_cols
    assert "mid_score" in grade_cols


def test_new_check_constraints_exist():
    """TASK-002 新增的 CHECK 约束必须已写入数据库。"""
    with engine.connect() as conn:
        names = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT CONSTRAINT_NAME FROM information_schema.CHECK_CONSTRAINTS "
                    "WHERE CONSTRAINT_SCHEMA = DATABASE()"
                )
            )
        }
    assert "ck_courses_assessment" in names
    assert "ck_grades_mid" in names


# --- CHECK 约束行为 ---


def test_course_assessment_type_check_constraint():
    """非法 assessment_type 必须被数据库拒绝。"""
    with engine.connect() as conn:
        college_id = conn.execute(
            text("SELECT id FROM colleges LIMIT 1")
        ).scalar()
        conn.rollback()  # 结束 SELECT 触发的 autobegin 事务
        if college_id is None:
            return  # 无学院数据则跳过（seed 未执行）
        trans = conn.begin()
        try:
            conn.execute(
                text(
                    "INSERT INTO courses (code, name, college_id, course_type, "
                    "credits, total_hours, assessment_type) "
                    "VALUES ('__ck_assess__', '测试', :cid, 'REQUIRED', 2.0, 32, '99')"
                ),
                {"cid": college_id},
            )
            trans.rollback()
            raise AssertionError("CHECK 约束未生效：非法 assessment_type 被写入")
        except (IntegrityError, OperationalError):
            trans.rollback()  # 预期：被数据库拒绝


# --- 理论/实践成绩字段（TASK-002 补充）---

THEORY_PRACTICE_COLS = (
    "mid_theory_score", "mid_practice_score",
    "final_theory_score", "final_practice_score",
)


def _free_grade_slot():
    """返回一个尚无成绩的 (student_id, teaching_class_id, course_id, semester) 或 None。"""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT s.id, tc.id, tc.course_id, tc.semester "
                "FROM students s JOIN teaching_classes tc "
                "ON tc.course_id IS NOT NULL AND tc.semester IS NOT NULL "
                "WHERE NOT EXISTS (SELECT 1 FROM grades g "
                "  WHERE g.student_id = s.id AND g.teaching_class_id = tc.id) "
                "LIMIT 1"
            )
        ).first()
        return tuple(row) if row else None


def test_theory_practice_columns_exist_in_db():
    """新增理论/实践字段必须已存在于数据库。"""
    with engine.connect() as conn:
        cols = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'grades'"
                )
            )
        }
    assert set(THEORY_PRACTICE_COLS) <= cols


def test_theory_practice_columns_nullable():
    """新增字段必须允许 NULL。"""
    with engine.connect() as conn:
        nullable = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'grades' "
                    "AND IS_NULLABLE = 'YES'"
                )
            )
        }
    assert set(THEORY_PRACTICE_COLS) <= nullable


def test_theory_practice_check_constraints_exist():
    """新增字段的 0-100 CHECK 约束必须已写入数据库。"""
    with engine.connect() as conn:
        names = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT CONSTRAINT_NAME FROM information_schema.CHECK_CONSTRAINTS "
                    "WHERE CONSTRAINT_SCHEMA = DATABASE()"
                )
            )
        }
    assert {
        "ck_grades_mid_theory", "ck_grades_mid_practice",
        "ck_grades_final_theory", "ck_grades_final_practice",
    } <= names


def test_theory_practice_score_check_constraint_rejects_invalid():
    """非法 mid_theory_score（>100）必须被数据库拒绝。"""
    slot = _free_grade_slot()
    if slot is None:
        return  # 无可用数据则跳过
    sid, tcid, cid, sem = slot
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(
                text(
                    "INSERT INTO grades (student_id, teaching_class_id, course_id, "
                    "semester, credits, mid_theory_score) "
                    "VALUES (:sid, :tcid, :cid, :sem, 2.0, 101)"
                ),
                {"sid": sid, "tcid": tcid, "cid": cid, "sem": sem},
            )
            trans.rollback()
            raise AssertionError("CHECK 约束未生效：非法 mid_theory_score 被写入")
        except (IntegrityError, OperationalError):
            trans.rollback()  # 预期：被数据库拒绝


def test_theory_practice_scores_allow_null():
    """新增字段为 NULL 时应可正常写入。"""
    slot = _free_grade_slot()
    if slot is None:
        return  # 无可用数据则跳过
    sid, tcid, cid, sem = slot
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(
                text(
                    "INSERT INTO grades (student_id, teaching_class_id, course_id, "
                    "semester, credits, regular_score, final_score, "
                    "mid_theory_score, mid_practice_score, "
                    "final_theory_score, final_practice_score) "
                    "VALUES (:sid, :tcid, :cid, :sem, 2.0, 90, 80, "
                    "NULL, NULL, NULL, NULL)"
                ),
                {"sid": sid, "tcid": tcid, "cid": cid, "sem": sem},
            )
        except (IntegrityError, OperationalError) as e:  # pragma: no cover
            trans.rollback()
            raise AssertionError(f"NULL 分数应被允许写入：{e}") from e
        else:
            trans.rollback()  # 成功写入后回滚，不污染数据

