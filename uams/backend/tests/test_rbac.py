"""TASK-001：用户权限体系测试。

覆盖三类角色登录与权限隔离（CLAUDE.md §9），以及用户管理接口的越权防护。
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.role import Role, RoleCode, UserRole
from app.models.user import User, UserType

client = TestClient(app)
LOGIN = f"{settings.API_V1_PREFIX}/auth/login"
USERS = f"{settings.API_V1_PREFIX}/users"

STUDENT_UNAME = "__pytest_rbac_stu__"
TEACHER_UNAME = "__pytest_rbac_tch__"
PWD = "test123456"


def _create_user(username: str, user_type: str, role_code: str) -> int:
    with SessionLocal() as db:
        db.execute(delete(User).where(User.username == username))
        db.commit()
        user = User(
            username=username,
            password_hash=hash_password(PWD),
            real_name="权限测试用户",
            user_type=user_type,
        )
        db.add(user)
        db.flush()
        role = db.execute(select(Role).where(Role.code == role_code)).scalar_one()
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
        return user.id


def _cleanup(username: str) -> None:
    with SessionLocal() as db:
        u = db.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()
        if u:
            db.execute(delete(UserRole).where(UserRole.user_id == u.id))
            db.execute(delete(User).where(User.id == u.id))
            db.commit()


@pytest.fixture
def student_user():
    uid = _create_user(STUDENT_UNAME, UserType.STUDENT, RoleCode.STUDENT)
    yield uid
    _cleanup(STUDENT_UNAME)


@pytest.fixture
def teacher_user():
    uid = _create_user(TEACHER_UNAME, UserType.TEACHER, RoleCode.TEACHER)
    yield uid
    _cleanup(TEACHER_UNAME)


def _login(username: str, password: str = PWD):
    return client.post(LOGIN, json={"username": username, "password": password})


def _auth(username: str, password: str = PWD) -> dict:
    token = _login(username, password).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- 三类角色登录 ---


def test_three_roles_login_and_home_route(student_user, teacher_user):
    """admin / teacher / student 均能登录并跳转到各自首页。"""
    admin = _login("admin", "admin123")
    assert admin.status_code == 200, "seed 脚本是否已执行？"
    assert admin.json()["home_route"] == "/admin/dashboard"

    teacher = _login(TEACHER_UNAME)
    assert teacher.status_code == 200
    assert teacher.json()["home_route"] == "/teacher/dashboard"

    student = _login(STUDENT_UNAME)
    assert student.status_code == 200
    assert student.json()["home_route"] == "/student/dashboard"


# --- 权限规则（TASK-001）---


def test_admin_has_required_permissions():
    perms = set(_login("admin", "admin123").json()["permissions"])
    required = {
        "user:read", "user:write",          # 用户管理
        "major:write", "class:write",       # 专业/班级管理
        "course:write",                      # 课程管理
        "grade:approve",                     # 成绩审核
        "statistics:read",                   # 数据统计
    }
    assert required <= perms, f"教务应拥有: {required - perms}"


def test_teacher_permission_isolation(teacher_user):
    perms = set(_login(TEACHER_UNAME).json()["permissions"])
    allowed = {"teaching:read", "grade:write", "grade:submit", "student:read"}
    assert allowed <= perms, f"教师应拥有: {allowed - perms}"
    forbidden = {
        "user:read", "user:write", "grade:approve", "statistics:read",
        "student:write", "course:write",
    }
    assert not (perms & forbidden), f"教师不应拥有: {perms & forbidden}"


def test_student_permission_isolation(student_user):
    perms = set(_login(STUDENT_UNAME).json()["permissions"])
    allowed = {"course:read", "grade:read", "selection:write"}
    assert allowed <= perms, f"学生应拥有: {allowed - perms}"
    forbidden = {
        "user:read", "user:write", "grade:write", "grade:submit",
        "grade:approve", "student:write", "course:write", "teaching:write",
    }
    assert not (perms & forbidden), f"学生不应拥有: {perms & forbidden}"


# --- 用户管理接口越权防护 ---


def test_admin_can_list_users():
    r = client.get(USERS, headers=_auth("admin", "admin123"))
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_teacher_cannot_list_users(teacher_user):
    r = client.get(USERS, headers=_auth(TEACHER_UNAME))
    assert r.status_code == 403
    assert r.json()["code"] == "PERM_DENIED"


def test_student_cannot_list_users(student_user):
    r = client.get(USERS, headers=_auth(STUDENT_UNAME))
    assert r.status_code == 403
    assert r.json()["code"] == "PERM_DENIED"


def test_student_cannot_reset_password(student_user):
    r = client.put(
        f"{USERS}/{student_user}/password",
        json={"new_password": "hacked123"},
        headers=_auth(STUDENT_UNAME),
    )
    assert r.status_code == 403


# --- 用户管理功能 ---


def test_admin_reset_password_and_disable(student_user):
    # 重置密码
    r = client.put(
        f"{USERS}/{student_user}/password",
        json={"new_password": "newpass123"},
        headers=_auth("admin", "admin123"),
    )
    assert r.status_code == 204
    assert _login(STUDENT_UNAME, "newpass123").status_code == 200  # 新密码可登录

    # 停用账号
    r = client.put(
        f"{USERS}/{student_user}/status",
        json={"status": "DISABLED"},
        headers=_auth("admin", "admin123"),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "DISABLED"
    assert _login(STUDENT_UNAME, "newpass123").status_code == 403  # 停用后拒绝登录
