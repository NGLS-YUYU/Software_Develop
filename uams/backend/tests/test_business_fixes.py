"""V3.2 FIX-BUSINESS-001 业务测试（uams_test）。"""
from __future__ import annotations

from datetime import date
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import delete, select, text

from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.main import app
from app.models.course import Course
from app.models.grade import Grade
from app.models.organization import Class, College, Major
from app.models.person import Student, Teacher
from app.models.teaching import TeachingClass
from app.models.role import Role, RoleCode, UserRole
from app.models.user import User, UserType


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _admin_headers() -> dict[str, str]:
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.username == "admin")).scalar_one()
    return {"Authorization": f"Bearer {create_access_token(user.id, {'username': user.username})}"}


def _ids(prefix: str) -> dict:
    with SessionLocal() as db:
        college = db.execute(select(College).order_by(College.id)).scalars().first()
        major = db.execute(
            select(Major).where(Major.college_id == college.id).order_by(Major.id)
        ).scalars().first()
        klass = db.execute(
            select(Class).where(Class.major_id == major.id).order_by(Class.id)
        ).scalars().first()
        other_college = db.execute(
            select(College).where(College.id != college.id).order_by(College.id)
        ).scalars().first()
        # 同学院下至少还有一个其他专业：用于构造“专业与班级不一致”。
        other_major = db.execute(
            select(Major).where(Major.id != major.id).order_by(Major.id)
        ).scalars().first()
        return {
            "college": college.id, "major": major.id, "class": klass.id,
            "other_college": other_college.id if other_college else None,
            "other_major": other_major.id if other_major else None,
            "prefix": prefix,
        }


def test_student_college_major_consistency(client):
    ids = _ids("FIXB")
    h = _admin_headers()
    no = f"{ids['prefix']}_S_{uuid4().hex[:6]}"
    assert ids["other_major"] is not None, "测试库需至少包含两个专业"
    stu_id = None
    try:
        # 专业与班级不一致 -> 拒绝
        r = client.post("/api/v1/students", headers=h, json={
            "student_no": no, "real_name": "学院校验", "class_id": ids["class"],
            "college_id": ids["college"], "major_id": ids["other_major"],
            "enrollment_year": 2026,
        })
        assert r.status_code == 409, r.text
        # 学院与班级不一致 -> 拒绝（测试库存在第二个学院时才可构造）
        if ids["other_college"] is not None:
            r = client.post("/api/v1/students", headers=h, json={
                "student_no": no, "real_name": "学院校验", "class_id": ids["class"],
                "college_id": ids["other_college"], "major_id": ids["major"],
                "enrollment_year": 2026,
            })
            assert r.status_code == 409, r.text
        # 正确层级 -> 创建，学院/专业由班级派生
        r = client.post("/api/v1/students", headers=h, json={
            "student_no": no, "real_name": "学院校验", "class_id": ids["class"],
            "college_id": ids["college"], "major_id": ids["major"],
            "enrollment_year": 2026, "gender": "FEMALE",
        })
        assert r.status_code == 201, r.text
        stu_id = r.json()["id"]
        assert r.json()["college_id"] == ids["college"]
        # 编辑时专业与班级不一致 -> 拒绝
        r = client.put(f"/api/v1/students/{stu_id}", headers=h, json={
            "major_id": ids["other_major"],
        })
        assert r.status_code == 409, r.text
    finally:
        # 清理
        with SessionLocal() as db:
            student = db.get(Student, stu_id) if stu_id else None
            if student:
                user = db.get(User, student.user_id)
                db.execute(delete(Student).where(Student.id == stu_id))
                if user:
                    db.execute(delete(User).where(User.id == user.id))
                db.commit()


def test_batch_delete_students_partial(client):
    ids = _ids("FIXB")
    h = _admin_headers()
    no = f"{ids['prefix']}_B_{uuid4().hex[:6]}"
    r = client.post("/api/v1/students", headers=h, json={
        "student_no": no, "real_name": "批量删除", "class_id": ids["class"],
        "enrollment_year": 2026,
    })
    assert r.status_code == 201, r.text
    temp_id = r.json()["id"]
    # 学生 1 有选课，应失败；临时学生成功
    r = client.post("/api/v1/students/batch-delete", headers=h, json={"ids": [temp_id, 1]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert temp_id in body["deleted"]
    assert any(f["id"] == 1 for f in body["failed"])
    # 重复提交（已删除）仍返回明确失败
    r = client.post("/api/v1/students/batch-delete", headers=h, json={"ids": [temp_id]})
    assert r.status_code == 200 and r.json()["failed"]
    # 权限不足
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.username == "20260001")).scalar_one()
    sh = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    assert client.post("/api/v1/students/batch-delete", headers=sh, json={"ids": [2]}).status_code == 403


def test_batch_delete_courses_partial(client):
    ids = _ids("FIXB")
    h = _admin_headers()
    code = f"{ids['prefix']}C{uuid4().hex[:6]}"
    r = client.post("/api/v1/courses", headers=h, json={
        "code": code, "name": "批量课程", "college_id": ids["college"],
        "course_type": "ELECTIVE", "credits": 2, "total_hours": 32,
        "theory_hours": 32, "practice_hours": 0,
    })
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    # 课程 1 有教学任务，应失败；临时课程成功
    r = client.post("/api/v1/courses/batch-delete", headers=h, json={"ids": [cid, 1]})
    assert r.status_code == 200, r.text
    assert cid in r.json()["deleted"]
    assert any(f["id"] == 1 for f in r.json()["failed"])


