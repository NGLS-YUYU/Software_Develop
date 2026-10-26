"""UAMS V3.1 剩余修复项集成测试（F-03/05/07/08/09/10/11/13/14/15/16/17/19/20/21/22）。

全部测试只连接 ``uams_test``（由 conftest.py 强制覆盖 DATABASE_URL），
不读写正式库 ``uams``。测试产生的数据在 finally 中清理。
"""
from __future__ import annotations

import io
from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.security import create_access_token
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.grade import Grade
from app.models.material import TeachingMaterial
from app.models.person import Student
from app.models.role import UserRole
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import TeachingClass


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _token(uid: int, username: str = "pytest") -> str:
    return create_access_token(uid, {"username": username})


def _h(uid: int, username: str = "pytest") -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(uid, username)}"}


ADMIN = _h(1, "admin")
TEACHER1 = _h(2, "T001")
STUDENT1 = _h(7, "20260001")


def _db():
    return SessionLocal()


def _scalar(sql: str, **params):
    with engine.connect() as c:
        return c.execute(text(sql), params).scalar()


def _exec(sql: str, **params):
    with engine.begin() as c:
        c.execute(text(sql), params)


# ---------------- F-05 统一 ACTIVE 学期 ----------------

def test_active_term_endpoint(client):
    r = client.get("/api/v1/terms/active", headers=ADMIN)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ACTIVE"
    assert r.json()["academic_year"] == "2026-2027"


# ---------------- F-03 成绩更正/撤销/历史 ----------------

def test_grade_correct_and_history(client):
    cols = (
        "regular_score", "mid_score", "mid_theory_score", "mid_practice_score",
        "final_score", "final_theory_score", "final_practice_score",
        "theory_total_score", "practice_total_score", "total_score",
        "grade_point", "is_passed", "status", "approved_by", "approved_at",
    )
    with engine.connect() as c:
        row = c.execute(text(f"SELECT {', '.join(cols)} FROM grades WHERE id=1")).one()
        orig = dict(row._mapping)
        stu_row = c.execute(
            text("SELECT total_credits, gpa FROM students WHERE id=1")
        ).one()
        stu_orig = dict(stu_row._mapping)
    try:
        # 课程 1 含实践学时：合并的 final_score 只读，必须改理论/实践分项
        r = client.post(
            "/api/v1/grades/1/correct",
            headers=ADMIN,
            json={"reason": "PYTEST 无效更正", "final_score": 80},
        )
        assert r.status_code == 409, r.text

        r = client.post(
            "/api/v1/grades/1/correct",
            headers=ADMIN,
            json={
                "reason": "PYTEST 更正",
                "final_theory_score": 85,
                "final_practice_score": 85,
            },
        )
        assert r.status_code == 200, r.text
        assert float(r.json()["final_score"]) == 85
        assert float(r.json()["total_score"]) != float(orig["total_score"])
        h = client.get("/api/v1/grades/1/history", headers=ADMIN)
        assert h.status_code == 200, h.text
        assert any(x["action"] == "CORRECT" for x in h.json())
        assert "before_snapshot" in h.json()[0]
    finally:
        sets = ", ".join(f"{k}=:{k}" for k in cols)
        _exec(f"UPDATE grades SET {sets} WHERE id=1", **orig)
        _exec(
            "UPDATE students SET total_credits=:c, gpa=:g WHERE id=1",
            c=stu_orig["total_credits"], g=stu_orig["gpa"],
        )
        _exec("DELETE FROM grade_change_logs WHERE grade_id=1")
    # 非 APPROVED 不可更正
    r = client.post(
        "/api/v1/grades/999999/correct", headers=ADMIN,
        json={"reason": "x", "final_score": 80},
    )
    assert r.status_code == 404


