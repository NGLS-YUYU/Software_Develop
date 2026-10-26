"""核心回归测试（F-18）。运行方式：cd backend && .venv/bin/pytest -q"""
from datetime import date, datetime, time

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.core.email import normalize_email
from app.models.grade import Grade
from app.services.exam import ExamService
from app.services.grade import GradeService


def test_database_target_is_isolated_test_db():
    eng = create_engine(settings.DATABASE_URL)
    with eng.connect() as c:
        assert c.execute(text("SELECT DATABASE()")).scalar() == "uams_test"


def test_email_normalization_regression():
    assert normalize_email(None) is None
    assert normalize_email("") is None
    assert normalize_email("   ") is None
    assert normalize_email("  user@example.com  ") == "user@example.com"
    for bad in ("not-an-email", "a@b", "a@b..com"):
        try:
            normalize_email(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected invalid: {bad}")


def test_grade_snapshot_contains_full_fields():
    g = Grade(
        student_id=1, teaching_class_id=2, course_id=3, semester="2026-2027-1",
        regular_score=80, mid_score=70, final_score=60, total_score=68,
        grade_point=2.3, credits=3, is_passed=True, status="APPROVED",
    )
    snap = GradeService._snapshot(g)
    for field in ("regular_score", "mid_score", "final_score", "total_score",
                  "grade_point", "credits", "is_passed", "status"):
        assert field in snap


def test_exam_duration_minutes():
    assert ExamService.duration_minutes(time(9, 0), time(11, 0)) == 120
    assert ExamService.duration_minutes(time(14, 30), time(16, 0)) == 90


def test_grade_change_log_table_exists():
    eng = create_engine(settings.DATABASE_URL)
    with eng.connect() as c:
        n = c.execute(text("""
            SELECT COUNT(*) FROM information_schema.TABLES
            WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='grade_change_logs'
        """)).scalar()
    assert n == 1


def test_selection_window_unknown_semester():
    from app.db.session import SessionLocal
    from app.models.person import Student
    from app.services.selection import SelectionService

    with SessionLocal() as db:
        student = Student(student_no="PYTEST_NO_DB_ROW", class_id=1, major_id=1,
                          college_id=1, enrollment_year=2026)
        state = SelectionService(db).selection_window_status(student, "2097-2098-1")
        assert state["can_select"] is False
        assert state["reason_code"] == "TERM_NOT_FOUND"