def test_batch_delete_teachers_partial(client):
    ids = _ids("FIXB")
    h = _admin_headers()
    no = f"{ids['prefix']}T{uuid4().hex[:6]}"
    r = client.post("/api/v1/teachers", headers=h, json={
        "teacher_no": no, "real_name": "批量教师", "college_id": ids["college"],
        "title": "LECTURER", "gender": "MALE",
    })
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    with SessionLocal() as db:
        # 有教学班的教师不能被删，用于验证关联保护
        busy_teacher = db.execute(
            select(TeachingClass.teacher_id)
            .where(TeachingClass.teacher_id.isnot(None)).limit(1)
        ).scalar_one()
    r = client.post("/api/v1/teachers/batch-delete", headers=h,
                    json={"ids": [tid, busy_teacher]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert tid in body["deleted"]
    assert any(f["id"] == busy_teacher for f in body["failed"])
    with SessionLocal() as db:
        assert db.execute(
            select(User).where(User.username == no)
        ).scalar_one_or_none() is None


def test_batch_remove_students_blocks_graded(client):
    h = _admin_headers()
    with SessionLocal() as db:
        g = db.execute(select(Grade).limit(1)).scalar_one()
        cid, sid = g.teaching_class_id, g.student_id
    r = client.post(
        f"/api/v1/teaching-classes/{cid}/students/batch-delete",
        headers=h, json={"student_ids": [sid, 999999]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # 有成绩的学生、不存在的学生都失败，且不产生任何 DROPPED 记录
    assert body["deleted"] == []
    assert {f["id"] for f in body["failed"]} == {sid, 999999}


def test_batch_delete_requires_items(client):
    h = _admin_headers()
    r = client.post("/api/v1/students/batch-delete", headers=h, json={"ids": []})
    assert r.status_code == 422


def test_import_template_fields_and_student_import(client):
    h = _admin_headers()
    ids = _ids("FIXB")
    # 模板包含学生性别/学院等列
    r = client.get("/api/v1/imports/templates/students", headers=h)
    assert r.status_code == 200 and r.content[:2] == b"PK"
    wb = Workbook()
    ws = wb.active
    ws.append(["学号", "姓名", "性别", "学院", "专业", "行政班", "入学年份", "邮箱", "手机"])
    no = f"{ids['prefix']}I{uuid4().hex[:6]}"
    with SessionLocal() as db:
        college = db.get(College, ids["college"])
        major = db.get(Major, ids["major"])
        klass = db.get(Class, ids["class"])
    ws.append([no, "导入学生", "女", college.name, major.name, klass.name, 2026, "", ""])
    buf = BytesIO(); wb.save(buf)
    r = client.post(
        "/api/v1/imports/students", headers=h,
        files={"file": ("students.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["success"] == 1
    with SessionLocal() as db:
        stu = db.execute(select(Student).where(Student.student_no == no)).scalar_one_or_none()
        assert stu is not None and stu.gender == "FEMALE" and stu.college_id == ids["college"]
    # 清理
    with SessionLocal() as db:
        stu = db.execute(select(Student).where(Student.student_no == no)).scalar_one_or_none()
        if stu:
            user = db.get(User, stu.user_id)
            db.delete(stu)
            if user: db.delete(user)
            db.commit()


def test_import_rejects_invalid_gender(client):
    ids = _ids("FIXB")
    h = _admin_headers()
    wb = Workbook(); ws = wb.active
    ws.append(["学号", "姓名", "性别", "学院", "专业", "行政班"])
    with SessionLocal() as db:
        college = db.get(College, ids["college"]); major = db.get(Major, ids["major"]); klass = db.get(Class, ids["class"])
    ws.append([f"{ids['prefix']}G{uuid4().hex[:6]}", "非法性别", "未知X", college.name, major.name, klass.name])
    buf=BytesIO(); wb.save(buf)
    r = client.post("/api/v1/imports/students", headers=h, files={"file": ("x.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200
    assert r.json()["failed"] == 1
    assert r.json()["errors"][0]["field"] == "gender"


def test_teacher_admin_reuses_account_and_name(client):
    h = _admin_headers()
    with SessionLocal() as db:
        teacher_user = db.execute(
            select(User).where(User.username == "T001")
        ).scalar_one()
        uid = teacher_user.id
    ok = {"username": "T001", "real_name": teacher_user.real_name, "password": "T001"}
    assert client.post("/api/v1/auth/login", json=ok).status_code == 200
    assert client.post(f"/api/v1/admins/{uid}/grant", headers=h).status_code == 200
    try:
        # 兼任管理员后：同一账号、同一姓名、原密码均可继续登录
        r = client.post("/api/v1/auth/login", json=ok)
        assert r.status_code == 200, r.text
        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {r.json()['access_token']}"},
        ).json()
        assert "ACADEMIC_ADMIN" in me["roles"]
        with SessionLocal() as db:
            u = db.get(User, uid)
            # 身份类别不变，教师业务归属不受影响
            assert u.user_type == UserType.TEACHER
            assert u.real_name == teacher_user.real_name
        # 姓名不符仍拒绝
        bad = client.post("/api/v1/auth/login", json={**ok, "real_name": "错误姓名"})
        assert bad.status_code == 401
    finally:
        assert client.post(f"/api/v1/admins/{uid}/revoke", headers=h).status_code == 200


def test_login_requires_three_fields(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 422
    r = client.post("/api/v1/auth/login", json={"username": "admin", "real_name": "admin", "password": "admin123"})
    assert r.status_code == 200
    r = client.post("/api/v1/auth/login", json={"username": "admin", "real_name": "系统管理员", "password": "admin123"})
    assert r.status_code == 200
    r = client.post("/api/v1/auth/login", json={"username": "admin", "real_name": "错误", "password": "admin123"})
    assert r.status_code == 401
    assert r.json()["code"] == "AUTH_INVALID_CREDENTIALS"