def test_grade_unapprove(client):
    with _db() as db:
        g = db.get(Grade, 2)
        orig = (g.status, g.approved_by, g.approved_at, g.reject_reason)
        stu = db.get(Student, 3)
        stu_orig = (stu.total_credits, stu.gpa)
    try:
        r = client.post(
            "/api/v1/grades/2/unapprove", headers=ADMIN, json={"reason": "PYTEST 撤销"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "REJECTED"
        hist = client.get("/api/v1/grades/2/history", headers=ADMIN).json()
        assert any(x["action"] == "UN_APPROVE" for x in hist)
    finally:
        _exec(
            "UPDATE grades SET status=:s, approved_by=:b, approved_at=:a, reject_reason=:r WHERE id=2",
            s=orig[0], b=orig[1], a=orig[2], r=orig[3],
        )
        _exec(
            "UPDATE students SET total_credits=:c, gpa=:g WHERE id=3",
            c=stu_orig[0], g=stu_orig[1],
        )
        _exec("DELETE FROM grade_change_logs WHERE grade_id=2")


# ---------------- F-07/F-16/F-19 考试冲突与考场 ----------------

def test_exam_conflict_detection():
    from app.models.exam import Exam, ExamRoom
    from app.services.exam import ExamService

    with _db() as db:
        exam = db.get(Exam, 1)
        svc = ExamService(db)
        assert svc.room_conflict(1, exam.exam_date, exam.start_time, exam.end_time) is not None
        assert svc.invigilator_conflict(1, exam.exam_date, exam.start_time, exam.end_time) is not None
        # 教学班 1 在第 1-16 周的周一有排课；2026-10-05 为第 5 周周一
        assert svc.schedule_conflict(
            exam, date(2026, 10, 5), exam.start_time, exam.end_time
        ) is not None

        tmp = Exam(
            teaching_class_id=6, course_id=7, semester="2026-2027-1",
            exam_type="MAKEUP", exam_date=exam.exam_date,
            start_time=exam.start_time, end_time=exam.end_time,
            duration_minutes=120, status="DRAFT",
        )
        db.add(tmp)
        db.commit()
        try:
            assert svc.student_conflicts(exam, exam.exam_date, exam.start_time, exam.end_time)
            # 新建考试（id=None）也必须检测到与已有考试的学生冲突
            transient = Exam(
                teaching_class_id=2, course_id=2, semester="2026-2027-1",
                exam_type="MAKEUP", exam_date=exam.exam_date,
                start_time=exam.start_time, end_time=exam.end_time,
                duration_minutes=120, status="DRAFT",
            )
            assert transient.id is None
            assert svc.student_conflicts(
                transient, exam.exam_date, exam.start_time, exam.end_time
            )
        finally:
            db.delete(tmp)
            db.commit()


def test_exam_api_validation_and_room_crud(client):
    # 时长与起止时间不一致
    r = client.put("/api/v1/exams/2", headers=ADMIN, json={"duration_minutes": 60})
    assert r.status_code == 409, r.text

    # 考场容量超过教室容量
    r = client.put("/api/v1/exams/2/rooms/2", headers=ADMIN, json={"capacity": 100})
    assert r.status_code == 409, r.text

    # 已分配考生的考场不可删除
    r = client.delete("/api/v1/exams/2/rooms/2", headers=ADMIN)
    assert r.status_code == 409, r.text

    # 正常修改考场容量
    r = client.put("/api/v1/exams/2/rooms/2", headers=ADMIN, json={"capacity": 50})
    assert r.status_code == 200, r.text
    assert r.json()["capacity"] == 50
    r = client.put("/api/v1/exams/2/rooms/2", headers=ADMIN, json={"capacity": 60})
    assert r.status_code == 200, r.text


def test_exam_delete_empty_room(client):
    from app.models.exam import Exam, ExamRoom

    with _db() as db:
        e = Exam(
            teaching_class_id=5, course_id=4, semester="2026-2027-1",
            exam_type="MAKEUP", exam_date=date(2026, 12, 20),
            start_time=time(9, 0), end_time=time(11, 0),
            duration_minutes=120, status="DRAFT",
        )
        db.add(e)
        db.flush()
        room = ExamRoom(exam_id=e.id, classroom_id=5, capacity=10, assigned_count=0)
        db.add(room)
        db.commit()
        eid, rid = e.id, room.id
    try:
        r = client.delete(f"/api/v1/exams/{eid}/rooms/{rid}", headers=ADMIN)
        assert r.status_code == 204, r.text
    finally:
        _exec("DELETE FROM exams WHERE id=:i", i=eid)


# ---------------- F-08 教学任务编辑 ----------------

def test_teaching_task_update(client):
    before = _scalar("SELECT planned_classes FROM teaching_tasks WHERE id=1")
    try:
        r = client.put(
            "/api/v1/teaching-tasks/1", headers=ADMIN,
            json={"planned_classes": int(before) + 1},
        )
        assert r.status_code == 200, r.text
        assert r.json()["planned_classes"] == int(before) + 1
    finally:
        _exec("UPDATE teaching_tasks SET planned_classes=:n WHERE id=1", n=before)


def test_teaching_class_cannot_open_without_teacher_or_schedule(client):
    """F-12：编辑教学班不能绕过开放选课前置条件。"""
    with _db() as db:
        tc = TeachingClass(
            code="PYTEST-OPEN-CHECK", task_id=1, course_id=1,
            semester="2026-2027-1", term_id=1, teacher_id=None,
            capacity=30, selection_status="CLOSED", status="ACTIVE", name="pytest",
        )
        db.add(tc)
        db.commit()
        cid = tc.id
    try:
        r = client.put(
            f"/api/v1/teaching-classes/{cid}", headers=ADMIN,
            json={"selection_status": "OPEN"},
        )
        assert r.status_code == 409, r.text
        # 有教师但无排课仍不能开放
        r = client.put(
            f"/api/v1/teaching-classes/{cid}", headers=ADMIN,
            json={"selection_status": "OPEN", "teacher_id": 1},
        )
        assert r.status_code == 409, r.text
    finally:
        _exec("DELETE FROM teaching_classes WHERE id=:i", i=cid)


# ---------------- F-10 评价任务管理 ----------------

def test_evaluation_task_update(client):
    before = _scalar("SELECT name FROM evaluation_tasks WHERE id=1")
    try:
        r = client.put(
            "/api/v1/evaluations/tasks/1", headers=ADMIN,
            json={"name": "PYTEST 评价任务"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "PYTEST 评价任务"
    finally:
        _exec("UPDATE evaluation_tasks SET name=:n WHERE id=1", n=before)
    r = client.put(
        "/api/v1/evaluations/tasks/1", headers=ADMIN,
        json={"start_time": "2026-11-01T00:00:00", "end_time": "2026-10-01T00:00:00"},
    )
    assert r.status_code == 409, r.text


# ---------------- F-09/F-15 审计日志 ----------------

def test_audit_log_written_and_query(client):
    baseline = _scalar("SELECT COALESCE(MAX(id),0) FROM operation_logs")
    try:
        r = client.put(
            "/api/v1/evaluations/tasks/1", headers=ADMIN,
            json={"name": "PYTEST 审计"},
        )
        assert r.status_code == 200
        r = client.get(
            "/api/v1/audit-logs", headers=ADMIN,
            params={"action": "PUT 1", "page_size": 50},
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert any("/evaluations/tasks/1" in (x.get("detail") or "") for x in items)
    finally:
        _exec("DELETE FROM operation_logs WHERE id > :i", i=baseline)
        _exec("UPDATE evaluation_tasks SET name='2026-2027-1 期末教学评价' WHERE id=1")

    assert client.get("/api/v1/audit-logs", headers=TEACHER1).status_code == 403


# ---------------- F-11 教师兼任管理员 ----------------

def test_dual_identity_teacher_admin(client):
    role_id = _scalar("SELECT id FROM roles WHERE code='ACADEMIC_ADMIN'")
    assert client.get("/api/v1/audit-logs", headers=TEACHER1).status_code == 403
    with _db() as db:
        db.add(UserRole(user_id=2, role_id=role_id))
        db.commit()
    try:
        assert client.get("/api/v1/audit-logs", headers=TEACHER1).status_code == 200
    finally:
        _exec("DELETE FROM user_roles WHERE user_id=2 AND role_id=:r", r=role_id)


# ---------------- F-13 对象级数据隔离 ----------------

def test_teacher_data_isolation(client):
    with _db() as db:
        owned = select(TeachingClass.id).where(TeachingClass.teacher_id == 1)
        owned_ids = list(db.execute(owned).scalars())
        selected = set(
            db.execute(
                select(CourseSelection.student_id).where(
                    CourseSelection.teaching_class_id.in_(owned_ids),
                    CourseSelection.status == SelectionState.SELECTED,
                )
            ).scalars()
        )
        students = list(db.execute(text("SELECT id FROM students ORDER BY id")).scalars())
        outsider = next(s for s in students if s not in selected)
        insider = next(iter(selected))
    assert client.get(f"/api/v1/students/{outsider}", headers=TEACHER1).status_code == 403
    assert client.get(f"/api/v1/students/{insider}", headers=TEACHER1).status_code == 200
    assert client.get(
        f"/api/v1/schedules/students/{outsider}", headers=TEACHER1,
        params={"semester": "2026-2027-1"},
    ).status_code == 403


# ---------------- F-14 学生排名 ----------------

def test_student_grade_ranking(client):
    r = client.get("/api/v1/grades/my", headers=STUDENT1)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gpa"] is not None
    assert body["class_rank"] is not None and body["major_rank"] is not None


# ---------------- F-17 Excel 导出 ----------------

def test_exports(client):
    for name in ("students", "courses", "grades", "selections"):
        r = client.get(f"/api/v1/exports/{name}", headers=ADMIN)
        assert r.status_code == 200, (name, r.text)
        assert r.content[:2] == b"PK"
        assert "spreadsheetml" in r.headers["content-type"]
    # 学生无权导出学生名单
    assert client.get("/api/v1/exports/students", headers=STUDENT1).status_code == 403


# ---------------- F-20 学生培养方案 ----------------

def test_student_curriculum_readable(client):
    r = client.get("/api/v1/curriculum-plans", headers=STUDENT1, params={"page_size": 5})
    assert r.status_code == 200, r.text
    if r.json()["items"]:
        pid = r.json()["items"][0]["id"]
        assert client.get(
            f"/api/v1/curriculum-plans/{pid}/courses", headers=STUDENT1
        ).status_code == 200


# ---------------- F-21 教学资料 ----------------

def test_materials_flow(client):
    before = _scalar("SELECT COALESCE(MAX(id),0) FROM teaching_materials")
    files = []
    try:
        r = client.post(
            "/api/v1/materials",
            headers=TEACHER1,
            data={"teaching_class_id": "1", "title": "PYTEST 资料"},
            files={"file": ("pytest.txt", io.BytesIO(b"hello uams"), "text/plain")},
        )
        assert r.status_code == 201, r.text
        mid = r.json()["id"]
        files.append(r.json())
        # 已选该班的学生可查看/下载
        r = client.get(
            "/api/v1/materials", headers=STUDENT1, params={"teaching_class_id": 1}
        )
        assert r.status_code == 200
        assert any(x["id"] == mid for x in r.json())
        r = client.get(f"/api/v1/materials/{mid}/download", headers=STUDENT1)
        assert r.status_code == 200 and r.content == b"hello uams"
        # 学生不能删除
        assert client.delete(f"/api/v1/materials/{mid}", headers=STUDENT1).status_code == 403
        assert client.delete(f"/api/v1/materials/{mid}", headers=TEACHER1).status_code == 204
    finally:
        with _db() as db:
            for m in db.execute(
                select(TeachingMaterial).where(TeachingMaterial.id > before)
            ).scalars():
                from pathlib import Path
                Path(m.file_path).unlink(missing_ok=True)
                db.delete(m)
            db.commit()


def test_material_upload_rejects_bad_type(client):
    r = client.post(
        "/api/v1/materials",
        headers=TEACHER1,
        data={"teaching_class_id": "1", "title": "bad"},
        files={"file": ("x.exe", io.BytesIO(b"x"), "application/octet-stream")},
    )
    assert r.status_code == 409, r.text


# ---------------- F-22 调停课 ----------------

def test_adjustment_flow(client):
    before_sched = _scalar("SELECT COALESCE(MAX(id),0) FROM schedules")
    before_adj = _scalar("SELECT COALESCE(MAX(id),0) FROM schedule_adjustments")
    try:
        r = client.post(
            "/api/v1/schedule-adjustments",
            headers=TEACHER1,
            json={
                "teaching_class_id": 1, "request_type": "ADD",
                "reason": "PYTEST 补课",
                "new_day_of_week": 7, "new_start_period": 5,
                "new_end_period": 6, "new_start_week": 1,
                "new_end_week": 16, "new_classroom_id": 5,
            },
        )
        assert r.status_code == 201, r.text
        aid = r.json()["id"]
        r = client.get("/api/v1/schedule-adjustments/mine", headers=TEACHER1)
        assert r.status_code == 200
        assert any(x["id"] == aid for x in r.json())
        r = client.post(f"/api/v1/schedule-adjustments/{aid}/approve", headers=ADMIN)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "APPROVED"
        added = _scalar(
            "SELECT COUNT(*) FROM schedules WHERE teaching_class_id=1 AND day_of_week=7"
        )
        assert added >= 1
    finally:
        _exec("DELETE FROM schedules WHERE id > :i", i=before_sched)
        _exec("DELETE FROM schedule_adjustments WHERE id > :i", i=before_adj)


def test_adjustment_reject_and_permissions(client):
    before_adj = _scalar("SELECT COALESCE(MAX(id),0) FROM schedule_adjustments")
    try:
        r = client.post(
            "/api/v1/schedule-adjustments",
            headers=TEACHER1,
            json={
                "teaching_class_id": 1, "request_type": "CANCEL",
                "schedule_id": 1, "reason": "PYTEST 停课",
            },
        )
        assert r.status_code == 201, r.text
        aid = r.json()["id"]
        # 学生不能提交
        assert client.post(
            "/api/v1/schedule-adjustments", headers=STUDENT1,
            json={"teaching_class_id": 1, "request_type": "CANCEL",
                  "schedule_id": 1, "reason": "x"},
        ).status_code == 403
        # 教师不能审核
        assert client.post(
            f"/api/v1/schedule-adjustments/{aid}/reject", headers=TEACHER1,
            json={"reason": "x"},
        ).status_code == 403
        r = client.post(
            f"/api/v1/schedule-adjustments/{aid}/reject", headers=ADMIN,
            json={"reason": "PYTEST 驳回"},
        )
        assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    finally:
        _exec("DELETE FROM schedule_adjustments WHERE id > :i", i=before_adj)
